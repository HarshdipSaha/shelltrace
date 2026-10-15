# ShellTrace v2

ShellTrace v2 is the event-day build for Graph Hacks, developed in this repository from 15 October 2026 onward. The pre-event research, specification, and implementation plan are preserved under [`docs/pre-event/`](docs/pre-event/).

Investigative evidence under stated rule-pack interpretations — not legal advice.

Task 0's FalkorDB verification is recorded in [`docs/verified-facts.md`](docs/verified-facts.md).


## Optional live providers

The default live agent is Groq `openai/gpt-oss-120b`. Copy `.env.example` to `backend/.env`, add your credentials, and set `LLM_PROVIDER=groq`. `GROQ_API_KEYS` is a JSON array; `GROQ_API_KEY` is also accepted and deduplicated. Case starts rotate through the pool; each model invocation makes at most two HTTP attempts, each bounded to eight seconds. All physical HTTP attempts, including retries and the proposal, share the case model-call budget (ten by default); exhausting it triggers deterministic fallback. Rate limits, connection failures, malformed responses and refusals fall back to the deterministic playbook. `LLM_PROVIDER=none` runs without a model. Explicit legacy Anthropic configuration remains supported, but is unnecessary for Groq.

Set `JEV_ENABLED=true` and `TYPESAFE_API_KEY` (or `JEV_API_KEY`) to enable optional TypeSafe Jev identity recommendations. `JEV_MODEL` defaults to `jev-latest`; the returned model identity is included in the result. `POST /api/aliases/judge?workspace=demo` accepts only `{"a_id":"existing-id", "b_id":"existing-id"}` for an existing pending candidate. It fetches stored identity fields, blocks conflicting identifiers before a network call, and never modifies candidates, accepted aliases, clusters, or case dispositions. Jev uses a typed Choice question (`same_entity`, `different_entity`, `uncertain`), exposes its confidence/distribution, and abstains below 0.8 confidence or selected probability. Calls are bounded to five seconds and failures return `uncertain`. Missing workspaces and nonpending pairs return 404. Analyst acceptance remains a separate endpoint.

`GET /api/health` reports configured agent and alias-judge models without credentials. Reports retain the deterministic citation-verified template writer. Neither model computes ownership arithmetic or authorizes a case disposition.

Provider contracts: [Groq chat API](https://console.groq.com/docs/api-reference), [Groq local tools](https://console.groq.com/docs/tool-use/local-tool-calling), and [TypeSafe official API schema](https://api.typesafe.ai/openapi.json).
