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

  await page.getByLabel('As of').fill('2023-01-01');
  await expect(page.getByTestId('validated-badge')).toHaveCount(0);
  await expect(page.getByText('Awaiting investigation')).toBeVisible();
});

test('entity search ignores a response for an older query', async ({ page }) => {
  let markOldRequestStarted;
  let releaseOldRequest;
  const oldRequestStarted = new Promise((resolve) => { markOldRequestStarted = resolve; });
  const oldRequestRelease = new Promise((resolve) => { releaseOldRequest = resolve; });

  await page.route('**/api/entities/search**', async (route) => {
    const q = new URL(route.request().url()).searchParams.get('q');
    if (q === 'nord ha') {
      markOldRequestStarted();
      await oldRequestRelease;
      await route.fulfill({
        json: { hits: [{ id: 'old', name: 'Nord Harbor Older Result', kind: 'Company', country: 'CY', designated: false }] },
      });
      return;
    }
    await route.fulfill({
      json: { hits: [{ id: 'new', name: 'Nord Harbor Current Result', kind: 'Company', country: 'CY', designated: false }] },
    });
  });

  await page.goto('/');
  const input = page.getByPlaceholder('Search company, LEI or IMO');
  await input.fill('nord ha');
  await oldRequestStarted;
  await input.fill('nord harbor');
  await expect(page.getByRole('option', { name: /Current Result/ })).toBeVisible();
  releaseOldRequest();
  await expect(page.getByRole('option', { name: /Current Result/ })).toBeVisible();
  await expect(page.getByRole('option', { name: /Older Result/ })).toHaveCount(0);
});
