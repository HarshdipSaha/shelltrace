from uuid import uuid4

import pytest

from shelltrace.agent.ports import McpMemoryToolPort
from shelltrace.agent.runner import run_case
from shelltrace.config import get_settings
from shelltrace.db import ro, rw
from shelltrace.graph.ownership import evaluate
from shelltrace.memory.cases import CaseStore
from shelltrace.mcp_server import build_mcp
from shelltrace.models import CaseRequest, DesignationEvent
from shelltrace.rulepacks import get_pack
from shelltrace.seed.synthetic import load_synthetic

from shelltrace.events import process_designation
from shelltrace.graph.impact import designation_key as impact_designation_key
from shelltrace.graph.impact import downstream_candidates, event_id


def fresh(store):
    workspace = f"ev_{uuid4().hex[:8]}"
    store.provision(workspace, seeder=load_synthetic, force_seed=True)
    return workspace


def designation(workspace):
    return DesignationEvent(
        workspace=workspace,
        entity_id="p_nikos",
        authority="OFAC",
        program="SDN (demo)",
        listed_on="2024-03-15",
        source="Demo injection",
    )


def clear_designation(store, key):
    query = "MATCH ()-[d:DESIGNATED {k:$k}]->() DELETE d"
    rw(store.template(), query, {"k": key})
    for workspace in store.workspaces():
        rw(store.workspace(workspace), query, {"k": key})


def drop_workspaces(store, workspaces):
    for workspace in workspaces:
        if workspace in store.workspaces():
            store.drop(workspace)


async def run_playbook(store, workspace, entity_id, as_of):
    settings = get_settings()
    request = CaseRequest(
        workspace=workspace,
        entity_id=entity_id,
        as_of=as_of,
        max_hops=6,
        rulepacks=["OFAC", "EU", "UK"],
        mode="playbook",
    )
    async with McpMemoryToolPort(build_mcp(store)) as port:
        return await run_case(
            request,
            port,
            CaseStore(store.workspace(workspace)),
            None,
            settings,
            settings.snapshot,
        )


def memory_port(store):
    server = build_mcp(store)
    return lambda: McpMemoryToolPort(server)


@pytest.mark.asyncio
async def test_designation_flips_watched_case_and_deduplicates(store):
    workspace = fresh(store)
    ev = designation(workspace)
    cases = CaseStore(store.workspace(workspace))
    try:
        clear = await run_playbook(store, workspace, "c_aegean", "2024-03-01")
        assert clear.disposition == "CLEAR_WITHIN_BOUNDS"
        cases.set_watch(clear.case_id, True)

        out = await process_designation(
            store, ev, port_factory=memory_port(store), settings=get_settings()
        )

        assert {item["entity_id"] for item in out.blast_radius} == {
            "c_aegean",
            "c_olive",
        }
        assert [
            (item["case_id"], item["old"], item["new"])
            for item in out.notifications
        ] == [(clear.case_id, "CLEAR_WITHIN_BOUNDS", "EXPOSED")]
        assert len(out.rechecked) == 1
        recheck = out.rechecked[0]
        new_case = cases.get(recheck["new_case_id"])
        assert new_case.disposition == "EXPOSED"
        assert new_case.actor_model == "watch-agent"
        assert all(step.actor == "watch-agent" for step in new_case.steps)

        assert ro(
            store.workspace(workspace),
            """MATCH (new:Case {id:$new})-[:RECHECK_OF]->(old:Case {id:$old}),
                      (event:Event {id:$event})-[:TRIGGERED]->(new)
               RETURN count(new) AS linked""",
            {"new": recheck["new_case_id"], "old": clear.case_id, "event": out.event_id},
        )[0]["linked"] == 1
        assert ro(
            store.workspace(workspace),
            """MATCH (n:Notification {event_id:$event})-[:NOTIFIED]->(old:Case {id:$case})
               RETURN count(n) AS linked""",
            {"event": out.event_id, "case": clear.case_id},
        )[0]["linked"] == 1

        again = await process_designation(
            store, ev, port_factory=memory_port(store), settings=get_settings()
        )
        assert again.duplicate and again.notifications == []
        assert again.rechecked == []
    finally:
        clear_designation(store, impact_designation_key(ev))
        drop_workspaces(store, [workspace])


@pytest.mark.asyncio
async def test_unwatched_cases_are_not_rerun(store):
    workspace = fresh(store)
    ev = designation(workspace)
    try:
        clear = await run_playbook(store, workspace, "c_aegean", "2024-03-01")
        assert clear.disposition == "CLEAR_WITHIN_BOUNDS"

        out = await process_designation(
            store, ev, port_factory=memory_port(store), settings=get_settings()
        )

        assert {item["entity_id"] for item in out.blast_radius} == {
            "c_aegean",
            "c_olive",
        }
        assert out.rechecked == []
        assert out.notifications == []
    finally:
        clear_designation(store, impact_designation_key(ev))
        drop_workspaces(store, [workspace])


@pytest.mark.asyncio
async def test_designation_updates_template_existing_and_future_workspaces(store):
    workspace = fresh(store)
    existing = fresh(store)
    future = f"ev_{uuid4().hex[:8]}"
    ev = designation(workspace)
    try:
        out = await process_designation(
            store, ev, port_factory=memory_port(store), settings=get_settings()
        )
        store.provision(future, seeder=load_synthetic)

        assert evaluate(
            store.template(), "c_olive", ev.listed_on, get_pack("OFAC")
        ).verdict == "BLOCKED"
        assert evaluate(
            store.workspace(existing), "c_olive", ev.listed_on, get_pack("OFAC")
        ).verdict == "BLOCKED"
        assert evaluate(
            store.workspace(future), "c_olive", ev.listed_on, get_pack("OFAC")
        ).verdict == "BLOCKED"
        assert out.event_id == event_id(ev)
        assert out.designation_key == impact_designation_key(ev)
    finally:
        clear_designation(store, impact_designation_key(ev))
        drop_workspaces(store, [workspace, existing, future])


def test_downstream_candidates_follow_ownership_out_and_respect_cap(store):
    workspace = fresh(store)
    try:
        graph = store.workspace(workspace)
        candidates = downstream_candidates(graph, "p_volkov", "2024-01-01")
        assert {
            "c_meridian",
            "c_bluelagoon",
            "c_nordharbor",
            "c_alder",
            "c_birch",
        } <= set(candidates)
        assert len(downstream_candidates(graph, "p_volkov", "2024-01-01", cap=2)) <= 2
    finally:
        drop_workspaces(store, [workspace])


def test_event_id_is_deterministic():
    ev = designation("demo")

    assert event_id(ev) == event_id(ev.model_copy())
