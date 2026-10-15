from __future__ import annotations

from collections import defaultdict
from datetime import date

from ..db import ro
from ..models import RedFlag
from .ownership import canon_of, upstream_scope


DIVESTMENTS = """
MATCH (o:Entity)-[r:OWNS]->(x:Entity), (o)-[d:DESIGNATED]->(pg:Program)
WHERE x.canon IN $scope AND pg.authority IN $authorities
  AND r.valid_to IS NOT NULL AND r.pct IS NOT NULL AND r.pct >= 50.0
  AND r.valid_to < d.listed_on AND d.listed_on <= $as_of
  AND (d.delisted_on IS NULL OR d.delisted_on > $as_of)
RETURN o.id AS owner, x.id AS asset, r.k AS k, r.pct AS pct, r.valid_to AS ended,
       d.k AS designation_key, d.listed_on AS listed
"""

CYCLE_EDGES = """
MATCH (o:Entity)-[r:OWNS]->(x:Entity)
WHERE o.canon IN $scope AND x.canon IN $scope
  AND (r.valid_from IS NULL OR r.valid_from <= $as_of)
  AND (r.valid_to IS NULL OR r.valid_to >= $as_of)
RETURN o.id AS owner, o.canon AS owner_canon, x.id AS asset, x.canon AS asset_canon, r.k AS k
"""

CYCLE_PATHS = """
MATCH p=(x:Entity)-[rs:OWNS*2..6]->(x)
WHERE x.canon IN $scope
  AND all(r IN relationships(p) WHERE
    (r.valid_from IS NULL OR r.valid_from <= $as_of)
    AND (r.valid_to IS NULL OR r.valid_to >= $as_of))
RETURN [n IN nodes(p) | n.id] AS entity_ids,
       [n IN nodes(p) | n.canon] AS canons,
       [r IN relationships(p) | r.k] AS keys
LIMIT 3
"""

MASS_ADDRESSES = """
MATCH (s:Entity)-[sr:REGISTERED_AT]->(a:Address)
WHERE s.canon IN $scope
  AND (sr.valid_from IS NULL OR sr.valid_from <= $as_of)
  AND (sr.valid_to IS NULL OR sr.valid_to >= $as_of)
WITH DISTINCT a
MATCH (o:Entity)-[r:REGISTERED_AT]->(a)
WHERE (r.valid_from IS NULL OR r.valid_from <= $as_of)
  AND (r.valid_to IS NULL OR r.valid_to >= $as_of)
WITH a, count(DISTINCT o) AS n, collect(DISTINCT o.id) AS entity_ids, collect(DISTINCT r.k) AS keys
WHERE n >= $mass_min
RETURN a.id AS address, a.name AS address_name, n, entity_ids, keys
ORDER BY address
"""

DESIGNATED_CONTROL = """
MATCH (o:Entity)-[r:CONTROLS|OFFICER_OF]->(x:Entity), (o)-[d:DESIGNATED]->(pg:Program)
WHERE x.canon IN $scope AND pg.authority IN $authorities
  AND d.listed_on <= $as_of AND (d.delisted_on IS NULL OR d.delisted_on > $as_of)
  AND (r.valid_from IS NULL OR r.valid_from <= $as_of)
  AND (r.valid_to IS NULL OR r.valid_to >= $as_of)
RETURN o.id AS controller, x.id AS controlled, type(r) AS rel_type,
       r.k AS k, d.k AS designation_key
"""


def _valid_date(value: str) -> str:
    date.fromisoformat(value)
    return value


def _cycles(rows: list[dict]) -> list[tuple[list[str], list[str]]]:
    """Return strongly connected ownership components and their internal keys."""
    adjacency: dict[str, set[str]] = defaultdict(set)
    ids_by_canon: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        owner = row["owner_canon"]
        asset = row["asset_canon"]
        adjacency[owner].add(asset)
        adjacency.setdefault(asset, set())
        ids_by_canon[owner].add(row["owner"])
        ids_by_canon[asset].add(row["asset"])

    index = 0
    stack: list[str] = []
    on_stack: set[str] = set()
    indices: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    components: list[set[str]] = []

    def visit(node: str) -> None:
        nonlocal index
        indices[node] = lowlinks[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)

        for neighbor in adjacency[node]:
            if neighbor not in indices:
                visit(neighbor)
                lowlinks[node] = min(lowlinks[node], lowlinks[neighbor])
            elif neighbor in on_stack:
                lowlinks[node] = min(lowlinks[node], indices[neighbor])

        if lowlinks[node] == indices[node]:
            component: set[str] = set()
            while True:
                member = stack.pop()
                on_stack.remove(member)
                component.add(member)
                if member == node:
                    break
            if len(component) >= 2:
                components.append(component)

    for node in adjacency:
        if node not in indices:
            visit(node)

    results = []
    for component in components:
        keys = sorted(
            {
                row["k"]
                for row in rows
                if row["owner_canon"] in component and row["asset_canon"] in component
            }
        )
        entity_ids = sorted(
            {entity_id for canon in component for entity_id in ids_by_canon[canon]}
        )
        results.append((entity_ids, keys))
    return results


def red_flags(
    g,
    entity_id: str,
    as_of: str,
    max_hops: int,
    authorities: tuple[str, ...] | list[str],
    window_days: int = 180,
    mass_min: int = 20,
) -> list[RedFlag]:
    """Find bounded ownership, registration, and designated-control red flags."""
    as_of = _valid_date(as_of)
    if (
        isinstance(window_days, bool)
        or not isinstance(window_days, int)
        or window_days < 0
    ):
        raise ValueError("window_days must be a non-negative integer")
    if isinstance(mass_min, bool) or not isinstance(mass_min, int) or mass_min < 1:
        raise ValueError("mass_min must be a positive integer")

    canon = canon_of(g, entity_id)
    scope, _ = upstream_scope(g, canon, as_of, max_hops)
    context = {"scope": scope, "as_of": as_of, "authorities": list(authorities)}
    flags: list[RedFlag] = []

    for row in ro(g, DIVESTMENTS, context):
        gap_days = (date.fromisoformat(row["listed"]) - date.fromisoformat(row["ended"])).days
        if gap_days <= window_days:
            flags.append(
                RedFlag(
                    kind="divestment_near_listing",
                    entity_ids=[row["owner"], row["asset"]],
                    evidence_keys=[row["k"], row["designation_key"]],
                    detail=(
                        f"{row['pct']:g}% stake ended on {row['ended']}, {gap_days} days "
                        f"before listing on {row['listed']}."
                    ),
                )
            )

    try:
        cycle_rows = ro(g, CYCLE_PATHS, {"scope": scope, "as_of": as_of})
        cycles = [
            (sorted(set(row["entity_ids"][:-1])), sorted(set(row["keys"])))
            for row in cycle_rows
            if len(set(row["canons"][:-1])) >= 2
        ]
    except Exception:
        # Keep the portable fallback for FalkorDB versions that cannot execute
        # the bounded variable-length cycle pattern.
        cycle_rows = ro(g, CYCLE_EDGES, {"scope": scope, "as_of": as_of})
        cycles = _cycles(cycle_rows)

    for entity_ids, keys in cycles:
        flags.append(
            RedFlag(
                kind="circular_ownership",
                entity_ids=entity_ids,
                evidence_keys=keys,
                detail=f"Valid ownership edges form a cycle among {', '.join(entity_ids)}.",
            )
        )

    for row in ro(
        g,
        MASS_ADDRESSES,
        {"scope": scope, "as_of": as_of, "mass_min": mass_min},
    ):
        flags.append(
            RedFlag(
                kind="mass_registration_address",
                entity_ids=sorted(row["entity_ids"] or []),
                evidence_keys=sorted(set(row["keys"] or [])),
                detail=(
                    f"{row['n']} currently registered entities share {row['address_name']} "
                    f"({row['address']})."
                ),
            )
        )

    for row in ro(g, DESIGNATED_CONTROL, context):
        flags.append(
            RedFlag(
                kind="control_by_designated",
                entity_ids=[row["controller"], row["controlled"]],
                evidence_keys=[row["k"], row["designation_key"]],
                detail=(
                    f"Actively designated controller {row['controller']} has a valid "
                    f"{row['rel_type']} relationship to {row['controlled']}."
                ),
            )
        )

    unique: dict[tuple[str, tuple[str, ...]], RedFlag] = {}
    for flag in flags:
        evidence = tuple(sorted(flag.evidence_keys))
        unique[(flag.kind, evidence)] = flag.model_copy(update={"evidence_keys": list(evidence)})
    return sorted(unique.values(), key=lambda flag: (flag.kind, tuple(flag.evidence_keys)))
