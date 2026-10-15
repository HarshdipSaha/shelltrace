"""Explicit opt-in live checks; sends synthetic identity data only."""

import os
from dataclasses import replace
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from shelltrace.api import create_app
from shelltrace.config import get_settings
from shelltrace.db import ro
from shelltrace.seed.synthetic import load_synthetic


pytestmark = pytest.mark.skipif(
    os.getenv("ST_LIVE_PROVIDERS") != "1",
    reason="set ST_LIVE_PROVIDERS=1 to spend provider tokens on synthetic live checks",
)


def test_live_jev_endpoint_preserves_graph_and_validated_disposition(store):
    settings = get_settings()
    if not settings.jev_api_key:
        pytest.skip("requires a TypeSafe/JEV credential")
    workspace = f"jev_live_{uuid4().hex[:8]}"
    store.provision(workspace, seeder=load_synthetic, force_seed=True)
    graph = store.workspace(workspace)
    settings = replace(
        settings, default_workspace=workspace, llm_provider="none", jev_enabled=True
    )

    def snapshot():
        return (
            ro(
                graph, "MATCH (e:Entity) RETURN e.id AS id,e.canon AS canon ORDER BY id"
            ),
            ro(
                graph,
                "MATCH ()-[r:CANDIDATE_SAME_AS]->() RETURN properties(r) AS p ORDER BY r.k",
            ),
            ro(
                graph, "MATCH ()-[r:SAME_AS]->() RETURN properties(r) AS p ORDER BY r.k"
            ),
        )

    try:
        from shelltrace.agent.ports import McpMemoryToolPort
        from shelltrace.mcp_server import build_mcp

        with TestClient(
            create_app(settings, store, lambda: McpMemoryToolPort(build_mcp(store)))
        ) as client:
            payload = {
                "workspace": workspace,
                "entity_id": "c_juniper",
                "as_of": "2024-01-01",
                "mode": "playbook",
            }
            case_before = client.post("/api/cases", json=payload)
            assert case_before.status_code == 200
            assert case_before.json()["disposition"] == "ESCALATE"
            candidates = ro(
                graph,
                "MATCH (a:Entity)-[c:CANDIDATE_SAME_AS]->(b:Entity) WHERE c.state='pending' RETURN a.id AS a_id,b.id AS b_id ORDER BY a_id LIMIT 3",
            )
            assert candidates
            before = snapshot()
            live_responses = []
            for pair in candidates:
                response = client.post(
                    "/api/aliases/judge", params={"workspace": workspace}, json=pair
                )
                assert response.status_code == 200
                answer = response.json()
                assert answer["recommendation"] in {
                    "same_entity",
                    "different_entity",
                    "uncertain",
                }
                live_responses.append(answer)
                assert snapshot() == before
            assert any(
                answer["source"] == "jev" for answer in live_responses
            ), live_responses
            case_after = client.post("/api/cases", json=payload)
            assert case_after.status_code == 200
            assert case_after.json()["disposition"] == case_before.json()["disposition"]

            def semantic_packs(response):
                return {
                    name: {
                        key: value for key, value in pack.items() if key != "latency_ms"
                    }
                    for name, pack in response.json()["packs"].items()
                }

            assert semantic_packs(case_after) == semantic_packs(case_before)
    finally:
        store.drop(workspace)
