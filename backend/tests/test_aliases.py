from threading import Barrier, Event, Lock, Thread
from uuid import uuid4

import pytest

from shelltrace.db import GraphStore, ro, rw
from shelltrace.graph import aliases as aliases_module
from shelltrace.graph.aliases import (
    ClusterTooLarge,
    IdentifierConflict,
    MergeNeedsConfirmation,
    decide,
    generate_candidates,
    list_candidates,
    pending_to_designated,
    score_pair,
)
from shelltrace.graph.clusters import recompute_clusters
from shelltrace.graph.ownership import evaluate
from shelltrace.rulepacks import OFAC
from shelltrace.seed.synthetic import load_synthetic


def E(**values):
    return {
        "name": values.get("name", ""),
        "country": values.get("country"),
        "lei": values.get("lei"),
        "imo": values.get("imo"),
        "reg_no": values.get("reg_no"),
    }


def fresh(store):
    workspace = f"t_alias_{uuid4().hex[:8]}"
    store.provision(workspace, seeder=load_synthetic, force_seed=True)
    return workspace


def test_score_pair_identifier_conflicts_and_matches():
    assert score_pair(
        E(name="Harbor Trading GmbH", country="DE", lei="L1"),
        E(name="Harbour Trading GmbH", country="DE", lei="L2"),
    )[1:] == ("rejected", "identifier_conflict:lei")
    assert score_pair(
        E(name="Blue Lagoon Capital Ltd", country="VG", reg_no="R1"),
        E(name="BlueLagoon Cap Limited", country="VG", reg_no="R1"),
    )[1:] == ("accepted", "identifier_match:reg_no")

    score, state, _ = score_pair(
        E(name="ION Holdings Limited", country="HK"),
        E(name="I.O.N. Holding Ltd", country="HK"),
    )
    assert state == "pending" and score >= 0.85


def test_reg_no_conflict_overrides_another_identifier_match_only_in_same_country():
    matched_lei_conflict = score_pair(
        E(name="Alpha Ltd", country="HK", lei="L1", reg_no="R1"),
        E(name="Alpha Ltd", country="HK", lei="L1", reg_no="R2"),
    )
    assert matched_lei_conflict[1:] == ("rejected", "identifier_conflict:reg_no")

    different_countries = score_pair(
        E(name="Alpha Ltd", country="HK", lei="L1", reg_no="R1"),
        E(name="Alpha Ltd", country="SG", lei="L1", reg_no="R2"),
    )
    assert different_countries[1:] == ("accepted", "identifier_match:lei")


def test_candidate_generation_is_idempotent_and_keeps_candidates_separate(
    store,
):
    workspace = fresh(store)
    graph = store.workspace(workspace)
    try:
        rw(graph, "MATCH ()-[c:CANDIDATE_SAME_AS]->() DELETE c")

        first_counts = generate_candidates(graph)
        candidates = {
            (candidate.b_id, candidate.state)
            for entity_id in ("c_ion_holdings", "c_harbor_trading")
            for candidate in list_candidates(graph, entity_id)
        }
        juniper = evaluate(graph, "c_juniper", "2024-01-01", OFAC)
        ion_candidate_count = ro(
            graph,
            "MATCH (a:Entity {id:'c_ion_holdings'})-[c:CANDIDATE_SAME_AS]-(b:Entity {id:'c_ion_alias'}) "
            "RETURN count(c) AS n",
        )[0]["n"]

        second_counts = generate_candidates(graph)
        repeated_candidate_count = ro(
            graph,
            "MATCH (a:Entity {id:'c_ion_holdings'})-[c:CANDIDATE_SAME_AS]-(b:Entity {id:'c_ion_alias'}) "
            "RETURN count(c) AS n",
        )[0]["n"]

        assert first_counts == second_counts
        assert ("c_ion_alias", "pending") in candidates
        assert ("c_harbour_trading", "rejected") in candidates
        assert juniper.verdict == "NOT_BLOCKED"
        assert ion_candidate_count == repeated_candidate_count == 1
        assert ro(
            graph,
            "MATCH (a:Entity {id:'c_bluelagoon'})-[r:SAME_AS]-(b:Entity {id:'c_bluelagoon_alias'}) "
            "RETURN count(r) AS n",
        )[0]["n"] == 2
    finally:
        store.drop(workspace)


def test_conflicting_imo_blocks_auto_merge_even_when_lei_matches(store):
    workspace = fresh(store)
    graph = store.workspace(workspace)
    try:
        rw(
            graph,
            "MATCH (a:Entity {id:'c_ion_holdings'}), (b:Entity {id:'c_ion_alias'}) "
            "SET a.lei='SHARED-LEI', b.lei='SHARED-LEI', "
            "a.imo='IMO-1111111', b.imo='IMO-2222222'",
        )

        generate_candidates(graph)

        candidate = next(
            item
            for item in list_candidates(graph, "c_ion_holdings")
            if item.b_id == "c_ion_alias"
        )
        assert (candidate.state, candidate.reason) == (
            "rejected",
            "identifier_conflict:imo",
        )
        assert ro(
            graph,
            "MATCH (a:Entity {id:'c_ion_holdings'})-[r:SAME_AS]-"
            "(b:Entity {id:'c_ion_alias'}) RETURN count(r) AS n",
        )[0]["n"] == 0
    finally:
        store.drop(workspace)


def test_list_candidates_uses_the_other_endpoint_from_either_side(store, golden_ws):
    graph = store.workspace(golden_ws)

    from_a = list_candidates(graph, "c_ion_holdings")
    from_b = list_candidates(graph, "c_ion_alias")

    assert any(
        candidate.a_id == "c_ion_holdings" and candidate.b_id == "c_ion_alias"
        for candidate in from_a
    )
    assert any(
        candidate.a_id == "c_ion_alias" and candidate.b_id == "c_ion_holdings"
        for candidate in from_b
    )
    assert next(candidate for candidate in from_a if candidate.b_id == "c_ion_alias").touches_designated
    assert not next(candidate for candidate in from_b if candidate.b_id == "c_ion_holdings").touches_designated


def test_pending_candidate_reports_designated_other_side(store, golden_ws):
    graph = store.workspace(golden_ws)
    target = list_candidates(graph, "c_ion_holdings")[0]

    assert (target.b_id, target.state, target.touches_designated) == (
        "c_ion_alias",
        "pending",
        True,
    )
    pending = pending_to_designated(
        graph, [target.a_id], authorities=("OFAC", "EU", "UK")
    )
    assert any(candidate.b_id == "c_ion_alias" for candidate in pending)


def test_accepting_alias_exposes_juniper_and_is_idempotent(store):
    workspace = fresh(store)
    graph = store.workspace(workspace)
    try:
        assert evaluate(graph, "c_juniper", "2024-01-01", OFAC).verdict == "NOT_BLOCKED"

        first = decide(
            graph,
            "c_ion_holdings",
            "c_ion_alias",
            accept=True,
            by="analyst_1",
            reason="same HK registry entry, manual check",
        )
        second = decide(
            graph,
            "c_ion_holdings",
            "c_ion_alias",
            accept=True,
            by="analyst_1",
            reason="same HK registry entry, manual check",
        )

        assert first == second
        assert evaluate(graph, "c_juniper", "2024-01-01", OFAC).verdict == "BLOCKED"
        assert ro(
            graph,
            "MATCH (a:Entity {id:'c_ion_holdings'})-[r:SAME_AS]-(b:Entity {id:'c_ion_alias'}) "
            "RETURN count(r) AS n",
        )[0]["n"] == 2
        assert ro(
            graph,
            "MATCH (a:Entity {id:'c_ion_holdings'})-[c:CANDIDATE_SAME_AS]-(b:Entity {id:'c_ion_alias'}) "
            "RETURN count(c) AS n",
        )[0]["n"] == 0
    finally:
        store.drop(workspace)


def test_rejecting_candidate_is_idempotent_and_never_creates_alias_edges(store):
    workspace = fresh(store)
    graph = store.workspace(workspace)
    try:
        decide(
            graph,
            "c_ion_holdings",
            "c_ion_alias",
            accept=False,
            by="analyst_1",
            reason="different beneficial owners",
        )
        decide(
            graph,
            "c_ion_alias",
            "c_ion_holdings",
            accept=False,
            by="analyst_1",
            reason="still different beneficial owners",
        )

        candidate = list_candidates(graph, "c_ion_holdings")[0]
        assert candidate.state == "rejected"
        assert ro(
            graph,
            "MATCH (a:Entity {id:'c_ion_holdings'})-[c:CANDIDATE_SAME_AS]-(b:Entity {id:'c_ion_alias'}) "
            "RETURN count(c) AS n",
        )[0]["n"] == 1
        assert ro(
            graph,
            "MATCH (a:Entity {id:'c_ion_holdings'})-[r:SAME_AS]-(b:Entity {id:'c_ion_alias'}) "
            "RETURN count(r) AS n",
        )[0]["n"] == 0
    finally:
        store.drop(workspace)


def test_candidate_generation_preserves_analyst_rejection(store):
    workspace = fresh(store)
    graph = store.workspace(workspace)
    try:
        decide(
            graph,
            "c_ion_holdings",
            "c_ion_alias",
            accept=False,
            by="analyst_1",
            reason="not the same legal entity",
        )

        generate_candidates(graph)

        candidate = next(
            item
            for item in list_candidates(graph, "c_ion_holdings")
            if item.b_id == "c_ion_alias"
        )
        assert (candidate.state, candidate.reason) == (
            "rejected",
            "not the same legal entity",
        )
    finally:
        store.drop(workspace)


def test_identifier_conflict_cannot_be_accepted(store, golden_ws):
    with pytest.raises(IdentifierConflict):
        decide(
            store.workspace(golden_ws),
            "c_harbor_trading",
            "c_harbour_trading",
            accept=True,
            by="analyst_1",
            reason="looks the same to me",
        )


def test_merging_two_non_singleton_clusters_needs_confirmation(store):
    workspace = fresh(store)
    graph = store.workspace(workspace)
    try:
        decide(
            graph,
            "c_ion_holdings",
            "c_ion_alias",
            accept=True,
            by="analyst_1",
            reason="registry match confirmed",
        )

        with pytest.raises(MergeNeedsConfirmation):
            decide(
                graph,
                "c_ion_alias",
                "c_bluelagoon",
                accept=True,
                by="analyst_1",
                reason="testing the cluster merge guard",
            )
    finally:
        store.drop(workspace)


def test_candidate_generation_routes_cluster_merge_to_confirmation(store):
    workspace = fresh(store)
    graph = store.workspace(workspace)
    try:
        decide(
            graph,
            "c_ion_holdings",
            "c_ion_alias",
            accept=True,
            by="analyst_1",
            reason="same registry entry",
        )
        rw(
            graph,
            "MATCH (a:Entity {id:'c_ion_holdings'}), (b:Entity {id:'c_bluelagoon'}) "
            "SET a.lei='CONFIRM-LEI', b.lei='CONFIRM-LEI'",
        )

        generate_candidates(graph)

        candidate = next(
            item
            for item in list_candidates(graph, "c_ion_holdings")
            if item.b_id == "c_bluelagoon"
        )
        assert candidate.state == "pending"
        assert candidate.reason == "confirmation_required:cluster_merge"
        assert candidate.features == {
            "identifier_match": "lei",
            "confirmation_required": "cluster_merge",
        }
        assert ro(
            graph,
            "MATCH (a:Entity {id:'c_ion_holdings'}), (b:Entity {id:'c_bluelagoon'}) "
            "RETURN a.canon = b.canon AS same",
        )[0]["same"] is False

        result = decide(
            graph,
            "c_ion_holdings",
            "c_bluelagoon",
            accept=True,
            by="analyst_2",
            reason="reviewed cluster merge",
            confirm_merge=True,
        )
        assert result["accepted"] is True
        assert ro(
            graph,
            "MATCH (a:Entity {id:'c_ion_holdings'}), (b:Entity {id:'c_bluelagoon'}) "
            "RETURN a.canon = b.canon AS same",
        )[0]["same"] is True
    finally:
        store.drop(workspace)


def test_acceptance_that_would_exceed_cluster_cap_is_rejected(store):
    workspace = fresh(store)
    graph = store.workspace(workspace)
    try:
        nodes = [
            {"id": f"cluster_member_{index:02d}", "name": f"Cluster Member {index:02d}"}
            for index in range(23)
        ] + [{"id": "cluster_newcomer", "name": "Independent Newcomer"}]
        rw(
            graph,
            "UNWIND $rows AS row CREATE (:Entity {id:row.id, name:row.name, "
            "kind:'Company', country:'VG', canon:row.id})",
            {"rows": nodes},
        )
        links = []
        for node in nodes[:-1]:
            key = f"test:{node['id']}"
            links.extend(
                [
                    {"a": "c_bluelagoon", "b": node["id"], "k": key},
                    {"a": node["id"], "b": "c_bluelagoon", "k": f"{key}~r"},
                ]
            )
        rw(
            graph,
            "UNWIND $rows AS row MATCH (a:Entity {id:row.a}), (b:Entity {id:row.b}) "
            "CREATE (a)-[:SAME_AS {k:row.k, score:1.0, method:'test', "
            "accepted_by:'test', accepted_at:'2026-10-15T00:00:00Z'}]->(b)",
            {"rows": links},
        )
        recompute_clusters(graph)
        rw(
            graph,
            "MATCH (a:Entity {id:'c_bluelagoon'}), (b:Entity {id:'cluster_newcomer'}) "
            "SET a.lei='OVER-CAP-LEI', b.lei='OVER-CAP-LEI'",
        )

        generate_candidates(graph)

        candidate = next(
            item
            for item in list_candidates(graph, "c_bluelagoon")
            if item.b_id == "cluster_newcomer"
        )
        assert (candidate.state, candidate.reason) == (
            "rejected",
            "cluster_size_limit",
        )

        with pytest.raises(ClusterTooLarge):
            decide(
                graph,
                "c_bluelagoon",
                "cluster_newcomer",
                accept=True,
                by="analyst_1",
                reason="would exceed the component cap",
            )

        assert ro(
            graph,
            "MATCH (a:Entity {id:'c_bluelagoon'})-[r:SAME_AS]-(b:Entity {id:'cluster_newcomer'}) "
            "RETURN count(r) AS n",
        )[0]["n"] == 0
    finally:
        store.drop(workspace)


def test_concurrent_accepts_preserve_hard_cluster_cap(store, monkeypatch):
    workspace = fresh(store)
    graph_a = store.workspace(workspace)
    graph_b = GraphStore(store.s).workspace(workspace)
    try:
        members = [
            {"id": f"concurrent_member_{index:02d}", "name": f"Concurrent Member {index:02d}"}
            for index in range(22)
        ]
        rw(
            graph_a,
            "UNWIND $rows AS row CREATE (:Entity {id:row.id, name:row.name, "
            "kind:'Company', country:'HK', canon:row.id})",
            {"rows": members},
        )
        links = []
        for member in members:
            key = f"concurrent:{member['id']}"
            links.extend(
                [
                    {"a": "c_bluelagoon", "b": member["id"], "k": key},
                    {"a": member["id"], "b": "c_bluelagoon", "k": f"{key}~r"},
                ]
            )
        rw(
            graph_a,
            "UNWIND $rows AS row MATCH (a:Entity {id:row.a}), (b:Entity {id:row.b}) "
            "CREATE (a)-[:SAME_AS {k:row.k, score:1.0, method:'test', "
            "accepted_by:'test', accepted_at:'2026-10-15T00:00:00Z'}]->(b)",
            {"rows": links},
        )
        recompute_clusters(graph_a)
        initial_canon = ro(
            graph_a,
            "MATCH (e:Entity {id:'c_bluelagoon'}) RETURN e.canon AS canon",
        )[0]["canon"]
        assert ro(
            graph_a,
            "MATCH (e:Entity {canon:$canon}) RETURN count(e) AS n",
            {"canon": initial_canon},
        )[0]["n"] == 24

        original_cluster_sizes = aliases_module._cluster_sizes
        calls_lock = Lock()
        calls = 0
        second_size_check = Event()

        def synchronized_cluster_sizes(graph, canon_a, canon_b):
            nonlocal calls
            sizes = original_cluster_sizes(graph, canon_a, canon_b)
            with calls_lock:
                calls += 1
                call_number = calls
            if call_number == 1:
                second_size_check.wait(timeout=0.4)
            else:
                second_size_check.set()
            return sizes

        monkeypatch.setattr(aliases_module, "_cluster_sizes", synchronized_cluster_sizes)
        start = Barrier(3)
        outcomes = []

        def accept(graph, entity_id):
            start.wait(timeout=3)
            try:
                outcomes.append(
                    decide(
                        graph,
                        "c_bluelagoon",
                        entity_id,
                        accept=True,
                        by="concurrent_test",
                        reason="concurrency cap test",
                    )
                )
            except Exception as exc:
                outcomes.append(exc)

        workers = [
            Thread(target=accept, args=(graph_a, "c_juniper")),
            Thread(target=accept, args=(graph_b, "c_aegean")),
        ]
        for worker in workers:
            worker.start()
        start.wait(timeout=3)
        for worker in workers:
            worker.join(timeout=10)

        assert all(not worker.is_alive() for worker in workers)
        assert sum(isinstance(outcome, dict) and outcome["accepted"] for outcome in outcomes) == 1
        assert sum(isinstance(outcome, ClusterTooLarge) for outcome in outcomes) == 1

        canon = ro(
            graph_a,
            "MATCH (e:Entity {id:'c_bluelagoon'}) RETURN e.canon AS canon",
        )[0]["canon"]
        assert ro(
            graph_a,
            "MATCH (e:Entity {canon:$canon}) RETURN count(e) AS n",
            {"canon": canon},
        )[0]["n"] == 25
    finally:
        store.drop(workspace)
