from __future__ import annotations

import time
from typing import Any

from ..db import ro
from ..models import TraceEdge, TraceNode, TraceResult
from .ownership import EntityNotFound, canon_of


OWN_RELS = "OWNS|CONTROLS|SAME_AS"
CTX_RELS = "OWNS|CONTROLS|SAME_AS|OFFICER_OF|REGISTERED_AT"
TRACE_PATH_CANDIDATE_BUDGET = 1_000


class TraceUnavailable(RuntimeError):
    """The bounded trace could not be completed safely."""

ZERO_HOP_CYPHER = """
MATCH (t:Entity {id:$id})-[d:DESIGNATED]->(pg:Program)
WHERE pg.authority IN $auth AND NOT d.k IN $exclude
  AND d.listed_on <= $as_of AND (d.delisted_on IS NULL OR d.delisted_on > $as_of)
RETURN t, d.k AS dk, pg.authority AS authority, pg.name AS program,
       d.listed_on AS listed_on
LIMIT $path_limit"""


def trace_cypher(max_hops: int, mode: str, depth: int | None = None) -> str:
    if mode not in {"ownership", "context"}:
        raise ValueError(f"unsupported trace mode: {mode}")
    hops = max(1, min(6, int(max_hops)))
    if depth is not None and not 1 <= int(depth) <= hops:
        raise ValueError(f"trace depth must be between 1 and {hops}")
    path_length = f"*{int(depth)}" if depth is not None else f"*1..{hops}"
    if mode == "ownership":
        pattern = f"(t:Entity)-[:{OWN_RELS}{path_length}]->(s:Entity {{id:$id}})"
    else:
        pattern = f"(t:Entity)-[:{CTX_RELS}{path_length}]-(s:Entity {{id:$id}})"
    return (
        f"MATCH p = {pattern}\n"
        "WHERE t <> s AND all(r IN relationships(p) WHERE NOT r.k IN $exclude\n"
        "  AND (r.valid_from IS NULL OR r.valid_from <= $as_of)\n"
        "  AND (r.valid_to IS NULL OR r.valid_to >= $as_of))\n"
        "MATCH (t)-[d:DESIGNATED]->(pg:Program)\n"
        "WHERE pg.authority IN $auth AND NOT d.k IN $exclude\n"
        "  AND d.listed_on <= $as_of\n"
        "  AND (d.delisted_on IS NULL OR d.delisted_on > $as_of)\n"
        "RETURN nodes(p) AS ns, relationships(p) AS rs, length(p) AS hops,\n"
        "       d.k AS dk, pg.authority AS authority, pg.name AS program,\n"
        "       d.listed_on AS listed_on\n"
        "LIMIT $path_limit"
    )


def _trace_node(node: Any) -> TraceNode:
    properties = node.properties
    return TraceNode(
        id=properties["id"],
        name=properties["name"],
        kind=properties["kind"],
        country=properties.get("country"),
    )


def _internal_id(endpoint: Any) -> int:
    return endpoint.id if hasattr(endpoint, "id") else int(endpoint)


def _trace_edge(edge: Any, entity_ids: dict[int, str]) -> TraceEdge:
    properties = edge.properties
    return TraceEdge(
        k=properties["k"],
        type=edge.relation,
        from_id=entity_ids[_internal_id(edge.src_node)],
        to_id=entity_ids[_internal_id(edge.dest_node)],
        pct=properties.get("pct"),
        basis=properties.get("pct_basis") or properties.get("basis"),
        role=properties.get("role"),
        valid_from=properties.get("valid_from"),
        valid_to=properties.get("valid_to"),
        src=properties.get("src"),
        src_record=properties.get("src_record"),
    )


def trace(
    g,
    entity_id: str,
    as_of: str,
    max_hops: int,
    authorities: tuple[str, ...] | list[str],
    mode: str = "ownership",
    exclude: tuple[str, ...] = (),
) -> TraceResult | None:
    if mode not in {"ownership", "context"}:
        raise ValueError(f"unsupported trace mode: {mode}")
    started = time.perf_counter()
    try:
        canon_of(g, entity_id)
    except EntityNotFound:
        raise
    except Exception as exc:
        raise TraceUnavailable("trace query failed or timed out") from exc
    params = {
        "id": entity_id,
        "as_of": as_of,
        "auth": list(authorities),
        "exclude": list(exclude),
    }
    remaining = TRACE_PATH_CANDIDATE_BUDGET

    try:
        direct = ro(
            g,
            ZERO_HOP_CYPHER,
            {**params, "path_limit": remaining + 1},
        )
    except Exception as exc:
        raise TraceUnavailable("trace query failed or timed out") from exc
    if len(direct) > remaining:
        raise TraceUnavailable(
            f"trace candidate path cap {TRACE_PATH_CANDIDATE_BUDGET} exceeded at depth 0"
        )
    remaining -= len(direct)
    if direct:
        most_recent = max(row["listed_on"] for row in direct)
        row = min(
            (candidate for candidate in direct if candidate["listed_on"] == most_recent),
            key=lambda candidate: candidate["dk"],
        )
        node = _trace_node(row["t"])
        return TraceResult(
            hops=0,
            nodes=[node],
            edges=[],
            designation_key=row["dk"],
            authority=row["authority"],
            program=row["program"],
            listed_on=row["listed_on"],
            mode=mode,
            cypher=ZERO_HOP_CYPHER,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

    bounded_hops = max(1, min(6, int(max_hops)))
    query = ""
    selected_path = None
    for depth in range(1, bounded_hops + 1):
        query = trace_cypher(bounded_hops, mode, depth=depth)
        try:
            paths = ro(
                g,
                query,
                {**params, "path_limit": remaining + 1},
            )
        except Exception as exc:
            raise TraceUnavailable("trace query failed or timed out") from exc
        if len(paths) > remaining:
            raise TraceUnavailable(
                f"trace candidate path cap {TRACE_PATH_CANDIDATE_BUDGET} exceeded at depth {depth}"
            )
        remaining -= len(paths)
        if paths:
            most_recent = max(row["listed_on"] for row in paths)
            selected = [row for row in paths if row["listed_on"] == most_recent]
            selected_path = min(
                selected,
                key=lambda row: (
                    row["dk"],
                    tuple(node.properties["id"] for node in row["ns"]),
                ),
            )
            break

    if selected_path is None:
        return None

    row = selected_path
    nodes = [_trace_node(node) for node in row["ns"]]
    entity_ids = {
        node.id: trace_node.id for node, trace_node in zip(row["ns"], nodes)
    }
    edges = [_trace_edge(edge, entity_ids) for edge in row["rs"]]
    return TraceResult(
        hops=row["hops"],
        nodes=nodes,
        edges=edges,
        designation_key=row["dk"],
        authority=row["authority"],
        program=row["program"],
        listed_on=row["listed_on"],
        mode=mode,
        cypher=query,
        latency_ms=int((time.perf_counter() - started) * 1000),
    )
