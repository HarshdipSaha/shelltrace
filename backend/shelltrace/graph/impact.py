from __future__ import annotations

from hashlib import sha1

from ..db import ro, rw
from ..models import DesignationEvent
from ..rulepacks import get_pack
from .ownership import canon_of, evaluate


PROG = {"OFAC": "prog_ofac", "EU": "prog_eu", "UK": "prog_uk"}

APPLY = """
MERGE (p:Program {id:$pid}) ON CREATE SET p.authority=$auth, p.name=$pname
WITH p MATCH (e:Entity {id:$eid})
MERGE (e)-[d:DESIGNATED {k:$k}]->(p)
SET d.listed_on=$listed, d.delisted_on=NULL, d.reason=$program, d.src=$src, d.src_record=$eventid,
    d.snapshot='event', d.licence='analyst-supplied', d.url=$url
RETURN d.k AS k"""

DOWN_STEP = """
MATCH (x:Entity)-[r:OWNS|CONTROLS]->(y:Entity)
WHERE x.canon IN $frontier
  AND NOT y.canon IN $visited
  AND (r.valid_from IS NULL OR r.valid_from <= $as_of)
  AND (r.valid_to IS NULL OR r.valid_to >= $as_of)
RETURN DISTINCT y.canon AS c
ORDER BY c
LIMIT $limit"""

REPRESENTATIVE = """
MATCH (e:Entity {canon:$canon})
RETURN e.id AS entity_id, e.name AS name
ORDER BY e.id
LIMIT 1"""


def event_id(ev: DesignationEvent) -> str:
    identity = f"{ev.entity_id}|{ev.authority}|{ev.program}|{ev.listed_on}"
    return "ev:" + sha1(identity.encode()).hexdigest()[:16]


def designation_key(ev: DesignationEvent) -> str:
    return f"evt:D-{ev.entity_id}-{PROG[ev.authority]}-{ev.listed_on}"


def apply_designation(g, ev: DesignationEvent) -> str:
    key = designation_key(ev)
    rows = rw(
        g,
        APPLY,
        {
            "pid": PROG[ev.authority],
            "auth": ev.authority,
            "pname": ev.program,
            "eid": ev.entity_id,
            "k": key,
            "listed": ev.listed_on,
            "program": ev.program,
            "src": ev.source,
            "eventid": event_id(ev),
            "url": ev.source_url,
        },
    )
    if not rows or rows[0].get("k") != key:
        raise ValueError(f"designation entity {ev.entity_id!r} was not found")
    return key


def downstream_candidates(
    g,
    entity_id: str,
    as_of: str,
    max_hops: int = 6,
    cap: int = 500,
) -> list[str]:
    root = canon_of(g, entity_id)
    frontier = {root}
    visited = {root}
    candidate_count = 0
    max_hops = max(0, int(max_hops))
    cap = max(0, int(cap))

    for _ in range(max_hops):
        remaining = cap - candidate_count
        if not frontier or remaining <= 0:
            break
        rows = ro(
            g,
            DOWN_STEP,
            {
                "frontier": sorted(frontier),
                "visited": sorted(visited),
                "as_of": as_of,
                "limit": remaining,
            },
        )
        next_frontier = {
            row["c"]
            for row in rows
            if row.get("c") is not None and row["c"] not in visited
        }
        if len(next_frontier) > remaining:
            next_frontier = set(sorted(next_frontier)[:remaining])
        visited.update(next_frontier)
        candidate_count += len(next_frontier)
        frontier = next_frontier

    visited.discard(root)
    return sorted(visited)


def blast_radius(g, ev: DesignationEvent, dk: str, candidates: list[str]) -> list[dict]:
    pack = get_pack(ev.authority)
    designated_canon = canon_of(g, ev.entity_id)
    impacted = []
    for canon in sorted(set(candidates)):
        # The designated person is the cause of the impact, not an affected company.
        if canon == designated_canon:
            continue
        rows = ro(g, REPRESENTATIVE, {"canon": canon})
        if not rows:
            continue
        entity_id = rows[0]["entity_id"]
        before = evaluate(g, entity_id, ev.listed_on, pack, exclude=(dk,))
        after = evaluate(g, entity_id, ev.listed_on, pack)
        if before.verdict != "BLOCKED" and after.verdict == "BLOCKED":
            impacted.append(
                {
                    "entity_id": entity_id,
                    "name": rows[0]["name"],
                    "pack": pack.id,
                    "before": before.verdict,
                    "after": after.verdict,
                }
            )
    return impacted
