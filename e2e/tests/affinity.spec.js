import { test, expect } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

// Affinity report on the option card. Mocked backend: the existing recording, with an affinity report added to
// option 0 (a hard miss, soft misses, one item not measured). Option 1 keeps no key and must render as before.
const here = path.dirname(fileURLToPath(import.meta.url));
const FIX = path.join(here, '..', 'fixtures');

const item = (o) => ({ others: [], weight: 1, met: false, value: null, target: null, unit: null, by: null, ...o });
const REPORT = {
  score: 0.5, soft: { met: 1, total: 2 }, hard: { met: 0, total: 1 }, unmeasured: 1,
  items: [
    item({ kind: 'stack', a: 'wc_1', others: ['wc_0'], strength: 'should', met: false, value: 0.31, target: 0.5, unit: 'share', by: 'wc_0', source: 'tag wet: stack' }),
    item({ kind: 'apart', a: 'kitchen', others: ['meeting'], strength: 'must', met: false, value: 12.4, target: 0, unit: 'm2', source: 'between kitchen, meeting: apart' }),
    item({ kind: 'exterior', a: 'wc_0', strength: 'should', met: true, value: 3, target: 1, unit: 'm', source: 'wc_0: exterior' }),
    item({ kind: 'facade', a: 'office_a', strength: 'should', met: null, source: 'office_a: facade sun' }),
  ],
};

async function mockBackend(page) {
  const read = (f) => fs.readFileSync(path.join(FIX, f));
  const rec = JSON.parse(read('recording.json').toString());
  const options = structuredClone(rec.options);
  options[0].analysis = { affinity: REPORT };
  await page.route('**/api/health', (r) => r.fulfill({ json: { ok: true, generators: ['beam'], capabilities: { beam: { multi_level: true } } } }));
  await page.route('**/api/fixtures', (r) => r.fulfill({ json: rec.fixtures }));
  await page.route('**/api/fixtures/*', (r) => r.fulfill({ json: rec.brief }));
  await page.route('**/api/brief', (r) => r.fulfill({ json: { brief_id: 'mock', brief: rec.brief } }));
  await page.route('**/api/generate', (r) => r.fulfill({ json: { ...rec.job, status: 'running' } }));
  await page.route('**/api/jobs/*', (r) => r.fulfill({ json: rec.job }));
  await page.route(/\/api\/options\/[^/]+$/, (r) => r.fulfill({ json: options }));
  await page.route(/\/api\/options\/[^/]+\/\d+$/, (r) => r.fulfill({ json: rec.details[0] }));
  await page.route('**/static/**', (r) => r.fulfill({ body: read('option.glb'), contentType: 'model/gltf-binary' }));
}

test('option card shows the affinity report only when the option has one', async ({ page }) => {
  await mockBackend(page);
  await page.goto('/');
  await page.getByTestId('fixture-select').selectOption('two_levels_stair');
  await page.getByTestId('generate-button').click();
  const cards = page.getByTestId('option-card');
  await expect(cards.first()).toBeVisible({ timeout: 60_000 });

  const card = cards.nth(0);
  await expect(card.getByTestId('affinity')).toHaveCount(1);
  await expect(card.locator('.bar__label', { hasText: 'affinity' })).toHaveCount(1);
  await expect(card.locator('.bar--reported .bar__value')).toHaveText('0.50');
  const summary = card.getByTestId('affinity-summary');
  await expect(summary).toContainText('soft wishes met 1 / 2');
  await expect(summary).toContainText('hard wishes met 0 / 1');
  await expect(summary).toContainText('1 not measured yet');
  await expect(summary.locator('.card__unmet')).toHaveCount(1);

  // missed wishes only, hard first, one plain sentence each
  const missed = card.getByTestId('affinity-missed');
  await expect(missed).toHaveCount(2);
  await expect(missed.nth(0)).toHaveText('kitchen must stay apart from meeting — found 12.4 m² of wall');
  await expect(missed.nth(0)).toHaveClass(/card__unmet/);
  await expect(missed.nth(1)).toHaveText('wc_1 should stack over or under wc_0 — best 0.31 overlap, needs 0.50 overlap (wc_0)');
  await expect(card.getByTestId('affinity-more')).toHaveCount(0);

  // an option without the key looks as before
  await expect(cards.nth(1).getByTestId('affinity')).toHaveCount(0);
  await expect(cards.nth(1).locator('.bar')).toHaveCount(7);
});
