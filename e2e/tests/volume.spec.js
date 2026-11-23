import { test, expect } from '@playwright/test';

// M29: bodies on springs in a void. Storey cells are cut from them; a body can be inflated and moved between storeys.
test.describe('volume canvas', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.getByTestId('mode-volume').click();
    await page.getByTestId('volume-fixture').selectOption('stepped');
    await expect(page.getByTestId('storey-row').first()).toBeVisible();
  });

  test('the schedule floats into the void and every storey is asked about what it has', async ({ page }) => {
    await expect.poll(() => page.evaluate(() => window.__volume?.bodies)).toBe(22);
    expect(await page.evaluate(() => window.__volume.cells)).toBe(22);
    const rows = await page.getByTestId('storey-row').allTextContents();
    expect(rows).toHaveLength(4);
    for (const row of rows) {
      const [, asked, has] = row.match(/asked ([\d.]+) m² of ([\d.]+)/).map(Number);
      expect(Math.abs(asked - has) / has).toBeLessThan(0.25);
    }
    await expect(page.getByTestId('volume-error')).toHaveCount(0);
  });

  test('inflating a body gives it more ground and the rest answer', async ({ page }) => {
    await page.getByTestId('body-name').filter({ hasText: 'gym' }).click();
    const area = async () => parseFloat((await page.getByTestId('body-area').textContent()).split(' ')[0]);
    const before = await area();
    await page.getByTestId('body-size').focus();
    for (let i = 0; i < 16; i += 1) await page.keyboard.press('ArrowRight');
    await expect.poll(area, { timeout: 15_000 }).toBeGreaterThan(before * 1.3);
    await expect.poll(async () => parseInt((await page.getByTestId('volume-ms').textContent()) || '9999', 10)).toBeLessThan(1500);
  });

  test('a body sent up a storey stays there, pinned', async ({ page }) => {
    await page.getByTestId('body-name').filter({ hasText: 'salon' }).click();
    const level = async () => (await page.getByTestId('body-card').textContent()).match(/level (\d)/)[1];
    const before = await level();
    await page.getByTestId(before === '3' ? 'body-down' : 'body-up').click();
    await expect.poll(level).not.toBe(before);
    await expect(page.getByText(/release 1 pinned/)).toBeVisible();
  });

  test('the sketch builds free cells in topologic', async ({ page }) => {
    await page.getByTestId('sketch-button').click();
    await expect(page.getByTestId('sketch-info')).toContainText('sloping', { timeout: 60_000 });
    await expect(page.getByTestId('sketch-close')).toBeVisible();
  });
});
