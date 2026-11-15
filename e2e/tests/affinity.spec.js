import { test, expect } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

// Affinity report on the option card. Mocked backend: the existing recording, with an affinity report added to
// option 0. A verified option cannot miss a hard wish (the eighth check removes it), so the reports here have every
// hard wish met, soft misses, and an item not measured. Option 1 keeps no key and must render as before.
const here = path.dirname(fileURLToPath(import.meta.url));
const FIX = path.join(here, '..', 'fixtures');

const item = (o) => ({ others: [], weight: 1, met: false, value: null, target: null, unit: null, by: null, ...o });
const REPORT = {
  score: 0.5, soft: { met: 1, total: 3 }, hard: { met: 1, total: 1 }, unmeasured: 1,
  items: [
    item({ kind: 'stack', a: 'wc_1', others: ['wc_0'], strength: 'should', met: false, value: 0.31, target: 0.5, unit: 'share', by: 'wc_0', source: 'tag wet: stack' }),
    item({ kind: 'apart', a: 'kitchen', others: ['meeting'], strength: 'must', met: true, value: 0, target: 0, unit: 'm2', source: 'between kitchen, meeting: apart' }),
    item({ kind: 'exterior', a: 'wc_0', strength: 'should', met: true, value: 3, target: 1, unit: 'm', source: 'wc_0: exterior' }),
    item({ kind: 'same_level', a: 'wc_2', others: ['wc_0'], strength: 'should', met: false, source: 'tag wet: same_level' }),
    item({ kind: 'facade', a: 'office_a', strength: 'should', met: null, source: 'office_a: facade sun' }),
  ],
};
// eight missed soft wishes: six are listed, the rest are counted
const MANY = {
  score: 0.2, soft: { met: 2, total: 10 }, hard: { met: 0, total: 0 }, unmeasured: 0,
  items: Array.from({ length: 8 }, (_, k) => item({ kind: 'same_level', a: `room_${k}`, others: ['wc_0'], strength: 'should', source: `room_${k}: same_level` })),
};

async function mockBackend(page, report) {
  const read = (f) => fs.readFileSync(path.join(FIX, f));
  const rec = JSON.parse(read('recording.json').toString());
  const options = structuredClone(rec.options);
  options[0].analysis = { affinity: report };
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

async function openCards(page, report) {
  await mockBackend(page, report);
  await page.goto('/');
  await page.getByTestId('fixture-select').selectOption('two_levels_stair');
  await page.getByTestId('generate-button').click();
  const cards = page.getByTestId('option-card');
  await expect(cards.first()).toBeVisible({ timeout: 60_000 });
  return cards;
}

test('option card shows the affinity report only when the option has one', async ({ page }) => {
  const cards = await openCards(page, REPORT);

  const card = cards.nth(0);
  await expect(card.getByTestId('affinity')).toHaveCount(1);
  await expect(card.locator('.bar__label', { hasText: 'affinity' })).toHaveCount(1);
  await expect(card.locator('.bar--separate .bar__value')).toHaveText('0.50');
  await expect(card.locator('.bar--separate')).not.toHaveAttribute('title', /not used for ranking/);
  const summary = card.getByTestId('affinity-summary');
  await expect(summary).toContainText('soft wishes met 1 / 3');
  await expect(summary).toContainText('hard wishes met 1 / 1');
  await expect(summary).toContainText('1 not measured yet');
  await expect(summary.locator('.card__unmet')).toHaveCount(0);

  // missed wishes only, one plain sentence each; the met hard wish and the unmeasured item are not listed
  const missed = card.getByTestId('affinity-missed');
  await expect(missed).toHaveCount(2);
  await expect(missed.nth(0)).toHaveText('wc_1 should stack over or under wc_0 — best 0.31 overlap, needs 0.50 overlap (wc_0)');
  await expect(missed.nth(1)).toHaveText('wc_2 should be on the same level as wc_0');
  await expect(card.getByTestId('affinity-more')).toHaveCount(0);

  // an option without the key looks as before
  await expect(cards.nth(1).getByTestId('affinity')).toHaveCount(0);
  await expect(cards.nth(1).locator('.bar')).toHaveCount(7);
});

test('more than six missed wishes list six and count the rest', async ({ page }) => {
  const cards = await openCards(page, MANY);
  const card = cards.nth(0);
  await expect(card.getByTestId('affinity-summary')).toContainText('soft wishes met 2 / 10');
  await expect(card.getByTestId('affinity-missed')).toHaveCount(6);
  await expect(card.getByTestId('affinity-more')).toHaveText('+ 2 more');
});
