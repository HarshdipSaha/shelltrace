from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from ..models import RulePack


EPS = 1e-9


@dataclass(frozen=True)
class RefEdge:
    k: str
    src: str
    dst: str
    pct: float | None
    basis: str = "synthetic"


@dataclass(frozen=True)
class RefGraph:
    owns: tuple[RefEdge, ...]
    controls: tuple[RefEdge, ...]
    seeds: dict[str, tuple[str, ...]]


@dataclass(frozen=True)
class RefResult:
    verdict: str
    lo: float
    hi: float
    proof: frozenset[str]
    decisive: frozenset[str]
    presumptions: frozenset[str]
    data_errors: frozenset[str]


@dataclass
class _Pair:
    keys: list[str] = field(default_factory=list)
    pmin: float | None = None
    pmax: float | None = None


def crosses(value: float, pack: RulePack) -> bool:
    if pack.inclusive:
        return value >= pack.threshold
    return value > pack.threshold


def _pairs(edges: tuple[RefEdge, ...], accepted_basis: tuple[str, ...]) -> dict[str, dict[str, _Pair]]:
    """Group duplicate records into one (owner, asset) holding interval."""
    by_asset: dict[str, dict[str, _Pair]] = defaultdict(dict)
    for edge in edges:
        if edge.basis not in accepted_basis:
            continue
        pair = by_asset[edge.dst].setdefault(edge.src, _Pair())
        pair.keys.append(edge.k)
        if edge.pct is not None:
            pair.pmin = edge.pct if pair.pmin is None else min(pair.pmin, edge.pct)
            pair.pmax = edge.pct if pair.pmax is None else max(pair.pmax, edge.pct)
    return by_asset


def _share(asset: str, blocked: set[str], pairs: dict[str, dict[str, _Pair]]) -> tuple[float, float, list[str]]:
    lower = upper = other_min = 0.0
    has_blocked_unknown = False
    proof: list[str] = []
    for owner, holding in pairs.get(asset, {}).items():
        if owner in blocked:
            if holding.pmax is None:
                has_blocked_unknown = True
            else:
                # A non-None max implies that at least one duplicate has a
                # known percentage, so the corresponding minimum is known too.
                assert holding.pmin is not None
                lower += holding.pmin
                upper += holding.pmax
                proof.extend(holding.keys)
        elif holding.pmin is not None:
            other_min += holding.pmin

    if has_blocked_unknown:
        upper += max(0.0, 100.0 - upper - other_min)
    return lower, upper, proof


def _fixpoint(
    seeds: set[str],
    pairs: dict[str, dict[str, _Pair]],
    pack: RulePack,
    *,
    upper: bool,
) -> tuple[set[str], dict[str, list[str]], int]:
    blocked = set(seeds)
    proof: dict[str, list[str]] = {}
    rounds = 0
    while True:
        rounds += 1
        newly: dict[str, list[str]] = {}
        for asset in sorted(pairs.keys() - blocked):
            lower, high, keys = _share(asset, blocked, pairs)
            if crosses(high if upper else lower, pack):
                newly[asset] = keys
        if not newly:
            return blocked, proof, rounds
        blocked.update(newly)
        proof.update(newly)


def _decisive_keys(
    target: str,
    possible: set[str],
    definite: set[str],
    pairs: dict[str, dict[str, _Pair]],
) -> frozenset[str]:
    keys: set[str] = set()
    visited = {target}
    frontier = {target}
    while frontier:
        next_frontier: set[str] = set()
        for asset in frontier:
            for owner, holding in pairs.get(asset, {}).items():
                if owner not in possible:
                    continue
                if (
                    holding.pmax is None
                    or holding.pmin != holding.pmax
                    or owner not in definite
                ):
                    keys.update(holding.keys)
                if owner not in definite and owner not in visited:
                    next_frontier.add(owner)
        visited.update(next_frontier)
        frontier = next_frontier
    return frozenset(keys)


def _proof_closure(
    target: str,
    proof: dict[str, list[str]],
    owner_by_key: dict[str, str],
    seeds: dict[str, tuple[str, ...]],
) -> frozenset[str]:
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
        for key in proof.get(asset, ()):
            evidence.add(key)
            owner = owner_by_key.get(key)
            if owner is not None:
                pending.append(owner)
    return frozenset(evidence)


def _control_closure(
    blocked: set[str], controls: tuple[RefEdge, ...]
) -> tuple[set[str], frozenset[str]]:
    presumed: set[str] = set()
    evidence: set[str] = set()
    frontier = set(blocked)
    while frontier:
        outgoing = [edge for edge in controls if edge.src in frontier and edge.dst not in blocked]
        evidence.update(edge.k for edge in outgoing)
        next_frontier = {edge.dst for edge in outgoing if edge.dst not in presumed}
        presumed.update(next_frontier)
        frontier = next_frontier
    return presumed, frozenset(evidence)


def ref_evaluate(target: str, graph: RefGraph, pack: RulePack) -> RefResult:
    """Evaluate one target against an already date-filtered, canonical graph."""
    pairs = _pairs(graph.owns, pack.basis_accepted)
    owner_by_key = {edge.k: edge.src for edge in graph.owns}
    errors = frozenset(
        asset
        for asset, owners in pairs.items()
        if sum(pair.pmin for pair in owners.values() if pair.pmin is not None) > 100.0 + EPS
    )

    if target in graph.seeds:
        return RefResult(
            "BLOCKED",
            100.0,
            100.0,
            frozenset(graph.seeds[target]),
            frozenset(),
            frozenset(),
            errors,
        )

    if pack.aggregate:
        seed_groups = [set(graph.seeds)]
    else:
        seed_groups = [{seed} for seed in sorted(graph.seeds)]
    if not seed_groups:
        seed_groups = [set()]

    best: tuple[float, set[str], dict[str, list[str]], set[str]] | None = None
    possible: set[str] = set()
    definite_groups: list[set[str]] = []
    possible_groups: list[set[str]] = []
    upper_target = 0.0
    rounds = 0
    for group in seed_groups:
        definite, proof, definite_rounds = _fixpoint(group, pairs, pack, upper=False)
        maybe, _, possible_rounds = _fixpoint(group, pairs, pack, upper=True)
        definite_groups.append(definite)
        possible_groups.append(maybe)
        lower_target = _share(target, definite, pairs)[0]
        high_target = _share(target, maybe, pairs)[1]
        possible.update(maybe)
        upper_target = max(upper_target, high_target)
        rounds = max(rounds, definite_rounds, possible_rounds)
        if best is None or lower_target > best[0] or target in definite:
            best = (lower_target, definite, proof, group)

    assert best is not None
    lower_target, definite, proof, selected_group = best
    selected_seeds = {seed: graph.seeds[seed] for seed in selected_group if seed in graph.seeds}
    if pack.control_limb:
        presumed: set[str] = set()
        presumption_keys: set[str] = set()
        for group in definite_groups:
            group_presumed, group_keys = _control_closure(group, graph.controls)
            presumed.update(group_presumed)
            presumption_keys.update(group_keys)
        presumptions = frozenset(presumption_keys)
    else:
        presumed, presumptions = set(), frozenset()

    if target in definite:
        return RefResult(
            "BLOCKED",
            lower_target,
            upper_target,
            _proof_closure(target, proof, owner_by_key, selected_seeds),
            frozenset(),
            presumptions,
            errors,
        )

    if target in possible:
        decisive: set[str] = set()
        for group_definite, group_possible in zip(definite_groups, possible_groups):
            if target not in group_possible or target in group_definite:
                continue
            decisive.update(_decisive_keys(target, group_possible, group_definite, pairs))
        return RefResult(
            "INDETERMINATE",
            lower_target,
            upper_target,
            frozenset(),
            frozenset(decisive),
            presumptions,
            errors,
        )

    if target in presumed:
        return RefResult(
            "PRESUMED_CONTROLLED",
            lower_target,
            upper_target,
            frozenset(),
            frozenset(),
            presumptions,
            errors,
        )

    return RefResult(
        "NOT_BLOCKED",
        lower_target,
        upper_target,
        frozenset(),
        frozenset(),
        presumptions,
        errors,
    )
