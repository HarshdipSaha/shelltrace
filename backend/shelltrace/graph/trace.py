from __future__ import annotations

import time
from typing import Any

from ..db import ro
from ..models import TraceEdge, TraceNode, TraceResult
from .ownership import canon_of


OWN_RELS = "OWNS|CONTROLS|SAME_AS"
CTX_RELS = "OWNS|CONTROLS|SAME_AS|OFFICER_OF|REGISTERED_AT"

ZERO_HOP_CYPHER = """
MATCH (t:Entity {id:$id})-[d:DESIGNATED]->(pg:Program)
WHERE pg.authority IN $auth AND NOT d.k IN $exclude
  AND d.listed_on <= $as_of AND (d.delisted_on IS NULL OR d.delisted_on > $as_of)
RETURN t, d.k AS dk, pg.authority AS authority, pg.name AS program,
       d.listed_on AS listed_on
ORDER BY d.listed_on DESC, d.k ASC LIMIT 1"""


def trace_cypher(max_hops: int, mode: str) -> str:
    if mode not in {"ownership", "context"}:
        raise ValueError(f"unsupported trace mode: {mode}")
    hops = max(1, min(6, int(max_hops)))
    if mode == "ownership":
        pattern = f"(t:Entity)-[:{OWN_RELS}*1..{hops}]->(s:Entity {{id:$id}})"
    else:
        pattern = f"(t:Entity)-[:{CTX_RELS}*1..{hops}]-(s:Entity {{id:$id}})"
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
        "ORDER BY hops ASC, d.listed_on DESC, d.k ASC LIMIT 1"
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
    canon_of(g, entity_id)
    params = {
        "id": entity_id,
        "as_of": as_of,
        "auth": list(authorities),
        "exclude": list(exclude),
    }

    direct = ro(g, ZERO_HOP_CYPHER, params)
    if direct:
        row = direct[0]
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

    query = trace_cypher(max_hops, mode)
    paths = ro(g, query, params)
    if not paths:
        return None

    row = paths[0]
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
