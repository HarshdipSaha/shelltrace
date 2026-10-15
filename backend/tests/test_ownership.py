from uuid import uuid4

import pytest

from shelltrace.db import rw
from shelltrace.graph import ownership
from shelltrace.graph.ownership import EntityNotFound, canon_of, evaluate, seeds_in_scope, upstream_scope
from shelltrace.rulepacks import EU, OFAC, UK


@pytest.mark.parametrize(
    ("entity_id", "as_of", "pack", "verdict"),
    [
        ("c_nordharbor", "2024-01-01", OFAC, "BLOCKED"),
        ("c_nordharbor", "2020-06-01", OFAC, "BLOCKED"),
        ("c_birch", "2024-01-01", OFAC, "BLOCKED"),
        ("c_birch", "2024-01-01", UK, "NOT_BLOCKED"),
        ("c_cedar", "2024-01-01", EU, "BLOCKED"),
        ("c_cedar", "2024-01-01", UK, "NOT_BLOCKED"),
        ("c_dune", "2024-01-01", OFAC, "INDETERMINATE"),
        ("c_elm", "2024-01-01", OFAC, "NOT_BLOCKED"),
        ("c_fjord", "2024-01-01", OFAC, "NOT_BLOCKED"),
        ("c_gamma", "2024-01-01", OFAC, "NOT_BLOCKED"),
        ("v_kestrel_star", "2024-01-01", UK, "BLOCKED"),
        ("c_larch", "2022-06-01", OFAC, "BLOCKED"),
        ("c_larch", "2024-01-01", OFAC, "NOT_BLOCKED"),
        ("c_maple", "2024-01-01", EU, "PRESUMED_CONTROLLED"),
        ("c_maple", "2024-01-01", OFAC, "NOT_BLOCKED"),
        ("c_rostok", "2024-01-01", UK, "BLOCKED"),
        ("c_nimbus", "2024-01-01", OFAC, "BLOCKED"),
        ("c_otter", "2024-01-01", OFAC, "INDETERMINATE"),
        ("c_juniper", "2024-01-01", OFAC, "NOT_BLOCKED"),
    ],
)
def test_golden_verdicts(store, golden_ws, entity_id, as_of, pack, verdict):
    result = evaluate(store.workspace(golden_ws), entity_id, as_of, pack)
    assert result.verdict == verdict


def test_hero_proof_uses_alias_chain_and_designation(store, golden_ws):
    result = evaluate(store.workspace(golden_ws), "c_nordharbor", "2024-01-01", OFAC)

    assert set(result.proof) == {
        "syn:G1-1",
        "syn:G1-2",
        "syn:G1-3",
        "syn:D-p_volkov-prog_ofac",
    }
    assert "syn:G2-1" not in result.proof
    assert result.rounds >= 3


def test_temporal_proof_switches_to_the_valid_direct_owner(store, golden_ws):
    result = evaluate(store.workspace(golden_ws), "c_nordharbor", "2020-06-01", OFAC)

    assert set(result.proof) == {"syn:G2-1", "syn:D-p_sokolov-prog_ofac"}


def test_intervals_and_decisive_keys_match_golden_expectations(store, golden_ws):
    graph = store.workspace(golden_ws)
    dune = evaluate(graph, "c_dune", "2024-01-01", OFAC)
    otter = evaluate(graph, "c_otter", "2024-01-01", OFAC)
    nimbus = evaluate(graph, "c_nimbus", "2024-01-01", OFAC)

    assert (dune.lo, dune.hi, dune.decisive, dune.decisive_kind) == (
        0.0,
        60.0,
        ["syn:G5-1"],
        "unknown_or_conflict",
    )
    assert (otter.lo, otter.hi, sorted(otter.decisive)) == (
        45.0,
        55.0,
        ["syn:G17-2a", "syn:G17-2b"],
    )
    assert (nimbus.lo, nimbus.hi) == (60.0, 60.0)


def test_boundary_dates_are_inclusive_for_validity_and_exclusive_for_delisting(store, golden_ws):
    graph = store.workspace(golden_ws)

    assert evaluate(graph, "c_nordharbor", "2020-12-31", OFAC).verdict == "BLOCKED"
    assert evaluate(graph, "c_larch", "2023-01-01", OFAC).verdict == "NOT_BLOCKED"
    assert evaluate(graph, "c_larch", "2020-01-01", OFAC).verdict == "BLOCKED"


def test_counterfactual_marks_decisive_records(store, golden_ws):
    result = evaluate(store.workspace(golden_ws), "c_birch", "2024-01-01", OFAC, counterfactuals=True)

    assert result.decisive_kind == "counterfactual"
    assert set(result.decisive) == {
        "syn:G3-1",
        "syn:G3-2",
        "syn:D-p_volkov-prog_ofac",
    }


def test_excluding_a_proof_edge_clears_the_result(store, golden_ws):
    result = evaluate(
        store.workspace(golden_ws),
        "c_nordharbor",
        "2024-01-01",
        OFAC,
        exclude=("syn:G1-2",),
    )

    assert result.verdict == "NOT_BLOCKED"


def test_accepted_aliases_resolve_to_one_canonical_entity(store, golden_ws):
    graph = store.workspace(golden_ws)

    assert canon_of(graph, "c_bluelagoon") == canon_of(graph, "c_bluelagoon_alias")


def test_economic_exposure_resolves_accepted_alias_endpoints(store, golden_ws):
    graph = store.workspace(golden_ws)

    canonical = evaluate(graph, "c_bluelagoon", "2024-01-01", OFAC)
    alias = evaluate(graph, "c_bluelagoon_alias", "2024-01-01", OFAC)

    assert canonical.economic_exposure == 0.8
    assert alias.economic_exposure == 0.8


def test_economic_exposure_counts_duplicate_holding_once(store, golden_ws):
    result = evaluate(store.workspace(golden_ws), "c_nimbus", "2024-01-01", OFAC)

    assert result.economic_exposure == 0.6


def test_economic_exposure_omits_branching_graph_over_path_work_budget(monkeypatch):
    layers = [["a0", "b0"]]
    rows = [
        {"owner": "seed", "asset": node, "pct": 100.0}
        for node in layers[0]
    ]
    for layer_index in range(3):
        next_layer = [f"a{layer_index + 1}", f"b{layer_index + 1}"]
        rows.extend(
            {"owner": owner, "asset": asset, "pct": 100.0}
            for owner in layers[-1]
            for asset in next_layer
        )
        layers.append(next_layer)
    rows.extend(
        {"owner": owner, "asset": "target", "pct": 100.0}
        for owner in layers[-1]
    )
    monkeypatch.setattr(ownership, "ro", lambda *_args, **_kwargs: rows)
    monkeypatch.setattr(
        ownership, "ECONOMIC_EXPOSURE_PATH_EXPANSION_BUDGET", 5, raising=False
    )

    exposure, caveat = ownership._economic_exposure(
        object(), "target", ["seed", *sum(layers, []), "target"], ["seed"], {}, 6
    )

    assert exposure is None
    assert caveat == "Economic exposure unavailable: path expansion limit (5) exceeded."


def test_economic_exposure_omits_when_holding_rows_exceed_budget(monkeypatch):
    rows = [
        {"owner": "seed", "asset": f"asset_{index}", "pct": 100.0}
        for index in range(3)
    ]
    monkeypatch.setattr(ownership, "ro", lambda *_args, **_kwargs: rows)
    monkeypatch.setattr(
        ownership, "ECONOMIC_EXPOSURE_HOLDING_ROW_BUDGET", 2, raising=False
    )

    exposure, caveat = ownership._economic_exposure(
        object(), "target", ["seed", "asset_0", "asset_1", "asset_2"], ["seed"], {}, 6
    )

    assert exposure is None
    assert caveat == "Economic exposure unavailable: holding row limit (2) exceeded."


def test_evaluation_explains_when_economic_exposure_is_omitted(monkeypatch, store, golden_ws):
    monkeypatch.setattr(ownership, "ECONOMIC_EXPOSURE_HOLDING_ROW_BUDGET", 0)

    result = evaluate(store.workspace(golden_ws), "c_nimbus", "2024-01-01", OFAC)

    assert result.economic_exposure is None
    assert "Economic exposure unavailable: holding row limit (0) exceeded." in result.caveats


def test_direct_designation_counterfactual_marks_its_designation(store, golden_ws):
    result = evaluate(
        store.workspace(golden_ws),
        "p_volkov",
        "2024-01-01",
        OFAC,
        counterfactuals=True,
    )

    assert result.verdict == "BLOCKED"
    assert result.proof == ["syn:D-p_volkov-prog_ofac"]
    assert result.decisive == ["syn:D-p_volkov-prog_ofac"]
    assert result.decisive_kind == "counterfactual"


def test_decisive_keys_exclude_seed_reachable_uncertain_sibling(store):
    workspace = f"t_dec_{uuid4().hex[:8]}"

    def seed(graph):
        rw(
            graph,
            "UNWIND $rows AS row CREATE (:Entity {id:row.id, canon:row.id})",
            {"rows": [{"id": node} for node in ("S", "U", "T", "W", "Z")]},
        )
        rw(graph, "CREATE (:Program {id:'prog_uk', authority:'UK'})")
        rw(
            graph,
            "MATCH (e:Entity {id:'S'}), (p:Program {id:'prog_uk'}) "
            "CREATE (e)-[:DESIGNATED {k:'dS', listed_on:'2000-01-01'}]->(p)",
        )
        rw(
            graph,
            "UNWIND $rows AS row MATCH (o:Entity {id:row.owner}), "
            "(x:Entity {id:row.asset}) "
            "CREATE (o)-[:OWNS {k:row.key, pct:row.pct, pct_basis:'synthetic'}]->(x)",
            {
                "rows": [
                    {"key": "seed-u-unknown", "owner": "S", "asset": "U", "pct": None},
                    {"key": "u-target", "owner": "U", "asset": "T", "pct": 60.0},
                    {"key": "seed-w-unknown", "owner": "S", "asset": "W", "pct": None},
                    {"key": "w-sibling", "owner": "W", "asset": "Z", "pct": 60.0},
                ]
            },
        )
        rw(
            graph,
            "UNWIND $rows AS row MATCH (o:Entity {id:row.owner}), "
            "(x:Entity {id:row.asset}) "
            "CREATE (o)-[:CONTROLS {k:row.key, basis:'board_majority'}]->(x)",
            {
                "rows": [
                    {"key": "w-controls-target", "owner": "W", "asset": "T"},
                    {"key": "z-controls-target", "owner": "Z", "asset": "T"},
                ]
            },
        )

    try:
        store.provision(workspace, seeder=seed, force_seed=True)
        result = evaluate(store.workspace(workspace), "T", "2024-01-01", UK)
        assert result.verdict == "INDETERMINATE"
        assert set(result.decisive) == {"u-target", "seed-u-unknown"}
    finally:
        store.drop(workspace)


def test_hop_bound_limits_the_upstream_scope(store, golden_ws):
    graph = store.workspace(golden_ws)
    canon = canon_of(graph, "c_nordharbor")
    scope_two, truncated_two = upstream_scope(graph, canon, "2024-01-01", max_hops=2)

    assert not truncated_two
    assert evaluate(graph, "c_nordharbor", "2024-01-01", OFAC, max_hops=2).verdict == "NOT_BLOCKED"
    assert evaluate(graph, "c_nordharbor", "2024-01-01", OFAC, max_hops=3).verdict == "BLOCKED"
    assert len(scope_two) == 3


def test_seeds_are_scoped_and_date_filtered(store, golden_ws):
    graph = store.workspace(golden_ws)
    canon = canon_of(graph, "c_nordharbor")
    scope, _ = upstream_scope(graph, canon, "2020-06-01", max_hops=6)

    assert seeds_in_scope(graph, scope, OFAC.authorities, "2020-06-01") == {
        canon_of(graph, "p_sokolov"): ["syn:D-p_sokolov-prog_ofac"]
    }


def test_control_presumption_is_separate_from_ofac_ownership(store, golden_ws):
    graph = store.workspace(golden_ws)
    eu = evaluate(graph, "c_maple", "2024-01-01", EU)
    ofac = evaluate(graph, "c_maple", "2024-01-01", OFAC)

    assert eu.verdict == "PRESUMED_CONTROLLED"
    assert eu.presumptions == ["syn:G13-1"]
    assert ofac.verdict == "NOT_BLOCKED"


def test_unknown_entity_raises_entity_not_found(store, golden_ws):
    with pytest.raises(EntityNotFound):
        evaluate(store.workspace(golden_ws), "c_nope", "2024-01-01", OFAC)


def test_clear_entity_without_a_designated_seed_has_no_economic_exposure(store, golden_ws):
    result = evaluate(store.workspace(golden_ws), "c_aegean", "2024-01-01", OFAC)

    assert result.economic_exposure is None
