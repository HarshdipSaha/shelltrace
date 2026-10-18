# ShellTrace

**An investigation agent that answers: *can we deal with this entity, under this law, as of this date?***

ShellTrace traces ownership and control through a FalkorDB graph and returns a cited, dated, jurisdiction-aware sanctions-exposure verdict. Built from 15 October 2026 for the WeMakeDevs × FalkorDB **Graph Hacks: Context for AI Agents** hackathon (Track 01, Agents That Act on Connected Data).

> Investigative evidence under stated rule-pack interpretations — not legal advice.

| | |
| --- | --- |
| **Live app** | https://frontend-five-opal-42.vercel.app |
| **Live API** | https://shelltrace-api-796979480738.us-central1.run.app/api/health |
| **Specification and plan** | [`docs/pre-event/`](docs/pre-event/) |
| **Test report** | [`docs/testing/2026-10-16-exploratory-e2e-report.md`](docs/testing/2026-10-16-exploratory-e2e-report.md) |
| **Deployment runbook** | [`docs/deployment.md`](docs/deployment.md) |
| **Recording script** | [`docs/demo-script.md`](docs/demo-script.md) |
| **Real-data evaluation** | [`docs/real-data-evaluation.md`](docs/real-data-evaluation.md) |

## Why it exists

Name screening asks whether a company's own name is on a list. The law asks something harder, and the two answers diverge in exactly the cases that matter:

- **Ownership blocks unnamed companies.** Under OFAC's 50 Percent Rule an entity owned 50% or more, in aggregate, by blocked persons is blocked even if it appears on no list. The rule chains through intermediaries.
- **The answer depends on the regime.** OFAC aggregates stakes; the EU aggregates and adds control presumptions; the UK needs *more than* 50% and does not aggregate across designated persons. One company can be blocked for a US desk and clear for a UK desk on the same day.
- **The answer depends on the date.** Stakes move and designations are added and lifted.
- **The data is incomplete.** Missing percentages must surface as uncertainty, not as a guess.

## How it works

1. **Open a case.** Choose an entity, an as-of date, a hop bound and one or more rule packs (OFAC, EU, UK).
2. **The agent investigates through MCP.** It selects from ShellTrace's own read-only MCP tools (entity search, dated exposure trace, ownership stakes, rule-pack evaluation, alias candidates, red flags, evidence lookup, case history). Every call is logged in a hash-chained timeline. Without a model key a fixed, deterministic playbook runs the same tools through the same client, so every result is reproducible.
3. **The graph does the reasoning.** Dated path search, a rule-pack fix-point computed as graph queries, ownership *intervals* (lower and upper bounds), alias clusters over accepted links only, counterfactual re-evaluation, and impact traversal when a new designation lands.
4. **Code decides, not the model.** A deterministic authoriser maps graph results to one disposition: `EXPOSED`, `ESCALATE` or `CLEAR_WITHIN_BOUNDS`, each stated with its date, hop bound, scope, rule pack and data snapshot. Any model output is shown as a labelled *proposal* and can never authorise a disposition.
5. **Everything is cited.** Reports are generated from validated evidence, and every claim links to a record in the evidence locker.

### What you can do in the UI

Search by name, LEI or IMO · run side-by-side OFAC / EU / UK verdicts with ownership interval meters · scrub the investigation date and watch a verdict flip across a listing boundary · inspect the evidence graph and click any edge into the locker · accept or reject alias candidates with a recorded reason · record human reviews · draft a cited report · watch a case and see which past clearances a new designation overturns · view the evaluation page (`#/eval`).

## Architecture

```
React + Vite UI  ──/api,/mcp──▶  FastAPI + MCP server  ──▶  FalkorDB (property graph)
                                     │
                                     ├─ deterministic playbook / optional Groq agent
                                     ├─ rule packs, authoriser, report writer
                                     └─ optional TypeSafe JEV alias advisor
```

- `backend/shelltrace` — API, MCP tools, graph store, rule packs, agent runner, seed data
- `backend/eval` — golden cases (24 checks), ablations
- `frontend` — React UI and Playwright suites
- `docs` — specification, plan, verified platform facts, provider and test reports

## Run it locally

Requirements: Python 3.12, Node 20+, Docker.

```bash
docker compose up -d                      # FalkorDB on :6379
python -m pip install -e "./backend[dev]"
cp .env.example backend/.env              # optional; defaults run the deterministic playbook
cd backend && python -m shelltrace        # API on :8000, seeds the synthetic graph on first start
cd ../frontend && npm install && npm run dev   # UI on http://127.0.0.1:5173
```

`ST_API_TARGET` and `ST_UI_PORT` override the proxy target and UI port, which is how you run a second isolated stack.

## Tests

```bash
cd backend && python -m pytest -q          # backend suite (needs FalkorDB)
cd backend && python -m eval.run_golden --gate   # deterministic golden gate
cd frontend && npm run e2e                 # browser suites (walkthrough, task19, exploratory)
```

The exploratory suite drives the full golden table through the real UI and adds hostile search input, API failure modes, mobile layouts, keyboard-only use and API contract probes. See the [test report](docs/testing/2026-10-16-exploratory-e2e-report.md) for results and open findings.

## Deployment

The UI is on Vercel; `frontend/vercel.json` rewrites `/api/*` and `/mcp/*` to the API on Google Cloud Run, which talks to FalkorDB on a private VM. Details, redeploy and teardown commands are in [`docs/deployment.md`](docs/deployment.md).

## Optional live providers

The default live agent is Groq `openai/gpt-oss-120b`. Copy `.env.example` to `backend/.env`, add credentials and set `LLM_PROVIDER=groq`. `GROQ_API_KEYS` is a JSON array; `GROQ_API_KEY` is also accepted and deduplicated. Case starts rotate through the pool; each model invocation makes at most two HTTP attempts, each bounded to eight seconds. All physical attempts share the case model-call budget (ten by default); exhausting it triggers deterministic fallback, as do rate limits, connection failures, malformed responses and refusals. `LLM_PROVIDER=none` runs without a model. Explicit legacy Anthropic configuration remains supported but is unnecessary for Groq.

Set `JEV_ENABLED=true` and `TYPESAFE_API_KEY` (or `JEV_API_KEY`) to enable optional TypeSafe Jev identity recommendations. `JEV_MODEL` defaults to `jev-latest`, and the returned model identity is included in the result. `POST /api/aliases/judge?workspace=demo` accepts only `{"a_id":"existing-id", "b_id":"existing-id"}` for an existing pending candidate. It fetches stored identity fields, blocks conflicting identifiers before any network call, and never modifies candidates, accepted aliases, clusters or case dispositions. Jev answers a typed choice (`same_entity`, `different_entity`, `uncertain`), exposes its confidence, and abstains below 0.8 confidence. Calls are bounded to five seconds and failures return `uncertain`. Missing workspaces and non-pending pairs return 404. Analyst acceptance is a separate endpoint.

`GET /api/health` reports the configured agent and alias-judge models without credentials. Reports keep the deterministic, citation-verified template writer; neither model computes ownership arithmetic or authorises a disposition.

Provider contracts: [Groq chat API](https://console.groq.com/docs/api-reference), [Groq local tools](https://console.groq.com/docs/tool-use/local-tool-calling), [TypeSafe API schema](https://api.typesafe.ai/openapi.json). Validation results: [`docs/provider-validation.md`](docs/provider-validation.md).

## Platform facts

FalkorDB behaviour the build depends on (pinned image, read-only query enforcement, fulltext DDL, graph copy, MCP SDK version) is verified and recorded in [`docs/verified-facts.md`](docs/verified-facts.md). Re-run with `python scripts/verify_falkordb.py`.

## Data scope and disclosure

The public demo uses disclosed synthetic data. A separate local OpenSanctions/
GLEIF slice and its source-date limitations are documented in the
[real-data evaluation runbook](docs/real-data-evaluation.md). GLEIF accounting
consolidation is excluded from legal ownership totals. Small real-data strata
are reported as counts; they don't establish general accuracy.

AI coding assistance was used during development. The pre-event research and
plan live under `docs/pre-event/`; the earlier project is
[HarshdipSaha/graphrag](https://github.com/HarshdipSaha/graphrag).

## License

Code is Apache-2.0 ([`LICENSE`](LICENSE)). The bundled synthetic dataset is CC0-1.0.
