# Exploratory browser test report — 16 October 2026

Scope: the full UI driven by Playwright against the real FastAPI + FalkorDB stack (isolated FalkorDB on :6390, API on :8010, Vite on :5180, `LLM_PROVIDER=none`, synthetic-v1 data). Suite: `frontend/e2e/exploratory.spec.js` (108 tests). The existing `walkthrough` and `task19` specs were run alongside it.

## Result

| Run | Passed | Failed | Notes |
| --- | --- | --- | --- |
| First pass (108 new tests) | 90 | 18 | Failures triaged below |
| Full suite, all three specs, after fixes | 123 | 2 | The 123 include 2 intentional expected-failures (F-3). The 2 failures: the alias test (my fixed workspace name kept state from the previous run; switched to a fresh workspace per run and re-verified passing on its own) and the existing `task19` spec (F-7). A final full rerun after that last tweak was not done |

## Coverage

- **Golden table through the UI (24 cases):** every disposition and per-pack verdict in `backend/eval/golden.py` (G1–G18 incl. temporal, delisting, 49% restructuring, circular, control-only, mass address, conflicting sources, prompt-injection name, vessel) matches in the browser. 24/24 pass.
- **Search robustness:** LEI, IMO, case, padding, accents, punctuation variants; hostile input (script tags, Cypher/SQL metacharacters, emoji, Cyrillic, CJK, 10 kB string, control characters, path traversal). No XSS, no crash, the page stays usable afterwards.
- **Case controls:** no packs, no entity, hops 1/2/3/6, extreme dates (1900, 2099, leap day, listing boundary), cleared date, double-click Run (exactly one POST), stale responses while moving the date slider, determinism.
- **Analyst workflow:** cited report and citation→locker, name screen, human review (validation, history, HTML in reason rendered as text), watch + designation injection + notifications, alias accept/reject with reason, timeline evidence keys.
- **Failure modes:** API down at load then retry, HTTP 500, HTML 404 (the deployed-without-backend symptom), connection reset, malformed JSON, `{}` 200, slow backend, unknown/invalid/hostile workspace.
- **Layout and accessibility:** 375 px and 768 px have no horizontal scroll; keyboard-only flow; every control has an accessible name; no failed requests in a full run.
- **API contract probes:** 16 malformed/hostile `POST /api/cases` bodies never return 5xx, limit abuse, 8 parallel cases agree, wrong HTTP methods, no credentials in `/api/health`.

## Findings

### Fixed in this change

| ID | Severity | Finding | Fix |
| --- | --- | --- | --- |
| F-1 | High | A `200` response with malformed JSON or `{}` crashed the whole React tree (`Cannot read properties of undefined (reading 'name')`) and left a blank page. | `api.js` rejects non-JSON success bodies and validates the case shape (`requireCase`); the user sees a readable alert and the form stays usable. |
| F-2 | Medium | A non-JSON error body was echoed verbatim into the error banner. This is what produced `API 404: The page could not be found NOT_FOUND bom1::…` on Vercel when no backend sat behind `/api`. | Non-JSON errors now read `API 404: the ShellTrace API is not reachable at this address (the backend may not be running or deployed)`. |

### Open — not fixed here

| ID | Severity | Finding | Evidence / suggestion |
| --- | --- | --- | --- |
| F-3 | Low | Entity search is not typo tolerant: `nord harbour` (British spelling) and `nrod harbor` (transposition) return nothing. Case, accents and punctuation variants work. | Two tests are marked `test.fail` and will start reporting once search improves. Harbor/Harbour lookalikes must stay distinct (G9), so any fuzziness needs care. |
| F-4 | Medium | With max hops 1 or 2, the hero case (exposed at 6 hops) returns `CLEAR_WITHIN_BOUNDS` with `bounds.truncated=false`. The hop limit is shown, but an analyst lowering hops sees a clean verdict with no warning that the chain to the designated owner is out of reach. | Suggest flagging when `max_hops` cuts off the scope frontier (e.g. an "ownership continues beyond hop limit" warning). |
| F-5 | Low | `?ws=<name>` with a hyphen returns `422 invalid workspace` on search. The UI shows it, but the message does not say which characters are allowed. | Test `invalid workspace name (hyphen)…` pins current behaviour. Workspaces are created on the first case, so searching a new valid workspace is also empty until a case is run. |
| F-6 | Observation | Byte-identical case requests give identical dispositions, verdicts and tool sequences, but some tool-result digests differ run to run (4 of 13 steps on the Rostok case). | Probably volatile fields inside tool results. Worth confirming before claiming run-to-run reproducible proof hashes. Recorded as a `digest-drift` annotation. |
| F-7 | Unresolved | Existing `task19.spec.js › watch flip after a designation` expects `2 entities newly blocked · 1 watched case(s) changed` and gets `1 entities…`. | Not caused by the frontend changes here (it asserts a backend fan-out count) and not confirmed on a clean `main`. HANDOFF notes that leftover workspaces in a shared DB break designation fan-out tests, so check this on a fresh DB first. |
| F-8 | Cosmetic | Reports repeat the same claim sentence once per rule pack (12 claim sentences for Birch, 4 distinct citations). | Consider de-duplicating citations shared across packs. |

All report claims carry citations: every `claim` sentence cites evidence; `meta` sentences (headline, bounds, disclaimer) are uncited by design.

## Deployment

- Frontend: Vercel project `harsh-1b18/frontend`. `frontend/vercel.json` rewrites `/api/*` and `/mcp/*` to the backend below.
- Backend: Google Cloud project `shelltrace-demo-54136`. API on Cloud Run service `shelltrace-api` (us-central1, 1 instance always on, CPU not throttled). FalkorDB on VM `falkordb-vm`, which has no public IP; Cloud NAT gives it outbound access only, and the firewall allows 6379 only from the VPC. The FalkorDB password is in the Cloud Run env var `FALKORDB_PASSWORD`; it is not committed.
- The API is unauthenticated by design for the demo (synthetic CC0 data, `LLM_PROVIDER=none`, no provider keys configured). Mutating endpoints (review, watch, designation, alias decisions) are therefore publicly callable.

## Running the suite

```
# terminal 1 — isolated DB + API
docker run -d -p 127.0.0.1:6390:6379 falkordb/falkordb:6.0.2
cd backend && FALKORDB_PORT=6390 PORT=8010 ST_MCP_URL=http://127.0.0.1:8010/mcp/ python -m shelltrace
# terminal 2 — UI + tests
cd frontend && ST_API_TARGET=http://127.0.0.1:8010 ST_UI_PORT=5180 npx vite
ST_UI_PORT=5180 npx playwright test e2e/exploratory.spec.js --workers=1
```

Mutating tests use a fresh `?ws=` workspace per run, so reruns do not leak state.
