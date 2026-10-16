/* Recorded integration tests of the deployed UI with an authentic local API.
 * No response fixtures: route.fetch forwards every API request to REAL_API_URL.
 * Requires the person-free graph to be copied to REAL_WORKSPACE beforehand.
 */
const { chromium, expect } = require('../frontend/node_modules/@playwright/test');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');

const site = process.env.REAL_SITE_URL || 'https://frontend-five-opal-42.vercel.app';
const api = process.env.REAL_API_URL || 'http://127.0.0.1:8012';
const workspace = process.env.REAL_WORKSPACE || 'realbrowser_1016';
const out = path.resolve(process.env.REAL_RUN_DIR || 'docs/testing/real-data-runs/2026-10-16');
const scenarios = [
  { id: '01-clearing-current', query: '2534007UK6G30KDX1A47', date: '2026-10-15', name: 'National Clearing Centre' },
  { id: '02-clearing-historical', query: '2534007UK6G30KDX1A47', date: '2010-01-01', name: 'National Clearing Centre' },
  { id: '03-gtlk-capital', query: '635400I6H6CSZ39WIN49', date: '2026-10-15', name: 'GTLK Europe Capital' },
  { id: '04-vessel-imo', query: '9422964', date: '2026-10-15', name: 'ABRAU' },
  { id: '05-depository-mobile', query: '253400M18U5TB02TW421', date: '2026-10-15', name: 'National Settlement Depository', mobile: true },
];

(async () => {
  if (fs.existsSync(path.join(out, 'summary.json'))) {
    throw new Error('Run directory already contains a summary. Set REAL_RUN_DIR to a fresh directory to preserve recordings.');
  }
  fs.mkdirSync(out, { recursive: true });
  // Visible Chromium by default; HEADLESS=1 is available for display-less CI.
  const browser = await chromium.launch({ headless: process.env.HEADLESS === '1' });
  const summary = { started: new Date().toISOString(), site, api, workspace,
    setup: 'Deployed UI; browser API requests forwarded to authentic local FalkorDB API. Public deployment unchanged.', runs: [] };
  try {
    const probe = await browser.newContext();
    const health = await probe.request.get(`${api}/api/health`);
    summary.health = await health.json();
    expect(summary.health.status).toBe('ok');
    expect(summary.health.graph).toMatch(/^st_facts_real_/);
    expect(summary.health.node_count).toBeGreaterThan(1000);
    summary.publicHealth = await (await probe.request.get(`${site}/api/health`)).json();
    await probe.close();
    for (const scenario of scenarios) {
      const dir = path.join(out, scenario.id); fs.mkdirSync(dir, { recursive: true });
      const context = await browser.newContext({ viewport: scenario.mobile ? { width: 390, height: 844 } : { width: 1440, height: 1000 },
        recordVideo: { dir, size: { width: 1440, height: 1000 } } });
      await context.tracing.start({ screenshots: true, snapshots: true, sources: false });
      const page = await context.newPage(); const errors = []; const requests = [];
      page.on('pageerror', err => errors.push(err.message));
      page.on('response', response => { if (new URL(response.url()).pathname.startsWith('/api/')) requests.push({ path: new URL(response.url()).pathname, status: response.status() }); });
      const result = { ...scenario, started: new Date().toISOString(), errors, requests };
      const started = Date.now();
      try {
        await page.route(`${site}/api/**`, async route => {
          const source = new URL(route.request().url());
          const response = await route.fetch({ url: `${api}${source.pathname}${source.search}`, timeout: 90000 });
          await route.fulfill({ response });
        });
        await page.goto(`${site}/?ws=${workspace}`, { waitUntil: 'domcontentloaded' });
        await expect(page.getByRole('heading', { name: 'Investigate an entity' })).toBeVisible();
        await page.evaluate(() => {
          const note = document.createElement('div'); note.textContent = 'RECORDED REAL-DATA TEST: deployed UI → local OpenSanctions/GLEIF API';
          note.style.cssText = 'position:fixed;bottom:0;left:0;right:0;background:#fff3c4;color:#222;padding:8px;z-index:99999;font:12px sans-serif'; document.body.appendChild(note);
        });
        await page.getByPlaceholder('Search company, LEI or IMO').fill(scenario.query);
        await page.getByRole('option', { name: new RegExp(scenario.name, 'i') }).first().click({ timeout: 20000 });
        await page.getByLabel('As of').fill(scenario.date);
        const responsePromise = page.waitForResponse(r => new URL(r.url()).pathname === '/api/cases' && r.request().method() === 'POST', { timeout: 90000 });
        await page.getByRole('button', { name: 'Run investigation' }).click();
        const response = await responsePromise;
        expect(response.status(), await response.text()).toBe(200);
        const body = await response.json();
        expect(body.entity.id).toMatch(/^(lei:|os:)/);
        expect(body.snapshot).toContain('os-20261015');
        await expect(page.getByTestId('validated-badge')).toContainText(body.disposition, { timeout: 15000 });
        for (const [pack, value] of Object.entries(body.packs)) await expect(page.getByTestId(`pack-verdict-${pack}`)).toContainText(value.verdict);
        result.entity = body.entity; result.disposition = body.disposition;
        result.packs = Object.fromEntries(Object.entries(body.packs).map(([key, value]) => [key, value.verdict]));
        result.evidenceCount = Object.keys(body.evidence).length;
        expect(Object.values(body.evidence).every(e => !(e.src || '').startsWith('synthetic'))).toBe(true);
        await page.getByRole('button', { name: 'Run name screen' }).click();
        await expect(page.locator('.screening-result')).toBeVisible({ timeout: 15000 });
        await page.getByRole('button', { name: 'Draft report' }).click();
        await expect(page.getByTestId('report-sentence').first()).toBeVisible({ timeout: 20000 });
        const claims = page.locator('[data-testid="report-sentence"][data-kind="claim"]');
        result.claims = await claims.count();
        for (const claim of await claims.all()) expect(await claim.getByTestId('report-citation').count()).toBeGreaterThan(0);
        result.horizontalOverflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
        if (scenario.mobile) expect(result.horizontalOverflow).toBeLessThanOrEqual(1);
        expect(errors).toEqual([]);
        expect(requests.filter(r => r.status >= 400)).toEqual([]);
        result.status = 'passed';
      } catch (error) { result.status = 'failed'; result.failure = error.message; }
      finally {
        result.durationMs = Date.now() - started;
        await page.screenshot({ path: path.join(dir, 'final.png'), fullPage: true }).catch(() => {});
        await context.tracing.stop({ path: path.join(dir, 'trace.zip') });
        const video = page.video(); await context.close(); if (video) await video.saveAs(path.join(dir, 'run.webm'));
        // Preserve one consistently named video per attempt.
        for (const file of fs.readdirSync(dir)) if (file.endsWith('.webm') && file !== 'run.webm') fs.unlinkSync(path.join(dir, file));
        result.artifacts = fs.readdirSync(dir).map(file => ({ file: `${scenario.id}/${file}`, sha256: crypto.createHash('sha256').update(fs.readFileSync(path.join(dir, file))).digest('hex') }));
        summary.runs.push(result); fs.writeFileSync(path.join(out, 'summary.json'), JSON.stringify(summary, null, 2));
        console.log(`${scenario.id}: ${result.status} (${result.durationMs}ms)${result.failure ? ` ${result.failure}` : ''}`);
      }
    }
  } finally { await browser.close(); }
  if (summary.runs.some(run => run.status !== 'passed')) process.exitCode = 1;
})().catch(error => { console.error(error); process.exitCode = 1; });
