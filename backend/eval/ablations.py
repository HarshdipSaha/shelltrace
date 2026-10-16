"""Deliberately weakened baselines; scores measure disposition agreement only."""
from shelltrace.screening import screen_name
from shelltrace.graph.trace import trace
from shelltrace.graph.ownership import evaluate, canon_of, upstream_scope
from shelltrace.graph.aliases import pending_to_designated
from shelltrace.graph.redflags import red_flags
from shelltrace.graph.evidence import evidence_get
from shelltrace.agent.authorise import authorise
from shelltrace.models import Bounds
from shelltrace.rulepacks import get_pack
from shelltrace.seed.synthetic import SNAP


def name_only(g, gc):
    return 'EXPOSED' if screen_name(g, gc.entity_id, gc.packs, gc.as_of)['hit'] else 'CLEAR_WITHIN_BOUNDS'


def path_only(g, gc):
    return 'EXPOSED' if trace(g, gc.entity_id, gc.as_of, 6, gc.packs) else 'CLEAR_WITHIN_BOUNDS'


def multiplicative(g, gc):
    result = trace(g, gc.entity_id, gc.as_of, 6, gc.packs)
    if result is None:
        return 'CLEAR_WITHIN_BOUNDS'
    product = 1.0
    for edge in result.edges:
        if edge.type == 'OWNS':
            product *= (edge.pct or 0.0) / 100
    return 'EXPOSED' if product * 100 >= 50 - 1e-9 else 'CLEAR_WITHIN_BOUNDS'


def _authorised(g, gc, *, ignore_time=False):
    packs = {p: evaluate(g, gc.entity_id, gc.as_of, get_pack(p), ignore_time=ignore_time) for p in gc.packs}
    flags = red_flags(g, gc.entity_id, gc.as_of, 6, gc.packs)
    scope, truncated = upstream_scope(g, canon_of(g, gc.entity_id), gc.as_of, 6)
    pending = pending_to_designated(g, scope, gc.packs)
    keys = {key for p in packs.values() for key in (*p.proof, *p.decisive, *p.presumptions)}
    keys.update(key for flag in flags for key in flag.evidence_keys)
    evidence = {e.k: e for e in evidence_get(g, sorted(keys))}
    bounds = Bounds(as_of=gc.as_of, max_hops=6, rel_scope=['OWNS', 'CONTROLS', 'SAME_AS (accepted)'], rulepacks=list(gc.packs), snapshot=SNAP, scope_nodes=len(scope), truncated=truncated or any(p.scope_truncated for p in packs.values()))
    return authorise(packs, flags, pending, evidence, bounds, []).disposition


def er_off(g_noalias, gc):
    return _authorised(g_noalias, gc)


def time_off(g, gc):
    return _authorised(g, gc, ignore_time=True)


ABLATIONS = {f.__name__: f for f in (name_only, path_only, multiplicative, er_off, time_off)}
