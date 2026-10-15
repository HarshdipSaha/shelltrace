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
