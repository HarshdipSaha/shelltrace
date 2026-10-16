from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .common import EdgeRow, NodeRow

AUTH_MAP = {"us_ofac_sdn": "OFAC", "eu_fsf": "EU", "gb_fcdo_sanctions": "UK"}
KEEP = {"Company": "Company", "Organization": "Company", "LegalEntity": "Company", "Vessel": "Vessel"}
LICENCE = "CC BY-NC 4.0 (OpenSanctions)"


def _first(props, *names):
    for name in names:
        value = props.get(name) or []
        if value:
            return value[0]
    return None


def _imo(value):
    return str(value).upper().replace("IMO", "").strip() if value else None


def _key(*parts):
    return "des:" + hashlib.sha1("|".join(map(str, parts)).encode()).hexdigest()[:16]


def parse_opensanctions(path: str | Path, datasets_to_authority=AUTH_MAP):
    """Stream a pinned FtM JSONL file; never ingest people or ownership facts."""
    kept, records, dropped = {}, [], 0
    with Path(path).open(encoding="utf8") as handle:
        for raw in handle:
            if not raw.strip():
                continue
            item = json.loads(raw)
            schema, props = item.get("schema"), item.get("properties") or {}
            if schema == "Person":
                dropped += 1
            elif schema in KEEP:
                lei = _first(props, "leiCode")
                entity_id = f"lei:{lei}" if lei else f"os:{item['id']}"
                datasets = item.get("datasets") or []
                source = datasets[0] if datasets else "unknown"
                kept[item["id"]] = entity_id
                records.append(NodeRow(entity_id, KEEP[schema], item.get("caption") or entity_id, {
                    "os_id": item["id"], "country": _first(props, "jurisdiction", "country"),
                    "lei": lei, "imo": _imo(_first(props, "imoNumber")),
                    "reg_no": _first(props, "registrationNumber"), "src": f"opensanctions:{source}",
                    "src_record": item["id"],
                }))
            elif schema == "Sanction":
                records.append(("sanction", item))
    nodes = [row for row in records if isinstance(row, NodeRow)]
    edges = []
    for row in records:
        if not isinstance(row, tuple):
            continue
        item = row[1]; props = item.get("properties") or {}
        target = _first(props, "entity")
        authority = next((datasets_to_authority[d] for d in item.get("datasets") or [] if d in datasets_to_authority), None)
        if target not in kept or not authority:
            continue
        listed = _first(props, "listingDate", "startDate") or (item.get("first_seen") or "")[:10]
        basis = "source" if _first(props, "listingDate", "startDate") else "first_seen"
        program = f"program:{authority.lower()}"
        edges.append(EdgeRow(kept[target], program, "DESIGNATED", _key(item["id"], kept[target], authority), {
            "authority": authority, "listed_on": listed, "listed_on_basis": basis,
            "delisted_on": _first(props, "endDate"), "reason": _first(props, "reason"),
            "src": f"opensanctions:{next((d for d in item.get('datasets') or [] if d in datasets_to_authority), 'unknown')}",
            "src_record": item["id"],
        }))
    return nodes, edges, dropped
