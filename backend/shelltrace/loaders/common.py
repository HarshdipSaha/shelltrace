from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from typing import Any, Iterable

from ..db import rw
from ..names import core, norm, phon


class PctError(ValueError):
    pass


@dataclass(frozen=True)
class NodeRow:
    id: str
    label: str
    name: str
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EdgeRow:
    source: str
    target: str
    label: str
    key: str
    properties: dict[str, Any] = field(default_factory=dict)


def normalise_pct(value: Any, unit: str) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise PctError("boolean is not a percentage")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise PctError(f"invalid percentage: {value!r}") from exc
    if not isfinite(number):
        raise PctError("percentage must be finite")
    if unit == "fraction":
        number *= 100
    elif unit != "percent":
        raise PctError(f"unknown percentage unit: {unit}")
    if not 0 <= number <= 100:
        raise PctError(f"percentage out of range: {number}")
    return int(number) if number.is_integer() else number


def load_rows(g, nodes: Iterable[NodeRow], edges: Iterable[EdgeRow], snapshot: str,
              licence: str, batch_size: int = 500) -> dict[str, int]:
    """Idempotently load allowlisted rows and attach provenance to every fact."""
    nodes, edges = list(nodes), list(edges)
    if any(node.label == "Person" for node in nodes):
        raise ValueError("natural persons cannot be loaded into a real-data graph")
    allowed_nodes = {"Company", "Vessel", "Program"}
    allowed_edges = {"OWNS", "CONTROLS", "DESIGNATED"}
    if any(n.label not in allowed_nodes for n in nodes) or any(e.label not in allowed_edges for e in edges):
        raise ValueError("unsupported real-data graph label")
    for offset in range(0, len(nodes), batch_size):
        rows = []
        for node in nodes[offset:offset + batch_size]:
            props = dict(node.properties)
            rows.append({"id": node.id, "name": node.name, "kind": node.label,
                         "norm_name": norm(node.name), "core": core(node.name), "phon": phon(node.name), **props})
        for label in allowed_nodes:
            typed = [row for row in rows if row["kind"] == label]
            if typed:
                rw(g, f"UNWIND $rows AS r MERGE (e:Entity:{label} {{id:r.id}}) "
                      "SET e += r, e.canon=coalesce(e.canon,r.id), e.src=coalesce(r.src,'loader'), "
                      "e.src_record=coalesce(r.src_record,r.id), e.snapshot=$snapshot, e.licence=$licence",
                   {"rows": typed, "snapshot": snapshot, "licence": licence})
    for offset in range(0, len(edges), batch_size):
        for label in allowed_edges:
            typed = []
            for edge in edges[offset:offset + batch_size]:
                if edge.label == label:
                    typed.append({"a": edge.source, "b": edge.target, "k": edge.key, **edge.properties})
            if typed:
                rw(g, f"UNWIND $rows AS r MATCH (a:Entity {{id:r.a}}),(b:Entity {{id:r.b}}) "
                      f"MERGE (a)-[e:{label} {{k:r.k}}]->(b) SET e += r, e.src=coalesce(r.src,'loader'), "
                      "e.src_record=coalesce(r.src_record,r.k), e.snapshot=$snapshot, e.licence=$licence",
                   {"rows": typed, "snapshot": snapshot, "licence": licence})
    return {"nodes": len(nodes), "edges": len(edges)}
