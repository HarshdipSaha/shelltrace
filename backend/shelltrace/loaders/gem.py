from __future__ import annotations

import hashlib, json
from pathlib import Path

from .common import EdgeRow, NodeRow, normalise_pct


def _first(props, name): return (props.get(name) or [None])[0]


def parse_gem(path: str | Path):
    nodes, raw_ownership, dropped = {}, [], 0
    with Path(path).open(encoding="utf8") as handle:
        for raw in handle:
            item = json.loads(raw); props = item.get("properties") or {}; schema = item.get("schema")
            if schema == "Person": dropped += 1
            elif schema in {"Company", "Organization"}:
                lei = _first(props, "leiCode"); nid = f"lei:{lei}" if lei else f"gem:{item['id']}"
                nodes[item["id"]] = NodeRow(nid, "Company", item.get("caption") or nid, {"src": "gem", "src_record": item["id"], "lei": lei})
            elif schema == "Ownership": raw_ownership.append((item, props))
    edges=[]
    for item, props in raw_ownership:
        owner, asset = _first(props,"owner"), _first(props,"asset")
        if owner not in nodes or asset not in nodes: continue
        values = {"valid_from": _first(props,"startDate"), "valid_to": _first(props,"endDate"), "src":"gem", "src_record":item["id"]}
        if str(_first(props,"share_imputed")).lower() in {"true","1","yes"}:
            values["data_error"]="imputed_or_unverified_share"
        else:
            try: values.update({"pct": normalise_pct(_first(props,"percentage"),"percent"), "pct_basis":"shareholding"})
            except Exception: values["data_error"]="invalid_percentage"
        edges.append(EdgeRow(nodes[owner].id,nodes[asset].id,"OWNS","gem:"+hashlib.sha1(item["id"].encode()).hexdigest()[:16],values))
    return list(nodes.values()), edges, dropped
