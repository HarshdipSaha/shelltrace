# Submission readiness checks, 18 October 2026

This pass corrected the real-data evaluation and prepared a reproducible local
recording take. It doesn't claim completion of missing external datasets,
full GLEIF enrichment or the scale benchmark.

## Fixes verified

- E3 now calls production rule evaluation, trace and name screening. Subject
  alias-cluster labels are hidden. Positive counts are deduplicated. Official
  and approximate dates are separated. Prediction errors are incomplete
  measurements. OpenSanctions ownership/control input is rejected.
- E3 reads fact tables in pages below FalkorDB's 10,000-row result cap.
- GLEIF amount/unit/method values stay in their original slots. Missing GEM
  imputation flags retain uncertainty. Actually loaded edge counts are exposed.
- Accounting-consolidation amounts are excluded from legal ownership totals.
- Imported real templates are validated without synthetic seeding.
- Designation propagation skips unrelated workspace graphs with no such entity.
- The UI shows the actual snapshot, designation date basis and consolidation
  basis. E3 shows date strata and incomplete measurements. Agent provider labels
  identify Groq rather than hardcoding Claude.
- Derived evaluation outputs and provider credentials remain ignored.

## Evidence

The complete backend run on an isolated FalkorDB 6.0.2 container returned
**354 passed, 2 skipped**, with one dependency deprecation warning. The
deterministic golden command returned **24/24**. Ablations remained 7/24
(name-only), 14/24 (path-only), 15/24 (multiplicative), 23/24 (ER off), and
21/24 (time off).

The production frontend build passed, retaining the existing bundle-size
warning. The final combined browser suite returned **18 passed** across
source-disclosure regressions, Task 19 and walkthrough flows.

Five recorded browser investigations against the corrected local real API
passed. They cover National Clearing Centre at two dates, GTLK Europe Capital,
ABRAU by IMO and National Settlement Depository on mobile. All 35 observed API
responses returned 200; there were zero uncaught page errors. Generated videos,
screenshots, traces and the summary are local under
`backend/eval/out/real-browser-1018/`.

A separate live Groq investigation of the synthetic hero case returned an
EXPOSED proposal and validated EXPOSED in **9,030 ms**, with 15 timeline steps
and no fallback. This single run is a rehearsal, not a repeatability estimate.

The corrected real-data run produced 7 eligible positives, zero prediction
errors, 7 graph flags, 0 ownership-blocking predictions and 1 name-screen hit.
Five positives use approximate observation dates; two UK positives use source
listing dates. Counts, scope and source limitations are in
[the evaluation runbook](../real-data-evaluation.md).

## Record and submit

[The 180-second script](../demo-script.md) contains exact narration, clicks,
prepared tabs, a fresh-take launcher, and a Playbook alternative if a live model
call fails. It labels the synthetic and authentic local-data segments.

You still need to record your voice and screen, upload the finished demo to
YouTube as public/unlisted, and paste that URL into the submission form.
Publishing a blog and sending the submission weren't performed by this pass.
