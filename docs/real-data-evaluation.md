# Corrected real-data evaluation and local runbook

The original Task 21 report was a structural candidate count. Its blocked and
name-screen counters weren't measured. Schema version 2 replaces those
counters with calls to production `evaluate`, ownership `trace`, and
`screen_name`. Earlier recordings/reports remain historical artifacts.

## What changed

- Hide every designation of the subject's accepted alias cluster for the
  authority being evaluated. Hide the cluster from name screening as well.
- Prefer source listing dates. Report observation-date approximations in
  separate strata; exclude approximate designation seeds from source-date
  predictions and their name baselines.
- Deduplicate positives by accepted cluster and authority. Check relationship
  intervals and the ancestor's delisting date. A cycle cannot supply the
  subject's own designation as an ancestor label.
- Call actual prediction tools. Prediction failures are unknown/incomplete,
  with errors and evaluated denominators, rather than silently scored as zero.
- Page fact tables in batches of 1,000. FalkorDB's 10,000-row result cap caused
  unpaginated reads of this dataset to omit companies and designations.
- Reject evaluation graphs containing OpenSanctions ownership/control facts.
- Keep accounting-consolidation amounts out of statutory ownership totals.
  GLEIF consolidation remains graph context and can produce a path flag.
- Keep each GLEIF amount, method and unit in the same slot. GEM's omitted
  imputation flag now means uncertainty, rather than observed shareholding.
- Count actually loaded GLEIF edges, with missing endpoints reported. This
  build is the exact-LEI intersection with loaded corporate sanctions records;
  it doesn't enrich the missing GLEIF endpoint metadata through the remote API.

## Actual local run on 18 October 2026

Pinned OpenSanctions `20261015074704-lqt` and GLEIF RR `20261015-0800`, FalkorDB
6.0.2. The corrected graph is `st_facts_real_os_20261015_corrected` on port 6384.
It contains 32,169 companies/vessels, 3 programs, 15,713 designations, and **51
loaded GLEIF relationships**. Another 4,256 parsed relationships lacked a loaded
endpoint and were skipped. Person node count: 0. GEM wasn't loaded; its export
returned HTTP 404 during the source research on 15 October.

| Authority | Date basis | Name stratum | n | Graph flagged | Graph blocked | Name screen |
| --- | --- | --- | --- | --- | --- | --- |
| OFAC | first_seen approximation | brand visible | 2 | 2 | 0 | 1 |
| OFAC | first_seen approximation | neutral | 3 | 3 | 0 | 0 |
| UK | source listing date | neutral | 2 | 2 | 0 | 0 |

All other strata have zero eligible positives. There were zero prediction
errors in this run. These samples are too small for headline percentages.
Flagged paths are investigative leads, not proven legal ownership. The bounded
flagged-but-undesignated audit sample isn't a precision estimate.

## Reproduce the reports

Use the downloaded pinned inputs described in
[the source check](pre-event/research/2026-10-15-real-data-source-check.md).
Downloaded/derived bulk files stay ignored. From `backend/`:

```powershell
$env:FALKORDB_PORT='6384'
$env:LLM_PROVIDER='none'
python -m shelltrace.loaders.build_real --os ../data/raw/os_company_vessel_slice.ftm.jsonl --gleif ../data/raw/rr.csv --snapshot os-20261015074704-lqt+gleif-20261015 --graph st_facts_real_os_20261015_corrected
python -m eval.real_e3 --graph st_facts_real_os_20261015_corrected
```

Outputs: `backend/eval/out/real_e3.json`, `real_e3.md`, and the appended E3
section in `golden_report.md`. Repeated E3 writes replace that section. Run
the golden suite before E3 when regenerating both reports.

To serve the corrected graph locally from `backend/`:

```powershell
$env:FALKORDB_PORT='6384'
$env:ST_TEMPLATE='st_facts_real_os_20261015_corrected'
$env:ST_WORKSPACE='real_demo_1018'
$env:ST_SNAPSHOT='os-20261015074704-lqt+gleif-20261015'
$env:PORT='8012'
$env:ST_MCP_URL='http://127.0.0.1:8012/mcp/'
$env:LLM_PROVIDER='none'
$env:JEV_ENABLED='false'
python -m shelltrace
```

Build the frontend first (`npm --prefix frontend run build` from repo root).
Open `http://127.0.0.1:8012/?ws=real_demo_1018`. The real-template startup now
validates imported facts without calling the synthetic seeder. Keep this
service separate from the synthetic recording API.

OpenSanctions-derived data is CC BY-NC 4.0; GLEIF is CC0. These results don't
establish historical listing dates, calibrated accuracy, or general sanctions
evasion recall. Full GLEIF component enrichment, a verified GEM export and the
Task 22 scale benchmark remain outside these measured results.
