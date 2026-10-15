from __future__ import annotations

import json
from datetime import datetime, timezone
from itertools import combinations

from rapidfuzz import fuzz
from rapidfuzz.distance import JaroWinkler

from ..db import graph_operation_lock, ro, rw
from ..models import AliasCandidate
from ..names import core
from .clusters import recompute_clusters
from .ownership import canon_of


BLOCKING_KEYS = ("lei", "imo", "reg_no", "core", "phon")
MAX_BLOCKING_GROUP = 10
MAX_CLUSTER = 25
PENDING_MIN = 0.85


class MergeNeedsConfirmation(Exception):
    """Raised when joining two established alias clusters needs review."""


class ClusterTooLarge(Exception):
    """Raised when an accepted link would exceed the cluster size cap."""


class IdentifierConflict(Exception):
    """Raised when acceptance conflicts with a strong identifier."""


def score_pair(a: dict, b: dict) -> tuple[float, str, str]:
    matching_identifiers = []
    for field in ("lei", "imo"):
        left, right = a.get(field), b.get(field)
        if left and right:
            if left != right:
                return 0.0, "rejected", f"identifier_conflict:{field}"
            matching_identifiers.append(field)

    country_a, country_b = a.get("country"), b.get("country")
    if (
        a.get("reg_no")
        and b.get("reg_no")
        and country_a
        and country_b
        and country_a == country_b
    ):
        if a["reg_no"] != b["reg_no"]:
            return 0.0, "rejected", "identifier_conflict:reg_no"
        matching_identifiers.append("reg_no")

    if matching_identifiers:
        return 1.0, "accepted", f"identifier_match:{matching_identifiers[0]}"

    core_a, core_b = core(a.get("name", "")), core(b.get("name", ""))
    if not core_a or not core_b:
        return 0.0, "none", "below_threshold"
    score = max(
        fuzz.token_set_ratio(core_a, core_b) / 100.0,
        JaroWinkler.similarity(core_a, core_b),
    )
    if a.get("country") and b.get("country") and a["country"] != b["country"]:
        score -= 0.10
    score = round(max(0.0, score), 3)
    if score >= PENDING_MIN:
        return score, "pending", "name_core_match"
    return score, "none", "below_threshold"


def _candidate_features(a: dict, b: dict, reason: str) -> dict[str, str]:
    if reason.startswith("identifier_conflict:"):
        return {"identifier_conflict": reason.split(":", 1)[1]}
    if reason.startswith("identifier_match:"):
        return {"identifier_match": reason.split(":", 1)[1]}
    if reason == "name_core_match":
        return {"name_core": core(a.get("name", ""))}
    return {}


def _parse_features(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _as_candidate(row: dict) -> AliasCandidate:
    return AliasCandidate(
        a_id=row["a_id"],
        a_name=row["a_name"],
        b_id=row["b_id"],
        b_name=row["b_name"],
        score=float(row["score"]),
        state=row["state"],
        reason=row["reason"],
        touches_designated=bool(row["touches_designated"]),
        features=_parse_features(row.get("features_json")),
    )


def _candidate_listing_query(scope: bool = False, anchored: bool = False) -> str:
    anchor = "(a:Entity {id:$id})" if anchored else "(a:Entity)"
    scope_filter = "a.canon IN $scope AND " if scope else ""
    return (
        f"MATCH {anchor}-[c:CANDIDATE_SAME_AS]-(b:Entity)\n"
        f"WHERE {scope_filter}c.state IN ['pending', 'rejected']\n"
        "OPTIONAL MATCH (b)-[d:DESIGNATED]->(p:Program)\n"
        "WHERE p.authority IN $authorities AND d.delisted_on IS NULL\n"
        "WITH a, b, c, count(d) > 0 AS touches\n"
        "RETURN a.id AS a_id, a.name AS a_name, b.id AS b_id, b.name AS b_name,\n"
        "       c.score AS score, c.state AS state, c.reason AS reason,\n"
        "       c.features_json AS features_json, touches AS touches_designated\n"
        "ORDER BY score DESC, b_id ASC LIMIT $limit"
    )


def list_candidates(
    g,
    entity_id: str,
    authorities: tuple[str, ...] | list[str] = ("OFAC", "EU", "UK"),
    limit: int = 10,
) -> list[AliasCandidate]:
    bounded_limit = max(1, min(10, int(limit)))
    rows = ro(
        g,
        _candidate_listing_query(anchored=True),
        {"id": entity_id, "authorities": list(authorities), "limit": bounded_limit},
    )
    return [_as_candidate(row) for row in rows]


def pending_to_designated(
    g, scope: list[str], authorities: tuple[str, ...] | list[str]
) -> list[AliasCandidate]:
    query = _candidate_listing_query(scope=True).replace(
        "ORDER BY score DESC, b_id ASC LIMIT $limit", "ORDER BY score DESC, a_id ASC, b_id ASC"
    )
    return [
        _as_candidate(row)
        for row in ro(g, query, {"scope": scope, "authorities": list(authorities)})
        if row["state"] == "pending" and row["touches_designated"]
    ]


def _candidate_key(a_id: str, b_id: str) -> str:
    return "cand:" + "|".join(sorted((a_id, b_id)))


def _store_candidate(
    g,
    a_id: str,
    b_id: str,
    score: float,
    state: str,
    reason: str,
    features: dict,
) -> None:
    left_id, right_id = sorted((a_id, b_id))
    params = {
        "a_id": left_id,
        "b_id": right_id,
        "k": _candidate_key(left_id, right_id),
        "score": score,
        "state": state,
        "reason": reason,
        "features_json": json.dumps(features, sort_keys=True, separators=(",", ":")),
    }
    rw(
        g,
        "MATCH (a:Entity {id:$a_id}), (b:Entity {id:$b_id}) "
        "OPTIONAL MATCH (a)-[same:SAME_AS]-(b) "
        "WITH a, b, same WHERE same IS NULL "
        "MERGE (a)-[c:CANDIDATE_SAME_AS]-(b) "
        "WITH c, c.state = 'rejected' AS preserve_rejection "
        "SET c.k=$k, c.score=CASE WHEN preserve_rejection THEN c.score ELSE $score END, "
        "c.state=CASE WHEN preserve_rejection THEN c.state ELSE $state END, "
        "c.reason=CASE WHEN preserve_rejection THEN c.reason ELSE $reason END, "
        "c.features_json=CASE WHEN preserve_rejection THEN c.features_json ELSE $features_json END",
        params,
    )


def generate_candidates(g) -> dict[str, int]:
    by_id: dict[str, dict] = {}
    pair_blocks: dict[tuple[str, str], set[str]] = {}
    for blocking_key in BLOCKING_KEYS:
        query = (
            "MATCH (e:Entity) "
            f"WHERE e.kind <> 'Address' AND e.{blocking_key} IS NOT NULL AND e.{blocking_key} <> '' "
            f"WITH e.{blocking_key} AS key, collect({{id:e.id, name:e.name, country:e.country, "
            "lei:e.lei, imo:e.imo, reg_no:e.reg_no}) AS es "
            "WHERE size(es) > 1 AND size(es) <= $max_group RETURN es"
        )
        for row in ro(g, query, {"max_group": MAX_BLOCKING_GROUP}):
            entities = row["es"]
            for entity in entities:
                by_id[entity["id"]] = entity
            for left, right in combinations(sorted(entities, key=lambda item: item["id"]), 2):
                pair = (left["id"], right["id"])
                pair_blocks.setdefault(pair, set()).add(blocking_key)

    accepted_pairs = {
        tuple(sorted((row["a_id"], row["b_id"])))
        for row in ro(
            g,
            "MATCH (a:Entity)-[:SAME_AS]->(b:Entity) RETURN a.id AS a_id, b.id AS b_id",
        )
    }
    candidate_states = {
        tuple(sorted((row["a_id"], row["b_id"]))) : row["state"]
        for row in ro(
            g,
            "MATCH (a:Entity)-[c:CANDIDATE_SAME_AS]->(b:Entity) "
            "WHERE c.state IN ['pending', 'rejected'] "
            "RETURN a.id AS a_id, b.id AS b_id, c.state AS state",
        )
    }

    counts = {"accepted": 0, "pending": 0, "rejected": 0, "none": 0}
    for pair in sorted(pair_blocks):
        a_id, b_id = pair
        a, b = by_id[a_id], by_id[b_id]
        score, state, reason = score_pair(a, b)
        if pair in accepted_pairs:
            counts["accepted"] += 1
            continue
        # A rejection is a human decision or an established identifier conflict.
        # Re-scoring must never silently reopen it as pending.
        if candidate_states.get(pair) == "rejected":
            counts["rejected"] += 1
            continue
        if state == "accepted":
            try:
                decide(
                    g,
                    a_id,
                    b_id,
                    accept=True,
                    by="auto:identifier",
                    reason=reason,
                )
            except MergeNeedsConfirmation:
                _store_candidate(
                    g,
                    a_id,
                    b_id,
                    score,
                    "pending",
                    "confirmation_required:cluster_merge",
                    {
                        **_candidate_features(a, b, reason),
                        "confirmation_required": "cluster_merge",
                    },
                )
                counts["pending"] += 1
                continue
            except ClusterTooLarge:
                _store_candidate(
                    g,
                    a_id,
                    b_id,
                    score,
                    "rejected",
                    "cluster_size_limit",
                    {
                        **_candidate_features(a, b, reason),
                        "acceptance_blocked": "cluster_size_limit",
                    },
                )
                counts["rejected"] += 1
                continue
        elif state in {"pending", "rejected"}:
            _store_candidate(
                g,
                a_id,
                b_id,
                score,
                state,
                reason,
                _candidate_features(a, b, reason),
            )
        counts[state] += 1
    return counts


def _cluster_sizes(g, canon_a: str, canon_b: str) -> dict[str, int]:
    rows = ro(
        g,
        "MATCH (e:Entity) WHERE e.canon IN $canons "
        "RETURN e.canon AS canon, count(*) AS size",
        {"canons": sorted({canon_a, canon_b})},
    )
    return {row["canon"]: row["size"] for row in rows}


def decide(
    g,
    a_id: str,
    b_id: str,
    accept: bool,
    by: str,
    reason: str,
    confirm_merge: bool = False,
) -> dict:
    with graph_operation_lock(g) as locked_graph:
        return _decide_locked(
            locked_graph,
            a_id,
            b_id,
            accept,
            by,
            reason,
            confirm_merge,
        )


def _decide_locked(
    g,
    a_id: str,
    b_id: str,
    accept: bool,
    by: str,
    reason: str,
    confirm_merge: bool,
) -> dict:
    canon_a, canon_b = canon_of(g, a_id), canon_of(g, b_id)
    rows = ro(
        g,
        "MATCH (a:Entity {id:$a_id}), (b:Entity {id:$b_id}) "
        "RETURN properties(a) AS a, properties(b) AS b",
        {"a_id": a_id, "b_id": b_id},
    )
    if not rows:
        return {"accepted": False, "canon": canon_a}
    a, b = rows[0]["a"], rows[0]["b"]
    score, score_state, score_reason = score_pair(a, b)
    if accept and score_state == "rejected":
        raise IdentifierConflict(score_reason)

    if accept:
        sizes = _cluster_sizes(g, canon_a, canon_b)
        size_a, size_b = sizes.get(canon_a, 1), sizes.get(canon_b, 1)
        if canon_a != canon_b:
            if size_a > 1 and size_b > 1 and not confirm_merge:
                raise MergeNeedsConfirmation(f"Merging {size_a} and {size_b} entity clusters needs confirmation")
            if size_a + size_b > MAX_CLUSTER:
                raise ClusterTooLarge(f"Merged cluster would exceed {MAX_CLUSTER} entities")

        accepted_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        method = score_reason if score_reason != "below_threshold" else "manual"
        left_id, right_id = sorted((a_id, b_id))
        rw(
            g,
            "MATCH (a:Entity {id:$a_id}), (b:Entity {id:$b_id}) "
            "MERGE (a)-[r:SAME_AS {k:$k}]->(b) "
            "SET r.score=$score, r.method=$method, r.accepted_by=$by, "
            "r.accepted_at=coalesce(r.accepted_at,$accepted_at), r.reason=$reason, "
            "r.src='analyst', r.src_record=$k "
            "MERGE (b)-[rr:SAME_AS {k:$reverse_k}]->(a) "
            "SET rr.score=$score, rr.method=$method, rr.accepted_by=$by, "
            "rr.accepted_at=coalesce(rr.accepted_at,$accepted_at), rr.reason=$reason, "
            "rr.src='analyst', rr.src_record=$k",
            {
                "a_id": left_id,
                "b_id": right_id,
                "k": f"sa:{left_id}|{right_id}",
                "reverse_k": f"sa:{left_id}|{right_id}~r",
                "score": score,
                "method": method,
                "by": by,
                "accepted_at": accepted_at,
                "reason": reason,
            },
        )
        rw(
            g,
            "MATCH (a:Entity {id:$a_id})-[c:CANDIDATE_SAME_AS]-(b:Entity {id:$b_id}) DELETE c",
            {"a_id": a_id, "b_id": b_id},
        )
        recompute_clusters(g)
        return {"accepted": True, "canon": canon_of(g, a_id)}

    if canon_a == canon_b:
        raise ValueError("An accepted alias cannot be rejected as a candidate")
    _store_candidate(
        g,
        a_id,
        b_id,
        score,
        "rejected",
        reason,
        _candidate_features(a, b, score_reason),
    )
    return {"accepted": False, "canon": canon_of(g, a_id)}
