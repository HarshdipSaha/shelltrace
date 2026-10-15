from contextlib import contextmanager
from uuid import uuid4

import pytest

from shelltrace.db import rw
from shelltrace.graph.ownership import EntityNotFound
from shelltrace.graph import redflags as redflags_module
from shelltrace.graph.redflags import RedFlagsUnavailable, red_flags


ALL = ("OFAC", "EU", "UK")


@contextmanager
def custom_graph(
    store,
    entities,
    *,
    owns=(),
    controls=(),
    designations=(),
    addresses=(),
    registrations=(),
):
    workspace = f"t_redflag_{uuid4().hex[:8]}"

    def seed(graph):
        rw(
            graph,
            "UNWIND $rows AS row CREATE (:Entity {id:row.id, canon:row.canon, "
            "name:row.id, kind:'Company'})",
            {"rows": entities},
        )
        if owns:
            rw(
                graph,
                "UNWIND $rows AS row MATCH (o:Entity {id:row.owner}), "
                "(x:Entity {id:row.asset}) CREATE (o)-[:OWNS {k:row.k, pct:row.pct, "
                "valid_from:row.valid_from, valid_to:row.valid_to}]->(x)",
                {"rows": list(owns)},
            )
        if controls:
            rw(
                graph,
                "UNWIND $rows AS row MATCH (o:Entity {id:row.owner}), "
                "(x:Entity {id:row.asset}) CREATE (o)-[:CONTROLS {k:row.k, "
                "valid_from:row.valid_from, valid_to:row.valid_to}]->(x)",
                {"rows": list(controls)},
            )
        if designations:
            programs = {}
            for row in designations:
                programs[row["program"]] = row["authority"]
            rw(
                graph,
                "UNWIND $rows AS row CREATE (:Program {id:row.id, authority:row.authority})",
                {"rows": [{"id": key, "authority": value} for key, value in programs.items()]},
            )
            rw(
                graph,
                "UNWIND $rows AS row MATCH (e:Entity {id:row.entity}), "
                "(p:Program {id:row.program}) CREATE (e)-[:DESIGNATED {k:row.k, "
                "listed_on:row.listed_on, delisted_on:row.delisted_on}]->(p)",
                {"rows": list(designations)},
            )
        if addresses:
            rw(
                graph,
                "UNWIND $rows AS row CREATE (:Address {id:row.id, name:row.name})",
                {"rows": list(addresses)},
            )
        if registrations:
            rw(
                graph,
                "UNWIND $rows AS row MATCH (e:Entity {id:row.entity}), "
                "(a:Address {id:row.address}) CREATE (e)-[:REGISTERED_AT {k:row.k, "
                "valid_from:row.valid_from, valid_to:row.valid_to}]->(a)",
                {"rows": list(registrations)},
            )

    try:
        store.provision(workspace, seeder=seed, force_seed=True)
        yield store.workspace(workspace)
    finally:
        store.drop(workspace)


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
    mass_flags = red_flags(graph, "c_quartz", "2024-01-01", 6, ALL)
    assert "mass_registration_address" in kinds(mass_flags)
    mass_flag = next(flag for flag in mass_flags if flag.kind == "mass_registration_address")
    assert mass_flag.evidence_status == "complete"
    assert mass_flag.entity_count >= 20
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


def test_canonical_cycle_spans_accepted_alias_ids(store):
    entities = [
        {"id": "a1", "canon": "a"},
        {"id": "a2", "canon": "a"},
        {"id": "b", "canon": "b"},
    ]
    owns = [
        {"owner": "a1", "asset": "b", "k": "test:a-b"},
        {"owner": "b", "asset": "a2", "k": "test:b-a"},
    ]

    with custom_graph(store, entities, owns=owns) as graph:
        flags = red_flags(graph, "a1", "2024-01-01", 6, ALL)

    cycle = next(flag for flag in flags if flag.kind == "circular_ownership")
    assert set(cycle.evidence_keys) == {"test:a-b", "test:b-a"}
    assert set(cycle.entity_ids) == {"a1", "a2", "b"}


def test_seven_node_cycle_fits_the_six_hop_scope(store):
    entities = [{"id": f"n{i}", "canon": f"n{i}"} for i in range(7)]
    owns = [
        {"owner": f"n{i}", "asset": f"n{(i + 1) % 7}", "k": f"test:ring-{i}"}
        for i in range(7)
    ]

    with custom_graph(store, entities, owns=owns) as graph:
        flags = red_flags(graph, "n0", "2024-01-01", 6, ALL)

    cycle = next(flag for flag in flags if flag.kind == "circular_ownership")
    assert set(cycle.evidence_keys) == {f"test:ring-{i}" for i in range(7)}


def test_cycle_edge_budget_overflow_is_unavailable(store, monkeypatch):
    monkeypatch.setattr(redflags_module, "CYCLE_EDGE_BUDGET", 2, raising=False)
    real_ro = redflags_module.ro
    cycle_params = {}

    def capture_cycle_query(graph, cypher, params=None):
        if cypher == redflags_module.CYCLE_EDGES:
            cycle_params.update(params or {})
        return real_ro(graph, cypher, params)

    monkeypatch.setattr(redflags_module, "ro", capture_cycle_query)
    entities = [{"id": node, "canon": node} for node in "abc"]
    owns = [
        {"owner": "a", "asset": "b", "k": "test:a-b"},
        {"owner": "b", "asset": "c", "k": "test:b-c"},
        {"owner": "c", "asset": "a", "k": "test:c-a"},
    ]

    with custom_graph(store, entities, owns=owns) as graph:
        with pytest.raises(RedFlagsUnavailable, match="cycle.*row limit.*exceeded"):
            red_flags(graph, "a", "2024-01-01", 6, ALL)

    assert cycle_params["row_limit"] == 3


def test_cycles_outside_canonical_scope_are_ignored(store):
    entities = [{"id": node, "canon": node} for node in "abcd"]
    owns = [
        {"owner": "b", "asset": "a", "k": "test:b-a"},
        {"owner": "a", "asset": "c", "k": "test:a-c"},
        {"owner": "c", "asset": "d", "k": "test:c-d"},
        {"owner": "d", "asset": "b", "k": "test:d-b"},
    ]

    with custom_graph(store, entities, owns=owns) as graph:
        flags = red_flags(graph, "a", "2024-01-01", 1, ALL)

    assert "circular_ownership" not in kinds(flags)


def test_divestment_joins_designation_by_canonical_subject(store):
    entities = [
        {"id": "owner_record", "canon": "owner"},
        {"id": "owner_designation", "canon": "owner"},
        {"id": "asset", "canon": "asset"},
    ]
    owns = [{
        "owner": "owner_record", "asset": "asset", "k": "test:ended-stake",
        "pct": 60.0, "valid_to": "2023-05-01",
    }]
    designations = [{
        "entity": "owner_designation", "program": "ofac", "authority": "OFAC",
        "k": "test:designation", "listed_on": "2023-05-10",
    }]

    with custom_graph(store, entities, owns=owns, designations=designations) as graph:
        flags = red_flags(graph, "asset", "2024-01-01", 6, ALL)

    flag = next(flag for flag in flags if flag.kind == "divestment_near_listing")
    assert set(flag.evidence_keys) == {"test:ended-stake", "test:designation"}
    assert flag.entity_ids == ["owner_record", "asset"]


def test_designated_control_joins_designation_by_canonical_subject(store):
    entities = [
        {"id": "controller_record", "canon": "controller"},
        {"id": "controller_designation", "canon": "controller"},
        {"id": "asset", "canon": "asset"},
    ]
    controls = [{"owner": "controller_record", "asset": "asset", "k": "test:control"}]
    designations = [{
        "entity": "controller_designation", "program": "ofac", "authority": "OFAC",
        "k": "test:designation", "listed_on": "2020-01-01",
    }]

    with custom_graph(store, entities, controls=controls, designations=designations) as graph:
        flags = red_flags(graph, "asset", "2024-01-01", 6, ALL)

    flag = next(flag for flag in flags if flag.kind == "control_by_designated")
    assert set(flag.evidence_keys) == {"test:control", "test:designation"}
    assert flag.entity_ids == ["controller_record", "asset"]


def _mass_address_graph(store, address_ids=("shared",)):
    entities = [{"id": f"e{i}", "canon": f"e{i}"} for i in range(5)]
    addresses = [
        {"id": address_id, "name": f"Shared address {address_id}"}
        for address_id in address_ids
    ]
    registrations = [
        {
            "entity": f"e{i}",
            "address": address_id,
            "k": f"test:registration-{address_id}-{i}-{version}",
        }
        for i in range(5)
        for address_id in address_ids
        for version in range(2)
    ]
    return custom_graph(
        store, entities, addresses=addresses, registrations=registrations
    )


def test_mass_registration_evidence_is_bounded_with_accurate_count(store, monkeypatch):
    monkeypatch.setattr(redflags_module, "MASS_EVIDENCE_BUDGET", 2, raising=False)
    with _mass_address_graph(store) as graph:
        flags = red_flags(graph, "e0", "2024-01-01", 6, ALL, mass_min=2)

    flag = next(flag for flag in flags if flag.kind == "mass_registration_address")
    assert flag.evidence_status == "truncated"
    assert flag.entity_count == 5
    assert flag.evidence_count == 10
    assert len(flag.evidence_keys) == 2
    assert len(flag.entity_ids) <= 2
    assert "5 currently registered entities" in flag.detail


def test_mass_registration_evidence_failure_is_reported(store, monkeypatch):
    monkeypatch.setattr(redflags_module, "MASS_EVIDENCE_BUDGET", 2, raising=False)
    real_ro = redflags_module.ro

    def fail_sample_query(graph, cypher, params=None):
        if cypher == redflags_module.MASS_EVIDENCE:
            raise RuntimeError("sample unavailable")
        return real_ro(graph, cypher, params)

    monkeypatch.setattr(redflags_module, "ro", fail_sample_query)
    with _mass_address_graph(store) as graph:
        flags = red_flags(graph, "e0", "2024-01-01", 6, ALL, mass_min=2)

    flag = next(flag for flag in flags if flag.kind == "mass_registration_address")
    assert flag.evidence_status == "unavailable"
    assert flag.entity_count == 5
    assert flag.evidence_count == 10
    assert flag.evidence_keys == []


def test_distinct_mass_addresses_survive_empty_evidence_dedup(store, monkeypatch):
    def fail_sample_query(graph, cypher, params=None):
        if cypher == redflags_module.MASS_EVIDENCE:
            raise RuntimeError("sample unavailable")
        return real_ro(graph, cypher, params)

    real_ro = redflags_module.ro
    monkeypatch.setattr(redflags_module, "ro", fail_sample_query)
    with _mass_address_graph(store, ("shared-a", "shared-b")) as graph:
        flags = red_flags(graph, "e0", "2024-01-01", 6, ALL, mass_min=2)

    mass_flags = [flag for flag in flags if flag.kind == "mass_registration_address"]
    assert len(mass_flags) == 2
    assert all(flag.evidence_status == "unavailable" for flag in mass_flags)
    assert all(flag.evidence_keys == [] for flag in mass_flags)
    assert {flag.detail.split("(")[-1].split(")")[0] for flag in mass_flags} == {
        "shared-a", "shared-b"
    }


def test_red_flags_normalizes_as_of_dates(store):
    entities = [
        {"id": "owner", "canon": "owner"},
        {"id": "asset", "canon": "asset"},
    ]
    owns = [{
        "owner": "owner", "asset": "asset", "k": "test:ended-stake",
        "pct": 60.0, "valid_to": "2024-10-01",
    }]
    designations = [{
        "entity": "owner", "program": "ofac", "authority": "OFAC",
        "k": "test:designation", "listed_on": "2024-11-01",
    }]

    with custom_graph(store, entities, owns=owns, designations=designations) as graph:
        week_date = red_flags(graph, "asset", "2024-W27-1", 6, ALL)
        canonical = red_flags(graph, "asset", "2024-07-01", 6, ALL)

    assert week_date == canonical
    assert "divestment_near_listing" not in kinds(week_date)
