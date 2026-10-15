# Groq and JEV validation — 15 October 2026

The approved amendment uses Groq for optional investigation actions/proposals and TypeSafe JEV for advisory alias comparisons. No Anthropic credential was copied or used. Only synthetic data was sent to the providers. Credentials remain in ignored `backend/.env`; they are not required by CI.

## Automated checks

- Backend: **331 passed**, with a fresh FalkorDB 6.0.2 instance on port 6381 and `ST_REQUIRE_DB=1`. Command from `backend`: `python -m pytest -q --ignore=tests/live`.
- Provider regression coverage includes malformed/refused/truncated output, unknown/parallel tool calls, invalid confidence, connection failures, bounded key rotation, a shared physical-request budget, exact candidate lookup, missing workspaces, identifier and cluster conflicts, and read-only recommendations.
- Live JEV API integration: **1 passed**. Opt in using `ST_LIVE_PROVIDERS=1` and run `python -m pytest tests/live/test_providers_live.py -q`. It compares candidate/alias/cluster snapshots before and after live recommendations and confirms the same validated disposition and rule-pack semantics afterward.
- Frontend production build passed; the existing bundle-size warning remains.
- Browser walkthrough: **7 passed serially**. The default Playwright configuration now uses one worker and a 15-second assertion timeout for the shared demo workspace and sequential MCP round trips.

## Live diagnostics

Run from the repository root:

```powershell
python scripts/check_live_providers.py --repeats 5
python scripts/check_live_aliases.py --repeats 5
```

Raw local JSON and logs are under ignored `eval/out/`. They contain synthetic results and model identities, not credentials. These diagnostics are opt-in and spend provider tokens.

All five configured Groq credentials authenticated and completed a real request against `openai/gpt-oss-120b`. The repeated investigation diagnostic covers 11 scenarios: the hero ownership chain, US/UK threshold differences, missing stakes, a clear case, red flags, pending/upstream aliases, injected names, historical exposure, and expired exposure. It compares validated dispositions and proof edges against the deterministic playbook and verifies persisted step hash chains. Model proposals and tool activity are reported separately from deterministic correctness.

The five-repeat diagnostic completed **55/55 matching validated dispositions and proof sets, with 55/55 valid hash chains**. Of those runs, **52 made model tool calls** and **42 received model proposals**. Median case latency was **11.64 seconds**. Recorded fallback events comprised 34 unavailable-model events, two tool timeouts and one tool error; these event counts can include multiple events per case. This is a deterministic correctness result under live-model variability, not a 100% agent-completion claim.

After the physical-request-budget fix, a two-case live smoke check matched both deterministic outcomes and verified both hash chains. The hero completed five model tool steps and a proposal using nine physical HTTP requests. The second case encountered a provider failure during exploration, completed deterministically, and still received a proposal; it used four requests. Both stayed under the ten-request cap.

The JEV diagnostic ran **40 checks: 30 live model responses and 10 deterministic identifier-conflict checks**. It matched expected choices in **35/40**. All five other results were abstentions on a positive synthetic matching-LEI example below the 0.8 confidence threshold. There were no unexpected substantive identity recommendations. Reversing pair order was included. A later eight-check smoke run again had no unexpected substantive recommendations. These small synthetic sets do not establish calibration or improved entity-resolution accuracy.

## Limits and unresolved behavior

- Groq returned HTTP 429 responses during repeated runs. Bounded key rotation and deterministic completion kept validation independent of provider availability. A correct final disposition is not evidence that every model call succeeded.
- The 55-case repeated run began before the physical-request cap was added. The subsequent live smoke and request-budget regression tests cover that final change.
- Six-worker browser execution reproduced the earlier concurrency problem: **3 passed, 4 timed out**. Serial operation passes. Parallel case latency/event-loop contention remains unresolved; changing the test worker default is not a product concurrency fix.
- Full backend suites against the pre-existing shared database failed event propagation when unrelated partial workspaces lacked the designated entity. A fresh isolated database passed. That existing assumption is outside this provider amendment.
- JEV is exposed through the read-only alias-judge API. It does not automatically merge candidates, change dispositions, or replace the deterministic report writer. The unfinished Task 19 UI work remains on its separate branch.
