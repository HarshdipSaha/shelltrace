import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';

test('real-data footer and observation-date evidence are disclosed', async ({ page }) => {
  const result = JSON.parse(readFileSync(new URL('../src/graph/fixtures/hero_case.json', import.meta.url), 'utf8').replace(/^\uFEFF/, ''));
  result.snapshot = 'os-20261015074704-lqt';
  const evidence = result.evidence[result.packs.OFAC.proof.find(key => result.evidence[key]?.type === 'DESIGNATED')];
  evidence.listed_on_basis = 'first_seen';
  evidence.src = 'opensanctions:us_ofac_sdn';
  await page.route('**/api/health', route => route.fulfill({ json: { status: 'ok', graph: 'st_facts_real_test', llm: 'deterministic' } }));
  await page.route('**/api/entities/search?*', route => route.fulfill({ json: { hits: [result.entity] } }));
  await page.route('**/api/cases', route => route.fulfill({ json: result }));
  await page.goto('/');
  await expect(page.locator('.app-footer')).toContainText('st_facts_real_test');
  await page.getByPlaceholder('Search company, LEI or IMO').fill(result.entity.name);
  await page.getByRole('listbox', { name: 'Entity results' }).getByRole('option').first().click();
  await page.getByRole('button', { name: 'Run investigation' }).click();
  await expect(page.getByTestId('validated-badge')).toBeVisible();
  await expect(page.locator('.app-footer')).toContainText(result.snapshot);
  await page.getByRole('button', { name: evidence.k, exact: true }).first().click();
  await expect(page.getByRole('region', { name: 'Evidence locker' })).toContainText('not an official listing date');
});

test('E3 separates observation dates and shows incomplete metrics honestly', async ({ page }) => {
  await page.route('**/api/eval/latest', route => route.fulfill({ json: { available: true, real_e3: {
    caveat: 'GLEIF consolidation is not legal ownership.', strata: [{
      authority: 'OFAC', stratum: 'neutral', source_date_basis: 'first_seen_approximation', n: 4, small_n: true,
      graph_flagged_count: 3, graph_flagged_evaluated_n: 4, graph_blocked_count: 0,
      graph_blocked_evaluated_n: 3, name_screen_count: 1, name_screen_evaluated_n: 4,
    }],
  } } }));
  await page.goto('/#/eval');
  const table = page.getByRole('region', { name: 'E3 recall by name visibility' });
  await expect(table).toContainText('First observed (approximation)');
  await expect(table).toContainText('small n (3/4)');
  await expect(table).toContainText('Incomplete (3/4 evaluated)');
  await expect(table).not.toContainText('%');
});
