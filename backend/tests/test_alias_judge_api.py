from dataclasses import asdict, replace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from shelltrace.api import create_app
from shelltrace.config import get_settings
from shelltrace.db import ro, rw
from shelltrace.graph.alias_judge import AliasJudgement
from shelltrace.seed.synthetic import load_synthetic


@pytest.fixture
def judge_bundle(store):
    ws = "judge_" + uuid4().hex[:8]
    store.provision(ws, seeder=load_synthetic)
    graph = store.workspace(ws)
    rw(
        graph,
        "CREATE (a:Entity {id:'judge_a',name:'Nord Harbor',canon:'judge_a',lei:'AAA'}), (b:Entity {id:'judge_b',name:'Nord Harbour',canon:'judge_b',lei:'BBB'}), (a)-[:CANDIDATE_SAME_AS {state:'pending',score:0.9}]->(b)",
    )
    with TestClient(
        create_app(
            replace(
                get_settings(),
                default_workspace=ws,
                llm_provider="none",
                jev_enabled=False,
            ),
            store,
        )
    ) as client:
        yield client, ws, graph
    store.drop(ws)


def snapshot(graph):
    return ro(
        graph,
        "MATCH (a:Entity {id:'judge_a'})-[c:CANDIDATE_SAME_AS]->(b:Entity {id:'judge_b'}) RETURN c.state AS state,a.canon AS ac,b.canon AS bc",
    ), ro(graph, "MATCH ()-[s:SAME_AS]->() RETURN count(s) AS n")


def test_judge_conflict_is_read_only(judge_bundle):
    client, ws, graph = judge_bundle
    before = snapshot(graph)
    response = client.post(
        "/api/aliases/judge",
        params={"workspace": ws},
        json={"a_id": "judge_a", "b_id": "judge_b"},
    )
    assert response.status_code == 200
    assert response.json()["recommendation"] == "different_entity"
    assert response.json()["reason"] == "identifier_conflict:lei"
    assert snapshot(graph) == before


def test_judge_existing_pair_disabled_and_missing_pairs(judge_bundle):
    client, ws, graph = judge_bundle
    rw(graph, "MATCH (e:Entity {id:'judge_b'}) REMOVE e.lei")
    before = snapshot(graph)
    response = client.post(
        "/api/aliases/judge",
        params={"workspace": ws},
        json={"a_id": "judge_b", "b_id": "judge_a"},
    )
    assert response.status_code == 200
    assert response.json()["recommendation"] == "uncertain"
    assert snapshot(graph) == before
    assert (
        client.post(
            "/api/aliases/judge",
            params={"workspace": ws},
            json={"a_id": "judge_a", "b_id": "nope"},
        ).status_code
        == 404
    )
    rw(graph, "MATCH ()-[c:CANDIDATE_SAME_AS]->() SET c.state='rejected'")
    assert (
        client.post(
            "/api/aliases/judge",
            params={"workspace": ws},
            json={"a_id": "judge_a", "b_id": "judge_b"},
        ).status_code
        == 404
    )


def test_judge_missing_workspace_does_not_provision(judge_bundle, store):
    client, _, _ = judge_bundle
    ws = "missing_" + uuid4().hex[:8]
    response = client.post(
        "/api/aliases/judge", params={"workspace": ws}, json={"a_id": "a", "b_id": "b"}
    )
    assert response.status_code == 404
    assert ws not in store.workspaces()


@pytest.mark.parametrize(
    "result",
    [
        AliasJudgement(
            "same_entity",
            "jev",
            "model_recommendation",
            "jev",
            0.95,
            {"same_entity": 0.95, "different_entity": 0.03, "uncertain": 0.02},
        ),
        AliasJudgement(reason="api_503"),
    ],
)
def test_judge_recommendations_never_mutate_graph(judge_bundle, monkeypatch, result):
    from shelltrace.graph.alias_judge import JevAliasJudge

    client, ws, graph = judge_bundle
    rw(graph, "MATCH (e:Entity {id:'judge_b'}) REMOVE e.lei")
    before = snapshot(graph)

    async def judge(self, a, b):
        assert a["id"] == "judge_a"
        assert b["name"] == "Nord Harbour"
        return result

    monkeypatch.setattr(JevAliasJudge, "judge", judge)
    response = client.post(
        "/api/aliases/judge",
        params={"workspace": ws},
        json={"a_id": "judge_a", "b_id": "judge_b"},
    )
    assert response.status_code == 200
    assert response.json()["recommendation"] == result.recommendation
    assert snapshot(graph) == before


def test_judge_rejects_user_supplied_entity_text(judge_bundle):
    client, ws, _ = judge_bundle
    assert (
        client.post(
            "/api/aliases/judge",
            params={"workspace": ws},
            json={"a_id": "judge_a", "b_id": "judge_b", "name": "injected"},
        ).status_code
        == 422
    )


def test_judge_cluster_identifier_conflict_blocks_before_model(
    judge_bundle, monkeypatch
):
    from shelltrace.graph.alias_judge import JevAliasJudge

    client, ws, graph = judge_bundle
    rw(
        graph,
        "MATCH (b:Entity {id:'judge_b'}) REMOVE b.lei CREATE (:Entity {id:'judge_member', name:'Alias', canon:'judge_b',lei:'BBB'})",
    )

    async def judge(self, a, b):
        pytest.fail("cluster conflict must block model")

    monkeypatch.setattr(JevAliasJudge, "judge", judge)
    response = client.post(
        "/api/aliases/judge",
        params={"workspace": ws},
        json={"a_id": "judge_a", "b_id": "judge_b"},
    )
    assert response.status_code == 200
    assert response.json()["recommendation"] == "different_entity"
    assert response.json()["reason"] == "identifier_conflict:lei"
