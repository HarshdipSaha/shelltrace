import pytest

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
