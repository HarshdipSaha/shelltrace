# R6: Competition, agent architecture, and demo/UX craft

_Researched on 2026-10-05 with web search and fetches of primary pages wherever they loaded. **UNVERIFIED** marks a claim that rests only on a secondary source, or whose primary page could not be fetched. Domain papers are in [R0](R0-arxiv-domain-scan.md)._

## Key findings that change the spec

1. **The brief now scores agents, MCP and actions.** The live event is "Graph Hacks: Context for AI Agents" (Oct 15–18, 2026, $20K). It is not the "Building Next-Gen RAG / Investigation & Risk" brief that `rules.txt` and `README.md` still quote. Track 1, "Agents That Act on Connected Data", lists *multi-hop reasoning, graph queries and algorithms as agent tools, **tool selection through MCP**, actions based on what the graph shows, explainable results* ([event page](https://www.wemakedevs.org/hackathons/falkordb), [schedule](https://www.wemakedevs.org/hackathons/falkordb/schedule)). Two consequences follow:
   - The in-app agent should select tools *through an MCP client* talking to ShellTrace's own MCP server. Function calls hidden behind FastAPI would miss the judged criterion.
   - The rules say "main coding and design work must begin after the hackathon starts" and require disclosure of AI assistance ([rules](https://www.wemakedevs.org/hackathons/falkordb/rules)). The `2026-10-01` baseline commit needs an organizer ruling, or a clearly tagged prior-work boundary. Spec 05 already flags this; treat it as a P0 risk.
2. **A shortest path is not the legal test, and multiplying stakes along a path is wrong under OFAC.** OFAC's own example: X owns 50% of A and A owns 50% of B, so B is blocked, because A becomes blocked and A's stake then counts in full ([OFAC FAQ topic 1521](https://ofac.treasury.gov/faqs/topic/1521); example text via [sanctions.org mirror](https://sanctions.org/turbofac/research/OFAC-FAQ-398-402-Preface)). Path products (50%×50% = 25%) are the KYC/UBO calculation. Neo4j-style UBO demos and `bods-neo4j` use them ([bods-neo4j](https://github.com/StephenAbbott/bods-neo4j)), and several 2026 explainer blogs get this wrong ([Sanction Scanner example](https://www.sanctionscanner.com/blog/ofacs-50-percent-rule-how-indirect-ownership-triggers-sanctions-1363)). ShellTrace needs a deterministic **fix-point "blocked-by-ownership" computation as of the selected date**, in addition to its path trace.
3. **Jurisdiction must be a parameter, so rule packs belong in code.** The OFAC–OFSI joint comparative guidance (June 23, 2026) sets out the differences ([DLA Piper summary](https://www.dlapiper.com/en-us/insights/publications/2026/07/ofac-and-ofsi-publish-joint-comparative-guidance-on-us-and-uk-sanctions)):
   - OFAC: "50% or more", *aggregated* across blocked persons.
   - UK: "more than 50%", *no* aggregation across different designated persons, plus a freestanding *control* test.
   - EU Best Practices: aggregation applies to asset-freeze ownership ([Skadden](https://www.skadden.com/insights/publications/2024/09/eu-updates-sanctions-best-practices)).

   "Same graph, different law, different answer" is a strong demo beat, and only the graph plus deterministic rules can produce it.
4. **The BIS Affiliates Rule gives the demo a timely hook, with a caveat.** The BIS 50% Affiliates Rule was suspended until Nov 9, 2026 and snaps back on Nov 10, 2026 unless extended ([Blank Rome](https://www.blankrome.com/publications/bis-suspends-affiliates-rule-one-year-effective-november-10)). On Sept 23, 2026 Treasury announced a two-month extension of the truce to Jan 10, 2027. As of Oct 2 no Federal Register notice had appeared ([NatLawReview, 2026-10-02](https://natlawreview.com/article/bis-affiliates-rule-suspension-extended-uncertainty-remains)). Say "suspended, scheduled to return" and never give a single certain date.
5. **OpenSanctions `sanction.control` has no percentage threshold.** The topic (Aug 13, 2026) covers subsidiaries "anywhere in a sanctioned party's ownership chain". It applies "no percentage threshold, because reliable ownership figures are rare", and end-dated holdings break chains ([article](https://www.opensanctions.org/articles/2026-08-13-sanction-control/), [topics doc](https://www.opensanctions.org/docs/topics/)). The label therefore matches ShellTrace's *control-path* output, not a 50%-rule verdict. Evaluate the two outputs separately. Scoring a 50%-rule verdict against `sanction.control` would count every correctly cleared minority stake as a false negative.
6. **Missing percentages need interval arithmetic, not guessing.** Real ownership edges usually lack a percentage. Compute aggregated blocked ownership as an interval [lo, hi]:
   - lo ≥ threshold → rule met.
   - hi < threshold → rule not met.
   - Straddling the threshold → `ESCALATE_TO_HUMAN`, naming the edges whose missing stakes decide the outcome.

   This gives the agent a real job: deciding which missing evidence to seek. It also extends the spec's honest abstention to a third state.
7. **Under MCP 2026-07-28, case IDs must travel as tool arguments.** The protocol is stateless: no `initialize`, no `Mcp-Session-Id`. Elicitation moves to Multi Round-Trip Requests (`resultType: "input_required"`), Tasks becomes an extension, and **Sampling is deprecated** ([changelog](https://modelcontextprotocol.io/specification/2026-07-28/changelog)). So:
   - `case_id` should be an explicit server-minted handle passed as a tool argument.
   - Analyst approval should be an MRTR elicitation.
   - The LLM must never be reached through MCP sampling.
8. **Citations and structured outputs can't share one Claude call.** Combining them returns a 400 ([Citations docs](https://platform.claude.com/docs/en/build-with-claude/citations)). Use two kinds of call:
   - Decision calls: strict tools or JSON output.
   - Report call: graph evidence returned as `search_result` blocks with citations enabled ([Search results docs](https://platform.claude.com/docs/en/build-with-claude/search-results)).

   Forced `tool_choice` returns a 400 on Claude Opus 5.5 and Fable 5.1, so the harness must use `auto` + `strict: true` (Anthropic skill reference, cached 2026-06-24).
9. **The closest commercial analogue is already shipping, so openness and published evals are the edge.** Sayari Pilot "plans and executes its own research path … until sufficiency is met or human escalation is triggered" and claims "deterministic, verifiable, source-linked" outputs ([Pilot](https://sayari.com/platform/pilot/)). ShellTrace cannot win on data scale. It can win on being open, reproducible, cited and *measured*: Castellum's September 2026 market map found that no vendor except itself publishes consistency tests ([market map](https://www.castellum.ai/agentic-screening-market-map)).
10. **Cite the 2026 OWASP LLM Top 10, not the 2025 list.** The August 2026 edition moves Excessive Agency to third and renames System Prompt Leakage to Hidden Context Exposure (§3). The threat model and README should cite it, plus the Agentic Top 10.

---

## 1. Competitive landscape

| Product | Ownership/control exposure | 50%-rule aggregation | Explainability | Openness / price |
|---|---|---|---|---|
| **Sayari Graph / Signal / Pilot** | Multi-hop ownership traversal; claims "3.4× deeper ownership traversal"; <4h list lag ([sanctions page](https://sayari.com/risk/sanctions/)) | Yes, automated across multi-hop structures (same page) | Source-linked records; Pilot agent with escalation; "Superconductor evaluates every Pilot response" ([Pilot](https://sayari.com/platform/pilot/)) | Closed. Reported £18,963 per named user per year from UK procurement (**UNVERIFIED**, secondary: [Zavia](https://zavia.ai/top-sayari-alternatives-in-2026-best-platforms-for-ubo-discovery-kyb-risk-intelligence/)) |
| **Kharon 50-Plus** | Analyst-researched dataset of "sanctioned-by-law" entities; >30% are 3+ degrees from the parent ([50-Plus](https://www.kharon.com/data/50-plus)) | Yes ("directly, indirectly, or in the aggregate") | Research-sourced, delivered as list/API, not a live computation | Closed, enterprise; no public price |
| **Moody's Orbis + Grid → Sanctions360 (Maxsight)** | Orbis ownership percentages and "power scores" across layers | Yes, applies 50% rules for US/EU/UK ([help centre](https://help.maxsight.com/en/sanctions360-data-sources)) | Platform audit trails, case management | Closed |
| **LSEG World-Check** | Lists of sanctioned entities and subsidiaries (50%+); Sanctioned Securities Data File, Jan 2026 ([AML Intelligence](https://www.amlintelligence.com/2026/01/news-lseg-risk-intelligence-launches-sanctioned-securities-data-file/)) | Precomputed subsidiaries, not user-computable | Profile citations | Closed |
| **Dow Jones SCO** | Covers companies where a sanctions target owns ≥10%, flagging 50%+ ([CCI](https://www.corporatecomplianceinsights.com/dow-jones-integrates-sanctions-ownership-research-data-with-swift-sanctions-screening-service/)) | Precomputed list | Research notes | Closed |
| **Castellum.AI (Arbiter)** | Agentic alert adjudication inside LexisNexis Bridger; owns its own data ([FinTech Global, 2026-09-10](https://fintech.global/2026/09/10/castellum-ai-brings-ai-inside-aml-screening/)) | Not ownership-graph-centred (**UNVERIFIED**) | Audit trail per adjudication. Standalone-LLM benchmark: ~45% self-agreement on repeat runs (**UNVERIFIED**; [A-Team](https://a-teaminsight.com/blog/castellum-ais-financial-crime-benchmark-finds-accuracy-consistency-gaps-in-standalone-llms/?brand=ati) summary, primary returned 403) | Closed |
| **ComplyAdvantage** | Screening, "agentic automation" claims | "Ownership data supporting the 50% rule" (**UNVERIFIED**, secondary) | Explainable-AI governance claims | Closed |
| **sanctions.io** | Name screening API, 75+ lists ([site](https://www.sanctions.io/)) | Not mentioned | Match scores | From $899/yr (secondary) |
| **Quantexa** | Entity resolution + network generation around sanctioned entities ([blog](https://www.quantexa.com/blog/enhancing-compliance-and-building-safe-foundations-for-export-lead-growth/)); "agent ready" with Agent Gateway + **MCP server** (Nov 4, 2025, [press](https://www.quantexa.com/press/quantexa-makes-its-decision-intelligence-platform-agent-ready/)) | Not documented publicly | Strong ER explainability | Closed enterprise |
| **Linkurious Enterprise 4.3** (Sept 22, 2026) | Graph investigation UI on Neo4j/Neptune; Copilot beta; Query AI generates *editable Cypher* ([release](https://linkurious.com/blog/linkurious-enterprise-4-3/)) | No | Query inspection | Closed |
| **Neo4j UBO use case** | 16M-node Companies House demo; `OWNS*` traversal ([page](https://neo4j.com/developer/industry-use-cases/finserv/retail-banking/company-ownership-ubo-graphs/)) | No percentage aggregation, thresholds or temporal logic on the page | Cypher | Open sample |
| **TigerGraph / Memgraph / Neptune** | Generic AML/fraud samples ([TigerGraph AML](https://www.tigergraph.com/solutions/anti-money-laundering-aml/), [Memgraph insurance-fraud](https://github.com/memgraph/insurance-fraud), [Neptune samples](https://github.com/aws-samples/amazon-neptune-samples)) | No | Varies | Open samples |
| **OpenSanctions (yente, nomenklatura)** | `sanction.control` vs `sanction.linked`; end dates terminate chains | **No threshold, by design** | Statement-level provenance ([nomenklatura](https://github.com/opensanctions/nomenklatura)) | Open data, CC BY-NC 4.0; commercial use requires a licence ([licensing](https://www.opensanctions.org/licensing/)) |
| **OCCRP Aleph Pro** (Dec 2025) | Rebuild with automated risk scoring and confidence-labelled connections for knowledge-graph generation ([FAQ](https://www.occrp.org/en/announcement/aleph-pro-frequently-asked-questions-on-the-future-of-occrps-investigative-data-platform)) | No | Document-centric | OCCRP stopped contributing to open source; OpenAleph continues under DARC; free for nonprofits |
| **ICIJ Datashare** | Documents → Neo4j entity graph plugin ([ICIJ](https://www.icij.org/inside-icij/2024/02/datashares-new-plug-in-helps-investigative-journalists-connect-the-dots-with-graphs/)); 2025 redesign | No | Document hits | Open source |
| **Open Ownership (BODS 0.4)** | Standard captures changes over time; [visualisation library](https://github.com/openownership/visualisation-tool) | No (KYC thresholds only) | Statement provenance | Open |

**The gap ShellTrace can credibly own.** Every vendor that computes the 50% rule is closed and costs five figures per seat. Each one is a black box you cannot reproduce. The open ecosystem has the data and standards: OpenSanctions, BODS, FtM. It explicitly declines to apply thresholds, and its graph demos multiply stakes or ignore time. Nobody open offers all of the following together:

- Jurisdiction-parameterised aggregation (OFAC/EU/UK/BIS) computed in the graph at an as-of date
- Interval-honest abstention when stakes are missing
- Per-hop citations to source record and snapshot
- A bounded agent whose every choice is logged
- A published, reproducible evaluation against name-only screening, including pass^k consistency

That combination is the pitch. The positioning line: "the open, auditable reference implementation of ownership-based sanctions exposure". Keep the spec's out-of-scope guard: this is investigative evidence, not a legal determination.

## 2. Open-source prior art (GitHub)

| Repo | What it does | What it lacks |
|---|---|---|
| [ankur-saran/knowledge_graph](https://github.com/ankur-saran/knowledge_graph) ("UBO-Sentinel") | Claims OFAC 50% by **fix-point aggregation**, cited memo, deterministic, OpenSanctions + GLEIF | "Under construction", step 0 of plan, 0 stars. No temporal logic, ER, UI or eval documented. **Closest conceptual competitor; watch it.** |
| [CasaisA/sanctions-rag](https://github.com/CasaisA/sanctions-rag) | Hybrid BM25/vector/name retrieval, 1-hop graph expansion. Claude Agent SDK variant with read-only tools (`search_entities`, `get_entity`, `get_neighbours`, `find_path`) and citation verification. 300-query eval gated in CI | No 50% rule, no temporal validity, machine-generated labels. A good model for CI-gated evals. |
| [rishitkam/graphite](https://github.com/rishitkam/graphite) | TigerGraph fraud investigator: "agent proposes; a deterministic policy engine decides", case memory as graph vertices. RAG vs GraphRAG vs agentic GraphRAG (44% → 75.6%) with risk-matched held-out split | Fraud rather than sanctions. Its ablation is the template ShellTrace should copy. |
| [StephenAbbott/bods-neo4j](https://github.com/StephenAbbott/bods-neo4j) | BODS 0.4 ↔ Neo4j; multiplicative effective stake (25% default); cycle detection | No sanctions, no point-in-time queries |
| [C-Research/followthemoney-neomodel](https://github.com/C-Research/followthemoney-neomodel/) (Jul 2026, [C4ADS](https://c4ads.org/tech-bulletin/bringing-follow-the-money-into-the-graph-a-new-neo4j-tool/)) | FtM → Neo4j Python classes | Flattens statement provenance; no analytics |
| [apifyforge/sanctions-network-analysis](https://github.com/apifyforge/sanctions-network-analysis) | Weighted "Evasion Probability Score" over 8 sources | No graph DB, no 50% rule; opaque weights |
| [pisethTang/sanctions-graph](https://github.com/pisethTang/sanctions-graph) | Shared-attribute risk graph for applicants | Adjacency only |
| [FalkorDB/FalkorDB-MCPServer](https://github.com/FalkorDB/FalkorDB-MCPServer) | `query_graph`, `query_graph_readonly` (`GRAPH.RO_QUERY`), schema tools, API-key auth on HTTP | Generic arbitrary Cypher. Too broad for a model-facing allowlist (OWASP excessive agency and output handling), so wrap it or replace it with a narrow ShellTrace server. |
| [howdycarter/graph-hacks-falkordb-2026](https://github.com/howdycarter/graph-hacks-falkordb-2026) | Same-event entry, Track 2 (memory), scaffolding only | Not a direct competitor |

The pattern: open projects have *either* aggregation *or* temporal edges *or* an agent *or* an eval, and none has all four on one graph.

## 3. Agent architecture best practices (2025–2026) and a concrete design for ShellTrace

### What the sources agree on

- **Use the simplest pattern that works; reserve agents for unpredictable paths.** Workflows follow "predefined code paths", while agents "dynamically direct their own processes". Use poka-yoke tool parameters ([Building effective agents, Dec 19, 2024](https://www.anthropic.com/engineering/building-effective-agents)).
- **Design tools for the agent, not as API wrappers.** The guidance ([Writing effective tools for agents, Sept 11, 2025](https://www.anthropic.com/engineering/writing-tools-for-agents)):
  - Consolidate operations into fewer tools and namespace them.
  - Return human-readable names alongside IDs.
  - Offer a `response_format: concise|detailed` option.
  - Paginate and truncate with guidance, and return actionable errors.
  - Evaluate tools on realistic tasks.
- **Keep context small and retrieve just in time.** Use a minimal tool set with no overlap ("If a human engineer can't definitively say which tool should be used … an AI agent can't be expected to do better"). Pass lightweight identifiers and load data just in time; use structured notes and compaction ([Effective context engineering, Sept 29, 2025](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)).
- **Evaluate the outcome, not the agent's claim about it.** Grade the final state, combine code, model and human graders, read transcripts, and report pass@k against pass^k for consistency ([Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents); Jan 2026 date and details via secondary summaries, **UNVERIFIED**: primary fetch failed).
- **Have the MCP server declare its tools honestly; clients still must not trust the hints.** Declare an `outputSchema` and return `structuredContent` plus a text mirror. Report business errors as `isError: true` with self-correctable messages. Servers MUST validate inputs, rate-limit and sanitise outputs. Annotations are untrusted unless the server is trusted ([tools spec 2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28/server/tools)). `readOnlyHint`/`idempotentHint`/`openWorldHint` default to the unsafe values, so set them explicitly ([schema 2025-06-18](https://modelcontextprotocol.io/specification/2025-06-18/schema)). [MCP Apps](https://modelcontextprotocol.io/seps/1865-mcp-apps-interactive-user-interfaces-for-mcp) (`ui://`, Final) can render an interactive view inside MCP hosts.
- **Make long-running work durable and resumable.** LangGraph checkpoints at every super-step, and `interrupt()` pauses until resumed. Resume *re-runs the node*, so side effects must be idempotent ([interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts), [durable execution](https://docs.langchain.com/oss/python/langgraph/durable-execution)). ShellTrace doesn't need LangGraph, but should copy its semantics: persisted state per transition and idempotent nodes.
- **Run guardrails on tool calls as well as on input and output.** The OpenAI Agents SDK has input, output *and tool* guardrails with tripwires that halt a run ([guardrails](https://openai.github.io/openai-agents-python/guardrails/)).
- **Map the security work to the OWASP lists, and cite the 2026 edition.** The 2025 LLM list has been superseded.
  - The **2026 OWASP Top 10 for LLM Applications** (Aug 2026) keeps Prompt Injection first and moves **Excessive Agency to third** ([Help Net Security, 2026-08-06](https://www.helpnetsecurity.com/2026/08/06/owasp-2026-llm-top-10-released/); [OWASP announcement](https://genai.owasp.org/2026/09/01/owasp-genai-security-project-unveils-2026-top-10-for-llm-applications-new-agent-control-standard-and-sponsors-as-community-tops-30000-members/)). Misinformation and Unbounded Consumption rose. System Prompt Leakage became "Hidden Context Exposure", and Output Handling dropped to tenth. Middle-rank order differs between secondary sources (**UNVERIFIED**), so cite entries by name, not number.
  - The OWASP GenAI project also adopted an **Agent Control Standard** for runtime enforcement of what agents "can access, decide and do".
  - The [OWASP Top 10 for Agentic Applications 2026](https://genai.owasp.org/2025/12/09/owasp-top-10-for-agentic-applications-the-benchmark-for-agentic-security-in-the-age-of-autonomous-ai/) (Dec 9, 2025) lists, among others, ASI01 goal hijack through content the agent reads, ASI02 tool misuse, ASI06 memory and context poisoning, ASI08 cascading failures and ASI09 human-agent trust exploitation.
- **Keep a full decision record.** "A disposition code and timestamp alone are not sufficient." A complete record holds "input data, sources consulted, policies applied, actions taken, final disposition and confidence score" ([Castellum market map](https://www.castellum.ai/agentic-screening-market-map)).

### Recommended architecture: "the LLM proposes, the graph and the rules dispose"

**The state machine is deterministic. LLM calls happen only at marked decision nodes.**

```
INTAKE(entity, as_of, max_hops, rulepack) ─► RESOLVE ─► RECALL ─► EXPLORE ⟲ ─► EVALUATE ─► PROPOSE ─► DRAFT ─► REVIEW ─► WATCH
                                   ▲ LLM: which alias      ▲ LLM: next tool / stop        code: rulepack    LLM: cited     human:
                                     candidates to examine    (bounded loop)              fix-point,        narrative      approve/override
                                                                                          path validator
```

Each transition writes a `Decision` node holding:

- input digest, tool name, arguments, result digest and evidence IDs
- model ID and prompt version, choice probability
- policy and rulepack versions, graph snapshot ID
- latency and fallback reason
- `prev_hash`, which hash-chains the audit trail

On model failure, a node runs its deterministic fallback: the fixed sequence `trace → aliases → stakes`, then `ESCALATE_TO_HUMAN`.

**What the agent decides.** These are judgment calls deterministic code cannot make well:

1. **Ambiguous alias triage.** Code produces blocked candidate pairs and features: name similarity, transliteration, shared address/LEI/date of birth, conflicting dates. The agent picks which few to examine under budget and proposes accept/hold/reject with a rationale. Code materialises `SAME_AS` only above threshold or after analyst approval (already in spec 05).
2. **Exploration under budget.** When the trace is empty or the 50% interval straddles the threshold, the agent chooses among:
   - pulling stakes on the decisive edges
   - checking aliases of intermediate nodes
   - widening hops by one
   - stopping

   Code computes the decisive-edge set from the interval arithmetic, so the agent's choice is informed but not arithmetic.
3. **Sufficiency.** The agent decides whether to seek corroboration. Typical triggers are conflicting validity dates, a single-source hop, or a stake reported differently by two sources. Code enforces the *minimum* bar for EXPOSED.
4. **Documents → candidate edges.** The agent extracts candidate ownership edges with quoted spans from supplied press releases or registry text, using Claude citations. Candidates live in a separate `CANDIDATE_OWNS` layer that the traversal never reads; an analyst must accept them. This is the R0 poisoning defence.
5. **Portfolio triage after a change event.** Code computes the impacted watched cases by reverse traversal from the changed node. The agent ranks and summarises "what changed and why it matters" for the analyst queue.
6. **The cited narrative.** The agent drafts the report; a verifier checks every claim (below).

**What code decides.** Never delegated:

- temporal validity of every edge
- path validity
- the 50% fix-point and intervals per rule pack
- the EXPOSED/CLEAR/ESCALATE authorisation table
- all writes, with `MERGE` on deterministic IDs
- `SAME_AS` materialisation
- budgets and access control
- whether a report sentence survives verification

**Tool contracts.** Exposed via a narrow ShellTrace MCP server (Streamable HTTP + stdio) and consumed by the in-app agent *through an MCP client*:

| Tool | Purpose | Key bounded params |
|---|---|---|
| `entity_search` | name/ID → entities with human-readable labels | `query`, `limit≤20` |
| `exposure_trace` | dated, bounded control-path search | `entity_id`, `as_of`, `max_hops 1..6`, `rel_types enum[]` |
| `ownership_stakes` | stakes into an entity with validity and source | `entity_id`, `as_of` |
| `rulepack_evaluate` | fix-point aggregation → `{lo, hi, verdict, decisive_edges}` | `entity_id`, `as_of`, `rulepack enum[OFAC, EU, UK, BIS]` |
| `alias_candidates` | blocked candidate pairs and features | `entity_id`, `limit≤10` |
| `neighborhood_expand` | context, never exposure | `entity_id`, `depth≤2`, `limit≤50`, `response_format` |
| `evidence_get` | source record, snapshot, licence, URL | `evidence_ids[]≤20` |
| `case_history` | earlier cases sharing entity, alias or address | `case_id` |

Every tool follows the same conventions:

- **Inputs:** JSON Schema with `additionalProperties:false`, enums and integer bounds. On Claude, `strict: true`.
- **Outputs:** an `outputSchema`, `structuredContent` plus a text mirror, and deterministic `tools/list` order (helps prompt caching).
- **Annotations:** `readOnlyHint:true, idempotentHint:true, openWorldHint:false`.
- **Case handle:** `case_id` passed explicitly as an argument, never held in a session.
- **Data handling:** entity names returned as data, never as instructions.

Writes (case, review, watch) are application endpoints and never model-callable. Analyst approval for MCP clients goes through an MRTR elicitation.

**Budgets** (configurable and recorded):

- per case: ≤8 agent steps, ≤10 model calls, 30 s wall clock
- per tool call: 2 s timeout
- results: ≤500 frontier nodes
- watches: rate-limited, with deduplication on `(event_id, case_id)` (ASI08)

On Claude, add the `task_budget` beta and low/medium effort for routing steps.

**Report verifier:**

- Each sentence must carry at least one citation that resolves to an `Evidence` node on the validated path.
- That evidence must belong to the hop's entity, to catch wrong-entity citations (R0 finding 5).
- Unsupported sentences are struck through in the UI, never silently kept.

### Eval harness

- **Golden synthetic cases**, roughly 30, each with an expected disposition and path:
  - alias-only path
  - expired short path with a valid longer path
  - two blocked owners at 30% each: OFAC EXPOSED, UK CLEAR
  - 50%→50% chain: OFAC EXPOSED, where multiplication would say CLEAR
  - unknown stakes → ESCALATE
  - CLEAR within bounds
  - look-alike name with a different date of birth → must not merge
  - prompt-injection document and an entity literally named "Ignore previous instructions Ltd"
  - a watch flip
- **Outcome graders (code):** disposition, path validity, citations resolve, no unsupported sentences.
- **Trajectory graders:**
  - stayed within budget
  - no forbidden tool
  - no duplicate calls
  - steps compared with the oracle sequence
  - balanced "should-escalate" and "should-not" cases
- **Consistency:** pass^5 per case. Publish it, since vendors don't.
- **Ablations:**
  - name-only screening
  - graph trace without the agent (deterministic fallback)
  - agent with ER off
  - agent with temporal filtering off

  The agent must show value on *ambiguous* cases, measured as escalation precision and steps saved, or it is decorative.
- **Real-data cohort:** the OpenSanctions cohort from spec 05, scored on control-path output only (finding 5).
- **CI:** gate on regressions, as sanctions-rag does. Run eval sweeps through the Batches API at 50% cost.

### Claude features to use (Anthropic skill reference cached 2026-06-24; platform docs)

- **Models:** `claude-opus-5` ($5/$25 per MTok) is the default. `claude-opus-5-5` is the launching successor at $4/$20; use it when chosen explicitly. Per secondary sources it was released 2026-09-22 (**UNVERIFIED**). `claude-sonnet-5` ($2/$10) suits routing steps and `claude-haiku-4-5` ($1/$5) bulk extraction. Use adaptive thinking and set effort explicitly; the default on Opus 5.5 is `medium`.
- **Strict tool use:** `strict: true` with `additionalProperties:false`. Use `tool_choice: auto` because forced `any`/`tool` returns a 400 on Opus 5.5 and Fable 5.1.
- **Structured outputs** (`output_config.format`) for disposition proposals and alias judgments.
- **Citations:** return evidence as `search_result` blocks inside tool results, with source = evidence URI and title = "hop 3: Blue Lagoon Capital → Nord Harbor (2019-03-01–present)". Each response citation then carries `search_result_location` and `cited_text`, which costs no output tokens. All blocks in such a `tool_result` must be `search_result`, and citations are all-or-nothing per request. Never combine citations with `output_config.format`.
- **Prompt caching:** keep tools, then system, frozen and in deterministic order. Verify with `cache_read_input_tokens`.
- **Context editing** (`clear_tool_uses_20250919`) for long cases. Memory stays in FalkorDB, not the memory tool, because case memory is graph data.
- **MCP connector** (`mcp-client-2025-11-20`) is optional. Running the loop in your own backend keeps the policy layer in code.
- **Refusals:** handle `stop_reason: "refusal"`; fallbacks are available.
- **Token efficiency:** token-efficient tool use is built into Claude 4+ ([docs](https://platform.claude.com/docs/en/agents-and-tools/tool-use/token-efficient-tool-use)).

Spec 05 uses TypeSafe Jev for typed Choice/Noul judgments ([docs](https://docs.typesafe.ai/introduction)). The decision-node contract can stay model-agnostic: `{choice ∈ enum, probability, rationale, evidence_ids[]}`. Claude's distinctive value is document → candidate-edge extraction and the cited report.

## 4. Demo and UX craft

**Analyst UX patterns.** AML case tools assemble investigation timelines and filing-ready narratives "citing which task produced each fact". QA flags dispositions that don't match the evidence ([Unit21](https://www.unit21.ai/blog/agentic-ai-for-aml-compliance-a-practitioners-guide)). Translate that into one screen:

- **Header:** entity, as-of date, hop bound, rule pack, plus *two* badges, "Agent proposal" and "Validated disposition". The split guards against ASI09 trust exploitation.
- **Left, case timeline:** every Decision with tool, arguments, probability, latency and evidence chips. Fallbacks are shown in amber.
- **Centre, graph:**
  - ownership flows top-down with [cytoscape-dagre](https://github.com/cytoscape/cytoscape.js-dagre) or [cytoscape-elk](https://github.com/cytoscape/cytoscape.js-elk), with the validated path animated hop by hop
  - `SAME_AS` clusters as **compound nodes** with [expand-collapse](https://github.com/iVis-at-Bilkent/cytoscape.js-expand-collapse), so aliases are visible but don't clutter
  - expired edges dashed grey; candidate edges dotted and labelled "unverified"
  - edge labels showing stake % (or "?") and the validity interval
  - progressive disclosure: path first, neighbourhood on click
- **Bottom, as-of "time travel" slider:** a histogram of edge start and end events, in the spirit of the KeyLines time bar ([Cambridge Intelligence](https://cambridge-intelligence.com/visualizing-dynamic-networks/)). Dragging the slider re-runs the trace.
- **Right, evidence locker:** for each hop, the source record, snapshot ID, licence and `cited_text`.
- **Right, rule-pack panel:** the [lo, hi] bar against the threshold for OFAC, EU, UK and BIS side by side.
- **Review:**
  - disposition codes: `EXPOSED_CONFIRMED`, `CLEAR_WITHIN_BOUNDS`, `FALSE_POSITIVE_ALIAS`, `ESCALATED_INSUFFICIENT_EVIDENCE`, `OVERRIDDEN`
  - a mandatory reason on every disposition
  - **four-eyes:** a second reviewer for any override that removes an exposure
- **Watch:** a toggle, plus a diff view of old and new paths when a recheck fires.

**3-minute video structure.** Devpost judges say the video is the "first indicator", storytelling "can be a huge part of your success", and "ambiguity is a red flag" ([judging tips](https://info.devpost.com/blog/hackathon-judging-tips), [video tips](https://info.devpost.com/blog/6-tips-for-making-a-hackathon-demo-video)).

| Time | Beat |
|---|---|
| 0:00–0:10 | **Hook.** A clean-looking company passes name screening, is 50%+ owned by a sanctioned person through four shells and an alias, and the BIS Affiliates Rule is scheduled to return. |
| 0:10–0:30 | Name-only screen says CLEAR (live). |
| 0:30–1:30 | Agent run with the timeline beside the graph. It holds one look-alike alias, accepts one, traces the path, and the rule pack fills the interval bar. Then flip OFAC → UK and the verdict changes ("same graph, different law"). |
| 1:30–1:55 | Time slider 2020 → 2024: the path changes, and the expired edge is excluded. |
| 1:55–2:20 | Live designation event: the watched case flips CLEAR → EXPOSED, with a diff and a notification. |
| 2:20–2:40 | **Failure modes, shown honestly:** a poisoned press release stays a *candidate*, the LLM-off run still returns a validated result, and a CLEAR states its bounds. |
| 2:40–3:00 | Eval table (name-only vs graph vs agent, pass^5), the Cypher on screen, links. |

Record from a live deployment, keep the cursor visible, and avoid cuts during the proof so judges can see it is real.

**README pattern:**

- First screen: one-line pitch, an animated GIF of the path and flip, and links to the live demo and the video.
- Badges: CI, eval pass^k, licence, FalkorDB version.
- Required by the rules: track named, setup, **graph data model**, **the Cypher and algorithms the product depends on**, and AI-assistance disclosure.
- Prior-work and timeline disclosure.
- One command to run: `docker compose up && make seed && make demo`.
- A Mermaid architecture diagram.
- A "What the agent decides vs what code decides" table.
- An eval table with denominators.
- A limitations and legal disclaimer.
- A data-licence table: OpenSanctions CC BY-NC 4.0, GLEIF CC0, synthetic people.
