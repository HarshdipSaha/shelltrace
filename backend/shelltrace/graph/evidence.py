from __future__ import annotations

from datetime import date

from ..db import ro
from ..models import EvidenceItem, Stake, TraceNode
from ..names import core, norm, phon
from .ownership import EntityNotFound, canon_of


EVIDENCE = """
MATCH (a:Entity)-[r]->(b)
WHERE r.k IN $keys
RETURN r.k AS k, type(r) AS type, a.id AS from_id, a.name AS from_name,
       b.id AS to_id, b.name AS to_name, r.pct AS pct,
       coalesce(r.pct_basis, r.basis) AS basis, r.role AS role,
       r.valid_from AS valid_from, r.valid_to AS valid_to,
       r.listed_on AS listed_on, r.delisted_on AS delisted_on,
       r.src AS src, r.src_record AS src_record, r.snapshot AS snapshot,
       r.licence AS licence, r.url AS url
"""

STAKES = """
MATCH (o:Entity)-[r:OWNS]->(x:Entity)
WHERE x.canon = $canon
  AND (r.valid_from IS NULL OR r.valid_from <= $as_of)
  AND (r.valid_to IS NULL OR r.valid_to >= $as_of)
RETURN o.id AS owner_id, o.name AS owner_name, r.pct AS pct,
       r.pct_basis AS basis, r.valid_from AS valid_from, r.valid_to AS valid_to,
       r.k AS k
ORDER BY coalesce(r.pct, -1.0) DESC, r.k
"""

EXACT_SEARCH = """
MATCH (e:Entity)
WHERE e.id = $query OR e.lei = $query OR e.imo = $query
RETURN e.id AS id, e.name AS name, e.kind AS kind, e.country AS country,
       e.lei AS lei, e.imo AS imo,
       CASE WHEN e.id = $query THEN 0 ELSE 1 END AS priority
ORDER BY priority, id
LIMIT $limit
"""

PHONETIC_SEARCH = """
MATCH (e:Entity) WHERE e.phon = $phon
RETURN e.id AS id, e.name AS name, e.kind AS kind, e.country AS country,
       e.lei AS lei, e.imo AS imo
ORDER BY id
LIMIT $limit
"""

FULLTEXT_SEARCH = """
CALL db.idx.fulltext.queryNodes('Entity', $query) YIELD node, score
RETURN node.id AS id, node.name AS name, node.kind AS kind, node.country AS country,
       node.lei AS lei, node.imo AS imo, score
ORDER BY score DESC, id
LIMIT $limit
"""

FALLBACK_SEARCH = """
MATCH (e:Entity)
WHERE e.norm_name CONTAINS $normalized OR e.core CONTAINS $core
RETURN e.id AS id, e.name AS name, e.kind AS kind, e.country AS country,
       e.lei AS lei, e.imo AS imo
ORDER BY id
LIMIT $limit
"""

DESIGNATED_IDS = """
MATCH (e:Entity)-[:DESIGNATED]->(:Program)
WHERE e.id IN $ids
RETURN DISTINCT e.id AS id
"""

NEIGHBORHOOD_STEP = """
MATCH (n)-[r:OWNS|CONTROLS|SAME_AS|OFFICER_OF|REGISTERED_AT]-(m)
WHERE n.id IN $frontier
RETURN n AS n, m AS m, r AS rel
ORDER BY rel.k, n.id, m.id
LIMIT $row_limit
"""

SEARCH_FIELDS = ("id", "name", "kind", "country", "lei", "imo", "designated")
MAX_SEARCH_LIMIT = 20
MAX_NEIGHBORHOOD_LIMIT = 50
MAX_NEIGHBORHOOD_DEPTH = 2
MAX_NEIGHBORHOOD_EDGE_ROWS = 1_000


def _date(value: str) -> str:
    date.fromisoformat(value)
    return value


def _limit(value: int, maximum: int, name: str) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 1 <= value <= maximum
    ):
        raise ValueError(f"{name} must be an integer between 1 and {maximum}")
    return value


def _search_result(row: dict) -> dict:
    result = {field: row.get(field) for field in SEARCH_FIELDS}
    result["designated"] = False
    return result


def _add_search_rows(
    results: list[dict], seen: set[str], rows: list[dict], limit: int
) -> None:
    for row in rows:
        entity_id = row.get("id")
        if entity_id is not None and entity_id not in seen:
            results.append(_search_result(row))
            seen.add(entity_id)
            if len(results) >= limit:
                return


def get_entity(g, entity_id: str) -> TraceNode:
    rows = ro(
        g,
        "MATCH (e:Entity {id:$id}) RETURN e.id AS id, e.name AS name, "
        "e.kind AS kind, e.country AS country LIMIT 1",
        {"id": entity_id},
    )
    if not rows:
        raise EntityNotFound(entity_id)
    return TraceNode(**rows[0])


def evidence_get(g, keys: list[str] | tuple[str, ...]) -> list[EvidenceItem]:
    ordered_keys = list(dict.fromkeys(keys))
    if not ordered_keys:
        return []
    rows = ro(g, EVIDENCE, {"keys": ordered_keys})
    by_key = {row["k"]: EvidenceItem(**row) for row in rows}
    return [by_key[key] for key in ordered_keys if key in by_key]


def ownership_stakes(g, entity_id: str, as_of: str) -> list[Stake]:
    as_of = _date(as_of)
    canon = canon_of(g, entity_id)
    rows = ro(g, STAKES, {"canon": canon, "as_of": as_of})
    return [Stake(**row) for row in rows]


def entity_search(g, query: str, limit: int = 10) -> list[dict]:
    limit = _limit(limit, MAX_SEARCH_LIMIT, "limit")
    if not isinstance(query, str):
        raise ValueError("query must be a string")
    normalized = norm(query)
    if not normalized:
        return []

    results: list[dict] = []
    seen: set[str] = set()
    _add_search_rows(
        results,
        seen,
        ro(g, EXACT_SEARCH, {"query": query, "limit": limit}),
        limit,
    )

    phonetic = phon(query)
    if len(results) < limit and phonetic:
        _add_search_rows(
            results,
            seen,
            ro(g, PHONETIC_SEARCH, {"phon": phonetic, "limit": limit}),
            limit,
        )
    if len(results) < limit:
        prefix_query = " ".join(f"{token}*" for token in normalized.split())
        try:
            fulltext_rows = ro(g, FULLTEXT_SEARCH, {"query": prefix_query, "limit": limit})
        except Exception:
            fulltext_rows = []
        _add_search_rows(results, seen, fulltext_rows, limit)

    if len(results) < limit:
        # Supplement full-text tokenization for joined spellings such as "BlueLagoon".
        # This same indexed-property query is the fallback when the full-text index is absent.
        _add_search_rows(
            results,
            seen,
            ro(
                g,
                FALLBACK_SEARCH,
                {"normalized": normalized, "core": core(query), "limit": limit},
            ),
            limit,
        )

    if results:
        designated_ids = {
            row["id"]
            for row in ro(g, DESIGNATED_IDS, {"ids": [result["id"] for result in results]})
        }
        for result in results:
            result["designated"] = result["id"] in designated_ids
    return results


def neighborhood(g, entity_id: str, depth: int = 1, limit: int = 50) -> dict:
    limit = _limit(limit, MAX_NEIGHBORHOOD_LIMIT, "limit")
    if (
        isinstance(depth, bool)
        or not isinstance(depth, int)
        or not 1 <= depth <= MAX_NEIGHBORHOOD_DEPTH
    ):
        raise ValueError(f"depth must be an integer between 1 and {MAX_NEIGHBORHOOD_DEPTH}")

    root = get_entity(g, entity_id)
    nodes = {
        root.id: {
            "id": root.id,
            "name": root.name,
            "kind": root.kind,
            "country": root.country,
        }
    }
    frontier = [root.id]
    edges: dict[str, dict] = {}
    today = date.today().isoformat()

    for _ in range(depth):
        if not frontier:
            break
        rows = ro(
            g,
            NEIGHBORHOOD_STEP,
            {"frontier": frontier, "row_limit": MAX_NEIGHBORHOOD_EDGE_ROWS},
        )
        next_frontier: list[str] = []
        for row in rows:
            current_node = row["n"]
            adjacent_node = row["m"]
            relationship = row["rel"]
            current_properties = current_node.properties
            adjacent_properties = adjacent_node.properties
            current_id = current_properties["id"]
            adjacent_id = adjacent_properties["id"]

            for node_id, properties, is_adjacent in (
                (current_id, current_properties, False),
                (adjacent_id, adjacent_properties, True),
            ):
                if node_id not in nodes and len(nodes) < limit:
                    nodes[node_id] = {
                        "id": node_id,
                        "name": properties.get("name"),
                        "kind": properties.get("kind"),
                        "country": properties.get("country"),
                    }
                    if is_adjacent:
                        next_frontier.append(node_id)
            if current_id not in nodes or adjacent_id not in nodes:
                continue
            relation_properties = relationship.properties
            key = relation_properties["k"]
            if key not in edges:
                source_internal_id = (
                    relationship.src_node.id
                    if hasattr(relationship.src_node, "id")
                    else int(relationship.src_node)
                )
                target_internal_id = (
                    relationship.dest_node.id
                    if hasattr(relationship.dest_node, "id")
                    else int(relationship.dest_node)
                )
                node_ids_by_internal_id = {
                    current_node.id: current_id,
                    adjacent_node.id: adjacent_id,
                }
                valid_to = relation_properties.get("valid_to")
                edges[key] = {
                    "k": key,
                    "type": relationship.relation,
                    "from_id": node_ids_by_internal_id[source_internal_id],
                    "to_id": node_ids_by_internal_id[target_internal_id],
                    "pct": relation_properties.get("pct"),
                    "basis": relation_properties.get("pct_basis")
                    or relation_properties.get("basis"),
                    "role": relation_properties.get("role"),
                    "valid_from": relation_properties.get("valid_from"),
                    "valid_to": valid_to,
                    "expired": valid_to is not None and valid_to < today,
                }
        frontier = list(dict.fromkeys(next_frontier))

    return {
        "nodes": list(nodes.values()),
        "edges": sorted(
            edges.values(),
            key=lambda edge: (edge["k"], edge["from_id"], edge["to_id"]),
        ),
    }
