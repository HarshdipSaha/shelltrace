from ..db import ro, rw


RESET = "MATCH (e:Entity) SET e.cluster_id = NULL"
WCC = (
    "CALL algo.WCC({nodeLabels:['Entity'], relationshipTypes:['SAME_AS']}) "
    "YIELD node, componentId SET node.cluster_id = toString(componentId)"
)
CANON = (
    "MATCH (e:Entity) "
    "WITH coalesce(e.cluster_id, 'solo:' + e.id) AS c, min(e.id) AS rep, collect(e) AS es "
    "UNWIND es AS e SET e.canon = rep"
)
STATS = "MATCH (e:Entity) WITH e.canon AS c, count(*) AS n RETURN count(c) AS clusters, max(n) AS largest"


def recompute_clusters(g) -> dict:
    rw(g, RESET)
    rw(g, WCC)
    rw(g, CANON)
    return ro(g, STATS)[0]
