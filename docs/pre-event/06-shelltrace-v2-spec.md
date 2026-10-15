# ShellTrace v2: an agent that acts on ownership graphs (spec)

> **Status:** replaces `docs/05-shelltrace-agent-extension-spec.md`. Written 2026-10-05 from the research in `docs/research/R0–R6`.
> **Event:** WeMakeDevs × FalkorDB **"Graph Hacks: Context for AI Agents"**, 15 Oct 2026 12:01 AM IST to 18 Oct 2026 11:59 PM IST ([R1](research/R1-hackathon-intel.md)).
> **Tracks:**
> - **Track 01, "Agents That Act on Connected Data"** (primary).
> - **Track 02, "Agent Memory and Coordination"** (secondary). Enter it only if per-workspace case memory and the watch agent both ship.
> **Pre-event status:** this document is a pre-event note, which rule 8 allows. The implementation is new work, built during the event in a fresh repository (see Further Notes).

## Problem Statement

A sanctions or KYC analyst is asked one question about a counterparty: *"Can we deal with this company today?"* The usual tool answers a different question: *"Is this company's own name on a list?"* The two answers diverge in exactly the cases that matter.

- **Ownership law blocks companies whose names appear on no list.**
  - Under OFAC's 50 Percent Rule, an entity owned 50% or more, in aggregate, by one or more blocked persons is blocked, even if it is never named.
  - The rule chains. If X owns 50% of A and A owns 50% of B, then B is blocked. Multiplying along the chain gives 25% and the wrong answer, which several public explainers and open-source UBO tools get wrong ([R3](research/R3-sanctions-ownership-law.md), [R6](research/R6-competition-agents-ux.md)).
- **The answer depends on which law applies.**
  - OFAC counts "50% or more" and adds together stakes held by different blocked persons.
  - The EU also aggregates, and adds rebuttable *control* presumptions.
  - The UK requires "more than 50%", does **not** aggregate across different designated persons, and has its own control test.
  - The same company can be blocked for a US desk and clear for a UK desk on the same day.
- **The answer depends on the date.** Stakes are bought and sold. Designations are added and lifted. A stake reduced to 49% shortly before a listing is a red flag, not a clean bill of health ([R3](research/R3-sanctions-ownership-law.md)).
- **The data is incomplete.** Open ownership data usually has no percentages. GLEIF carries only accounting-consolidation figures for about 19% of its parent links, and almost no end dates ([R4](research/R4-open-data-and-eval.md)). A tool that guesses hides the uncertainty the analyst most needs to see.
- **Names deceive.** Subsidiaries of sanctioned groups often have neutral names: Sovcomflot's Liberian and Cypriot ship-owning companies, for example ([R4](research/R4-open-data-and-eval.md)). Corporate-family matchers recover at most 4.7% of links where names share no token ([R5](research/R5-academic-sota.md)). Aliases split one actor across records, and fuzzy merging can wrongly join two different actors.
- **Yesterday's CLEAR goes stale.** When a new designation lands, the analyst cannot easily find which past clearances it overturns.
- **Today's options are poor.** The vendors that compute these rules are closed and five-figures-per-seat, and none can be reproduced (Sayari, Kharon, Moody's, LSEG, Dow Jones). The open ecosystem declines to apply thresholds, multiplies stakes, or ignores time ([R6](research/R6-competition-agents-ux.md)). Analysts end up reconstructing chains by hand.

**For the hackathon,** the brief asks for "an agent that makes decisions you can trace", with FalkorDB as the context layer that shapes what the agent does. If the product still works with FalkorDB removed, it fails (rule 3).

## Solution

ShellTrace is an investigation agent that answers *"can we deal with this entity, under this law, as of this date?"* It works in a FalkorDB property graph of companies, vessels, ownership, control, designations and case history. It returns a cited, dated, jurisdiction-specific determination, then acts on it:

1. **It opens a case.** The analyst names an entity, an as-of date, a hop bound and one or more rule packs (OFAC, EU, UK). The default is all three side by side.
2. **The agent investigates through MCP.**
   - A bounded agent selects tools from ShellTrace's own read-only MCP server: entity search, dated exposure trace, ownership stakes, rule-pack evaluation, alias candidates, neighbourhood context, evidence lookup, case history. Every selection, argument, result digest and latency is written to the case timeline.
   - Without a model key, a fixed deterministic playbook runs the same tools through the same MCP client, so the product is fully reproducible.
3. **The graph does the reasoning.**
   - **Dated path search:** finds the shortest path that is valid on the as-of date.
   - **Rule-pack fix-point:** an iterative computation, run as aggregate graph queries, that decides which entities are blocked under each law.
   - **Ownership intervals:** each total is a lower and upper bound, so missing percentages show up as uncertainty.
   - **Alias clusters:** connected components over *accepted* alias links only.
   - **Counterfactual re-evaluation:** re-runs the rules with one hop removed, to show which records the verdict rests on.
   - **Impact traversal:** when a designation lands, follows ownership downstream to find what it newly blocks.
   - **Red-flag pattern queries.**
4. **Code decides, not the model.** A deterministic authoriser turns the graph results into one of three case dispositions:
   - **EXPOSED:** a rule pack's ownership test is met by validated, cited evidence.
   - **ESCALATE:** the uncertainty is human-decidable, such as an interval that straddles the threshold, a rebuttable control presumption, a pending alias, a red flag, conflicting sources, or an exhausted budget.
   - **CLEAR_WITHIN_BOUNDS:** stated with its date, hop bound, relationship scope, rule pack and data snapshot.

   The agent's proposal is shown next to the authorised disposition, and the model can never assert or erase an exposure.
5. **It shows its work.** The evidence graph animates the ownership proof. Each hop shows its stake (or "?"), its validity interval and its source record. The rule-pack panel shows each law's interval bar against its threshold. The counterfactual panel marks the records the verdict depends on. A time slider re-runs the case at another date. A name-only screening button shows what a list lookup alone would have said.
6. **It acts.**
   - The analyst approves or overrides with a reason and a disposition code. An override that removes an exposure needs a second reviewer.
   - The agent drafts a cited report, and every sentence is checked against the validated evidence.
   - The analyst can subscribe the case to a watch. A designation event triggers the impact traversal, re-runs only the affected watched cases, and posts a CLEAR→EXPOSED notification with an old-versus-new diff.
7. **It remembers.**
   - Cases, steps, reviews, accepted aliases and watches persist in FalkorDB, in a graph per workspace.
   - When a new case opens, the agent retrieves earlier cases that touch the same entity, alias cluster, owners or address, and shows those findings.
   - Agent notes never become evidence without analyst sign-off.
8. **It is measured.**
   - A golden suite of planted synthetic cases is graded on disposition, proof edges and citations.
   - Ablations compare name-only screening, path-only tracing, multiplicative "UBO" arithmetic, entity resolution off, time filtering off, and agent versus playbook.
   - Repeated agent runs report pass^5 consistency.
   - A real-data evaluation on GLEIF + OpenSanctions + Global Energy Ownership Tracker companies reports recall stratified by whether the subsidiary's name reveals its parent.

The demo runs on two graphs:
- **Synthetic graph:** disclosed, with synthetic people. It drives the guaranteed, deterministic demo and the tests.
- **Real company-and-vessel slice:** loaded by script from public sources, with **no natural persons**.

## User Stories

### Investigation
1. As an analyst, I want to start a case from an entity name, LEI, IMO number or ID, so that I can investigate whatever identifier I was given.
2. As an analyst, I want fuzzy search that shows country, type and identifiers, so that I pick the right entity among similar names.
3. As an analyst, I want to set an as-of date, so that ownership and designations are judged at the relevant time.
4. As an analyst, I want to set a hop bound from 1 to 6, so that the scope and cost of the search are explicit.
5. As an analyst, I want to choose one or more rule packs (OFAC, EU, UK), so that the answer matches the jurisdiction I work under.
6. As an analyst, I want OFAC, EU and UK results side by side by default, so that I can see where the regimes diverge.
7. As an analyst, I want the aggregated blocked-ownership share of the entity shown as a lower and upper bound, so that missing percentages stay visible.
8. As an analyst, I want a stake held by a blocked company to count in full toward its subsidiaries under OFAC, so that a 50%→50% chain is correctly blocked.
9. As an analyst, I want stakes of different designated persons summed under OFAC and the EU but not the UK, so that each law's aggregation rule is respected.
10. As an analyst, I want a rebuttable control presumption flagged separately from ownership under the EU and UK, so that I can rebut or confirm it.
11. As an analyst, I want expired stakes and lifted designations excluded on the as-of date, so that stale facts don't create exposure.
12. As an analyst, I want a valid longer path returned when a shorter one has expired, so that a case is not falsely cleared.
13. As an analyst, I want to see the ownership proof (the edges that pushed each entity over the threshold), so that I can check the derivation hop by hop.
14. As an analyst, I want each hop to show its stake, validity interval, source dataset, record ID, snapshot and licence, so that I can cite it.
15. As an analyst, I want the records the verdict depends on highlighted, so that I know which facts to verify first.
16. As an analyst, I want an ESCALATE result to list the unknown stakes that decide it, so that I know what evidence to request.
17. As an analyst, I want shared-officer, shared-address and alias proximity shown as context rather than counted as ownership, so that weak links don't masquerade as control.
18. As an analyst, I want red flags highlighted:
    - a stake cut below the threshold near a listing date
    - circular ownership
    - a mass-registration address
    - control that continues after the stake ended

    so that evasion typologies trigger escalation.
19. As an analyst, I want a CLEAR result to state its date, hop bound, relationship scope, rule pack and snapshot, so that it is never read as proof of no exposure.
20. As an analyst, I want a time slider that re-runs the case at another date, so that I can see when exposure began or ended.
21. As an analyst, I want a name-only screening comparison, so that I can show a reviewer why a list lookup was insufficient.
22. As an analyst, I want the graph laid out top-down by ownership, with alias clusters collapsible, so that long chains stay readable.

### Aliases
23. As an analyst, I want alias candidates generated from shared identifiers, normalised names and transliteration, so that one actor split across records is reunited.
24. As an analyst, I want candidate aliases kept out of the traversal until accepted, so that a weak match cannot create an exposure.
25. As an analyst, I want identifier conflicts (different LEI, IMO or registration number) to block a merge, so that look-alikes are never joined.
26. As an analyst, I want any merge that would join two existing clusters routed to me, so that chained matches cannot grow a giant cluster.
27. As an analyst, I want to accept or reject an alias with a reason, so that my judgement persists in the workspace.

### Agent and traceability
28. As an analyst, I want the agent to choose its next tool among approved graph tools, so that it follows evidence without my directing each step.
29. As an analyst, I want each step's tool, arguments, rationale, probability, latency and evidence chips on a timeline, so that I can audit the investigation.
30. As an analyst, I want the agent's proposed disposition shown separately from the validated disposition, so that I can tell suggestion from authority.
31. As an analyst, I want the agent to spend its budget on the decisive unknowns (ambiguous aliases, missing stakes, one more hop), so that the investigation stays efficient.
32. As an analyst, I want the investigation to finish with the deterministic playbook when the model is unavailable, so that a case never fails silently.
33. As an analyst, I want to replay a case's step trail, so that I can reproduce how the result was reached.

### Review and reporting
34. As an analyst, I want to approve or override a disposition with a reason and a disposition code, so that my review is part of the record.
35. As a supervisor, I want overrides that remove an exposure to need a second reviewer, so that one person cannot clear a blocked entity alone.
36. As an analyst, I want a draft report in which every sentence cites evidence on the validated path, so that I can hand off a defensible note.
37. As an analyst, I want unsupported report sentences struck through rather than silently kept, so that hallucinated claims are visible.
38. As an analyst, I want the report to cite only records belonging to the entity on that hop, so that alias confusion cannot slip in as a citation.
39. As an analyst, I want to export the case as Markdown and JSON, so that I can attach it to my organisation's case system.

### Memory and watches
40. As an analyst, I want earlier cases that touch the same entity, alias cluster, owners or address surfaced when I open a case, so that prior findings inform my review.
41. As an analyst, I want cases and reviews to persist across sessions and restarts, so that history stays inspectable.
42. As an analyst, I want to put a watch on a case, so that I'm notified when the graph changes in a way that affects it.
43. As an analyst, I want a designation event to re-run only the affected watched cases, so that rechecks are fast and targeted.
44. As an analyst, I want a CLEAR→EXPOSED notification with an old-versus-new diff, so that I understand what changed.
45. As an analyst, I want to see everything a new designation blocks (its blast radius), so that I can assess portfolio impact.
46. As an analyst, I want repeated events deduplicated, so that one change does not produce a flood of alerts.
47. As a team lead, I want each workspace's cases, accepted aliases and watches isolated, so that teams do not see or change each other's judgements.

### Operator and security
48. As an operator, I want every model-reachable query to be read-only, parameterised, bounded and timed out, so that no tool call can mutate or exhaust the graph.
49. As an operator, I want per-case budgets on steps, model calls and wall-clock time, so that one case cannot run away.
50. As an operator, I want entity names and document text treated as untrusted data, so that prompt injection in records cannot steer the agent.
51. As an operator, I want text extracted by the model from documents kept as candidate edges with quoted spans until accepted, so that poisoned text cannot create exposure.
52. As an operator, I want database credentials never to enter model context, so that a model cannot reach the database directly.
53. As an operator, I want health, graph size, query latency and model status on a status endpoint, so that I can run the service.

### Data and evaluation
54. As a data maintainer, I want every imported record to carry source dataset, record ID, snapshot version, licence and retrieval date, so that results can be reproduced and attributed.
55. As a data maintainer, I want imports to be idempotent, so that re-running a snapshot never duplicates entities or edges.
56. As a data maintainer, I want natural persons excluded from real-data imports, so that the graph holds no personal data.
57. As a data maintainer, I want designations modelled per authority with listing and delisting dates, so that each rule pack uses its own lists over time.
58. As an evaluator, I want a golden suite of planted cases with expected dispositions and proof edges per rule pack, so that correctness is checked automatically.
59. As an evaluator, I want ablations against name-only screening, path-only tracing, multiplicative arithmetic, entity resolution off and time filtering off, so that each component's contribution is measured.
60. As an evaluator, I want pass^5 consistency for agent mode, so that run-to-run variance is published.
61. As an evaluator, I want real-data recall stratified by whether the subsidiary's name reveals its parent, so that the gain over name screening is shown where it matters.
62. As an evaluator, I want label leakage documented and avoided (no OpenSanctions-derived ownership edges when scoring against `sanction.control`), so that the metric is not circular.

### Hackathon reviewer
63. As a judge, I want the README to map each Track 01 focus bullet to a feature, so that fit is obvious.
64. As a judge, I want the graph data model, the exact Cypher and the algorithms in the README, so that I can verify FalkorDB does the reasoning.
65. As a judge, I want a live deployment and a ≤3-minute video, so that I can see it work without setup.
66. As a judge, I want a one-command local setup that works without any model key, so that I can reproduce the demo.
67. As a judge, I want an AI-assistance and prior-work disclosure, so that eligibility is transparent.
68. As a judge, I want to connect ShellTrace's MCP server to my own MCP host, so that I can use its graph tools directly.

## Implementation Decisions

### Product shape
- A web app plus API plus MCP server over FalkorDB.
  - **Backend:** Python 3.12, FastAPI, the official `falkordb` client and the official `mcp` Python SDK.
  - **Frontend:** React and Vite with Cytoscape.js, using dagre layout and expand-collapse for alias clusters.
  - **Deployment:** one container serves the API, the MCP endpoint and the built UI. FalkorDB runs on Docker locally and on FalkorDB Cloud for the live deployment.
- The model layer is optional and replaceable.
  - **Default live model (approved 2026-10-15 amendment, #35):** Groq `openai/gpt-oss-120b` (configurable), behind the existing Brain contract with bounded retries and deterministic playbook fallback. Explicit legacy Claude configuration remains available.
  - **Without a key:** the deterministic playbook runs instead.
  - **TypeSafe Jev:** an optional read-only alias recommendation for existing pending pairs after deterministic identifier checks; it never merges records or changes a disposition. Typed Choice returns same_entity, different_entity or uncertain with confidence and probabilities. Jev is the model; Choice, Score and Noul are its primitives. Its documented weaknesses (dates, multi-hop, numbers, option order) keep it off every decision except alias pairs ([R1](research/R1-hackathon-intel.md)).

### Graph data model (FalkorDB)
- **Graphs:**
  - `st_facts_<snapshot>` is the template. It holds entities, facts and designations.
  - Each workspace graph `st_ws_<workspace>` holds a copy of the facts, cloned from the template, plus that workspace's case memory and accepted aliases.
  - New designation events apply to the template and fan out to every workspace graph.
  - This is FalkorDB multigraph tenancy.
- **Nodes:**
  - `Entity` with a subtype label: `Company`, `Vessel`, `Person` (synthetic graph only) or `Address`. Properties:
    - `id` (deterministic, source-prefixed)
    - `name`, `norm_name`, `country`
    - `lei`, `imo`, `reg_no` (each optional)
    - `src`, `src_record`, `snapshot`
  - `Program`: `id`, `authority` ∈ {OFAC, EU, UK, UN}, `name`.
  - `Source`: `id`, `dataset`, `version`, `licence`, `url`, `retrieved_on`.
  - Case memory:
    - `Case`: `id`, `entity_id`, `as_of`, `max_hops`, `rulepacks`, `status`, `proposal`, `disposition`, `opened_at`, `snapshot`.
    - `Step`: `seq`, `kind`, `tool`, `args_json`, `result_digest`, `evidence_keys`, `probability`, `rationale`, `latency_ms`, `actor` (model ID or `playbook`), `fallback_reason`, `prev_hash`, `hash`.
    - `Review`: `reviewer`, `code`, `reason`, `at`, `second_reviewer`.
    - `Watch`: `id`, `active`, `created_at`.
    - `Event`: `id`, `kind`, `payload_json`, `at`.
    - `Notification`: `case_id`, `old`, `new`, `diff_json`, `at`.
- **Fact relationships** (each carries `k`, a deterministic evidence key, plus `src`, `src_record`, `snapshot`, `valid_from`, `valid_to` as ISO `YYYY-MM-DD` strings, or null when open):
  - `OWNS {pct, pct_basis ∈ shareholding|accounting_consolidation|synthetic}`: owner → asset.
  - `CONTROLS {basis ∈ board_majority|voting_majority|nominee|accounting_consolidation|other}`: controller → controlled.
  - `OFFICER_OF {role}`: person → company, synthetic graph only.
  - `REGISTERED_AT`: entity → address.
  - `DESIGNATED {listed_on, delisted_on, reason}`: entity → Program.
  - `SAME_AS {score, method, accepted_by, accepted_at}`: accepted aliases only.
  - `CANDIDATE_SAME_AS {score, features_json, state ∈ pending|rejected}`: never traversed.
  - `CANDIDATE_OWNS {pct, quote, doc_id}`: extracted from documents, never traversed until an analyst accepts it.
- **Workflow relationships** are separate types and never appear in traversal type lists: `ABOUT`, `HAS_STEP`, `NEXT`, `REVIEWED`, `WATCHES`, `TRIGGERED`, `NOTIFIED`. Because workflow edges are never traversed, case history cannot create a sanctions path.
- **Indexes:**
  - range indexes on `Entity.id`, `Entity.norm_name`, `Entity.lei`, `Entity.imo`, `Case.id` and `Case.entity_id`
  - a full-text index on `Entity.name`
- **Imports** use `MERGE` on `id` (nodes) and on `k` (edges), so they are idempotent.

### Rule packs (data plus code)
- Each rule pack is a versioned record:
  - `authority_set`: which programs seed the blocked set
  - `threshold` = 50, with an `inclusive` flag
  - `aggregate_across_persons`
  - `control_limb`: whether `CONTROLS` creates a presumption
  - `basis_accepted`: which `pct_basis` values count as ownership
  - a `citations` list
- The three packs:
  - **OFAC:** inclusive ≥ 50; aggregates across blocked persons; no control limb. Sources: FAQs 398–402 and the 2014 guidance.
  - **EU:** inclusive ≥ 50 of proprietary rights; aggregates; control limb is a rebuttable presumption. Sources: Council Best Practices 2024 paras 63–67 and Commission FAQ 8.

    The OFAC-style chain arithmetic for the EU is an interpretation, and the UI says so.
  - **UK:** strict > 50; no aggregation across different designated persons; a stake held by an entity that the designated person owns passes in full to that person. `CONTROLS` relationships create a separate control presumption and never feed ownership arithmetic; the control limb is "reasonable to expect" control. Sources: OFSI General Guidance 4.1 (May 2026) and the June 2026 joint OFAC–OFSI comparison.
- **Fix-point evaluation**, per pack and as-of date:
  1. Seed the blocked set from `DESIGNATED` edges valid on the as-of date for the pack's authorities. Designations propagate through accepted `SAME_AS` clusters.
  2. Over the target's upstream ownership subgraph (≤ `max_hops`), repeatedly run one aggregate Cypher round. Each round sums valid `OWNS` stakes held by currently-blocked owners, grouped by owned entity, and returns the entities that newly cross the threshold.
  3. Stop when no new entity is added. The blocked set only grows, so cycles terminate. Rounds are bounded by the scope size (≤ 500 entities).
  4. **Duplicate records:** several records of the same (owner, asset) pair are one holding reported twice, not two holdings. The lower bound uses the smallest reported stake and the upper bound the largest. Disagreeing sources therefore surface as `INDETERMINATE` exactly when the disagreement decides the verdict.
  5. **UK:** run once per designated seed with that seed's own closure. Never sum across seeds.
  6. Record which edges pushed each entity over the threshold. That record is the ownership proof.
- **Interval arithmetic:**
  - **Lower bound:** sums known stakes from *definitely* blocked owners.
  - **Upper bound:** adds the residual (100 − all known stakes into that entity) whenever a *possibly* blocked owner holds an unknown stake.
  - **Verdict:** the target is `BLOCKED` when lower ≥ threshold, `NOT_BLOCKED` when upper < threshold, otherwise `INDETERMINATE`. Decisive unknown or conflicting stakes are limited to accepted `OWNS` dependencies on the target's reverse ownership slice: start at the target, follow possible blocked owners back up for at most `max_hops`, and include dependencies only from seed groups where the target is possible but not definite. Unrelated uncertain siblings and `CONTROLS` edges are excluded.
  - Possibly blocked owners are computed by the same fix-point using upper bounds.
  - Known stakes summing over 100 into one entity are flagged as a data error, and the raw values are kept.
- **Control limb (EU and UK only):** a valid `CONTROLS` edge from a blocked entity creates `PRESUMED_CONTROLLED`. The presumption propagates downward only, and never feeds ownership arithmetic.
- **Multiplied-down economic exposure** (the product of stakes along paths) is displayed as an informational metric with a "not the legal test" label. It never decides anything. Limit raw matching `OWNS` records to 5,000 (using one extra row only to detect overflow) and path-edge expansions to 20,000; if either budget is exceeded or the metric query fails, show it as unavailable with a generic caveat instead of displaying a partial total. Deduplicate canonical owner/asset holdings and take the maximum reported stake only after the bounded raw rows are returned.

### Other graph computations
- **Dated exposure trace:** a bounded variable-length match over `OWNS|CONTROLS|SAME_AS`, plus `OFFICER_OF|REGISTERED_AT` for *context mode only*. The validity predicate is applied inside `all(relationships(p))`, terminating on an entity with a valid designation. `shortestPath` and `allShortestPaths` are not used, because their post-filtering yields false CLEARs ([R2](research/R2-falkordb-platform.md)).
- **Alias clusters:**
  - `algo.WCC` over accepted `SAME_AS` only, written as `cluster_id`, with a size cap of 25.
  - An acceptance that would merge two clusters that each have more than one member always needs the analyst.
  - Candidates come from blocking keys: identical LEI/IMO/reg_no, identical normalised core name, identical transliterated phonetic key. Conflicting identifiers cause automatic rejection.
- **Counterfactual "decisive records":**
  - For each proof edge, re-run the pack evaluation with that edge's key excluded. Edges whose removal changes the verdict are flagged decisive.
  - Capped at 20 re-evaluations per case.
- **Impact traversal on a designation event:**
  - Merge the `DESIGNATED` edge into the template graph and every workspace graph.
  - Compute the downstream candidate set by traversing ownership and control *out* of the newly designated entity and its alias cluster (≤ 6 hops).
  - Re-evaluate the pack for each candidate to get the blast radius, meaning the entities newly blocked.
  - Re-run only those watched cases whose entity is in the candidate set. Deduplicate on (event ID, case ID).
- **Red-flag queries** (each returns evidence keys):
  - a designated owner's stake ending, or dropping below threshold, within 180 days before that owner's listing date
  - circular ownership in the upstream subgraph
  - an address with ≥ 20 registered entities
  - a valid `CONTROLS` or `OFFICER_OF` edge from a designated party into the upstream subgraph (`control_by_designated`). OFAC does not count control, but its guidance advises caution, so this escalates under every pack
- **Enablers** (stretch): `algo.betweenness` over the case's evidence subgraph to name intermediaries that sit on many proof paths.
- **Case recall:** earlier cases in the workspace whose `entity_id` is in the target's alias cluster, upstream owners, or co-registered entities. Retrieval is by graph overlap, not text similarity.

### Agent
- **Deterministic state machine:** INTAKE → RESOLVE → RECALL → EXPLORE (bounded loop) → EVALUATE → PROPOSE → AUTHORISE → DRAFT → (REVIEW, human) → WATCH.
- The model is called only in EXPLORE (choose the next tool or stop), in PROPOSE (disposition plus rationale), for alias triage, and in DRAFT (cited narrative).
- Every transition writes a `Step` linked by `NEXT`. Each step's `hash` covers the previous hash plus the step body, which makes the trail tamper-evident.
- **Tools** come from ShellTrace's own MCP server, with read-only, idempotent, closed-world annotations. Each tool has bounded inputs (enums, integer ranges) and structured output.

  | Tool | Inputs and bounds |
  |---|---|
  | `entity_search` | `query`, `limit` ≤ 20 |
  | `exposure_trace` | `entity_id`, `as_of`, `max_hops` 1–6, `mode` ∈ ownership \| context |
  | `ownership_stakes` | `entity_id`, `as_of` |
  | `rulepack_evaluate` | `entity_id`, `as_of`, `rulepack` ∈ OFAC \| EU \| UK, `max_hops`, optional `exclude_keys` (for counterfactuals, ≤ 20) |
  | `alias_candidates` | `entity_id`, `limit` ≤ 10 |
  | `red_flags` | `entity_id`, `as_of`, `max_hops` |
  | `neighborhood` | `entity_id`, `depth` ≤ 2, `limit` ≤ 50 |
  | `evidence_get` | `keys` ≤ 20 |
  | `case_history` | `workspace`, `entity_id` |

  `case_id` and `workspace` are always explicit arguments; there is no session state. The in-app agent connects to this server as an MCP client over streamable HTTP. External MCP hosts can connect to the same endpoint with an API key.
- **Writes are never model-callable.** Opening cases, writing steps, reviews, watches, alias acceptance and event ingestion are application endpoints only.
- **Budgets** (configurable and recorded on the case):
  - per case: 8 explore steps, 10 model calls, 45 s wall clock
  - per tool call: 2 s timeout
  - per result: at most 500 nodes

  When a budget is exhausted, the agent goes to EVALUATE with whatever evidence it has, and the authoriser escalates if a decisive unknown remains.
- **Model calls:**
  - Strict tool schemas with `tool_choice: auto`, because forced tool choice is rejected on newer models.
  - Structured JSON output for proposals and alias judgements.
  - A separate call, with citations enabled, for the report. Citations and structured output can't share a call.
  - The decision contract is `{choice, probability, rationale, evidence_keys}`. Probabilities are decision metadata, not calibrated claims.
- **Untrusted content:** entity names, record text and documents are passed only as tool-result data, never as instructions. The tool list is fixed per run. A tool result cannot add calls beyond the budget.
- **Authoriser** (code), in order of precedence:

  | Disposition | Condition |
  |---|---|
  | EXPOSED | any selected pack returns `BLOCKED` with every proof edge valid on the as-of date and every edge sourced |
  | ESCALATE | (a) any pack `INDETERMINATE` (which includes decisive conflicting sources) or `PRESUMED_CONTROLLED`; (b) a red flag on the upstream subgraph; (c) a pending alias candidate linking an upstream node to a designated party; (d) a truncated scope; (e) budget exhausted before every selected pack was evaluated |
  | CLEAR_WITHIN_BOUNDS | otherwise, with the bounds statement |

  If the agent proposed something else, the case shows "proposal overridden by policy".
- **Report verifier:**
  - Every sentence must cite at least one evidence key on the validated proof or trace.
  - The cited record's entity must be the node on that hop, or in its accepted alias cluster.
  - Sentences that fail are struck through and listed.

### API contracts (application)
- `POST /api/cases`: open and run a case.
  - Request: `{workspace, entity_id, as_of, max_hops, rulepacks[], mode: agent|playbook}`.
  - Response: the full case, with `disposition`, `proposal`, per-pack results (`verdict`, `lo`, `hi`, `threshold`, `proof`, `decisive`, `presumptions`), `trace`, `red_flags`, `aliases`, `prior_cases`, `steps[]`, `bounds` and `latency`.
- `GET /api/cases/{id}`, plus `POST /api/cases/{id}/review` (`{reviewer, code, reason}`).
- `POST /api/cases/{id}/report`: draft and verify.
- `POST /api/cases/{id}/watch`: toggle a watch.
- `POST /api/events/designation`: `{entity_id, authority, program, listed_on, source}`. Returns `{event_id, blast_radius[], rechecked[], notifications[]}`.
- `GET /api/notifications`, `GET /api/entities/search`, `POST /api/aliases/{pair}/decide`.
- `POST /api/screen/name`: the name-only baseline.
- `GET /api/health`.
- `GET /api/eval/latest`: the last evaluation report, for the UI's evaluation page.
- MCP endpoint at `/mcp`.
- The existing `investigate` request and response shapes are not kept. This is a new build.

### Data
- **Synthetic graph** (disclosed): about 60 hand-planted nodes covering every golden case. People are synthetic. It can be regenerated deterministically.
- **Scale graph** (synthetic): a seeded generator producing 20k nodes with planted typologies:
  - nominee layering
  - circular ownership
  - restructuring to 49%
  - alias spellings
  - expired stakes
  - vessel ownership hops

  Used for latency figures.
- **Real slice,** loaded by script. No natural persons are loaded; any person-to-company edge is dropped. Every record carries licence attribution.
  - **Seeds:** companies, organisations and vessels from the OpenSanctions `sanctions` collection, at a pinned version (CC BY-NC 4.0). This is non-commercial use in a personal capacity. The repo ships a loader script, not data.
  - **Parent chains:** GLEIF Level 2 relationship records (CC0). An edge with a `QuantifierAmount` becomes `OWNS{pct_basis: accounting_consolidation}`; an edge without one becomes `CONTROLS{basis: accounting_consolidation}`.
  - **Shareholdings:** Global Energy Ownership Tracker shareholdings (CC BY 4.0), as `OWNS{pct_basis: shareholding}`.
- **Designations** are modelled per authority, from the OpenSanctions statement data for the OFAC, EU and UK source datasets.

### Evaluation
- **Golden suite:** about 30 synthetic cases, each with expected disposition per pack, expected proof edges and expected decisive records. They cover:
  - an alias-dependent chain
  - an expired short path next to a valid long path
  - a 50%→50% chain (OFAC/EU blocked; multiplication would have cleared it)
  - 30% + 25% from two designated persons (OFAC/EU blocked; UK not)
  - unknown stake straddling the threshold
  - a 49% restructuring before listing
  - circular ownership
  - a look-alike with a conflicting identifier
  - prompt injection in an entity name and in a document
  - a delisted owner
  - a control-only presumption
  - a watch flip
- **Graders (code):** disposition, proof-edge set, decisive set, citation validity, no unsupported sentence, budget respected, no forbidden tool, no duplicate call.
- **Ablations:** name-only screening; path-only tracing (the v1 behaviour); multiplicative arithmetic; entity resolution off; time filtering off; agent versus playbook. Report errors per golden category.
- **Consistency:** pass^5 in agent mode.
- **Real data** ([R4](research/R4-open-data-and-eval.md)):
  - **E0:** a reproduction sanity check against OpenSanctions `ann_graph_topics` (not a score).
  - **E1, coverage only:** recall of the control-path output against `sanction.control` labels that fall inside the loaded slice. This is not a headline number. OpenSanctions derives the label from GLEIF and GEM edges too (`ext_gleif`, `gem_energy_ownership`), so the overlap is circular.
  - **E3, the headline:** hidden-designation recovery. Positives are subsidiaries designated on or after a designated ancestor under the same authority. Hide each positive's own designation, evaluate it as of its listing date, and report graph recall (flagged and blocked) against the name-only baseline. Results are stratified by name visibility, for example "Sberbank CIB" against "Pabbay Shipping", with denominators.
  - **E2** (time split) is a stretch.
- **Published:** denominators, snapshot versions, confusion matrices and exclusions.
- `sanction.control` has no percentage threshold, so it scores only the control-path output, never a 50%-rule verdict.

## Testing Decisions

- **Prefer the highest seam.** The main seam is the application API backed by a real FalkorDB container, seeded with the synthetic graph. Tests assert visible outcomes, not internal call sequences:
  - dispositions, per-pack verdicts and intervals
  - proof and decisive edge sets
  - the persisted step trail
  - reviews and notifications
- **Second seam: the MCP boundary.**
  - Every tool lists the correct annotations and schemas.
  - Approved reads succeed. Writes, arbitrary Cypher, out-of-range arguments and oversized requests are rejected with `isError`.
  - No credential appears in any tool output.
- **Differential test for the fix-point:** the Cypher-round implementation must equal a pure-Python reference on the golden graph and on 200 random small ownership graphs with cycles and unknown stakes.
- **Model boundary:** the model client is replaceable. Tests cover success, low probability, malformed output, timeout and outage with scripted fakes, and assert the externally visible disposition and the recorded fallback. A fake model's probability is never treated as evidence of calibration.
- **Imports:** idempotency (run twice, same counts), no `Person` nodes in the real slice, licence and snapshot on every record, and date parsing. Tested on small frozen fixtures checked into tests.
- **Evaluation harness:** golden suite in CI on every push, with a regression gate. The pass^5 agent run and the real-data evaluation run on demand.
- **Frontend:** a scripted browser walkthrough of one EXPOSED case, one ESCALATE case, one CLEAR_WITHIN_BOUNDS case, a regime switch and a watch flip. It checks that the visible proof and timeline match the API response.
- **Prior art in the repo:** the existing FalkorDB integration tests (seed graph → assert path, temporal correctness, abstention, flip) are the model. Keep their pattern: a module-scoped fixture builds the graph, and tests are skipped when the database is unreachable locally. In CI the database is always present and tests must not skip.

## Out of Scope

- Legal determinations. ShellTrace gives investigative evidence under stated rule-pack interpretations, not legal advice. The UI and README say so.
- Filing reports with regulators. The report is a draft for human review.
- Real natural-person data of any kind. People exist only in the synthetic graph.
- Arbitrary model-generated Cypher, and any model-authorised write.
- Inferring hidden beneficial owners from structure. Recovery is provably near chance for isolated owners ([R0](research/R0-arxiv-domain-scan.md)), so ShellTrace traces only observed, cited edges.
- Calibration claims for any model's probabilities.
- BIS Entity List / Affiliates Rule evaluation. The rule is suspended and its return date is uncertain. It may be mentioned in the pitch as context only.
- Transaction monitoring, adverse media and PEP screening.
- Redistributing OpenSanctions-derived data in the repository.

## Further Notes

- **Eligibility (P0).**
  - Rule 8 and the FAQ say: "The submission and its main FalkorDB implementation must be new work completed during the event."
  - The pre-event repository (`HarshdipSaha/graphrag`) holds a v1 implementation dated 1 Oct 2026. It will not be submitted.
  - Build in a **new public repository** created after 15 Oct 12:01 AM IST, with granular commits. Copy in only `docs/` as labelled pre-event notes, plus generic infrastructure.
  - Disclose prior work and AI assistance in the README.
  - Rule 8 also covers "design work", and this spec and its plan are detailed. **Ask the organisers on Discord** whether detailed pre-event plans count as notes, and follow their ruling.
- **Re-check the rules on 14–15 Oct.** The organisers may still change them (R1).
- **Licence posture.** OpenSanctions is CC BY-NC 4.0, and use inside a for-profit business needs a licence. Build and demo in a personal, non-commercial capacity under the personal GitHub identity, or email OpenSanctions first (R4).
- **Track 02 decision gate** (end of day 3). Enter Track 02 only if all of these work:
  - per-workspace graphs
  - persistent case memory with recall
  - watch-driven re-runs

  Otherwise name Track 01 only.
- **Side prize.** Publish a blog post on "the 50% rule is a fix-point, not a product" for the best-blog prize.
- **Demo spine** (≤ 3 minutes):

  | Time | Beat |
  |---|---|
  | 0:00–0:10 | Hook |
  | 0:10–0:30 | Name screen says clear |
  | 0:30–1:30 | Agent run with timeline: alias held, proof animates, OFAC → UK switch changes the verdict |
  | 1:30–1:55 | Time slider |
  | 1:55–2:20 | Designation event flips a watched case, shown with a diff |
  | 2:20–2:40 | Honest failure modes: poisoned document stays a candidate, LLM-off playbook, bounded CLEAR |
  | 2:40–3:00 | Evaluation table and Cypher |

  Record from the live deployment.
- **Research base:** [R0 arXiv domain scan](research/R0-arxiv-domain-scan.md), [R1 hackathon and TypeSafe](research/R1-hackathon-intel.md), [R2 FalkorDB](research/R2-falkordb-platform.md) (partial; day-1 verification list), [R3 sanctions law](research/R3-sanctions-ownership-law.md), [R4 data and evaluation](research/R4-open-data-and-eval.md), [R5 literature](research/R5-academic-sota.md), [R6 competition, agents and UX](research/R6-competition-agents-ux.md).
- **No issue tracker** is configured for this repository, so this spec is published as a repository document rather than an issue (the `to-spec` skill's tracker step is skipped).
