import { test, expect } from '@playwright/test';

test('hero case: EXPOSED with timeline and badges', async ({ page }) => {
  await page.goto('/');
  await page.getByPlaceholder('Search company, LEI or IMO').fill('nord harbor');
  await page.getByRole('option', { name: /Nord Harbor Logistics/ }).click();
  await page.getByLabel('As of').fill('2024-01-01');
  await page.getByRole('button', { name: 'Run investigation' }).click();
  await expect(page.getByTestId('validated-badge')).toHaveText(/EXPOSED/);
  await expect(page.getByTestId('proposal-badge')).toBeVisible();
  await expect(page.getByTestId('timeline-step').filter({ hasText: 'case_history' }).first()).toBeVisible();
  await expect(page.getByText('not legal advice', { exact: false })).toBeVisible();
});
