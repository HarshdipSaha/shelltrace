from __future__ import annotations

import csv
import hashlib
from collections import defaultdict, deque
from pathlib import Path

from .common import EdgeRow, normalise_pct

GLEIF_COLS = {"start": "Relationship.StartNode.NodeID", "end": "Relationship.EndNode.NodeID", "type": "Relationship.RelationshipType", "status": "Relationship.RelationshipStatus"}


def _date(value):
    return value[:10] if value else None


def _slot(row, prefix, field):
    return next((row.get(f"{prefix}.{i}.{field}") for i in range(1, 6)
                 if row.get(f"{prefix}.{i}.{field}")), None)


def _relationship_period(row):
    for i in range(1, 6):
        if row.get(f"Relationship.Period.{i}.periodType") == "RELATIONSHIP_PERIOD":
            return _date(row.get(f"Relationship.Period.{i}.startDate")), _date(row.get(f"Relationship.Period.{i}.endDate"))
    return None, None


def parse_gleif_rr(path: str | Path, keep_leis: set[str]):
    edges = []
    with Path(path).open(encoding="utf8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get(GLEIF_COLS["type"]) != "IS_DIRECTLY_CONSOLIDATED_BY" or row.get(GLEIF_COLS["status"]) != "ACTIVE":
                continue
            child, parent = row.get(GLEIF_COLS["start"]), row.get(GLEIF_COLS["end"])
            if not child or not parent or (keep_leis and child not in keep_leis and parent not in keep_leis):
                continue
            amount = _slot(row, "Relationship.Quantifiers", "QuantifierAmount")
            unit = _slot(row, "Relationship.Quantifiers", "QuantifierUnits")
            start, end = _relationship_period(row)
            props = {"basis": "accounting_consolidation", "valid_from": start, "valid_to": end,
                     "src": "gleif:rr", "src_record": f"{parent}>{child}"}
            if amount and str(unit).upper() == "PERCENTAGE":
                props.update({"pct": normalise_pct(amount, "percent"), "pct_basis": "accounting_consolidation"})
                label = "OWNS"
            else:
                props["data_error"] = "missing_quantifier_units" if amount else "missing_quantifier_amount"
                label = "CONTROLS"
            key = "gle:" + hashlib.sha1(f"{parent}|{child}|{label}|{start}".encode()).hexdigest()[:16]
            edges.append(EdgeRow(f"lei:{parent}", f"lei:{child}", label, key, props))
    return edges


def select_component(edges, seeds: set[str]):
    """Keep up to three downstream and one upstream control hops from seed LEIs."""
    down, up = defaultdict(set), defaultdict(set)
    for edge in edges:
        a, b = edge.source.removeprefix("lei:"), edge.target.removeprefix("lei:")
        down[a].add(b); up[b].add(a)
    reachable, q = set(seeds), deque((seed, 0) for seed in seeds)
    while q:
        node, depth = q.popleft()
        neighbours = down[node] if depth < 3 else set()
        for neighbour in neighbours:
            if neighbour not in reachable:
                reachable.add(neighbour); q.append((neighbour, depth + 1))
    # One upstream layer of the selected downward component, never recursive.
    return reachable | {parent for node in reachable for parent in up[node]}
