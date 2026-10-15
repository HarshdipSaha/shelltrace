# R2: FalkorDB platform facts (partial)

_2026-10-05. The deep-research agent for this lane was stopped at the user's request before it wrote a report. This page collects the FalkorDB facts already verified elsewhere in the repo: `docs/04-review.md` (checked against docs.falkordb.com, Aug 2026), the working code in `backend/shelltrace/`, and R1/R6. Anything not verified there is marked **VERIFY ON DAY 1**. The implementation plan has a Day-1 task that runs each check against the pinned `falkordb/falkordb` image._

## Facts the spec relies on

| Capability | Status | Source / note |
|---|---|---|
| Bounded variable-length match `-[:A\|B*1..6]-` with `all(r IN relationships(p) WHERE …)` | VERIFIED (runs in repo code and tests) | `queries.trace_query_text`. A *named* var-length relationship variable binds to an Edge, not a List, so iterate `relationships(p)`. |
| `shortestPath` / `allShortestPaths` | VERIFIED constraint | Both endpoints must be bound, and property predicates apply only after expansion. A shorter expired path can then hide a valid longer one and produce a false CLEAR, so these must not be used for dated traces (04-review). |
| `algo.WCC({nodeLabels:[…], relationshipTypes:[…]}) YIELD node, componentId` | VERIFIED (docs) | Config map form; both `algo.wcc` and `algo.WCC` casings are accepted. |
| `algo.betweenness({...})` | VERIFIED (docs: config map) | Exact keys: VERIFY ON DAY 1. |
| `algo.pageRank(label, relType)` | VERIFIED (docs) | Positional arguments, one label and one relationship type. No config map, damping or iterations. Not personalised. |
| `algo.SPpaths` / `algo.SSpaths` | VERIFIED exist (docs: config map) | Can't express a per-edge validity predicate, so they are not used for dated traces. |
| `GRAPH.RO_QUERY` | VERIFIED (the FalkorDB MCP server's `query_graph_readonly` uses it, per R6) | Every model-reachable tool uses the read-only path. Python client `Graph.ro_query(q, params, timeout=…)`: VERIFY ON DAY 1. |
| Per-query timeout | VERIFY ON DAY 1 | `query(..., timeout=ms)` in falkordb-py, plus the server-side `TIMEOUT` config. |
| Full-text index: `CALL db.idx.fulltext.createNodeIndex('Entity','name')` and `CALL db.idx.fulltext.queryNodes('Entity',$q) YIELD node, score` | VERIFY ON DAY 1 | Used for fuzzy entity search. Fallback: `CONTAINS` on `norm_name`, which the current code uses. |
| Range index `CREATE INDEX FOR (e:Entity) ON (e.id)` | VERIFIED (repo `schema.py`) | Indexes on relationship properties: VERIFY ON DAY 1. |
| Multigraph: many isolated graphs in one instance | VERIFIED (event page, R1 §1.7) | Used for one case-memory graph per workspace. |
| `GRAPH.COPY src dst` | VERIFY ON DAY 1 | Would clone a template facts graph into each workspace. Fallback: re-run the loader per workspace. |
| ISO-8601 strings compare correctly with `<=`/`>=` | VERIFIED (repo tests) | Dates are kept as `YYYY-MM-DD` strings, with no `date()` sentinels. |
| FalkorDB MCP server (`query_graph`, `query_graph_readonly`, schema tools) | VERIFIED (R6 §2) | It runs arbitrary Cypher, which is too broad for a model-facing allowlist, so ShellTrace serves its own narrow MCP server. |
| GraphRAG SDK `apply_changes()` / `finalize()` | VERIFIED exist (04-review) | Built for document ingestion; it can't attach to a hand-built graph. Not on the critical path. |
| FalkorDB Browser on container port 3000 | VERIFIED (repo `docker-compose.yml`) | Used for the README data-model screenshot. |

## Consequences for the design

1. The dated exposure trace stays a bounded var-length `MATCH` with the validity predicate inside `all(...)`, and its hop bound is clamped to ≤ 6.
2. The ownership-rule fix-point runs as repeated aggregate Cypher rounds (`sum(r.pct)` grouped by owned entity). A Python loop carries the growing blocked set between rounds. This keeps the aggregation in the graph. A pure-Python reference implementation is used only for differential tests.
3. Alias clusters: `algo.WCC` over *accepted* `SAME_AS` only, plus a cluster-size cap.
4. Enablers: `algo.betweenness` over the case subgraph (stretch).
5. All model-reachable reads go through `ro_query` with a timeout.
