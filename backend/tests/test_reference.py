import pytest

from shelltrace.models import RulePack
from shelltrace.graph.reference import EPS, RefEdge, RefGraph, crosses, ref_evaluate
from shelltrace.rulepacks import EU, OFAC, UK


def G(owns=(), controls=(), seeds=None):
    return RefGraph(
        tuple(RefEdge(*edge) for edge in owns),
        tuple(RefEdge(*edge) for edge in controls),
        seeds or {},
    )


def test_fifty_percent_through_fifty_percent_chain_uses_pack_threshold():
    graph = G(
        [("e1", "X", "A", 50.0), ("e2", "A", "B", 50.0)],
        seeds={"X": ("dX",)},
    )

    assert ref_evaluate("B", graph, OFAC).verdict == "BLOCKED"
    assert ref_evaluate("B", graph, OFAC).proof == {"e1", "e2", "dX"}
    assert ref_evaluate("B", graph, EU).verdict == "BLOCKED"
    assert ref_evaluate("B", graph, UK).verdict == "NOT_BLOCKED"


def test_aggregation_across_designated_persons_is_pack_specific():
    graph = G(
        [("e1", "P", "C", 30.0), ("e2", "Q", "C", 25.0)],
        seeds={"P": ("dP",), "Q": ("dQ",)},
    )

    ofac = ref_evaluate("C", graph, OFAC)
    uk = ref_evaluate("C", graph, UK)
    assert (ofac.verdict, ofac.lo, ofac.hi) == ("BLOCKED", 55.0, 55.0)
    assert (uk.verdict, uk.lo) == ("NOT_BLOCKED", 30.0)


def test_unknown_stake_straddling_threshold_is_indeterminate_and_decisive():
    graph = G(
        [("e1", "X", "D", None), ("e2", "O", "D", 40.0)],
        seeds={"X": ("dX",)},
    )

    result = ref_evaluate("D", graph, OFAC)
    assert (result.verdict, result.lo, result.hi) == ("INDETERMINATE", 0.0, 60.0)
    assert result.decisive == {"e1"}


def test_unknown_stake_upper_bound_can_remain_below_threshold():
    graph = G(
        [("e1", "X", "E", None), ("e2", "O", "E", 70.0)],
        seeds={"X": ("dX",)},
    )

    result = ref_evaluate("E", graph, OFAC)
    assert (result.verdict, result.lo, result.hi) == ("NOT_BLOCKED", 0.0, 30.0)
    assert result.decisive == frozenset()


def test_ownership_cycle_cannot_self_justify():
    graph = G(
        [("e1", "X", "Ga", 30.0), ("e2", "Ga", "De", 60.0), ("e3", "De", "Ga", 60.0)],
        seeds={"X": ("dX",)},
    )

    assert ref_evaluate("Ga", graph, OFAC).verdict == "NOT_BLOCKED"
    assert ref_evaluate("De", graph, OFAC).verdict == "NOT_BLOCKED"


def test_duplicate_records_for_one_holding_count_once():
    graph = G(
        [("a", "X", "N", 60.0), ("b", "X", "N", 60.0)],
        seeds={"X": ("dX",)},
    )

    result = ref_evaluate("N", graph, OFAC)
    assert (result.verdict, result.lo, result.hi) == ("BLOCKED", 60.0, 60.0)
    assert result.proof == {"a", "b", "dX"}


def test_conflicting_duplicate_records_create_an_interval():
    graph = G(
        [("a", "X", "O", 45.0), ("b", "X", "O", 55.0)],
        seeds={"X": ("dX",)},
    )

    result = ref_evaluate("O", graph, OFAC)
    assert (result.verdict, result.lo, result.hi) == ("INDETERMINATE", 45.0, 55.0)
    assert result.decisive == {"a", "b"}


def test_direct_designation_has_full_bounds_and_its_own_evidence():
    graph = G(seeds={"R": ("dR1", "dR2")})

    result = ref_evaluate("R", graph, UK)
    assert (result.verdict, result.lo, result.hi) == ("BLOCKED", 100.0, 100.0)
    assert result.proof == {"dR1", "dR2"}


def test_control_limb_is_separate_and_presumptions_propagate_downward():
    graph = G(controls=[("c1", "X", "M", None), ("c2", "M", "N", None)], seeds={"X": ("dX",)})

    assert ref_evaluate("M", graph, OFAC).verdict == "NOT_BLOCKED"
    eu = ref_evaluate("N", graph, EU)
    uk = ref_evaluate("M", graph, UK)
    assert (eu.verdict, eu.presumptions) == ("PRESUMED_CONTROLLED", {"c1", "c2"})
    assert (uk.verdict, uk.presumptions) == ("PRESUMED_CONTROLLED", {"c1", "c2"})


def test_control_presumption_does_not_feed_ownership_arithmetic():
    graph = G(
        owns=[("e1", "M", "B", 100.0)],
        controls=[("c1", "X", "M", None)],
        seeds={"X": ("dX",)},
    )

    assert ref_evaluate("B", graph, EU).verdict == "NOT_BLOCKED"


def test_known_stakes_over_one_hundred_are_reported_by_asset():
    graph = G(
        [("a", "P", "Q", 70.0), ("b", "R", "Q", 60.0)],
        seeds={},
    )

    assert ref_evaluate("Q", graph, OFAC).data_errors == {"Q"}


def test_uk_counts_a_controlled_entities_stake_in_full():
    graph = G(
        [
            ("e1", "X", "A", 60.0),
            ("e2", "A", "B", 30.0),
            ("e3", "X", "B", 25.0),
        ],
        seeds={"X": ("dX",)},
    )

    assert ref_evaluate("B", graph, UK).verdict == "BLOCKED"


def test_only_rulepack_accepted_bases_contribute_to_ownership():
    graph = G([("e1", "X", "A", 100.0, "accounting_consolidation")], seeds={"X": ("dX",)})
    shareholding_only = OFAC.model_copy(update={"basis_accepted": ("shareholding",)})

    assert ref_evaluate("A", graph, shareholding_only).verdict == "NOT_BLOCKED"


def test_crosses_uses_exact_inclusive_and_strict_legal_thresholds():
    assert crosses(50.0, OFAC)
    assert not crosses(50.0 - EPS / 2, OFAC)
    assert not crosses(50.0, UK)
    assert crosses(50.0 + EPS / 2, UK)


def test_uk_control_presumptions_include_each_designated_seed_group():
    graph = G(
        owns=[("e1", "P", "A", 10.0)],
        controls=[("c1", "Q", "T", None)],
        seeds={"P": ("dP",), "Q": ("dQ",)},
    )

    result = ref_evaluate("T", graph, UK)
    assert result.verdict == "PRESUMED_CONTROLLED"
    assert result.presumptions == {"c1"}
