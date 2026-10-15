from __future__ import annotations

from rapidfuzz import fuzz, process

from .db import ro
from .graph.ownership import EntityNotFound


DESIGNATED_NAMES = """
MATCH (e:Entity)-[d:DESIGNATED]->(p:Program)
WHERE p.authority IN $auth AND d.listed_on <= $as_of
  AND (d.delisted_on IS NULL OR d.delisted_on > $as_of)
RETURN DISTINCT e.id AS id, e.name AS name, p.authority AS authority"""


def screen_name(
    g, entity_id: str, authorities, as_of: str, cutoff: int = 90
) -> dict:
    rows = ro(
        g,
        "MATCH (e:Entity {id:$id}) RETURN e.name AS name",
        {"id": entity_id},
    )
    if not rows:
        raise EntityNotFound(entity_id)
    name = rows[0]["name"]
    pool = ro(g, DESIGNATED_NAMES, {"auth": list(authorities), "as_of": as_of})
    matches = process.extract(
        name,
        [item["name"] for item in pool],
        scorer=fuzz.token_set_ratio,
        score_cutoff=cutoff,
        limit=5,
    )
    return {
        "hit": bool(matches),
        "query": name,
        "matches": [
            {**pool[index], "score": score}
            for _, score, index in matches
        ],
    }
