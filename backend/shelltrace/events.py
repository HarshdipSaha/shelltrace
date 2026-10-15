from __future__ import annotations

import inspect
from dataclasses import dataclass, field

from .agent.runner import run_case
from .db import GraphStore, rw
from .graph.impact import (
    apply_designation,
    blast_radius,
    downstream_candidates,
    event_id,
)
from .graph.ownership import canon_of
from .memory.cases import CaseStore
from .models import CaseRequest, CaseResult, DesignationEvent


LINK_RECHECK = """
MATCH (new:Case {id:$new_id}), (old:Case {id:$old_id}), (event:Event {id:$event_id})
MERGE (new)-[:RECHECK_OF]->(old)
MERGE (event)-[:TRIGGERED]->(new)
RETURN new.id AS case_id"""


@dataclass
class EventOutcome:
    event_id: str
    designation_key: str
    blast_radius: list[dict]
    rechecked: list[dict] = field(default_factory=list)
    notifications: list[dict] = field(default_factory=list)
    duplicate: bool = False


async def _run_watch_case(
    req: CaseRequest,
    cases: CaseStore,
    port_factory,
    settings,
) -> CaseResult:
    candidate = port_factory() if callable(port_factory) else port_factory
    if inspect.isawaitable(candidate):
        candidate = await candidate
    if hasattr(candidate, "__aenter__"):
        async with candidate as port:
            return await run_case(
                req,
                port,
                cases,
                None,
                settings,
                settings.snapshot,
                actor_override="watch-agent",
            )
    return await run_case(
        req,
        candidate,
        cases,
        None,
        settings,
        settings.snapshot,
        actor_override="watch-agent",
    )


async def process_designation(
    store: GraphStore,
    ev: DesignationEvent,
    port_factory,
    settings,
) -> EventOutcome:
    eid = event_id(ev)
    graphs = [store.template()]
    graphs.extend(store.workspace(ws) for ws in sorted(set(store.workspaces())))
    designation_key = None
    for graph in graphs:
        designation_key = apply_designation(graph, ev)

    # GraphStore always has a template, so this is only a defensive type guard.
    if designation_key is None:
        raise RuntimeError("designation was not applied to any graph")

    graph = store.workspace(ev.workspace)
    cases = CaseStore(graph)
    fresh = cases.record_event(eid, "designation", ev.model_dump())
    if not fresh:
        return EventOutcome(eid, designation_key, [], duplicate=True)

    downstream = downstream_candidates(graph, ev.entity_id, ev.listed_on)
    case_canons = sorted({*downstream, canon_of(graph, ev.entity_id)})
    radius = blast_radius(graph, ev, designation_key, case_canons)
    rechecked = []
    notifications = []

    for watched in cases.watched_cases(case_canons):
        old_case_id = watched["case_id"]
        old_result = cases.get(old_case_id)
        if old_result is None:
            continue
        as_of = max(watched["as_of"], ev.listed_on)
        request = CaseRequest(
            workspace=ev.workspace,
            entity_id=watched["entity_id"],
            as_of=as_of,
            max_hops=watched["max_hops"],
            rulepacks=watched["rulepacks"],
            mode="playbook",
        )
        new_result = await _run_watch_case(request, cases, port_factory, settings)
        rw(
            graph,
            LINK_RECHECK,
            {"new_id": new_result.case_id, "old_id": old_case_id, "event_id": eid},
        )
        rechecked.append(
            {
                "case_id": old_case_id,
                "new_case_id": new_result.case_id,
                "old": old_result.disposition,
                "new": new_result.disposition,
            }
        )

        if old_result.disposition != new_result.disposition:
            new_proof = sorted(
                {key for pack in new_result.packs.values() for key in pack.proof}
            )
            diff = {
                "new_proof": new_proof,
                "event": eid,
                "new_case_id": new_result.case_id,
            }
            if cases.notify(
                eid,
                old_case_id,
                old_result.disposition,
                new_result.disposition,
                diff,
            ):
                notifications.append(
                    {
                        "case_id": old_case_id,
                        "old": old_result.disposition,
                        "new": new_result.disposition,
                        "event_id": eid,
                        "new_case_id": new_result.case_id,
                        "diff": diff,
                    }
                )

    return EventOutcome(eid, designation_key, radius, rechecked, notifications)
