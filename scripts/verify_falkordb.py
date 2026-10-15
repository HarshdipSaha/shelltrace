"""Verify the FalkorDB and MCP features required by the ShellTrace plan."""

from __future__ import annotations

import os
import sys
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any


BACKEND = str(Path(__file__).resolve().parents[1] / "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)


def _connection(db: Any) -> Any:
    connection = getattr(db, "connection", None)
    if connection is None:
        raise RuntimeError("FalkorDB client has no connection handle")
    return connection


def _execute(db: Any, *args: Any) -> Any:
    connection = _connection(db)
    execute = getattr(connection, "execute_command", None)
    if execute is None:
        raise RuntimeError("FalkorDB connection has no execute_command method")
    return execute(*args)


def _rows(result: Any) -> list[list[Any]]:
    rows = getattr(result, "result_set", None)
    if rows is None:
        raise RuntimeError(f"query result has no result_set: {result!r}")
    return rows


def _clear_graphs(db: Any, graph_name: str, copy_name: str) -> None:
    errors: list[str] = []
    for name in (copy_name, graph_name):
        try:
            if _connection(db).exists(name):
                _execute(db, "GRAPH.DELETE", name)
        except Exception as exc:
            errors.append(f"{name}: {type(exc).__name__}: {exc}")
    if errors:
        raise RuntimeError(
            "could not clean up verification graphs: " + "; ".join(errors)
        )


def _v2(g: Any) -> None:
    rows = _rows(
        g.query(
            "CALL algo.WCC({nodeLabels:['N'], relationshipTypes:['S']}) "
            "YIELD node, componentId RETURN count(*)"
        )
    )
    if not rows or rows[0][0] != 3:
        raise AssertionError(f"WCC should return all 3 N nodes, got {rows!r}")


def _v1(g: Any) -> None:
    # Exercise the application's actual read-only boundary. Do not substitute a
    # verifier-only keyword guard: Graph.ro_query must reject the attempted write.
    from shelltrace.db import ro

    try:
        ro(g, "CREATE (:V1WriteProbe {id:'must-not-exist'})")
    except Exception:
        pass
    else:
        raise AssertionError("production ro() accepted a write query")
    rows = _rows(g.query("MATCH (n:V1WriteProbe) RETURN count(n)"))
    if not rows or rows[0][0] != 0:
        raise AssertionError(f"read-only write probe created data: {rows!r}")


def _v3(g: Any) -> str:
    try:
        g.query("CALL db.idx.fulltext.createNodeIndex('N','name')")
        create_mode = "legacy createNodeIndex procedure"
    except Exception as legacy_error:
        # FalkorDB 6.x accepts full-text index creation through DDL. The legacy
        # procedure still works on earlier releases but changed in 6.0.
        g.query("CREATE FULLTEXT INDEX FOR (n:N) ON (n.name)")
        create_mode = (
            "CREATE FULLTEXT INDEX DDL fallback; legacy procedure rejected: "
            f"{legacy_error}"
        )
    rows = _rows(
        g.query(
            "CALL db.idx.fulltext.queryNodes('N','blue') "
            "YIELD node RETURN node.name"
        )
    )
    if not rows or not any("blue" in str(row[0]).lower() for row in rows):
        raise AssertionError(f"full-text query did not return a blue node: {rows!r}")
    return create_mode


def _v4(db: Any, graph_name: str, copy_name: str) -> None:
    _execute(db, "GRAPH.COPY", graph_name, copy_name)
    copied = db.select_graph(copy_name)
    rows = _rows(copied.query("MATCH (n:N) RETURN count(n)"))
    if not rows or rows[0][0] != 3:
        raise AssertionError(f"GRAPH.COPY should copy 3 nodes, got {rows!r}")


def _v5(g: Any) -> None:
    rows = _rows(
        g.query(
            "UNWIND [1,2,null] AS x "
            "WITH collect(CASE WHEN x > 1 THEN x END) AS c "
            "RETURN c, 2 IN $l",
            {"l": [2]},
        )
    )
    if not rows or rows[0] != [[2], True]:
        raise AssertionError(f"expected [2] and true with a list parameter, got {rows!r}")


def _v6(g: Any) -> None:
    rows = _rows(g.query("MATCH p=(x:N)-[:OWNS*2..6]->(x) RETURN count(p)"))
    if not rows or rows[0][0] < 1:
        raise AssertionError(f"cycle query did not find the OWNS cycle: {rows!r}")


def _v7(g: Any) -> None:
    g.query("CREATE INDEX FOR ()-[r:OWNS]-() ON (r.k)")


def _v8(g: Any) -> None:
    rows = _rows(
        g.query("MERGE (e:Entity:Company {id:$id}) RETURN labels(e)", {"id": "v8"})
    )
    if not rows or set(rows[0][0]) != {"Entity", "Company"}:
        raise AssertionError(f"MERGE did not apply both labels: {rows!r}")


def _v9() -> None:
    from mcp.server.fastmcp import FastMCP
    from mcp.shared.memory import create_connected_server_and_client_session

    server = FastMCP("shelltrace-verify", stateless_http=True)
    if not callable(getattr(server, "streamable_http_app", None)):
        raise AssertionError("FastMCP.streamable_http_app is missing")
    if not callable(create_connected_server_and_client_session):
        raise AssertionError("create_connected_server_and_client_session is missing")

    # Confirm the structured-output option is accepted by the installed SDK.
    @server.tool(structured_output=True)
    def structured_probe() -> dict[str, bool]:
        return {"ok": True}


CHECK_NAMES = (
    "V1_ro_query_rejects_write",
    "V2_wcc",
    "V3_fulltext",
    "V4_graph_copy",
    "V5_collect_nulls_and_in",
    "V6_cycle",
    "V7_rel_index",
    "V8_two_labels_merge",
    "V9_mcp_sdk_imports",
)


def _connect() -> Any:
    from falkordb import FalkorDB

    host = os.getenv("FALKORDB_HOST", "127.0.0.1")
    port = int(os.getenv("FALKORDB_PORT", "6379"))
    kwargs: dict[str, Any] = {"host": host, "port": port}
    username = os.getenv("FALKORDB_USERNAME")
    password = os.getenv("FALKORDB_PASSWORD")
    if username:
        kwargs["username"] = username
    if password:
        kwargs["password"] = password

    deadline = time.monotonic() + 30
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            db = FalkorDB(**kwargs)
            db.connection.ping()
            return db
        except Exception as exc:
            last_error = exc
            time.sleep(1)
    raise ConnectionError(
        f"could not connect to FalkorDB at {host}:{port} after 30s: {last_error}"
    )


def _server_facts(db: Any) -> tuple[str, str, str]:
    info = _execute(db, "INFO", "server")
    redis_version = str(info.get("redis_version", "unknown")) if isinstance(info, dict) else "unknown"
    modules = _execute(db, "MODULE", "LIST")
    falkordb_version = "unknown"
    for module in modules:
        if not isinstance(module, (list, tuple)):
            continue
        fields = {str(module[i]): module[i + 1] for i in range(0, len(module) - 1, 2)}
        if fields.get("name") == "graph":
            module_version = int(fields["ver"])
            falkordb_version = (
                f"{module_version // 10000}."
                f"{(module_version // 100) % 100}."
                f"{module_version % 100}"
            )
            break
    graph_config = _execute(db, "GRAPH.CONFIG", "GET", "*")
    return redis_version, falkordb_version, str(graph_config)


def main() -> int:
    run_id = uuid.uuid4().hex
    graph_name = f"st_verify_{run_id}"
    copy_name = f"st_verify_copy_{run_id}"
    try:
        db = _connect()
    except Exception as exc:
        print(f"FAIL connection: {exc}", file=sys.stderr)
        return 2

    deferred = 0
    failures = 0
    names_reserved = False
    try:
        graph = db.select_graph(graph_name)
        connection = _connection(db)
        if connection.exists(graph_name) or connection.exists(copy_name):
            raise RuntimeError(
                "generated verification graph name already exists; "
                "refusing to use or delete it"
            )
        names_reserved = True

        graph.query(
            "CREATE (a:N {name:'blue harbor'}), "
            "(b:N {name:'red harbor'}), "
            "(c:N {name:'blue vessel'}), "
            "(a)-[:S]->(c), (a)-[:OWNS {k:'a-b'}]->(b), "
            "(b)-[:OWNS {k:'b-a'}]->(a)"
        )

        checks: dict[str, Callable[[], str | None]] = {
            CHECK_NAMES[0]: lambda: _v1(graph),
            CHECK_NAMES[1]: lambda: _v2(graph),
            CHECK_NAMES[2]: lambda: _v3(graph),
            CHECK_NAMES[3]: lambda: _v4(db, graph_name, copy_name),
            CHECK_NAMES[4]: lambda: _v5(graph),
            CHECK_NAMES[5]: lambda: _v6(graph),
            CHECK_NAMES[6]: lambda: _v7(graph),
            CHECK_NAMES[7]: lambda: _v8(graph),
            CHECK_NAMES[8]: _v9,
        }
        for name, check in checks.items():
            try:
                note = check()
            except Exception as exc:
                failures += 1
                print(f"FAIL {name}: {type(exc).__name__}: {exc}")
            else:
                print(f"PASS {name}" + (f": {note}" if note else ""))

        try:
            redis_version, falkordb_version, graph_config = _server_facts(db)
            print(f"SERVER redis_version={redis_version}")
            print(f"FALKORDB version={falkordb_version}")
            print(f"GRAPH.CONFIG GET *: {graph_config}")
        except Exception as exc:
            failures += 1
            print(f"FAIL server_facts: {type(exc).__name__}: {exc}")
    except Exception as exc:
        failures += 1
        print(f"FAIL setup: {type(exc).__name__}: {exc}")
    finally:
        if names_reserved:
            try:
                _clear_graphs(db, graph_name, copy_name)
            except Exception as exc:
                failures += 1
                print(f"FAIL cleanup: {type(exc).__name__}: {exc}")

    print(
        f"RESULT {'FAIL' if failures else 'PASS'} "
        f"({failures} failures; {deferred} deferred)"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
