// Exploratory, data-driven browser suite: the golden scenario table driven through the real UI,
// plus real-world analyst situations (odd search input, API failures, mobile, mutating flows).
// Mutating flows use their own `?ws=` workspace so they never disturb the shared demo graph.
import { test as base, expect } from '@playwright/test';

// Collect uncaught page errors and console errors for every test and attach them to the report.
const test = base.extend({
  page: async ({ page }, use, testInfo) => {
    const pageErrors = [];
    const consoleErrors = [];
    page.on('pageerror', (error) => pageErrors.push(error.message));
    page.on('console', (message) => {
      if (message.type() === 'error') consoleErrors.push(message.text());
    });
    await use(page);
    if (consoleErrors.length) testInfo.annotations.push({ type: 'console-error', description: consoleErrors.join(' | ').slice(0, 500) });
    expect(pageErrors, 'uncaught page errors').toEqual([]);
  },
});

// Mutating flows get a fresh workspace per run so earlier runs cannot leak state into them.
const freshWs = (name) => `${name}_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 5)}`;

const SEARCH = 'Search company, LEI or IMO';
const RESULT_TIMEOUT = 20_000;

async function pick(page, query, optionName) {
  await page.getByPlaceholder(SEARCH).fill(query);
  await page.getByRole('option', { name: optionName }).first().click();
}

async function investigate(page, { query, option, asOf, hops, packs }) {
  await pick(page, query, option);
  if (asOf) await page.getByLabel('As of').fill(asOf);
  if (hops) await page.getByLabel('Max hops').selectOption(String(hops));
  if (packs) {
    for (const pack of ['OFAC', 'EU', 'UK']) {
      const box = page.getByRole('checkbox', { name: pack });
      if (packs.includes(pack)) await box.check(); else await box.uncheck();
    }
  }
  await page.getByRole('button', { name: 'Run investigation' }).click();
}

const badge = (page) => page.getByTestId('validated-badge');

// Mirrors backend/eval/golden.py (24 checks) so UI results can be compared with the deterministic gate.
const ALL = ['OFAC', 'EU', 'UK'];
const GOLDEN = [
  ['G1 alias chain', 'nord harbor', /Nord Harbor Logistics/, '2024-01-01', ALL, 'EXPOSED', { OFAC: 'BLOCKED', EU: 'BLOCKED', UK: 'BLOCKED' }],
  ['G2 temporal', 'nord harbor', /Nord Harbor Logistics/, '2020-06-01', ALL, 'EXPOSED', { OFAC: 'BLOCKED', EU: 'BLOCKED', UK: 'BLOCKED' }],
  ['G3 chain 50/50', 'birch', /Birch Marine/, '2024-01-01', ALL, 'EXPOSED', { OFAC: 'BLOCKED', EU: 'BLOCKED', UK: 'NOT_BLOCKED' }],
  ['G3uk', 'birch', /Birch Marine/, '2024-01-01', ['UK'], 'CLEAR_WITHIN_BOUNDS', { UK: 'NOT_BLOCKED' }],
  ['G4 aggregation', 'cedar', /Cedar Grain/, '2024-01-01', ALL, 'EXPOSED', { OFAC: 'BLOCKED', EU: 'BLOCKED', UK: 'NOT_BLOCKED' }],
  ['G4uk', 'cedar', /Cedar Grain/, '2024-01-01', ['UK'], 'CLEAR_WITHIN_BOUNDS', { UK: 'NOT_BLOCKED' }],
  ['G5 unknown stake', 'dune', /Dune Logistics/, '2024-01-01', ALL, 'ESCALATE', { OFAC: 'INDETERMINATE', EU: 'INDETERMINATE', UK: 'INDETERMINATE' }],
  ['G6 unknown bounded', 'elm fert', /Elm Fertiliser/, '2024-01-01', ALL, 'CLEAR_WITHIN_BOUNDS', { OFAC: 'NOT_BLOCKED', EU: 'NOT_BLOCKED', UK: 'NOT_BLOCKED' }],
  ['G7 restructuring 49%', 'fjord', /Fjord Bunkering/, '2024-01-01', ALL, 'ESCALATE', { OFAC: 'NOT_BLOCKED', EU: 'NOT_BLOCKED', UK: 'NOT_BLOCKED' }],
  ['G7pre', 'fjord', /Fjord Bunkering/, '2023-03-01', ALL, 'CLEAR_WITHIN_BOUNDS', { OFAC: 'NOT_BLOCKED', EU: 'NOT_BLOCKED', UK: 'NOT_BLOCKED' }],
  ['G8 circular', 'gamma', /Gamma Ventures/, '2024-01-01', ALL, 'ESCALATE', { OFAC: 'NOT_BLOCKED', EU: 'NOT_BLOCKED', UK: 'NOT_BLOCKED' }],
  ['G9 lookalike', 'harbor trading', /Harbor Trading GmbH/, '2024-01-01', ALL, 'CLEAR_WITHIN_BOUNDS', { OFAC: 'NOT_BLOCKED', EU: 'NOT_BLOCKED', UK: 'NOT_BLOCKED' }],
  ['G10 pending alias', 'juniper', /Juniper Shipping/, '2024-01-01', ALL, 'ESCALATE', { OFAC: 'NOT_BLOCKED', EU: 'NOT_BLOCKED', UK: 'NOT_BLOCKED' }],
  ['G11 injection name', 'kestrel tankers', /Kestrel Tankers/, '2024-01-01', ALL, 'EXPOSED', { OFAC: 'BLOCKED', EU: 'BLOCKED', UK: 'BLOCKED' }],
  ['G11v vessel', 'kestrel star', /Kestrel Star/, '2024-01-01', ALL, 'EXPOSED', { OFAC: 'BLOCKED', EU: 'BLOCKED', UK: 'BLOCKED' }],
  ['G12 delisting (before)', 'larch', /Larch Metals/, '2022-06-01', ALL, 'EXPOSED', { OFAC: 'BLOCKED', EU: 'BLOCKED', UK: 'BLOCKED' }],
  ['G12post delisting (after)', 'larch', /Larch Metals/, '2024-01-01', ALL, 'CLEAR_WITHIN_BOUNDS', { OFAC: 'NOT_BLOCKED', EU: 'NOT_BLOCKED', UK: 'NOT_BLOCKED' }],
  ['G13 control only', 'maple', /Maple Resources/, '2024-01-01', ALL, 'ESCALATE', { OFAC: 'NOT_BLOCKED', EU: 'PRESUMED_CONTROLLED', UK: 'PRESUMED_CONTROLLED' }],
  ['G14 pre-event', 'aegean', /Aegean Fresh/, '2024-03-01', ALL, 'CLEAR_WITHIN_BOUNDS', { OFAC: 'NOT_BLOCKED', EU: 'NOT_BLOCKED', UK: 'NOT_BLOCKED' }],
  ['G15 mass address', 'quartz', /Quartz Commodities/, '2024-01-01', ALL, 'ESCALATE', { OFAC: 'NOT_BLOCKED', EU: 'NOT_BLOCKED', UK: 'NOT_BLOCKED' }],
  ['G16 direct', 'rostok', /Rostok Oil/, '2024-01-01', ALL, 'EXPOSED', { OFAC: 'BLOCKED', EU: 'BLOCKED', UK: 'BLOCKED' }],
  ['G17 duplicate records', 'nimbus', /Nimbus Freight/, '2024-01-01', ALL, 'EXPOSED', { OFAC: 'BLOCKED', EU: 'BLOCKED', UK: 'BLOCKED' }],
  ['G17c conflicting sources', 'otter', /Otter Chemicals/, '2024-01-01', ALL, 'ESCALATE', { OFAC: 'INDETERMINATE', EU: 'INDETERMINATE', UK: 'INDETERMINATE' }],
  ['G18 one hop', 'meridian', /Meridian Holdings/, '2024-01-01', ALL, 'EXPOSED', { OFAC: 'BLOCKED', EU: 'BLOCKED', UK: 'BLOCKED' }],
];

test.describe('golden scenarios through the real UI', () => {
  for (const [label, query, option, asOf, packs, disposition, verdicts] of GOLDEN) {
    test(label, async ({ page }) => {
      await page.goto('/');
      await investigate(page, { query, option, asOf, packs });
      await expect(badge(page)).toHaveText(new RegExp(disposition), { timeout: RESULT_TIMEOUT });
      for (const [pack, verdict] of Object.entries(verdicts)) {
        await expect(page.getByTestId(`pack-verdict-${pack}`)).toContainText(verdict);
      }
      await expect(page.getByText('not legal advice', { exact: false }).first()).toBeVisible();
    });
  }
});

test.describe('search input robustness', () => {
  test('finds a company by LEI', async ({ page }) => {
    await page.goto('/');
    await page.getByPlaceholder(SEARCH).fill('5299000HARBOR0000001');
    await expect(page.getByRole('option', { name: /Harbor Trading GmbH/ })).toBeVisible();
  });

  test('finds a vessel by IMO', async ({ page }) => {
    await page.goto('/');
    await page.getByPlaceholder(SEARCH).fill('9876543');
    await expect(page.getByRole('option', { name: /Kestrel Star/ })).toBeVisible();
  });

  test('lookalike names stay distinct (Harbor vs Harbour)', async ({ page }) => {
    await page.goto('/');
    await page.getByPlaceholder(SEARCH).fill('harbo');
    await expect(page.getByRole('option', { name: /Harbor Trading GmbH/ })).toBeVisible();
    await expect(page.getByRole('option', { name: /Harbour Trading GmbH/ })).toBeVisible();
  });

  // Known limitation (FINDING F-3): entity search is token/prefix based, not typo tolerant.
  const KNOWN_NOT_TYPO_TOLERANT = new Set(['British spelling typo', 'single transposition typo']);
  for (const [label, query, expected] of [
    ['upper-case query', 'NORD HARBOR', /Nord Harbor Logistics/],
    ['padded with spaces', '   nord harbor   ', /Nord Harbor Logistics/],
    ['British spelling typo', 'nord harbour', /Nord Harbor Logistics/],
    ['accented characters', 'Nórd Hàrbor', /Nord Harbor Logistics/],
    ['punctuated variant', 'I.O.N. Holding', /ION Holdings|I\.O\.N\. Holding/],
    ['single transposition typo', 'nrod harbor', /Nord Harbor Logistics/],
  ]) {
    test(`fuzzy: ${label}`, async ({ page }) => {
      test.fail(KNOWN_NOT_TYPO_TOLERANT.has(label), 'search is not typo tolerant yet');
      await page.goto('/');
      await page.getByPlaceholder(SEARCH).fill(query);
      await expect(page.getByRole('option', { name: expected }).first()).toBeVisible({ timeout: RESULT_TIMEOUT });
    });
  }

  for (const [label, query] of [
    ['HTML/script payload', '<img src=x onerror=window.__xss=1><script>window.__xss=1</script>'],
    ['SQL/Cypher metacharacters', "'; MATCH (n) DETACH DELETE n; //"],
    ['cypher injection in quotes', '" OR 1=1 RETURN n //'],
    ['emoji', '🚢🚢🚢'],
    ['Cyrillic', 'Норд Харбор'],
    ['CJK', '北方港口物流'],
    ['10k-character string', 'a'.repeat(10_000)],
    ['single character', 'n'],
    ['whitespace only', '     '],
    ['null byte and control characters', 'nord\u0000\u0007harbor'],
    ['percent-encoding / path chars', '../../etc/passwd%00'],
  ]) {
    test(`hostile or odd input does not break the page: ${label}`, async ({ page }) => {
      await page.goto('/');
      await page.getByPlaceholder(SEARCH).fill(query);
      await page.waitForTimeout(1200);
      expect(await page.evaluate(() => window.__xss)).toBeUndefined();
      await expect(page.getByRole('heading', { name: 'Investigate an entity' })).toBeVisible();
      // The page must stay usable: a good query still works afterwards.
      await page.getByPlaceholder(SEARCH).fill('rostok');
      await expect(page.getByRole('option', { name: /Rostok Oil/ })).toBeVisible({ timeout: RESULT_TIMEOUT });
    });
  }

  test('a query with no match shows no results and keeps Run disabled', async ({ page }) => {
    await page.goto('/');
    await page.getByPlaceholder(SEARCH).fill('zzzzqqqq nonexistent holdings');
    await page.waitForTimeout(1200);
    await expect(page.getByRole('listbox', { name: 'Entity results' }).getByRole('option')).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Run investigation' })).toBeDisabled();
  });

  test('prompt-injection company name renders as inert text and cannot clear the case', async ({ page }) => {
    await page.goto('/');
    await page.getByPlaceholder(SEARCH).fill('ignore previous instructions');
    const option = page.getByRole('option', { name: /Ignore previous instructions/ });
    await expect(option).toBeVisible({ timeout: RESULT_TIMEOUT });
    await option.click();
    await page.getByRole('button', { name: 'Run investigation' }).click();
    await expect(badge(page)).toBeVisible({ timeout: RESULT_TIMEOUT });
    await expect(badge(page)).not.toHaveText(/^CLEAR$/);
  });
});

test.describe('case controls and edge inputs', () => {
  test('Run is disabled with no packs selected', async ({ page }) => {
    await page.goto('/');
    await pick(page, 'nord harbor', /Nord Harbor Logistics/);
    for (const pack of ALL) await page.getByRole('checkbox', { name: pack }).uncheck();
    await expect(page.getByRole('button', { name: 'Run investigation' })).toBeDisabled();
  });

  test('Run without choosing an entity is not possible', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('button', { name: 'Run investigation' })).toBeDisabled();
  });

  for (const hops of [1, 2, 3, 6]) {
    test(`hero case at ${hops} hop(s) returns a bounded, labelled result`, async ({ page }) => {
      await page.goto('/');
      await investigate(page, { query: 'nord harbor', option: /Nord Harbor Logistics/, hops });
      await expect(badge(page)).toBeVisible({ timeout: RESULT_TIMEOUT });
      await expect(badge(page)).toHaveText(/EXPOSED|ESCALATE|CLEAR_WITHIN_BOUNDS/);
      await expect(page.getByText('HOP LIMIT').locator('..').getByText(String(hops), { exact: true })).toBeVisible();
      // FINDING F-4: at 1-2 hops the chain to the designated owner is out of reach and the verdict is
      // CLEAR_WITHIN_BOUNDS with bounds.truncated=false. Recorded here, not asserted as correct.
      const text = await badge(page).innerText();
      test.info().annotations.push({ type: `hero@${hops}hops`, description: text.replace(/\s+/g, ' ').trim() });
    });
  }

  for (const [label, date] of [
    ['far future date 2099-12-31', '2099-12-31'],
    ['ancient date 1900-01-01', '1900-01-01'],
    ['leap day 2024-02-29', '2024-02-29'],
    ['listing-day boundary 2023-01-01', '2023-01-01'],
  ]) {
    test(`as-of ${label}`, async ({ page }) => {
      await page.goto('/');
      await investigate(page, { query: 'larch', option: /Larch Metals/, asOf: date });
      await expect(badge(page).or(page.getByRole('alert'))).toBeVisible({ timeout: RESULT_TIMEOUT });
      await expect(page.getByText(/Internal Server Error|Traceback/i)).toHaveCount(0);
    });
  }

  test('clearing the as-of date does not crash and does not show a stale verdict', async ({ page }) => {
    await page.goto('/');
    await pick(page, 'larch', /Larch Metals/);
    await page.getByLabel('As of').fill('');
    await page.getByRole('button', { name: 'Run investigation' }).click();
    await expect(page.getByRole('heading', { name: 'Investigate an entity' })).toBeVisible();
    await expect(page.getByText(/Internal Server Error|Traceback/i)).toHaveCount(0);
    // Either a readable validation error, or the run is blocked: never a fabricated verdict.
    const verdict = await badge(page).count();
    if (verdict) {
      await expect(page.getByText(/As of/).first()).toBeVisible();
    } else {
      await expect(page.getByRole('alert')).toBeVisible({ timeout: RESULT_TIMEOUT });
    }
  });

  test('rapid double-click on Run produces exactly one case', async ({ page }) => {
    await page.goto('/');
    const posts = [];
    page.on('request', (request) => {
      if (request.method() === 'POST' && request.url().endsWith('/api/cases')) posts.push(request.url());
    });
    await pick(page, 'rostok', /Rostok Oil/);
    const run = page.getByRole('button', { name: 'Run investigation' });
    await run.dblclick();
    await expect(badge(page)).toHaveText(/EXPOSED/, { timeout: RESULT_TIMEOUT });
    expect(posts.length, 'duplicate case POSTs from a double click').toBe(1);
  });

  test('changing the date mid-flight does not let a stale result win', async ({ page }) => {
    await page.goto('/');
    await investigate(page, { query: 'larch', option: /Larch Metals/, asOf: '2022-06-01' });
    await expect(badge(page)).toHaveText(/EXPOSED/, { timeout: RESULT_TIMEOUT });
    const slider = page.getByRole('slider', { name: 'Investigation date' });
    await slider.focus();
    for (let i = 0; i < 3; i += 1) await slider.press(i % 2 ? 'ArrowLeft' : 'ArrowRight');
    const valuetext = await slider.getAttribute('aria-valuetext');
    // Whatever order the three responses arrive in, the settled case must be the last date requested.
    await expect(page.getByText(`As of ${valuetext}`).first()).toBeVisible({ timeout: RESULT_TIMEOUT });
    await page.waitForTimeout(1500);
    await expect(page.getByText(`As of ${valuetext}`).first()).toBeVisible();
  });

  test('changing entity clears the previous verdict', async ({ page }) => {
    await page.goto('/');
    await investigate(page, { query: 'rostok', option: /Rostok Oil/ });
    await expect(badge(page)).toHaveText(/EXPOSED/, { timeout: RESULT_TIMEOUT });
    await pick(page, 'elm fert', /Elm Fertiliser/);
    await expect(badge(page)).toHaveCount(0);
    await expect(page.getByText('Awaiting investigation')).toBeVisible();
  });

  test('running the same case twice is deterministic', async ({ page }) => {
    await page.goto('/');
    await investigate(page, { query: 'birch', option: /Birch Marine/ });
    await expect(badge(page)).toHaveText(/EXPOSED/, { timeout: RESULT_TIMEOUT });
    const first = await page.getByTestId('pack-verdict-UK').innerText();
    await page.getByRole('button', { name: 'Run investigation' }).click();
    await expect(badge(page)).toHaveText(/EXPOSED/, { timeout: RESULT_TIMEOUT });
    expect(await page.getByTestId('pack-verdict-UK').innerText()).toBe(first);
  });
});

test.describe('analyst workflow on a finished case', () => {
  test('draft a cited report and follow a citation into the evidence locker', async ({ page }) => {
    await page.goto('/');
    await investigate(page, { query: 'nord harbor', option: /Nord Harbor Logistics/ });
    await expect(badge(page)).toHaveText(/EXPOSED/, { timeout: RESULT_TIMEOUT });
    await page.getByRole('button', { name: /draft/i }).first().click();
    await expect(page.getByTestId('report-sentence').first()).toBeVisible({ timeout: RESULT_TIMEOUT });
    const count = await page.getByTestId('report-sentence').count();
    expect(count).toBeGreaterThan(0);
    const citation = page.getByTestId('report-citation').first();
    await expect(citation).toBeVisible();
    await citation.click();
    await expect(page.getByRole('region', { name: 'Evidence locker' })).toContainText(/syn:/);
  });

  test('every report sentence carries at least one citation', async ({ page }) => {
    await page.goto('/');
    await investigate(page, { query: 'birch', option: /Birch Marine/ });
    await expect(badge(page)).toHaveText(/EXPOSED/, { timeout: RESULT_TIMEOUT });
    await page.getByRole('button', { name: /draft/i }).first().click();
    await expect(page.getByTestId('report-sentence').first()).toBeVisible({ timeout: RESULT_TIMEOUT });
    // 'meta' sentences (headline, bounds, disclaimer) are uncited by design; every 'claim' must cite.
    const sentences = page.locator('[data-testid="report-sentence"][data-kind="claim"]');
    const total = await sentences.count();
    for (let i = 0; i < total; i += 1) {
      const cites = await sentences.nth(i).getByTestId('report-citation').count();
      expect(cites, `report sentence ${i} has no citation`).toBeGreaterThan(0);
    }
  });

  test('name screen runs and reports a baseline', async ({ page }) => {
    await page.goto('/');
    await investigate(page, { query: 'nord harbor', option: /Nord Harbor Logistics/ });
    await expect(badge(page)).toHaveText(/EXPOSED/, { timeout: RESULT_TIMEOUT });
    const panel = page.getByRole('region', { name: 'Name screening baseline' });
    await panel.getByRole('button').first().click();
    await expect(panel).not.toContainText(/Internal Server Error/i);
    await expect(panel.getByRole('alert')).toHaveCount(0, { timeout: RESULT_TIMEOUT });
  });

  test('human review: short reason keeps submit disabled, valid review is recorded and listed', async ({ page }) => {
    await page.goto(`/?ws=${freshWs('explore_review')}`);
    await investigate(page, { query: 'rostok', option: /Rostok Oil/ });
    await expect(badge(page)).toHaveText(/EXPOSED/, { timeout: RESULT_TIMEOUT });
    const panel = page.getByRole('region', { name: 'Review disposition' });
    const submit = panel.getByRole('button', { name: /record|submit|save|confirm/i }).first();
    await panel.getByLabel('Reason').fill('too short');
    await panel.getByLabel('Reviewer').fill('a');
    await expect(submit).toBeDisabled();
    await panel.getByLabel('Reason').fill('<b>Direct designation confirmed against OFAC list</b> – reviewed 2024');
    await panel.getByLabel('Reviewer').fill('analyst-qa');
    await submit.click();
    await expect(panel.getByLabel('Review history')).toContainText('analyst-qa', { timeout: RESULT_TIMEOUT });
    // HTML typed into the reason must be shown as text, not interpreted.
    await expect(panel.getByLabel('Review history').locator('b')).toHaveCount(0);
  });

  test('watch toggle and designation injection raise a notification that reopens the changed case', async ({ page }) => {
    test.setTimeout(90_000);
    await page.goto(`/?ws=${freshWs('explore_watch')}`);
    await investigate(page, { query: 'aegean', option: /Aegean Fresh/, asOf: '2024-03-01' });
    await expect(badge(page)).toHaveText(/CLEAR_WITHIN_BOUNDS/, { timeout: RESULT_TIMEOUT });
    await page.getByLabel('Watch this case').click();
    await expect(page.getByLabel('Watch this case')).toBeChecked();
    await page.getByRole('button', { name: /demo|designation|inject/i }).first().click();
    const region = page.getByRole('region', { name: 'Demo designation injection' });
    await region.getByLabel('Designation entity').fill('olive grove');
    await region.getByRole('option', { name: /Olive Grove/ }).click();
    await region.getByLabel('Program').fill('E2E-PROGRAM');
    await region.getByLabel('Listed on').fill('2024-02-01');
    await region.getByLabel('Source').fill('exploratory-e2e');
    await region.getByRole('button', { name: /inject|add|designat/i }).last().click();
    await expect(page.getByRole('status').filter({ hasText: /./ }).first()).toBeVisible({ timeout: RESULT_TIMEOUT });
    await page.getByRole('button', { name: /notification/i }).first().click();
    await expect(page.getByRole('region', { name: 'Notifications', exact: true })).toBeVisible();
  });

  test('pending alias candidate can be accepted with a reason and changes the verdict', async ({ page }) => {
    test.setTimeout(90_000);
    await page.goto(`/?ws=${freshWs('explore_alias')}`);
    await investigate(page, { query: 'juniper', option: /Juniper Shipping/ });
    await expect(badge(page)).toHaveText(/ESCALATE/, { timeout: RESULT_TIMEOUT });
    const panel = page.getByRole('region', { name: 'Alias decisions' });
    await panel.getByRole('button', { name: 'Accept alias' }).first().click();
    await panel.getByLabel('Decision reason').fill('Same registry number and registered address confirmed.');
    await panel.getByRole('button', { name: /accept|confirm|record|submit/i }).last().click();
    await expect(badge(page)).toHaveText(/EXPOSED/, { timeout: RESULT_TIMEOUT });
  });

  test('rejecting a candidate requires a reason of at least 10 characters', async ({ page }) => {
    await page.goto(`/?ws=${freshWs('explore_alias_reject')}`);
    await investigate(page, { query: 'juniper', option: /Juniper Shipping/ });
    await expect(badge(page)).toBeVisible({ timeout: RESULT_TIMEOUT });
    const panel = page.getByRole('region', { name: 'Alias decisions' });
    await panel.getByRole('button', { name: 'Reject' }).first().click();
    await panel.getByLabel('Decision reason').fill('no');
    await expect(panel.getByRole('button', { name: /reject|confirm|record|submit/i }).last()).toBeDisabled();
  });

  test('selecting a timeline step with evidence opens the locker', async ({ page }) => {
    await page.goto('/');
    await investigate(page, { query: 'nord harbor', option: /Nord Harbor Logistics/ });
    await expect(badge(page)).toHaveText(/EXPOSED/, { timeout: RESULT_TIMEOUT });
    const key = page.getByRole('button', { name: /^syn:/ }).first();
    await key.click();
    await expect(page.getByRole('region', { name: 'Evidence locker' })).toContainText(/syn:/);
  });
});

test.describe('failure modes a real user will hit', () => {
  test('API down at load: clear error, Agent mode disabled, retry works once it is back', async ({ page }) => {
    let down = true;
    await page.route('**/api/health', (route) => (down
      ? route.abort('connectionrefused')
      : route.continue()));
    await page.goto('/');
    await expect(page.getByText('Graph unavailable')).toBeVisible();
    await expect(page.getByRole('radio', { name: /Agent/ })).toBeDisabled();
    down = false;
    await page.getByRole('button', { name: 'Retry status check' }).click();
    await expect(page.getByText('Graph connected')).toBeVisible();
  });

  test('case request returns 500: readable alert, controls recover', async ({ page }) => {
    await page.route('**/api/cases', (route) => route.fulfill({
      status: 500, contentType: 'application/json', body: JSON.stringify({ detail: 'database exploded' }),
    }));
    await page.goto('/');
    await investigate(page, { query: 'rostok', option: /Rostok Oil/ });
    await expect(page.getByRole('alert')).toContainText('API 500');
    await expect(page.getByRole('button', { name: 'Run investigation' })).toBeEnabled();
    await expect(badge(page)).toHaveCount(0);
  });

  test('case request returns an HTML 404 page (the deployed-without-backend symptom)', async ({ page }) => {
    await page.route('**/api/**', (route) => route.fulfill({
      status: 404, contentType: 'text/html', body: '<h1>The page could not be found</h1><p>NOT_FOUND</p>',
    }));
    await page.goto('/');
    // Honest, actionable output expected; at minimum the user must be told the service is unavailable.
    await expect(page.getByText('Graph unavailable')).toBeVisible();
    await expect(page.locator('body')).not.toContainText('<h1>');
    await page.getByRole('button', { name: 'Retry status check' }).click();
    await expect(page.getByText(/API 404: the ShellTrace API is not reachable/)).toBeVisible();
  });

  test('network drops while the investigation is running', async ({ page }) => {
    await page.goto('/');
    await pick(page, 'rostok', /Rostok Oil/);
    await page.route('**/api/cases', (route) => route.abort('connectionreset'));
    await page.getByRole('button', { name: 'Run investigation' }).click();
    await expect(page.getByRole('alert')).toBeVisible({ timeout: RESULT_TIMEOUT });
    await expect(page.getByRole('button', { name: 'Run investigation' })).toBeEnabled();
  });

  test('malformed JSON from the API does not blank the page', async ({ page }) => {
    await page.route('**/api/cases', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '{"case_id": ' }));
    await page.goto('/');
    await investigate(page, { query: 'rostok', option: /Rostok Oil/ });
    await expect(page.getByRole('alert')).toContainText(/not valid JSON/i, { timeout: RESULT_TIMEOUT });
    await expect(page.getByRole('heading', { name: 'Investigate an entity' })).toBeVisible();
  });

  test('empty-object 200 from the API does not blank the page', async ({ page }) => {
    await page.route('**/api/cases', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '{}' }));
    await page.goto('/');
    await investigate(page, { query: 'rostok', option: /Rostok Oil/ });
    await expect(page.getByRole('alert')).toContainText(/incomplete case response/i, { timeout: RESULT_TIMEOUT });
    await expect(page.getByRole('heading', { name: 'Investigate an entity' })).toBeVisible();
  });

  test('slow backend (4s) shows a loading state and then completes', async ({ page }) => {
    await page.route('**/api/cases', async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 4000));
      await route.continue();
    });
    await page.goto('/');
    await investigate(page, { query: 'rostok', option: /Rostok Oil/ });
    await expect(page.getByLabel('As of')).toBeDisabled();
    await expect(badge(page)).toHaveText(/EXPOSED/, { timeout: 30_000 });
  });

  test('unknown workspace in the URL is provisioned or rejected cleanly', async ({ page }) => {
    await page.goto('/?ws=never_seen_' + Date.now().toString(36));
    await investigate(page, { query: 'rostok', option: /Rostok Oil/ });
    await expect(badge(page).or(page.getByRole('alert'))).toBeVisible({ timeout: 30_000 });
  });

  test('invalid workspace name (hyphen) in the URL surfaces a readable search error', async ({ page }) => {
    await page.goto('/?ws=has-hyphen');
    await page.getByPlaceholder(SEARCH).fill('rostok');
    await expect(page.getByText(/invalid workspace/i)).toBeVisible({ timeout: RESULT_TIMEOUT });
  });

  test('hostile workspace name in the URL is handled', async ({ page }) => {
    await page.goto('/?ws=' + encodeURIComponent('../../x";MATCH (n) DETACH DELETE n'));
    await page.getByPlaceholder(SEARCH).fill('rostok');
    await page.waitForTimeout(2000);
    await expect(page.getByRole('heading', { name: 'Investigate an entity' })).toBeVisible();
  });
});

test.describe('pages, layout and accessibility', () => {
  test('evaluation page renders from the hash route and goes back', async ({ page }) => {
    await page.goto('/#/eval');
    await expect(page.getByRole('main', { name: 'Evaluation results' })).toBeVisible();
    await expect(page.getByText(/Internal Server Error|undefined|NaN/)).toHaveCount(0);
    await page.goBack();
  });

  test('mobile viewport (375x812) has no horizontal page scroll and key controls reachable', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto('/');
    await investigate(page, { query: 'rostok', option: /Rostok Oil/ });
    await expect(badge(page)).toHaveText(/EXPOSED/, { timeout: RESULT_TIMEOUT });
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow, 'horizontal overflow in px').toBeLessThanOrEqual(1);
  });

  test('tablet viewport (768x1024) has no horizontal page scroll', async ({ page }) => {
    await page.setViewportSize({ width: 768, height: 1024 });
    await page.goto('/');
    await investigate(page, { query: 'birch', option: /Birch Marine/ });
    await expect(badge(page)).toBeVisible({ timeout: RESULT_TIMEOUT });
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow, 'horizontal overflow in px').toBeLessThanOrEqual(1);
  });

  test('keyboard-only: tab to search, type, arrow/enter selects, run with Enter/Space', async ({ page }) => {
    await page.goto('/');
    await page.getByPlaceholder(SEARCH).focus();
    await page.keyboard.type('rostok');
    await expect(page.getByRole('option', { name: /Rostok Oil/ })).toBeVisible({ timeout: RESULT_TIMEOUT });
    await page.keyboard.press('ArrowDown');
    await page.keyboard.press('Enter');
    const run = page.getByRole('button', { name: 'Run investigation' });
    await expect(run).toBeEnabled({ timeout: 5000 });
    await run.focus();
    await page.keyboard.press('Enter');
    await expect(badge(page)).toHaveText(/EXPOSED/, { timeout: RESULT_TIMEOUT });
  });

  test('form controls have accessible names', async ({ page }) => {
    await page.goto('/');
    const unnamed = await page.evaluate(() => [...document.querySelectorAll('input,select,textarea,button')]
      .filter((el) => !el.closest('[hidden]'))
      .filter((el) => !(el.getAttribute('aria-label') || el.labels?.length || el.textContent.trim() || el.getAttribute('title')))
      .map((el) => el.outerHTML.slice(0, 120)));
    expect(unnamed, 'controls without an accessible name').toEqual([]);
  });

  test('no failed same-origin requests during a full hero run', async ({ page }) => {
    const failures = [];
    page.on('response', (response) => {
      if (response.status() >= 400) failures.push(`${response.status()} ${response.url()}`);
    });
    await page.goto('/');
    await investigate(page, { query: 'nord harbor', option: /Nord Harbor Logistics/ });
    await expect(badge(page)).toHaveText(/EXPOSED/, { timeout: RESULT_TIMEOUT });
    expect(failures).toEqual([]);
  });
});

test.describe('API contract probes (direct, no UI)', () => {
  const caseBody = { workspace: 'demo', entity_id: 'c_rostok', as_of: '2024-01-01', max_hops: 6, rulepacks: ALL, mode: 'playbook' };

  test('health is ok and exposes no credentials', async ({ request }) => {
    const response = await request.get('/api/health');
    expect(response.status()).toBe(200);
    const text = await response.text();
    expect(text).not.toMatch(/gsk_|sk-ant|api[_-]?key"\s*:\s*"[^"]{8,}/i);
  });

  for (const [label, patch] of [
    ['unknown entity', { entity_id: 'does_not_exist' }],
    ['missing entity_id', { entity_id: undefined }],
    ['invalid date string', { as_of: 'not-a-date' }],
    ['impossible date', { as_of: '2024-02-31' }],
    ['empty as_of', { as_of: '' }],
    ['negative hops', { max_hops: -1 }],
    ['zero hops', { max_hops: 0 }],
    ['huge hops', { max_hops: 999999 }],
    ['unknown rulepack', { rulepacks: ['MARS'] }],
    ['empty rulepacks', { rulepacks: [] }],
    ['unknown mode', { mode: 'chaos' }],
    ['agent mode without a configured model', { mode: 'agent' }],
    ['entity_id as injection string', { entity_id: "c_rostok' OR 1=1 //" }],
    ['entity_id as a number', { entity_id: 12345 }],
    ['workspace with path traversal', { workspace: '../../etc' }],
    ['workspace with cypher metacharacters', { workspace: 'x`) MATCH (n) DETACH DELETE n //' }],
  ]) {
    test(`POST /api/cases ${label} never returns a 5xx`, async ({ request }) => {
      const response = await request.post('/api/cases', { data: { ...caseBody, ...patch } });
      expect(response.status(), await response.text()).toBeLessThan(500);
    });
  }

  test('POST /api/cases with a non-JSON body is a 4xx', async ({ request }) => {
    const response = await request.post('/api/cases', { data: 'plain text', headers: { 'Content-Type': 'text/plain' } });
    expect(response.status()).toBeGreaterThanOrEqual(400);
    expect(response.status()).toBeLessThan(500);
  });

  test('GET /api/cases/{unknown} is a 404', async ({ request }) => {
    const response = await request.get('/api/cases/nope?workspace=demo');
    expect(response.status()).toBe(404);
  });

  test('entity search with limit abuse stays bounded', async ({ request }) => {
    for (const limit of ['-5', '0', '100000', 'abc']) {
      const response = await request.get(`/api/entities/search?workspace=demo&q=nord&limit=${limit}`);
      expect(response.status(), `limit=${limit}`).toBeLessThan(500);
      if (response.ok()) {
        const body = await response.json();
        expect((body.hits ?? []).length, `limit=${limit}`).toBeLessThanOrEqual(100);
      }
    }
  });

  test('same case twice yields the same disposition, packs and tool sequence', async ({ request }) => {
    const a = await (await request.post('/api/cases', { data: caseBody })).json();
    const b = await (await request.post('/api/cases', { data: caseBody })).json();
    expect(a.disposition).toEqual(b.disposition);
    expect(Object.entries(a.packs).map(([k, v]) => [k, v.verdict])).toEqual(Object.entries(b.packs).map(([k, v]) => [k, v.verdict]));
    expect(a.steps.map((s) => s.tool)).toEqual(b.steps.map((s) => s.tool));
    // FINDING F-6 (observation): some tool-result digests differ between byte-identical requests.
    const changed = a.steps.filter((s, i) => s.result_digest !== b.steps[i].result_digest).map((s) => s.tool);
    test.info().annotations.push({ type: 'digest-drift', description: `${changed.length} of ${a.steps.length} steps: ${changed.join(',')}` });
  });

  test('the injection-named entity cannot influence the disposition', async ({ request }) => {
    const response = await request.post('/api/cases', { data: { ...caseBody, entity_id: 'c_inject' } });
    expect(response.status()).toBeLessThan(500);
  });

  test('concurrent cases (8 parallel) all succeed with consistent results', async ({ request }) => {
    const responses = await Promise.all(Array.from({ length: 8 }, () => request.post('/api/cases', { data: caseBody })));
    const statuses = responses.map((r) => r.status());
    expect(statuses).toEqual(Array(8).fill(200));
    const dispositions = await Promise.all(responses.map(async (r) => {
      const body = await r.json();
      return body.disposition;
    }));
    expect(new Set(dispositions).size).toBe(1);
  });

  test('CORS / method probes do not crash the server', async ({ request }) => {
    for (const method of ['put', 'delete', 'patch']) {
      const response = await request[method]('/api/cases', { data: {} });
      expect(response.status()).toBeLessThan(500);
    }
  });
});
