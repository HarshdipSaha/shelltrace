import { test, expect } from '@playwright/test';

// Deliberately opt-in: this produces the compact, reproducible screenshots used in the blog.
// It talks to the configured local real-data API; CI keeps using deterministic fixtures.
test.skip(!process.env.ST_CAPTURE_REAL, 'Set ST_CAPTURE_REAL=1 against the local real-data API to refresh blog captures.');

test('captures focused panels from an ABRAU real-data investigation', async ({ page }) => {
  test.setTimeout(90_000);
  await page.setViewportSize({ width: 1440, height: 1050 });
  await page.goto('/?ws=demo');
  await page.getByRole('combobox', { name: 'Appearance' }).selectOption('dark');
  await page.getByPlaceholder('Search company, LEI or IMO').fill('ABRAU');
  await page.getByRole('option', { name: /ABRAU/ }).click();
  await page.getByRole('button', { name: 'Run investigation' }).click();
  await expect(page.getByTestId('validated-badge')).toBeVisible({ timeout: 60_000 });

  await page.locator('.case-header').screenshot({ path: '../docs/images/blog/real-verdict-dark.png' });
  await page.locator('.evidence-graph-panel').screenshot({ path: '../docs/images/blog/real-evidence-graph-dark.png' });
  await page.locator('.rule-pack-card').first().screenshot({ path: '../docs/images/blog/real-rulepack-ofac-dark.png' });
});
