# Recorded real-data browser tests — 16 October 2026

Five of five recorded Chromium runs passed using the deployed frontend at
https://frontend-five-opal-42.vercel.app. Start time: 05:37 UTC.

## Exact setup

The public API still reports `st_facts_synthetic` (67 nodes). These recordings
are **deployed-frontend / local-real-API integration tests**, not tests of real
data hosted on Cloud Run. Playwright forwards actual `/api/*` requests to
`http://127.0.0.1:8012` using `route.fetch`; no canned responses or synthetic
case fixtures are supplied. Browser videos include an explicit setup banner.

The local API used FalkorDB 6.0.2 on port 6384, template
`st_facts_real_os_20261015_slice`, snapshot
`os-20261015074704-lqt+gleif-20261015`, and the deterministic playbook.
The template contains 32,172 nodes. A direct graph check returned zero Person
nodes before testing. A graph copy, `st_ws_realbrowser_1016`, holds the recorded
cases. Its ready marker was set before API startup to prevent synthetic seeding.
No designation events or alias decisions were injected.

## Results

| Run | Subject and date | Observed disposition | OFAC / EU / UK | Duration |
| --- | --- | --- | --- | --- |
| 01 | National Clearing Centre, 2026-10-15 | EXPOSED | BLOCKED / BLOCKED / BLOCKED | 13.884 s |
| 02 | National Clearing Centre, 2010-01-01 | CLEAR_WITHIN_BOUNDS | NOT_BLOCKED / NOT_BLOCKED / NOT_BLOCKED | 7.663 s |
| 03 | GTLK Europe Capital, 2026-10-15 | EXPOSED | BLOCKED / NOT_BLOCKED / NOT_BLOCKED | 7.024 s |
| 04 | ABRAU, IMO 9422964, 2026-10-15 | CLEAR_WITHIN_BOUNDS | NOT_BLOCKED / NOT_BLOCKED / NOT_BLOCKED | 7.711 s |
| 05 | National Settlement Depository, mobile 390×844, 2026-10-15 | EXPOSED | BLOCKED / BLOCKED / BLOCKED | 7.032 s |

Each run performed real identifier search, entity selection, date entry,
investigation, name screening, and report drafting. Checks verify the displayed
disposition and pack verdicts agree with the actual case API response, evidence
sources do not identify synthetic data, and every generated claim has a citation.
Runs 01/03/05 generated 6/3/3 cited claims respectively. Runs 02/04 generated zero
claims; their citation checks are consequently vacuous. All 35 observed API
responses were 200, all five browser error lists were empty, and the mobile
document had zero horizontal overflow.

These are observed application results, not independently adjudicated legal
ground truth or recall estimates. Directly listed entities can be exposed from
their own designations; these tests do not establish hidden-owner recovery.
The historical CLEAR result reflects date-filtered source coverage; it does
not establish that the counterparty was historically safe. OFAC `first_seen`
fallbacks remain ingestion-date approximations. GLEIF accounting consolidation
does not establish legal shareholding. GEM remains absent from this graph.

## Finding

The deployed UI footer hardcodes “Synthetic investigation workspace” while
the browser supplies authentic data. The recording banner and this report
identify the actual source. A data-source-aware footer remains follow-up work.
The UI also does not prominently distinguish `first_seen` from official listing
dates. The tests do not certify those disclosure gaps as resolved.

## Recordings and replay

All five attempts are preserved under [real-data-runs/2026-10-16](real-data-runs/2026-10-16).
Each folder includes `run.webm`, `final.png`, and `trace.zip`; there were no failed
attempts or discarded reruns. [summary.json](real-data-runs/2026-10-16/summary.json)
contains request statuses, results, timings, and SHA-256 hashes for every artifact.

Run from the repository root with installed frontend dependencies:

```powershell
node scripts/real-data-browser.cjs
# Inspect any recorded run:
cd frontend
npx playwright show-trace ../docs/testing/real-data-runs/2026-10-16/01-clearing-current/trace.zip
```

The real API and prepared workspace are prerequisites; the script refuses a
synthetic template in its initial health check. `REAL_SITE_URL`, `REAL_API_URL`,
`REAL_WORKSPACE`, and `REAL_RUN_DIR` configure another run. Use a fresh output
directory to preserve earlier recordings. Visible Chromium is the default;
`HEADLESS=1` supports environments without a display.

## Source attribution and artifact licence

Recordings contain small derived excerpts from the authentic pinned sources
documented in [the source research](../pre-event/research/2026-10-15-real-data-source-check.md).
OpenSanctions snapshot `20261015074704-lqt` is licensed CC BY-NC 4.0;
GLEIF RR golden copy `20261015-0800` is CC0. Derived OpenSanctions content in
these artifacts remains subject to CC BY-NC 4.0 and is not relicensed by the
repository's Apache-2.0 code licence. Artifacts are shared for noncommercial
testing with source fields visible in the application. Bulk source files stay
in ignored `data/raw/`.
