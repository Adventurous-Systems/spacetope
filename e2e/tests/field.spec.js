import { test, expect } from '@playwright/test';

// M28: the field canvas. A site, a path and a schedule; the plan and its scores follow every drag.
test.describe('field canvas', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.getByTestId('mode-field').click();
    await page.getByTestId('field-fixture').selectOption('club');
    await expect(page.getByTestId('field-cell').first()).toBeVisible();
  });

  test('a field brief draws cells for every tessellation', async ({ page }) => {
    for (const kind of ['voronoi', 'power', 'slice', 'grid', 'hex']) {
      await page.getByTestId(`kind-${kind}`).click();
      await expect(page.getByTestId('field-live-card')).toContainText(kind);
      expect(await page.getByTestId('field-cell').count()).toBeGreaterThan(8);
      await expect(page.getByTestId('field-error')).toHaveCount(0);
    }
    await page.getByTestId('level-1').click();
    expect(await page.getByTestId('field-cell').count()).toBeGreaterThan(8);
  });

  test('dragging a room pins it and the plan answers within a second', async ({ page }) => {
    const seed = page.getByTestId('room-seed').first();
    const before = await page.getByTestId('field-cell').evaluateAll((els) => els.map((e) => e.getAttribute('points')).join('|'));
    const box = await seed.boundingBox();
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + 60, box.y + 40, { steps: 6 });
    await page.mouse.up();
    await expect(page.getByText(/release 1 pinned/)).toBeVisible();
    await expect.poll(async () => page.getByTestId('field-cell').evaluateAll((els) => els.map((e) => e.getAttribute('points')).join('|'))).not.toBe(before);
    await expect.poll(async () => parseInt((await page.getByTestId('field-ms').textContent()) || '9999', 10)).toBeLessThan(1000);
  });

  test('moving the path moves the mass', async ({ page }) => {
    const path = () => page.getByTestId('field-cell').evaluateAll((els) => els.map((e) => e.getAttribute('points')).join('|'));
    const before = await path();
    const handle = page.getByTestId('path-handle').nth(1);
    const box = await handle.boundingBox();
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + 70, box.y - 30, { steps: 6 });
    await page.mouse.up();
    await expect.poll(path).not.toBe(before);
    await expect(page.getByTestId('field-error')).toHaveCount(0);
  });

  test('options: one per aspect, built in topologic, shown in plan and in 3D', async ({ page }) => {
    await page.getByTestId('field-generate').click();
    await expect(page.getByTestId('field-option').first()).toBeVisible({ timeout: 110_000 });
    await expect(page.getByTestId('field-info')).toContainText('candidates');
    await page.getByTestId('field-option').first().click();
    await expect(page.getByTestId('field-live')).toBeVisible();
    await page.getByTestId('field-3d').click();
    await expect(page.getByTestId('field-model')).toBeVisible();
  });
});
