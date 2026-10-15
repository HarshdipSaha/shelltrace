from dataclasses import replace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from shelltrace.config import get_settings
from shelltrace.db import rw
from shelltrace.graph.impact import designation_key
from shelltrace.mcp_server import build_mcp
from shelltrace.models import DesignationEvent
from shelltrace.seed.synthetic import load_synthetic

from shelltrace.agent.ports import McpMemoryToolPort
from shelltrace.api import create_app


@pytest.fixture(scope="module")
def api_bundle(store):
    workspace = f"api_{uuid4().hex[:8]}"
    store.provision(workspace, seeder=load_synthetic, force_seed=True)
    settings = replace(
        get_settings(),
        default_workspace=workspace,
        llm_provider="none",
        anthropic_api_key=None,
    )

    def memory_port():
        return McpMemoryToolPort(build_mcp(store))

    try:
        with TestClient(create_app(settings, store, memory_port)) as client:
            yield client, workspace
    finally:
        store.drop(workspace)


@pytest.fixture
def client(api_bundle):
    return api_bundle[0]


@pytest.fixture
def api_workspace(api_bundle):
    return api_bundle[1]


def case_payload(workspace, entity_id="c_nordharbor", **overrides):
    return {
        "workspace": workspace,
        "entity_id": entity_id,
        "as_of": "2024-01-01",
        "max_hops": 6,
        "rulepacks": ["OFAC", "EU", "UK"],
        "mode": "playbook",
        **overrides,
    }


def fresh(store):
    workspace = f"api_{uuid4().hex[:8]}"
    store.provision(workspace, seeder=load_synthetic, force_seed=True)
    return workspace


def clear_event(store, ev):
    key = designation_key(ev)
    query = "MATCH ()-[d:DESIGNATED {k:$key}]->() DELETE d"
    rw(store.template(), query, {"key": key})
    for workspace in store.workspaces():
        rw(store.workspace(workspace), query, {"key": key})


async def test_health(client):
    response = client.get("/api/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["node_count"] > 0
    assert data["llm"] in {"deterministic", "claude-opus-5"}


def test_entities_search(client, api_workspace):
    response = client.get(
        "/api/entities/search",
        params={"workspace": api_workspace, "q": "nord harbor", "limit": 8},
    )

    assert response.status_code == 200
    assert response.json()["hits"][0]["id"] == "c_nordharbor"


def test_open_case_hero_exposed(client, api_workspace):
    response = client.post("/api/cases", json=case_payload(api_workspace))

    assert response.status_code == 200
    data = response.json()
    assert data["disposition"] == "EXPOSED"
    assert {"syn:G1-1", "syn:G1-2", "syn:G1-3"} <= set(data["packs"]["OFAC"]["proof"])
    assert data["steps"]
    assert data["bounds"]["max_hops"] == 6


def test_regime_switch(client, api_workspace):
    uk = client.post(
        "/api/cases",
        json=case_payload(api_workspace, "c_birch", rulepacks=["UK"]),
    )
    ofac = client.post(
        "/api/cases",
        json=case_payload(api_workspace, "c_birch", rulepacks=["OFAC"]),
    )

    assert uk.json()["disposition"] == "CLEAR_WITHIN_BOUNDS"
    assert ofac.json()["disposition"] == "EXPOSED"


def test_time_switch(client, api_workspace):
    old = client.post(
        "/api/cases",
        json=case_payload(api_workspace, "c_larch", as_of="2022-06-01"),
    )
    current = client.post(
        "/api/cases",
        json=case_payload(api_workspace, "c_larch", as_of="2024-01-01"),
    )

    assert old.json()["disposition"] == "EXPOSED"
    assert current.json()["disposition"] == "CLEAR_WITHIN_BOUNDS"


def test_unknown_entity_404(client, api_workspace):
    response = client.post(
        "/api/cases", json=case_payload(api_workspace, "c_nope")
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "entity 'c_nope' not found"}


def test_bad_request_422(client, api_workspace):
    too_many_hops = client.post(
        "/api/cases", json=case_payload(api_workspace, max_hops=7)
    )
    bad_date = client.post(
        "/api/cases", json=case_payload(api_workspace, as_of="2024/01/01")
    )

    assert too_many_hops.status_code == 422
    assert bad_date.status_code == 422


def test_review_four_eyes_409(client, api_workspace):
    case = client.post("/api/cases", json=case_payload(api_workspace)).json()
    response = client.post(
        f"/api/cases/{case['case_id']}/review",
        params={"workspace": api_workspace},
        json={
            "reviewer": "analyst-1",
            "code": "CONFIRMED_CLEAR",
            "reason": "Second review is required to clear an exposure.",
        },
    )

    assert response.status_code == 409


def test_report_endpoint(client, api_workspace):
    case = client.post("/api/cases", json=case_payload(api_workspace)).json()
    response = client.post(
        f"/api/cases/{case['case_id']}/report",
        params={"workspace": api_workspace},
    )

    assert response.status_code == 200
    report = response.json()
    assert report["writer"] == "template"
    assert all(sentence["supported"] for sentence in report["sentences"] if sentence["kind"] == "claim")


def test_watch_and_designation_flow(client, store):
    workspace = fresh(store)
    ev = DesignationEvent(
        workspace=workspace,
        entity_id="p_nikos",
        authority="OFAC",
        program="SDN (demo)",
        listed_on="2024-03-15",
        source="Demo injection",
    )
    try:
        case = client.post(
            "/api/cases",
            json=case_payload(workspace, "c_aegean", as_of="2024-03-01"),
        ).json()
        watched = client.post(
            f"/api/cases/{case['case_id']}/watch",
            params={"workspace": workspace},
            json={"active": True},
        )
        event = client.post("/api/events/designation", json=ev.model_dump())
        notifications = client.get("/api/notifications", params={"workspace": workspace})

        assert watched.status_code == 200
        assert event.status_code == 200
        assert {item["entity_id"] for item in event.json()["blast_radius"]} == {
            "c_aegean",
            "c_olive",
        }
        assert notifications.json()[0]["new"] == "EXPOSED"
    finally:
        clear_event(store, ev)
        if workspace in store.workspaces():
            store.drop(workspace)


def test_alias_decide_flow(client, store):
    workspace = fresh(store)
    try:
        accepted = client.post(
            "/api/aliases/decide",
            params={"workspace": workspace},
            json={
                "a_id": "c_ion_holdings",
                "b_id": "c_ion_alias",
                "accept": True,
                "by": "analyst-1",
                "reason": "Matched registered company identity.",
                "confirm_merge": False,
            },
        )
        case = client.post(
            "/api/cases",
            json=case_payload(workspace, "c_juniper", rulepacks=["OFAC"]),
        )
        conflict = client.post(
            "/api/aliases/decide",
            params={"workspace": workspace},
            json={
                "a_id": "c_harbor_trading",
                "b_id": "c_harbour_trading",
                "accept": True,
                "by": "analyst-1",
                "reason": "Names look similar, but identifiers conflict.",
                "confirm_merge": False,
            },
        )

        assert accepted.status_code == 200
        assert case.json()["disposition"] == "EXPOSED"
        assert conflict.status_code == 422
    finally:
        if workspace in store.workspaces():
            store.drop(workspace)


def test_name_screen_baseline(client, api_workspace):
    clear = client.post(
        "/api/screen/name",
        json={
            "workspace": api_workspace,
            "entity_id": "c_nordharbor",
            "as_of": "2024-01-01",
            "rulepacks": ["OFAC", "EU", "UK"],
        },
    )
    hit = client.post(
        "/api/screen/name",
        json={
            "workspace": api_workspace,
            "entity_id": "c_rostok",
            "as_of": "2024-01-01",
            "rulepacks": ["OFAC", "EU", "UK"],
        },
    )

    assert clear.status_code == 200 and clear.json()["hit"] is False
    assert hit.status_code == 200 and hit.json()["hit"] is True


def test_subgraph_and_eval_latest(client, api_workspace):
    subgraph = client.get(
        "/api/subgraph",
        params={"workspace": api_workspace, "entity_id": "c_nordharbor", "depth": 1},
    )
    latest = client.get("/api/eval/latest")

    assert subgraph.status_code == 200
    assert subgraph.json()["nodes"]
    assert latest.status_code == 200


def test_case_on_injection_named_owner_is_exposed(client, api_workspace):
    response = client.post(
        "/api/cases",
        json=case_payload(api_workspace, "c_kestrel", rulepacks=["OFAC"]),
    )

    assert response.status_code == 200
    assert response.json()["disposition"] == "EXPOSED"


def test_agent_mode_without_key_falls_back(client, api_workspace):
    response = client.post(
        "/api/cases",
        json=case_payload(api_workspace, mode="agent"),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["actor_model"] == "playbook"
    assert any(step["fallback_reason"] == "no_model_key" for step in data["steps"])
