import pytest

from shelltrace.graph.ownership import EntityNotFound
from shelltrace.graph.redflags import red_flags


ALL = ("OFAC", "EU", "UK")


def kinds(flags):
    return {flag.kind for flag in flags}


def test_divestment_near_listing(store, golden_ws):
    flags = red_flags(
        store.workspace(golden_ws), "c_fjord", "2024-01-01", 6, ALL
    )

    flag = next(flag for flag in flags if flag.kind == "divestment_near_listing")
    assert "syn:G7-1" in flag.evidence_keys
    assert any(key.startswith("syn:D-p_mira-") for key in flag.evidence_keys)


def test_divestment_needs_listing_before_as_of(store, golden_ws):
    flags = red_flags(
        store.workspace(golden_ws), "c_fjord", "2023-03-01", 6, ALL
    )

    assert "divestment_near_listing" not in kinds(flags)


def test_circular_mass_and_control(store, golden_ws):
    graph = store.workspace(golden_ws)

    assert "circular_ownership" in kinds(
        red_flags(graph, "c_gamma", "2024-01-01", 6, ALL)
    )
    assert "mass_registration_address" in kinds(
        red_flags(graph, "c_quartz", "2024-01-01", 6, ALL)
    )
    assert "control_by_designated" in kinds(
        red_flags(graph, "c_maple", "2024-01-01", 6, ALL)
    )


def test_clean_entities_have_no_flags(store, golden_ws):
    graph = store.workspace(golden_ws)

    for entity_id in ("c_elm", "c_aegean", "c_harbor_trading", "c_nordharbor"):
        assert red_flags(graph, entity_id, "2024-01-01", 6, ALL) == []


def test_unknown_entity_raises_entity_not_found(store, golden_ws):
    with pytest.raises(EntityNotFound):
        red_flags(store.workspace(golden_ws), "c_missing", "2024-01-01", 6, ALL)
