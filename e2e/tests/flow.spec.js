import { test, expect } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

// M5 gate, browser half. Default: mocked backend from recorded fixtures (e2e/fixtures, made by
// `npm run test:real` with RECORD=1). REAL_BACKEND=1 runs against uvicorn on :8000 via the Vite proxy.
const here = path.dirname(fileURLToPath(import.meta.url));
const FIX = path.join(here, '..', 'fixtures');
const REAL = !!process.env.REAL_BACKEND;
const RECORD = !!process.env.RECORD;

async function mockBackend(page) {
  const read = (f) => fs.readFileSync(path.join(FIX, f));
  const json = (f) => JSON.parse(read(f).toString());
  const rec = json('recording.json');
  // the mocked run must not need a live backend (found 2026-09-20: the health check fell through to the proxy)
  await page.route('**/api/health', (r) => r.fulfill({ json: { ok: true, generators: ['treemap', 'beam', 'cpsat', 'dual'],
    capabilities: { treemap: { multi_level: false }, beam: { multi_level: true }, cpsat: { multi_level: true }, dual: { multi_level: false } } } }));
  await page.route('**/api/fixtures', (r) => r.fulfill({ json: rec.fixtures }));
  await page.route('**/api/fixtures/*', (r) => r.fulfill({ json: rec.brief }));
  await page.route('**/api/brief', (r) => r.fulfill({ json: { brief_id: 'mock', brief: rec.brief } }));
  await page.route('**/api/generate', (r) => r.fulfill({ json: { ...rec.job, status: 'running' } }));
  await page.route('**/api/jobs/*', (r) => r.fulfill({ json: rec.job }));
  await page.route(/\/api\/options\/[^/]+$/, (r) => r.fulfill({ json: rec.options }));
  await page.route(/\/api\/options\/[^/]+\/\d+$/, (r) => {
    const i = parseInt(r.request().url().split('/').pop(), 10);
    return r.fulfill({ json: rec.details[i] ?? rec.details[0] });
  });
  await page.route('**/static/**', (r) => r.fulfill({ body: read('option.glb'), contentType: 'model/gltf-binary' }));
  await page.route('**/api/select', (r) => r.fulfill({ json: rec.select }));
}

test('brief -> generate -> view -> highlight -> select', async ({ page, request }) => {
  const consoleErrors = [];
  page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text()); });
  page.on('pageerror', (e) => consoleErrors.push(e.message));
  if (!REAL) await mockBackend(page);

  await page.goto('/');
  const select = page.getByTestId('fixture-select');
  await expect(select.locator('option', { hasText: 'two_levels_stair' })).toHaveCount(1);
  await select.selectOption('two_levels_stair');
  await expect(page.getByTestId('space-row')).toHaveCount(8);   // compact brief: rooms only

  const t0 = Date.now();
  await page.getByTestId('generate-button').click();
  await expect(page.getByTestId('option-card').first()).toBeVisible({ timeout: 60_000 });
  const cards = await page.getByTestId('option-card').count();
  expect(cards).toBeGreaterThanOrEqual(3);

  // the 3D background loads the GLB with one mesh per cell
  await expect(page.getByTestId('viewer-3d')).toBeVisible();
  await expect.poll(() => page.evaluate(() => window.__spacetope?.cells ?? 0), { timeout: 30_000 }).toBe(12);
  const firstVisibleMs = Date.now() - t0;
  if (REAL) expect(firstVisibleMs).toBeLessThan(15_000);

  // assembly graph: 14 space nodes, one wall node per shared face
  await expect(page.getByTestId('space-node')).toHaveCount(12);
  const walls = await page.getByTestId('wall-node').count();
  expect(walls).toBeGreaterThan(10);

  // the whole graph is fitted inside the canvas (regression: nodes rendered under the brief panel)
  await expect.poll(() => page.evaluate(() => {
    const c = document.querySelector('.app__canvas').getBoundingClientRect();
    return [...document.querySelectorAll('.react-flow__node')].filter((n) => {
      const r = n.getBoundingClientRect(); const x = r.x + r.width / 2, y = r.y + r.height / 2;
      return x < c.left || x > c.right || y < c.top || y > c.bottom;
    }).length;
  }), { timeout: 10_000 }).toBe(0);

  // clicking a wall node highlights exactly the two cells that share the face
  await page.getByTestId('wall-node').first().click({ force: true });
  await expect(page.locator('.wall-node--hl')).toHaveCount(1);
  await expect(page.locator('.space-node--hl')).toHaveCount(2);
  await page.screenshot({ path: 'test-results/canvas-after-highlight.png' });

  // switch option, then select and export
  await page.getByTestId('option-card').nth(1).click();
  await expect(page.locator('.card--current')).toHaveCount(1);
  const selectCall = page.waitForRequest((r) => r.url().includes('/api/select') && r.method() === 'POST');
  await page.getByTestId('select-button').click();
  const req = await selectCall;
  expect(JSON.parse(req.postData()).index).toBe(1);
  await expect(page.getByTestId('exported')).toContainText('.brep');

  expect(consoleErrors.filter((e) => !/Download the React DevTools|THREE\.WebGLRenderer/.test(e))).toEqual([]);

  if (REAL && RECORD) {
    // capture the backend responses the mocked run replays
    const fixtures = await (await request.get('http://localhost:8000/api/fixtures')).json();
    const brief = await (await request.get('http://localhost:8000/api/fixtures/two_levels_stair')).json();
    const posted = await (await request.post('http://localhost:8000/api/brief', { data: brief })).json();
    const job = await (await request.post('http://localhost:8000/api/generate', { data: { brief_id: posted.brief_id, generator: 'beam', seed: 0, wait: true } })).json();
    const options = await (await request.get(`http://localhost:8000/api/options/${job.job_id}`)).json();
    const details = [];
    for (let i = 0; i < Math.min(options.length, 3); i++) details.push(await (await request.get(`http://localhost:8000/api/options/${job.job_id}/${i}`)).json());
    const glb = await (await request.get(`http://localhost:8000${options[0].glb_url}`)).body();
    const sel = await (await request.post('http://localhost:8000/api/select', { data: { job_id: job.job_id, index: 1, name: 'e2e_record' } })).json();
    fs.mkdirSync(FIX, { recursive: true });
    fs.writeFileSync(path.join(FIX, 'option.glb'), glb);
    fs.writeFileSync(path.join(FIX, 'recording.json'), JSON.stringify({ fixtures, brief, job, options, details, select: sel }));
  }
});
