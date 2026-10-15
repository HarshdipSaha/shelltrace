import { test, expect } from '@playwright/test';

const nextWorkspace = () => `e2e_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;

async function openCase(page, workspace, term, asOf = '2024-01-01') {
  await page.goto(`/?ws=${workspace}`);
  await expect(page.locator('.search-panel .workspace-pill')).toHaveText(workspace);
  await page.getByPlaceholder('Search company, LEI or IMO').fill(term);
  await page.getByRole('option', { name: new RegExp(term, 'i') }).first().click();
  await page.getByLabel('As of').fill(asOf);
  await page.getByRole('button', { name: 'Run investigation' }).click();
}

test('watch flip after a designation', async ({ page }) => {
  test.setTimeout(60_000);
  const workspace = nextWorkspace();
  await openCase(page, workspace, 'Aegean Fresh Produce', '2024-03-01');
  await expect(page.getByTestId('validated-badge')).toHaveText(/CLEAR_WITHIN_BOUNDS/, { timeout: 15_000 });
  await page.getByLabel('Watch this case').click();
  await expect(page.getByText('Watching for changes')).toBeVisible();

  await page.getByRole('button', { name: 'Demo: inject designation' }).click();
  const form = page.getByRole('region', { name: 'Demo designation injection' });
  await form.getByLabel('Designation entity').fill('Nikos');
  await form.getByRole('option', { name: /Nikos/ }).click();
  await form.getByLabel('Authority').selectOption('OFAC');
  await form.getByLabel('Program').fill('SDN (demo)');
  await form.getByLabel('Listed on').fill('2024-03-15');
  await form.getByLabel('Source').fill('Demo injection');
  await form.getByRole('button', { name: 'Inject designation' }).click();

  await expect(page.getByRole('status').filter({ hasText: 'entities newly blocked' }))
    .toContainText('2 entities newly blocked · 1 watched case(s) changed');
  await page.getByRole('button', { name: /Notifications/ }).click();
  const drawer = page.getByRole('region', { name: 'Notifications', exact: true });
  await expect(drawer).toContainText('Aegean Fresh Produce SA');
  await expect(drawer).toContainText('CLEAR_WITHIN_BOUNDS → EXPOSED');
  await drawer.getByRole('link', { name: 'View diff' }).click();
  await expect(page.getByTestId('validated-badge')).toHaveText(/EXPOSED/, { timeout: 15_000 });
});

test('report sentences are cited and four-eyes is enforced', async ({ page }) => {
  const workspace = nextWorkspace();
  await openCase(page, workspace, 'Nord Harbor');
  await expect(page.getByTestId('validated-badge')).toHaveText(/EXPOSED/, { timeout: 15_000 });

  await page.getByRole('button', { name: 'Draft report' }).click();
  const claims = page.locator('[data-testid="report-sentence"][data-kind="claim"]');
  await expect(claims.first()).toBeVisible();
  for (const claim of await claims.all()) {
    expect(await claim.locator('[data-testid="report-citation"]').count()).toBeGreaterThan(0);
  }
  const citation = claims.first().locator('[data-testid="report-citation"]').first();
  const citationKey = (await citation.innerText()).replaceAll('[', '').replaceAll(']', '');
  await citation.click();
  await expect(page.getByRole('region', { name: 'Evidence locker' })).toContainText(citationKey);
  await expect(page.getByText(/Writer: template/i)).toBeVisible();

  const review = page.getByRole('region', { name: 'Review disposition' });
  await review.getByLabel('Review code').selectOption('CONFIRMED_CLEAR');
  await review.getByLabel('Reason').fill('The analyst confirms this is clear after reviewing the evidence.');
  await review.getByLabel('Reviewer', { exact: true }).fill('analyst-1');
  await review.getByRole('button', { name: 'Submit review' }).click();
  await expect(review).toContainText('A second reviewer is required to remove an exposure');
});

test('name screening is shown beside the validated disposition', async ({ page }) => {
  await openCase(page, nextWorkspace(), 'Nord Harbor');
  await expect(page.getByTestId('validated-badge')).toHaveText(/EXPOSED/, { timeout: 15_000 });
  await page.getByRole('button', { name: 'Run name screen' }).click();
  await expect(page.getByText('Name screen: no hit')).toBeVisible();
  await expect(page.getByTestId('validated-badge')).toHaveText(/EXPOSED/);
  await expect(page.locator('.screening-result')).toHaveAttribute(
    'title',
    'List lookup only — what ShellTrace adds is the ownership graph',
  );
});

test('pending alias decision can be accepted with a reason', async ({ page }) => {
  await openCase(page, nextWorkspace(), 'Juniper');
  await expect(page.getByTestId('validated-badge')).toHaveText(/ESCALATE/, { timeout: 15_000 });
  const aliases = page.getByRole('region', { name: 'Alias decisions' });
  await expect(aliases).toContainText('ION Holdings Limited');
  await aliases.getByRole('button', { name: 'Accept alias' }).click();
  await aliases.getByLabel('Decision reason').fill('Company identity confirmed from registry records.');
  await aliases.getByRole('button', { name: 'Confirm accept' }).click();
  await expect(page.getByTestId('validated-badge')).toHaveText(/EXPOSED/, { timeout: 15_000 });
});
