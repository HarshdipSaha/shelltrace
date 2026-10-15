import json

from shelltrace.db import ro
from shelltrace.names import core, norm, phon


def test_name_normalisation_and_matching_features():
    assert norm("  BLUE—Lagoon, Capital Ltd  ") == "blue lagoon capital ltd"
    assert core("Blue Lagoon Capital Ltd") == "bluelagoon"
    assert core("I.O.N. Holding Ltd") == core("ION Holdings Limited") == "ion"
    assert phon("Harbor Trading GmbH") == phon("Harbour Trading GmbH")


def test_schema_installs_fulltext_search_on_entity_name(store, golden_ws):
    graph = store.workspace(golden_ws)
    found = ro(
        graph,
        "CALL db.idx.fulltext.queryNodes('Entity', 'Nord Harbor') YIELD node RETURN node.id AS id",
    )
    assert {row["id"] for row in found} >= {"c_nordharbor"}


def test_schema_installs_case_entity_id_range_index(store, golden_ws):
    graph = store.workspace(golden_ws)
    indexes = ro(graph, "CALL db.indexes()")
    assert any(row["label"] == "Case" and "entity_id" in row["properties"] for row in indexes)


def test_golden_entity_count_and_alias_canonicalisation(store, golden_ws):
    graph = store.workspace(golden_ws)
    assert ro(graph, "MATCH (e:Entity) RETURN count(e) AS n")[0]["n"] == 64
    canon = {
        row["id"]: row["canon"]
        for row in ro(
            graph,
            "MATCH (e:Entity) WHERE e.id STARTS WITH 'c_bluelagoon' RETURN e.id AS id, e.canon AS canon",
        )
    }
    assert canon == {"c_bluelagoon": "c_bluelagoon", "c_bluelagoon_alias": "c_bluelagoon"}
    both = ro(
        graph,
        "MATCH (:Entity {id:'c_bluelagoon'})-[r:SAME_AS]-(:Entity {id:'c_bluelagoon_alias'}) RETURN count(r) AS n",
    )[0]["n"]
    assert both == 2


def test_seed_has_exact_golden_ids_and_evidence_keys(store, golden_ws):
    graph = store.workspace(golden_ws)
    assert ro(graph, "MATCH (e:Entity {id:'c_nordharbor'}) RETURN e.name AS name")[0]["name"] == "Nord Harbor Logistics Ltd"
    assert ro(graph, "MATCH ()-[r:OWNS {k:'syn:G1-1'}]->() RETURN count(r) AS n")[0]["n"] == 1
    assert ro(graph, "MATCH ()-[r:DESIGNATED {k:'syn:D-p_volkov-prog_ofac'}]->() RETURN count(r) AS n")[0]["n"] == 1


def test_seed_control_ground_uses_controls_basis(store, golden_ws):
    graph = store.workspace(golden_ws)
    edge = ro(graph, "MATCH ()-[r:CONTROLS {k:'syn:G13-1'}]->() RETURN r.basis AS basis, r.control AS control")[0]
    assert edge == {"basis": "board_majority", "control": None}


def test_seed_alias_edges_have_deterministic_timestamps_and_candidate_features(store, golden_ws):
    graph = store.workspace(golden_ws)
    accepted = ro(graph, "MATCH ()-[r:SAME_AS]->() RETURN r.k AS k, r.accepted_at AS accepted_at, r.accepted_by AS accepted_by")
    assert {row["k"] for row in accepted} == {"syn:AL-1", "syn:AL-1~r"}
    assert {row["accepted_at"] for row in accepted} == {"2026-10-15T00:00:00Z"}
    assert {row["accepted_by"] for row in accepted} == {"seed"}

    candidates = {
        row["k"]: row
        for row in ro(
            graph,
            "MATCH ()-[r:CANDIDATE_SAME_AS]->() RETURN r.k AS k, r.reason AS reason, r.features_json AS features_json",
        )
    }
    assert candidates["syn:CA-1"]["reason"] == "name_core_match"
    assert json.loads(candidates["syn:CA-1"]["features_json"]) == {"name_core": "ion"}
    assert candidates["syn:CA-2"]["reason"] == "identifier_conflict:lei"
    assert json.loads(candidates["syn:CA-2"]["features_json"]) == {"identifier_conflict": "lei"}


def test_all_seed_nodes_and_edges_have_provenance(store, golden_ws):
    graph = store.workspace(golden_ws)
    nodes_missing = ro(
        graph,
        "MATCH (n) WHERE n.src IS NULL OR n.src_record IS NULL OR n.snapshot IS NULL OR n.licence IS NULL RETURN count(n) AS n",
    )[0]["n"]
    edges_missing = ro(
        graph,
        "MATCH ()-[r]->() WHERE r.src IS NULL OR r.src_record IS NULL OR r.snapshot IS NULL OR r.licence IS NULL RETURN count(r) AS n",
    )[0]["n"]
    assert nodes_missing == 0
    assert edges_missing == 0


def test_clusters_only_connect_accepted_aliases(store, golden_ws):
    graph = store.workspace(golden_ws)
    assert ro(graph, "MATCH (a:Entity {id:'c_ion_holdings'}),(b:Entity {id:'c_ion_alias'}) RETURN a.canon = b.canon AS same")[0]["same"] is False
    assert ro(graph, "MATCH (a:Entity {id:'c_harbor_trading'}),(b:Entity {id:'c_harbour_trading'}) RETURN a.canon = b.canon AS same")[0]["same"] is False


def test_seed_is_idempotent(store, golden_ws):
    from shelltrace.seed.synthetic import load_synthetic

    graph = store.workspace(golden_ws)
    before = ro(graph, "MATCH ()-[r]->() RETURN count(r) AS n")[0]["n"]
    load_synthetic(graph)
    assert ro(graph, "MATCH ()-[r]->() RETURN count(r) AS n")[0]["n"] == before
