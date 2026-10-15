from .db import rw


INDEXES = [
    "CREATE INDEX FOR (e:Entity) ON (e.id)",
    "CREATE INDEX FOR (e:Entity) ON (e.canon)",
    "CREATE INDEX FOR (e:Entity) ON (e.norm_name)",
    "CREATE INDEX FOR (e:Entity) ON (e.lei)",
    "CREATE INDEX FOR (e:Entity) ON (e.imo)",
    "CREATE INDEX FOR (e:Entity) ON (e.core)",
    "CREATE INDEX FOR (e:Entity) ON (e.phon)",
    "CREATE INDEX FOR (p:Program) ON (p.id)",
    "CREATE INDEX FOR (c:Case) ON (c.id)",
    "CREATE INDEX FOR (c:Case) ON (c.entity_id)",
    "CREATE INDEX FOR (c:Case) ON (c.canon)",
    "CREATE INDEX FOR ()-[r:OWNS]-() ON (r.k)",
    "CREATE FULLTEXT INDEX FOR (n:Entity) ON (n.name)",
]


def ensure_schema(g) -> list[str]:
    log = []
    for statement in INDEXES:
        try:
            rw(g, statement)
            log.append(f"ok {statement}")
        except Exception as exc:
            log.append(f"skip {type(exc).__name__} {statement}")
    return log
