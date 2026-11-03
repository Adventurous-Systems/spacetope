import { test, expect } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

// M7.6 gate, browser half: shafts through floors, generated corridors, doors, validation messages.
// Default: mocked backend replaying e2e/fixtures/circulation (made by REAL_BACKEND=1 RECORD=1).
const here = path.dirname(fileURLToPath(import.meta.url));
const FIX = path.join(here, '..', 'fixtures', 'circulation');
const REAL = !!process.env.REAL_BACKEND;
const RECORD = !!process.env.RECORD;
const API = 'http://localhost:8100';
const EXPECTED_SPACES = 15;   // 10 rooms + 3 corridors + stair + lift
const EXPECTED_DOORS = 17;    // stair 3 + lift 3 + one per room 10 + office_c–meeting 1

function stairMissesTopLevel(body) {
  const stair = body?.circulation?.stairs?.[0];
  return !!(stair?.serves && stair.serves[1] < (body.levels || 1) - 1);
}

async function mockBackend(page) {
  const rec = JSON.parse(fs.readFileSync(path.join(FIX, 'recording.json')).toString());
  const glb = fs.readFileSync(path.join(FIX, 'option.glb'));
  await page.route('**/api/health', (r) => r.fulfill({ json: rec.health }));
  await page.route('**/api/fixtures', (r) => r.fulfill({ json: rec.fixtures }));
  await page.route('**/api/fixtures/*', (r) => r.fulfill({ json: rec.brief }));
  await page.route('**/api/brief', (r) => (stairMissesTopLevel(JSON.parse(r.request().postData() || '{}'))
    ? r.fulfill({ status: 422, json: rec.badBrief })
    : r.fulfill({ json: rec.goodBrief })));
  await page.route('**/api/generate', (r) => r.fulfill({ json: { ...rec.job, status: 'running' } }));
  await page.route('**/api/jobs/*', (r) => r.fulfill({ json: rec.job }));
  await page.route(/\/api\/options\/[^/]+$/, (r) => r.fulfill({ json: rec.options }));
  await page.route(/\/api\/options\/[^/]+\/\d+$/, (r) => {
    const i = parseInt(r.request().url().split('/').pop(), 10);
    return r.fulfill({ json: rec.details[i] ?? rec.details[0] });
  });
  await page.route('**/static/**', (r) => r.fulfill({ body: glb, contentType: 'model/gltf-binary' }));
  await page.route('**/api/select', (r) => r.fulfill({ json: rec.select }));
}

test('circulation brief -> validation -> shafts and doors -> export', async ({ page, request }) => {
  const consoleErrors = [];
  page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text()); });
  page.on('pageerror', (e) => consoleErrors.push(e.message));
  if (!REAL) await mockBackend(page);

  await page.goto('/');
  const fixtureSelect = page.getByTestId('fixture-select');
  await expect(fixtureSelect.locator('option', { hasText: 'three_levels_core' })).toHaveCount(1);
  await fixtureSelect.selectOption('three_levels_core');
  await expect(page.getByTestId('space-row')).toHaveCount(10);
  await expect(page.getByTestId('circulation')).toBeVisible();
  await expect(page.getByTestId('stairs-row')).toHaveCount(1);
  await expect(page.getByTestId('generator-select').locator('option[value="treemap"]')).toBeDisabled();

  // a stair that stops at level 1 is rejected with a plain message
  await page.getByTestId('stairs-to-0').selectOption('1');
  await page.getByTestId('generate-button').click();
  await expect(page.getByTestId('brief-problem').filter({ hasText: 'level 2 is not served by any stair' })).toHaveCount(1);
  await expect(page.getByTestId('option-card')).toHaveCount(0);

  // restore it and generate
  await page.getByTestId('stairs-to-0').selectOption('2');
  await page.getByTestId('generate-button').click();
  await expect(page.getByTestId('option-card').first()).toBeVisible({ timeout: 90_000 });
  expect(await page.getByTestId('option-card').count()).toBeGreaterThanOrEqual(3);
  await expect(page.getByTestId('brief-problems')).toHaveCount(0);
  await expect(page.getByTestId('expanded-count')).toHaveText(`${EXPECTED_SPACES} spaces after expansion`);

  // 3D: one mesh per cell, one per door
  await expect.poll(() => page.evaluate(() => window.__spacetope?.cells ?? 0), { timeout: 30_000 }).toBe(EXPECTED_SPACES);
  await expect.poll(() => page.evaluate(() => window.__spacetope?.doors ?? 0)).toBe(EXPECTED_DOORS);

  // graph: every space once, the two shafts marked, doors drawn as door nodes and door edges
  await expect(page.getByTestId('space-node')).toHaveCount(EXPECTED_SPACES);
  await expect(page.locator('[data-testid="space-node"][data-shaft="true"]')).toHaveCount(2);
  const doorWalls = page.locator('[data-testid="wall-node"][data-door="true"]');
  await expect(doorWalls).toHaveCount(EXPECTED_DOORS);
  for (const k of [0, 1, 2]) {
    await expect(page.locator(`[data-testid="wall-node"][data-door="true"][title="door: corridor_${k} – stair"]`)).toHaveCount(1);
  }
  await expect(page.locator('.react-flow__edge.door-edge')).toHaveCount(2 * EXPECTED_DOORS);

  // clicking the stair's door on level 1 highlights the stair and that corridor
  await page.locator('[data-testid="wall-node"][title="door: corridor_1 – stair"]').click({ force: true });
  await expect(page.locator('.wall-node--hl')).toHaveCount(1);
  await expect(page.locator('.space-node--hl')).toHaveCount(2);
  await page.screenshot({ path: 'test-results/circulation-after-highlight.png' });

  // export includes the doors sidecar
  const selectCall = page.waitForRequest((r) => r.url().includes('/api/select') && r.method() === 'POST');
  await page.getByTestId('select-button').click();
  await selectCall;
  await expect(page.getByTestId('exported')).toContainText('.doors.json');

  // the 422 is the deliberate rejection of the stair that stops at level 1; anything else is a real error
  expect(consoleErrors.filter((e) => !/Download the React DevTools|THREE\.WebGLRenderer|GL Driver|status of 422/.test(e))).toEqual([]);

  if (REAL && RECORD) {
    const get = async (p) => (await request.get(`${API}${p}`)).json();
    const post = async (p, data) => {
      const res = await request.post(`${API}${p}`, { data });
      return { status: res.status(), body: await res.json() };
    };
    const health = await get('/api/health');
    const fixtures = await get('/api/fixtures');
    const brief = await get('/api/fixtures/three_levels_core');
    const bad = structuredClone(brief);
    bad.circulation.stairs[0].serves = [0, 1];
    const badBrief = (await post('/api/brief', bad)).body;
    const goodBrief = (await post('/api/brief', brief)).body;
    const job = (await post('/api/generate', { brief_id: goodBrief.brief_id, generator: 'beam', seed: 0, wait: true })).body;
    const options = await get(`/api/options/${job.job_id}`);
    const details = [];
    for (let i = 0; i < Math.min(options.length, 3); i++) details.push(await get(`/api/options/${job.job_id}/${i}`));
    const glb = await (await request.get(`${API}${options[0].glb_url}`)).body();
    const select = (await post('/api/select', { job_id: job.job_id, index: 0, name: 'e2e_circulation' })).body;
    fs.mkdirSync(FIX, { recursive: true });
    fs.writeFileSync(path.join(FIX, 'option.glb'), glb);
    fs.writeFileSync(path.join(FIX, 'recording.json'), JSON.stringify({ health, fixtures, brief, badBrief, goodBrief, job, options, details, select }));
  }
});
