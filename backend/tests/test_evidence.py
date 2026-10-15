from uuid import uuid4

import pytest

from shelltrace.db import rw
from shelltrace.graph.ownership import EntityNotFound
from shelltrace.graph.evidence import (
    entity_search,
    evidence_get,
    get_entity,
    neighborhood,
    ownership_stakes,
)


def test_evidence_preserves_edge_and_designation_provenance(store, golden_ws):
    graph = store.workspace(golden_ws)

    [edge] = evidence_get(graph, ["syn:G1-2"])
    assert (edge.from_id, edge.to_id, edge.pct, edge.src, edge.snapshot) == (
        "c_meridian",
        "c_bluelagoon_alias",
        80.0,
        "synthetic",
        "synthetic-v1",
    )
    assert (edge.type, edge.basis, edge.valid_from, edge.valid_to) == (
        "OWNS",
        "synthetic",
        "2020-03-01",
        None,
    )
    assert (edge.src_record, edge.licence, edge.url) == (
        "G1-2",
        "CC0-1.0 (synthetic, disclosed)",
        None,
    )

    [designation] = evidence_get(graph, ["syn:D-p_petrov-prog_uk"])
    assert (designation.type, designation.listed_on, designation.delisted_on) == (
        "DESIGNATED",
        "2020-01-01",
        "2023-01-01",
    )
    assert (designation.src, designation.src_record, designation.snapshot) == (
        "synthetic",
        "D-p_petrov-prog_uk",
        "synthetic-v1",
    )


def test_ownership_stakes_respect_as_of_date(store, golden_ws):
    graph = store.workspace(golden_ws)

    assert [stake.k for stake in ownership_stakes(graph, "c_fjord", "2024-01-01")] == [
        "syn:G7-3",
        "syn:G7-2",
    ]
    assert {stake.k for stake in ownership_stakes(graph, "c_fjord", "2022-01-01")} == {
        "syn:G7-1"
    }


def test_ownership_stakes_normalizes_as_of_date(store):
    workspace = f"t_stake_date_{uuid4().hex[:8]}"

    def seed(graph):
        rw(
            graph,
            "CREATE (:Entity {id:'owner', name:'Owner', canon:'owner', kind:'Company'}), "
            "(:Entity {id:'asset', name:'Asset', canon:'asset', kind:'Company'})",
        )
        rw(
            graph,
            "MATCH (o:Entity {id:'owner'}), (x:Entity {id:'asset'}) "
            "CREATE (o)-[:OWNS {k:'test:future', pct:80.0, "
            "valid_from:'2024-11-01'}]->(x)",
        )

    try:
        store.provision(workspace, seeder=seed, force_seed=True)
        graph = store.workspace(workspace)

        assert ownership_stakes(graph, "asset", "2024-W27-1") == ownership_stakes(
            graph, "asset", "2024-07-01"
        ) == []
    finally:
        store.drop(workspace)


def test_search_finds_both_alias_spellings(store, golden_ws):
    graph = store.workspace(golden_ws)
    results = entity_search(graph, "blue lagoon")

    assert {result["id"] for result in results} >= {
        "c_bluelagoon",
        "c_bluelagoon_alias",
    }
    assert all(
        set(result)
        == {"id", "name", "kind", "country", "lei", "imo", "designated"}
        for result in results
    )


def test_search_exact_identifier_is_first_and_limit_is_respected(store, golden_ws):
    graph = store.workspace(golden_ws)

    results = entity_search(graph, "9876543", limit=1)

    assert len(results) == 1
    assert results[0]["id"] == "v_kestrel_star"
    assert results[0]["imo"] == "9876543"


def test_search_accepts_limits_above_legacy_cap(store, golden_ws):
    results = entity_search(store.workspace(golden_ws), "blue lagoon", limit=21)

    assert len(results) <= 21


def test_entity_lookup_and_neighborhood_are_bounded(store, golden_ws):
    graph = store.workspace(golden_ws)

    assert get_entity(graph, "v_kestrel_star").kind == "Vessel"
    result = neighborhood(graph, "c_fjord", depth=2, limit=2)
    node_ids = {node["id"] for node in result["nodes"]}

    assert len(result["nodes"]) <= 2
    assert all(edge["from_id"] in node_ids and edge["to_id"] in node_ids for edge in result["edges"])


def test_neighborhood_accepts_limits_above_legacy_cap(store, golden_ws):
    result = neighborhood(store.workspace(golden_ws), "c_fjord", depth=2, limit=51)

    assert 1 <= len(result["nodes"]) <= 51


def test_neighborhood_marks_expired_edges(store, golden_ws):
    result = neighborhood(store.workspace(golden_ws), "c_fjord", depth=1)

    expired = next(edge for edge in result["edges"] if edge["k"] == "syn:G7-1")
    assert expired["expired"] is True
    assert (expired["from_id"], expired["to_id"]) == ("p_mira", "c_fjord")


@pytest.mark.parametrize(
    ("call", "args"),
    [
        ("search", {"query": "blue lagoon", "limit": 0}),
        ("neighborhood", {"entity_id": "c_fjord", "depth": 3}),
        ("neighborhood", {"entity_id": "c_fjord", "limit": 0}),
    ],
)
def test_malformed_bounds_are_rejected(store, golden_ws, call, args):
    graph = store.workspace(golden_ws)

    if call == "search":
        with pytest.raises(ValueError):
            entity_search(graph, **args)
    else:
        with pytest.raises(ValueError):
            neighborhood(graph, **args)


def test_unknown_entity_and_missing_evidence_are_handled(store, golden_ws):
    graph = store.workspace(golden_ws)

    with pytest.raises(EntityNotFound):
        get_entity(graph, "c_missing")
    assert evidence_get(graph, ["no-such-key"]) == []
