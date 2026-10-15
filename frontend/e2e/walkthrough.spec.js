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
  await expect(page.getByTestId('validated-badge')).toHaveText(/EXPOSED/, { timeout: 15_000 });
});

test('failed health check offers an accurate retry before agent mode is enabled', async ({ page }) => {
  let shouldFail = true;
  await page.route('**/api/health', async (route) => {
    if (shouldFail) {
      await route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'health check unavailable' }),
      });
      return;
    }
    await route.fulfill({
      json: { status: 'ok', graph: 'st_facts_synthetic', llm: 'claude-opus-5', node_count: 1 },
    });
  });

  await page.goto('/');
  await expect(page.getByText('API 503: health check unavailable')).toBeVisible();
  await expect(page.getByText(/could not confirm model availability/i)).toBeVisible();
  await expect(page.getByText(/confirming model availability/i)).toHaveCount(0);
  await expect(page.getByRole('radio', { name: /Agent/ })).toBeDisabled();
  shouldFail = false;
  await page.getByRole('button', { name: 'Retry status check' }).click();
  await expect(page.getByRole('radio', { name: /Agent/ })).toBeEnabled();
  await expect(page.getByText('API 503: health check unavailable')).toHaveCount(0);
});

test('switching to the UK pack updates the displayed verdict', async ({ page }) => {
  test.setTimeout(60_000);
  await page.goto('/');
  await page.getByPlaceholder('Search company, LEI or IMO').fill('birch');
  await page.getByRole('option', { name: /Birch Marine Services/ }).click();
  await page.getByRole('button', { name: 'Run investigation' }).click();
  await expect(page.getByTestId('pack-verdict-OFAC')).toContainText('BLOCKED', { timeout: 15_000 });
  await expect(page.getByTestId('pack-verdict-UK')).toContainText('NOT_BLOCKED', { timeout: 15_000 });
  await expect(page.locator('svg.interval-meter')).toHaveCount(3);
  await expect(page.getByTestId('interval-threshold-OFAC')).toHaveClass(/interval-threshold--inclusive/);
  await expect(page.getByTestId('interval-threshold-UK')).toHaveClass(/interval-threshold--strict/);

  await page.getByRole('checkbox', { name: 'OFAC' }).uncheck();
  await page.getByRole('checkbox', { name: 'EU' }).uncheck();
  await page.getByRole('button', { name: 'Run investigation' }).click();

  await expect(page.getByTestId('validated-badge')).toHaveText(/CLEAR_WITHIN_BOUNDS/, { timeout: 15_000 });
  await expect(page.getByTestId('pack-verdict-UK')).toContainText('NOT_BLOCKED');
  await expect(page.getByTestId('pack-verdict-OFAC')).toHaveCount(0);
});

test('date slider reruns the case across a listing boundary', async ({ page }) => {
  test.setTimeout(60_000);
  await page.goto('/');
  await page.getByPlaceholder('Search company, LEI or IMO').fill('larch');
  await page.getByRole('option', { name: /Larch Metals/ }).click();
  await page.getByLabel('As of').fill('2022-01-01');
  await page.getByRole('button', { name: 'Run investigation' }).click();
  await expect(page.getByTestId('validated-badge')).toHaveText(/EXPOSED/, { timeout: 15_000 });

  const slider = page.getByRole('slider', { name: 'Investigation date' });
  await expect(slider).toHaveAttribute('aria-valuetext', '2022-01-01');
  await slider.focus();
  await slider.press('ArrowRight');
  await expect(slider).toHaveAttribute('aria-valuetext', '2023-01-01');
  await expect(page.getByTestId('validated-badge')).toHaveText(/CLEAR_WITHIN_BOUNDS/, { timeout: 15_000 });

  await expect(slider).toBeEnabled();
  await slider.focus();
  await slider.press('ArrowLeft');
  await expect(slider).toHaveAttribute('aria-valuetext', '2022-01-01');
  await expect(page.getByTestId('validated-badge')).toHaveText(/EXPOSED/, { timeout: 15_000 });
});

test('selecting a graph proof edge opens its evidence in the locker', async ({ page }) => {
  test.setTimeout(60_000);
  await page.goto('/');
  await page.getByPlaceholder('Search company, LEI or IMO').fill('nord harbor');
  await page.getByRole('option', { name: /Nord Harbor Logistics/ }).click();
  await page.getByRole('button', { name: 'Run investigation' }).click();
  await expect(page.getByTestId('validated-badge')).toHaveText(/EXPOSED/, { timeout: 15_000 });

  const graph = page.getByTestId('evidence-graph-canvas');
  await graph.scrollIntoViewIfNeeded();
  const edgePoint = await graph.evaluate((container, edgeId) => {
    const edge = container._cyreg?.cy?.getElementById(edgeId);
    if (!edge || edge.empty()) throw new Error(`Graph edge ${edgeId} was not rendered`);
    const point = edge.renderedMidpoint();
    const bounds = container.getBoundingClientRect();
    return { x: bounds.left + point.x, y: bounds.top + point.y };
  }, 'syn:G1-2');
  await page.mouse.click(edgePoint.x, edgePoint.y);

  const locker = page.getByRole('region', { name: 'Evidence locker' });
  await expect(locker).toContainText('syn:G1-2');
  await expect(locker).toContainText('Meridian Holdings SA');
  await expect(locker).toContainText('synthetic-v1');
  await expect(locker).toContainText('CC0-1.0');
  await expect(locker).toContainText('In proof');
  await expect(locker).toContainText('Decisive');
});
