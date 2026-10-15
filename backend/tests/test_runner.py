from dataclasses import replace
from uuid import uuid4

import pytest

from shelltrace.agent.brain import Action, ScriptedBrain
from shelltrace.agent.ports import McpMemoryToolPort
from shelltrace.agent.runner import run_case
from shelltrace.config import get_settings
from shelltrace.memory.cases import CaseStore
from shelltrace.mcp_server import build_mcp
from shelltrace.models import CaseRequest, Proposal
from shelltrace.seed.synthetic import load_synthetic


@pytest.fixture(scope="module")
def runner_workspace(store):
    """Keep persisted case and step nodes out of the seed-provenance fixture."""
    workspace = f"r_{uuid4().hex[:8]}"
    store.provision(workspace, seeder=load_synthetic, force_seed=True)
    try:
        yield workspace
    finally:
        store.drop(workspace)


def _request(workspace, entity_id="c_nordharbor", mode="playbook"):
    return CaseRequest(
        workspace=workspace,
        entity_id=entity_id,
        as_of="2024-01-01",
        max_hops=6,
        rulepacks=["OFAC", "EU", "UK"],
        mode=mode,
    )


async def _run(store, req, brain=None, settings=None):
    cases = CaseStore(store.workspace(req.workspace))
    async with McpMemoryToolPort(build_mcp(store)) as port:
        result = await run_case(
            req,
            port,
            cases,
            brain,
            settings or get_settings(),
            get_settings().snapshot,
        )
    return result, cases


async def test_playbook_exposes_hero(store, runner_workspace):
    req = _request(runner_workspace)
    result, cases = await _run(store, req)

    assert result.disposition == "EXPOSED"
    assert {name: pack.verdict for name, pack in result.packs.items()} == {
        "OFAC": "BLOCKED",
        "EU": "BLOCKED",
        "UK": "BLOCKED",
    }
    tool_steps = [step for step in result.steps if step.kind == "tool"]
    assert [step.tool for step in tool_steps[:3]] == [
        "case_history",
        "exposure_trace",
        "rulepack_evaluate",
    ]
    # The phase-specific evidence fetch is attributed to policy; mandatory playbook calls are playbook-owned.
    assert all(step.actor == "playbook" for step in tool_steps if step.tool != "evidence_get")
    assert any(step.actor == "policy" and step.tool == "evidence_get" for step in tool_steps)
    assert cases.verify_chain(result.case_id)


@pytest.mark.parametrize(
    "entity_id,disposition",
    [
        ("c_birch", "EXPOSED"),
        ("c_dune", "ESCALATE"),
        ("c_elm", "CLEAR_WITHIN_BOUNDS"),
        ("c_fjord", "ESCALATE"),
        ("c_juniper", "ESCALATE"),
        ("c_maple", "ESCALATE"),
    ],
)
async def test_playbook_dispositions_golden(store, runner_workspace, entity_id, disposition):
    result, _ = await _run(store, _request(runner_workspace, entity_id))

    assert result.disposition == disposition, result.model_dump()


async def test_agent_steps_recorded_with_probability(store, runner_workspace):
    req = _request(runner_workspace, mode="agent")
    mandatory_ofac = {
        "workspace": runner_workspace,
        "entity_id": req.entity_id,
        "as_of": req.as_of,
        "rulepack": "OFAC",
        "max_hops": req.max_hops,
        "exclude_keys": [],
        "counterfactuals": True,
    }
    brain = ScriptedBrain(
        [
            Action(
                "tool",
                "rulepack_evaluate",
                mandatory_ofac,
                "check OFAC first",
                0.8,
            ),
            Action("stop", None, {}, "done", None),
        ]
    )

    result, _ = await _run(store, req, brain)

    first_scripted = next(step for step in result.steps if step.actor == "scripted" and step.kind == "tool")
    assert (first_scripted.tool, first_scripted.probability) == ("rulepack_evaluate", 0.8)
    assert first_scripted.rationale == "check OFAC first"
    assert sum(step.kind == "tool" and step.tool == "rulepack_evaluate" for step in result.steps) == 3
    assert all(step.actor == "policy" for step in result.steps if step.kind == "tool" and step.actor != "scripted")


async def test_agent_cannot_change_disposition(store, runner_workspace):
    req = _request(runner_workspace, "c_kestrel", "agent")
    brain = ScriptedBrain(
        [Action("stop", None, {}, "enough evidence", None)],
        proposal=Proposal(
            disposition="CLEAR_WITHIN_BOUNDS",
            rationale="The model proposes a clear result.",
            confidence=0.7,
            evidence_keys=[],
        ),
    )

    result, _ = await _run(store, req, brain)

    assert result.disposition == "EXPOSED"
    assert result.proposal.disposition == "CLEAR_WITHIN_BOUNDS"
    assert result.proposal_overridden is True


async def test_brain_outage_falls_back(store, runner_workspace):
    req = _request(runner_workspace, mode="agent")
    result, _ = await _run(store, req, ScriptedBrain([], fail_after=0))

    assert result.disposition == "EXPOSED"
    assert any(step.fallback_reason == "brain_unavailable" for step in result.steps)
    assert all(pack.verdict == "BLOCKED" for pack in result.packs.values())


async def test_budget_exhaustion(store, runner_workspace):
    req = _request(runner_workspace, mode="agent")
    actions = [
        Action(
            "tool",
            "neighborhood",
            {"workspace": runner_workspace, "entity_id": req.entity_id, "depth": 1, "limit": 10},
            "inspect one bounded context neighborhood",
            0.2,
        )
        for _ in range(20)
    ]
    settings = replace(get_settings(), budget_steps=8, budget_model_calls=40)

    result, _ = await _run(store, req, ScriptedBrain(actions), settings)

    explored = [
        step
        for step in result.steps
        if step.kind == "tool" and step.actor == "scripted" and step.tool == "neighborhood"
    ]
    assert len(explored) == 8


async def test_unknown_tool_from_brain_is_refused(store, runner_workspace):
    req = _request(runner_workspace, mode="agent")
    brain = ScriptedBrain(
        [Action("tool", "run_cypher", {"query": "MATCH (n) RETURN n"}, "try a graph query", 0.9)]
    )

    result, _ = await _run(store, req, brain)

    assert any(step.fallback_reason == "tool_not_allowed" for step in result.steps)
    assert not any(step.tool == "run_cypher" and step.kind == "tool" for step in result.steps)
    assert result.disposition == "EXPOSED"


async def test_case_on_injection_named_owner_is_exposed(store, runner_workspace):
    result, _ = await _run(store, _request(runner_workspace, "c_kestrel"))

    assert result.disposition == "EXPOSED"


async def test_prior_cases_recalled(store, runner_workspace):
    req = _request(runner_workspace)
    first, _ = await _run(store, req)
    second, _ = await _run(store, req)

    assert first.case_id in {case.case_id for case in second.prior_cases}
