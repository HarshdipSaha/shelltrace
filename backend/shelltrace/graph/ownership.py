from __future__ import annotations

import time
from collections import defaultdict
from typing import Any

from ..db import ro
from ..models import PackResult, RulePack
from .reference import crosses

ECONOMIC_EXPOSURE_HOLDING_ROW_BUDGET = 5_000
ECONOMIC_EXPOSURE_PATH_EXPANSION_BUDGET = 20_000


class EntityNotFound(KeyError):
    """Raised when an entity ID is absent from the graph."""


VALID = (
    "($ignore_time OR ((r.valid_from IS NULL OR r.valid_from <= $as_of) "
    "AND (r.valid_to IS NULL OR r.valid_to >= $as_of)))"
)

SCOPE_STEP = f"""
MATCH (o:Entity)-[r:OWNS|CONTROLS]->(x:Entity)
WHERE x.canon IN $frontier AND NOT r.k IN $exclude AND {VALID}
RETURN DISTINCT o.canon AS c"""

SEEDS = """
MATCH (e:Entity)-[d:DESIGNATED]->(p:Program)
WHERE e.canon IN $scope AND p.authority IN $authorities AND NOT d.k IN $exclude
  AND ($ignore_time OR (d.listed_on <= $as_of AND (d.delisted_on IS NULL OR d.delisted_on > $as_of)))
RETURN e.canon AS c, collect(d.k) AS ks"""

ROUND_CYPHER = f"""
MATCH (o:Entity)-[r:OWNS]->(x:Entity)
WHERE x.canon IN $scope AND NOT x.canon IN $done AND r.pct_basis IN $basis
  AND NOT r.k IN $exclude AND {VALID}
WITH x.canon AS c, o.canon AS oc, min(r.pct) AS pmin, max(r.pct) AS pmax, collect(r.k) AS ks
WITH c, oc IN $blocked AS ob, pmin, pmax, ks
WITH c,
     sum(CASE WHEN ob AND pmax IS NOT NULL THEN pmin ELSE 0.0 END) AS lo_b,
     sum(CASE WHEN ob AND pmax IS NOT NULL THEN pmax ELSE 0.0 END) AS hi_b,
     sum(CASE WHEN NOT ob AND pmin IS NOT NULL THEN pmin ELSE 0.0 END) AS other_min,
     sum(CASE WHEN ob AND pmax IS NULL THEN 1 ELSE 0 END) AS unk_b,
     collect(CASE WHEN ob AND pmax IS NOT NULL THEN ks ELSE NULL END) AS kss
RETURN c, lo_b AS lo,
       CASE WHEN unk_b > 0 THEN hi_b + CASE WHEN 100.0 - hi_b - other_min > 0
            THEN 100.0 - hi_b - other_min ELSE 0.0 END ELSE hi_b END AS hi,
       kss"""

CONTROL_STEP = f"""
MATCH (a:Entity)-[r:CONTROLS]->(b:Entity)
WHERE a.canon IN $from AND b.canon IN $scope AND NOT b.canon IN $stop
  AND NOT r.k IN $exclude AND {VALID}
RETURN b.canon AS c, collect(r.k) AS ks"""

DECISIVE = f"""
MATCH (o:Entity)-[r:OWNS]->(x:Entity)
WHERE x.canon IN $frontier AND o.canon IN $possible AND r.pct_basis IN $basis
  AND NOT r.k IN $exclude AND {VALID}
WITH x.canon AS c, o.canon AS oc, min(r.pct) AS pmin, max(r.pct) AS pmax, collect(r.k) AS ks
RETURN c, oc, pmin, pmax, ks"""

OWNER_OF = """
MATCH (o:Entity)-[r:OWNS]->(:Entity)
WHERE r.k IN $keys
RETURN r.k AS k, o.canon AS oc, r.pct_basis AS basis"""

DATA_ERRORS = f"""
MATCH (o:Entity)-[r:OWNS]->(x:Entity)
WHERE x.canon IN $scope AND r.pct IS NOT NULL AND {VALID}
WITH x.canon AS c, o.canon AS oc, min(r.pct) AS p
WITH c, sum(p) AS s WHERE s > 100.000000001
RETURN c"""

ECON = f"""
MATCH (o:Entity)-[r:OWNS]->(x:Entity)
WHERE o.canon IN $scope AND x.canon IN $scope AND r.pct IS NOT NULL
  AND NOT r.k IN $exclude AND {VALID}
WITH o.canon AS owner, x.canon AS asset, max(r.pct) AS pct
RETURN owner, asset, pct
LIMIT $row_limit"""


def _ctx(as_of: str, exclude: tuple[str, ...], ignore_time: bool) -> dict[str, Any]:
    return {"as_of": as_of, "exclude": list(exclude), "ignore_time": ignore_time}


def canon_of(g, entity_id: str) -> str:
    result = ro(g, "MATCH (e:Entity {id:$id}) RETURN e.canon AS c", {"id": entity_id})
    if not result:
        raise EntityNotFound(entity_id)
    return result[0]["c"]


def upstream_scope(
    g,
    canon: str,
    as_of: str,
    max_hops: int,
    exclude: tuple[str, ...] = (),
    ignore_time: bool = False,
    cap: int = 500,
) -> tuple[list[str], bool]:
    seen = {canon}
    frontier = [canon]
    hop_limit = max(1, min(6, int(max_hops)))
    node_limit = max(1, int(cap))
    context = _ctx(as_of, exclude, ignore_time)

    for _ in range(hop_limit):
        rows = ro(g, SCOPE_STEP, {**context, "frontier": frontier})
        next_frontier = sorted({row["c"] for row in rows} - seen)
        if not next_frontier:
            break
        seen.update(next_frontier)
        frontier = next_frontier
        if len(seen) > node_limit:
            ordered = sorted(seen)
            limited = ordered[:node_limit]
            if canon not in limited:
                limited[-1] = canon
            return sorted(set(limited)), True
    return sorted(seen), False


def seeds_in_scope(
    g,
    scope: list[str],
    authorities: tuple[str, ...] | list[str],
    as_of: str,
    exclude: tuple[str, ...] = (),
    ignore_time: bool = False,
) -> dict[str, list[str]]:
    rows = ro(
        g,
        SEEDS,
        {
            **_ctx(as_of, exclude, ignore_time),
            "scope": scope,
            "authorities": list(authorities),
        },
    )
    return {row["c"]: sorted(row["ks"] or []) for row in rows}


def _flat(keys_by_group: list[list[str] | None] | None) -> list[str]:
    return [key for group in (keys_by_group or []) if group for key in group]


def _fixpoint(
    g,
    scope: list[str],
    seeds: set[str],
    pack: RulePack,
    context: dict[str, Any],
    *,
    upper: bool,
) -> tuple[set[str], dict[str, list[str]], int]:
    blocked = set(seeds)
    proof: dict[str, list[str]] = {}
    rounds = 0
    for rounds in range(1, len(scope) + 2):
        rows = ro(
            g,
            ROUND_CYPHER,
            {
                **context,
                "scope": scope,
                "done": sorted(blocked),
                "blocked": sorted(blocked),
                "basis": list(pack.basis_accepted),
            },
        )
        newly = {
            row["c"]: sorted(set(_flat(row.get("kss"))))
            for row in rows
            if crosses(float(row["hi"] if upper else row["lo"]), pack)
        }
        if not newly:
            break
        blocked.update(newly)
        proof.update(newly)
    return blocked, proof, rounds


def _decisive_keys(
    g,
    target: str,
    possible: set[str],
    definite: set[str],
    pack: RulePack,
    context: dict[str, Any],
    max_hops: int,
) -> list[str]:
    keys: set[str] = set()
    visited = {target}
    frontier = {target}
    for _ in range(max_hops):
        rows = ro(
            g,
            DECISIVE,
            {
                **context,
                "frontier": sorted(frontier),
                "possible": sorted(possible),
                "basis": list(pack.basis_accepted),
            },
        )
        next_frontier: set[str] = set()
        for row in rows:
            owner = row["oc"]
            if row["pmax"] is None or row["pmin"] != row["pmax"] or owner not in definite:
                keys.update(row["ks"] or [])
            if owner not in definite and owner not in visited:
                next_frontier.add(owner)
        visited.update(next_frontier)
        frontier = next_frontier
        if not frontier:
            break
    return sorted(keys)


def _target_share(
    g,
    canon: str,
    blocked: set[str],
    scope: list[str],
    pack: RulePack,
    context: dict[str, Any],
) -> tuple[float, float]:
    rows = ro(
        g,
        ROUND_CYPHER,
        {
            **context,
            "scope": [canon],
            "done": [],
            "blocked": sorted(blocked),
            "basis": list(pack.basis_accepted),
        },
    )
    return (float(rows[0]["lo"]), float(rows[0]["hi"])) if rows else (0.0, 0.0)


def _control_closure(
    g,
    scope: list[str],
    blocked: set[str],
    context: dict[str, Any],
) -> tuple[set[str], set[str]]:
    presumed: set[str] = set()
    evidence: set[str] = set()
    frontier = set(blocked)
    while frontier:
        rows = ro(
            g,
            CONTROL_STEP,
            {
                **context,
                "from": sorted(frontier),
                "scope": scope,
                "stop": sorted(blocked),
            },
        )
        next_frontier: set[str] = set()
        for row in rows:
            evidence.update(row["ks"] or [])
            if row["c"] not in presumed:
                next_frontier.add(row["c"])
        presumed.update(next_frontier)
        frontier = next_frontier
    return presumed, evidence


def _proof_closure(
    g,
    target: str,
    proof: dict[str, list[str]],
    seeds: dict[str, list[str]],
    context: dict[str, Any],
) -> tuple[list[str], list[str]]:
    proof_keys = sorted({key for keys in proof.values() for key in keys})
    owner_rows = ro(g, OWNER_OF, {**context, "keys": proof_keys}) if proof_keys else []
    owners = {row["k"]: row["oc"] for row in owner_rows}
    edge_bases = {row["k"]: row["basis"] for row in owner_rows}

    evidence: set[str] = set()
    pending = [target]
    seen: set[str] = set()
    while pending:
        asset = pending.pop()
        if asset in seen:
            continue
        seen.add(asset)
        if asset in seeds:
            evidence.update(seeds[asset])
            continue
        for key in proof.get(asset, []):
            evidence.add(key)
            owner = owners.get(key)
            if owner is not None:
                pending.append(owner)

    caveats = []
    if any(edge_bases.get(key) == "accounting_consolidation" for key in evidence):
        caveats.append("Proof uses accounting-consolidation percentages.")
    return sorted(evidence), caveats


def _data_errors(g, scope: list[str], context: dict[str, Any]) -> list[str]:
    return sorted(row["c"] for row in ro(g, DATA_ERRORS, {**context, "scope": scope}))


def _economic_exposure(
    g,
    target: str,
    scope: list[str],
    seeds: list[str],
    context: dict[str, Any],
    max_hops: int,
) -> tuple[float | None, str | None]:
    if not seeds:
        return None, None
    rows = ro(
        g,
        ECON,
        {
            **context,
            "scope": scope,
            "row_limit": ECONOMIC_EXPOSURE_HOLDING_ROW_BUDGET + 1,
        },
    )
    if len(rows) > ECONOMIC_EXPOSURE_HOLDING_ROW_BUDGET:
        return (
            None,
            "Economic exposure unavailable: holding row limit "
            f"({ECONOMIC_EXPOSURE_HOLDING_ROW_BUDGET}) exceeded.",
        )
    adjacency: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for row in rows:
        adjacency[row["owner"]].append((row["asset"], float(row["pct"]) / 100.0))

    exposure = 0.0
    path_expansions = 0
    for seed in seeds:
        pending = [(seed, 1.0, 0, frozenset({seed}))]
        while pending:
            owner, share, hops, visited = pending.pop()
            if hops >= max_hops:
                continue
            for asset, pct in adjacency.get(owner, ()):
                path_expansions += 1
                if path_expansions > ECONOMIC_EXPOSURE_PATH_EXPANSION_BUDGET:
                    return (
                        None,
                        "Economic exposure unavailable: path expansion limit "
                        f"({ECONOMIC_EXPOSURE_PATH_EXPANSION_BUDGET}) exceeded.",
                    )
                if asset in visited:
                    continue
                path_share = share * pct
                if asset == target:
                    exposure += path_share
                else:
                    pending.append((asset, path_share, hops + 1, visited | {asset}))
    return exposure, None


def _result(
    *,
    pack: RulePack,
    entity_id: str,
    canon: str,
    as_of: str,
    max_hops: int,
    verdict: str,
    lo: float,
    hi: float,
    proof: list[str],
    decisive: list[str],
    decisive_kind: str,
    presumptions: set[str],
    seeds: list[str],
    scope: list[str],
    truncated: bool,
    data_errors: list[str],
    caveats: list[str],
    economic_exposure: float | None,
    rounds: int,
    latency_ms: int,
) -> PackResult:
    return PackResult(
        rulepack=pack.id,
        version=pack.version,
        entity_id=entity_id,
        canon=canon,
        as_of=as_of,
        max_hops=max_hops,
        verdict=verdict,
        lo=lo,
        hi=hi,
        threshold=pack.threshold,
        inclusive=pack.inclusive,
        proof=sorted(proof),
        decisive=sorted(decisive),
        decisive_kind=decisive_kind,
        presumptions=sorted(presumptions),
        seeds=sorted(seeds),
        scope_size=len(scope),
        scope_truncated=truncated,
        data_errors=sorted(data_errors),
        caveats=sorted(set(caveats)),
        economic_exposure=economic_exposure,
        rounds=rounds,
        latency_ms=latency_ms,
        interpretation_note=pack.interpretation_note,
    )


def evaluate(
    g,
    entity_id: str,
    as_of: str,
    pack: RulePack,
    max_hops: int = 6,
    exclude: tuple[str, ...] = (),
    ignore_time: bool = False,
    counterfactuals: bool = False,
) -> PackResult:
    """Evaluate ownership intervals and control presumptions for one entity."""
    started = time.perf_counter()
    canon = canon_of(g, entity_id)
    effective_hops = max(1, min(6, int(max_hops)))
    context = _ctx(as_of, exclude, ignore_time)
    scope, truncated = upstream_scope(
        g, canon, as_of, effective_hops, exclude=exclude, ignore_time=ignore_time
    )
    seeds = seeds_in_scope(
        g,
        scope,
        pack.authorities,
        as_of,
        exclude=exclude,
        ignore_time=ignore_time,
    )
    errors = _data_errors(g, scope, context)
    all_seed_canons = sorted(seeds)
    economic_exposure, exposure_caveat = _economic_exposure(
        g, canon, scope, all_seed_canons, context, effective_hops
    )

    if canon in seeds:
        proof = sorted(seeds[canon])
        decisive: list[str] = []
        if counterfactuals:
            for key in proof[:20]:
                alternate = evaluate(
                    g,
                    entity_id,
                    as_of,
                    pack,
                    max_hops=effective_hops,
                    exclude=tuple(sorted(set(exclude) | {key})),
                    ignore_time=ignore_time,
                    counterfactuals=False,
                )
                if alternate.verdict != "BLOCKED":
                    decisive.append(key)
        elapsed = int((time.perf_counter() - started) * 1000)
        return _result(
            pack=pack,
            entity_id=entity_id,
            canon=canon,
            as_of=as_of,
            max_hops=effective_hops,
            verdict="BLOCKED",
            lo=100.0,
            hi=100.0,
            proof=proof,
            decisive=decisive,
            decisive_kind="counterfactual" if decisive else "none",
            presumptions=set(),
            seeds=[canon],
            scope=scope,
            truncated=truncated,
            data_errors=errors,
            caveats=[exposure_caveat] if exposure_caveat else [],
            economic_exposure=economic_exposure,
            rounds=0,
            latency_ms=elapsed,
        )

    if pack.aggregate:
        seed_groups = [set(seeds)]
    else:
        seed_groups = [{seed} for seed in all_seed_canons]
    if not seed_groups:
        seed_groups = [set()]

    best: tuple[float, set[str], dict[str, list[str]], set[str]] | None = None
    possible: set[str] = set()
    definite_groups: list[set[str]] = []
    possible_groups: list[set[str]] = []
    upper_target = 0.0
    rounds = 0
    for group in seed_groups:
        definite, proof, definite_rounds = _fixpoint(
            g, scope, group, pack, context, upper=False
        )
        maybe, _, possible_rounds = _fixpoint(
            g, scope, group, pack, context, upper=True
        )
        definite_groups.append(definite)
        possible_groups.append(maybe)
        lower_target, _ = _target_share(g, canon, definite, scope, pack, context)
        _, high_target = _target_share(g, canon, maybe, scope, pack, context)
        possible.update(maybe)
        upper_target = max(upper_target, high_target)
        rounds = max(rounds, definite_rounds, possible_rounds)
        if best is None or lower_target > best[0] or canon in definite:
            best = (lower_target, definite, proof, group)

    assert best is not None
    lower_target, definite, proof, selected_group = best
    selected_seeds = {seed: seeds[seed] for seed in selected_group if seed in seeds}
    if pack.control_limb:
        presumed: set[str] = set()
        presumption_keys: set[str] = set()
        for group in definite_groups:
            group_presumed, group_keys = _control_closure(g, scope, group, context)
            presumed.update(group_presumed)
            presumption_keys.update(group_keys)
    else:
        presumed, presumption_keys = set(), set()

    if canon in definite:
        proof_keys, caveats = _proof_closure(g, canon, proof, selected_seeds, context)
        verdict = "BLOCKED"
        decisive = []
        decisive_kind = "none"
    elif canon in possible:
        decisive_keys: set[str] = set()
        for group_definite, group_possible in zip(definite_groups, possible_groups):
            if canon not in group_possible or canon in group_definite:
                continue
            decisive_keys.update(
                _decisive_keys(
                    g,
                    canon,
                    group_possible,
                    group_definite,
                    pack,
                    context,
                    effective_hops,
                )
            )
        proof_keys, caveats = [], []
        verdict = "INDETERMINATE"
        decisive = sorted(decisive_keys)
        decisive_kind = "unknown_or_conflict"
    elif canon in presumed:
        proof_keys, caveats = [], []
        verdict = "PRESUMED_CONTROLLED"
        decisive = []
        decisive_kind = "none"
    else:
        proof_keys, caveats = [], []
        verdict = "NOT_BLOCKED"
        decisive = []
        decisive_kind = "none"

    used_seeds = sorted(selected_group)
    if exposure_caveat:
        caveats.append(exposure_caveat)
    if verdict == "BLOCKED" and counterfactuals:
        for key in proof_keys[:20]:
            alternate = evaluate(
                g,
                entity_id,
                as_of,
                pack,
                max_hops=effective_hops,
                exclude=tuple(sorted(set(exclude) | {key})),
                ignore_time=ignore_time,
                counterfactuals=False,
            )
            if alternate.verdict != "BLOCKED":
                decisive.append(key)
        if decisive:
            decisive_kind = "counterfactual"

    elapsed = int((time.perf_counter() - started) * 1000)
    return _result(
        pack=pack,
        entity_id=entity_id,
        canon=canon,
        as_of=as_of,
        max_hops=effective_hops,
        verdict=verdict,
        lo=lower_target,
        hi=upper_target,
        proof=proof_keys,
        decisive=decisive,
        decisive_kind=decisive_kind,
        presumptions=presumption_keys,
        seeds=used_seeds,
        scope=scope,
        truncated=truncated,
        data_errors=errors,
        caveats=caveats,
        economic_exposure=economic_exposure,
        rounds=rounds,
        latency_ms=elapsed,
    )
