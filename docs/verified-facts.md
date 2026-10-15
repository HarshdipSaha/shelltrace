# Verified platform facts

Task 0 was run on 15 October 2026 with Python 3.12.0, Docker Engine 28.3.2, and Docker Compose v2.38.2-desktop.1. The backend dependency installation completed, and importing the application dependencies printed `PASS dependency imports`.

## Pinned FalkorDB image

The tested image is `falkordb/falkordb:6.0.2@sha256:107455e862a824e45e8e9f5a7fbfdf5e00a08b14e13eae2577c72fd9e3f59ba6`. Compose and CI use this same immutable reference. The server reported Redis `8.10.2`; `MODULE LIST` reported graph module version `60002`, which is FalkorDB `6.0.2`.

The initial local `latest` image was older, so the exact 6.0.2 image was pulled and the full verifier rerun before pinning. Compose omits a fixed `container_name` because another worktree already has a stopped container with that name. That container and its volume were left untouched; Compose created a worktree-scoped container and named volume for this run.

## Verifier output

The verifier ran against the throwaway `st_verify` graph, cleaned it and its copy after the checks, and printed:

```text
DEFERRED V1_ro_query_rejects_write: verify against Task 1's production GraphStore helper after Tasks 1-3; a verifier-local guard would not test the application's read-only boundary.
PASS V2_wcc
PASS V3_fulltext: CREATE FULLTEXT INDEX DDL fallback; legacy procedure rejected: Received 2 arguments to procedure 'db.idx.fulltext.createNodeIndex', expected at most 1
PASS V4_graph_copy
PASS V5_collect_nulls_and_in
PASS V6_cycle
PASS V7_rel_index
PASS V8_two_labels_merge
PASS V9_mcp_sdk_imports
SERVER redis_version=8.10.2
FALKORDB version=6.0.2
GRAPH.CONFIG GET *: [['TIMEOUT', 1000], ['TIMEOUT_DEFAULT', 0], ['TIMEOUT_MAX', 0], ['CACHE_SIZE', 25], ['ASYNC_DELETE', 1], ['OMP_THREAD_COUNT', 12], ['THREAD_COUNT', 12], ['INDEX_WORKER_THREADS', 0], ['RESULTSET_SIZE', 10000], ['VKEY_MAX_ENTITY_COUNT', 100000], ['MAX_QUEUED_QUERIES', 25], ['QUERY_MEM_CAPACITY', 0], ['DELTA_MAX_PENDING_CHANGES', 10000], ['NODE_CREATION_BUFFER', 16384], ['CMD_INFO', 1], ['MAX_INFO_QUERIES', 1000], ['EFFECTS_COMPRESSION', 0], ['EFFECTS_THRESHOLD', 300], ['BOLT_PORT', 65535], ['DELAY_INDEXING', 0], ['IMPORT_FOLDER', '/var/lib/FalkorDB/import/'], ['TEMP_FOLDER', '/tmp'], ['JS_HEAP_SIZE', 268435456], ['JS_STACK_SIZE', 1048576]]
RESULT PASS (0 failures; 1 deferred)
```

## Follow-up requirements

- **V1 is deferred:** Task 1 must verify write rejection against the actual `GraphStore.ro_query` helper. The verifier does not substitute a local guard for that test.
- **V3 uses DDL on FalkorDB 6.0.2:** `CALL db.idx.fulltext.createNodeIndex('N','name')` is rejected by this server. `CREATE FULLTEXT INDEX FOR (n:N) ON (n.name)` plus `db.idx.fulltext.queryNodes` works. Later schema setup should use the DDL form on the pinned image; `CONTAINS` remains the fallback if full-text search is unavailable.
- **V2, V4-V9 passed:** the WCC procedure, graph copy, null collection/list parameter behavior, cycle query, relationship index, two-label MERGE, and required MCP SDK surface are available on the pinned image/dependencies.

The requested `pip install -e ".[dev]"` succeeded in the shared Python installation. Pip also reported pre-existing dependency conflicts involving unrelated globally installed packages; CI installs the project in a clean runner.
