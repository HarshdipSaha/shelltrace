import { test, expect } from '@playwright/test';

test('hero case: EXPOSED with timeline and badges', async ({ page }) => {
  let markCaseRequestStarted;
  let releaseCaseRequest;
  const caseRequestStarted = new Promise((resolve) => { markCaseRequestStarted = resolve; });
  const caseRequestRelease = new Promise((resolve) => { releaseCaseRequest = resolve; });

  await page.route('**/api/cases', async (route) => {
    markCaseRequestStarted();
    await caseRequestRelease;
    await route.continue();
  });

  await page.goto('/');
  await page.getByPlaceholder('Search company, LEI or IMO').fill('nord harbor');
  await page.getByRole('option', { name: /Nord Harbor Logistics/ }).click();
  await page.getByLabel('As of').fill('2024-01-01');
  await page.getByRole('button', { name: 'Run investigation' }).click();
  await caseRequestStarted;
  await expect(page.getByLabel('As of')).toBeDisabled();
  await expect(page.getByPlaceholder('Search company, LEI or IMO')).toBeDisabled();
  releaseCaseRequest();
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

test('late health response does not change the mode of an active case', async ({ page }) => {
  let markHealthRequestStarted;
  let releaseHealthRequest;
  let markCaseRequestStarted;
  let releaseCaseRequest;
  const healthRequestStarted = new Promise((resolve) => { markHealthRequestStarted = resolve; });
  const healthRequestRelease = new Promise((resolve) => { releaseHealthRequest = resolve; });
  const caseRequestStarted = new Promise((resolve) => { markCaseRequestStarted = resolve; });
  const caseRequestRelease = new Promise((resolve) => { releaseCaseRequest = resolve; });

  await page.route('**/api/health', async (route) => {
    markHealthRequestStarted();
    await healthRequestRelease;
    await route.fulfill({
      json: { status: 'ok', graph: 'st_facts_synthetic', llm: 'claude-opus-5', node_count: 1 },
    });
  });
  await page.route('**/api/cases', async (route) => {
    markCaseRequestStarted();
    await caseRequestRelease;
    await route.continue();
  });

  await page.goto('/');
  await healthRequestStarted;
  await page.getByPlaceholder('Search company, LEI or IMO').fill('nord harbor');
  await page.getByRole('option', { name: /Nord Harbor Logistics/ }).click();
  await expect(page.getByRole('radio', { name: /Agent/ })).toBeDisabled();
  await page.getByRole('button', { name: 'Run investigation' }).click();
  await caseRequestStarted;

  releaseHealthRequest();
  await expect(page.getByRole('radio', { name: /Playbook/ })).toBeChecked();
  releaseCaseRequest();
  await expect(page.getByTestId('validated-badge')).toHaveText(/EXPOSED/);
});
