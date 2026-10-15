from __future__ import annotations

import asyncio
import hashlib
import time
from typing import Any

from pydantic import ValidationError

from ..db import ro
from ..graph.ownership import canon_of
from ..memory.cases import CaseStore, canonical_json
from ..models import (
    AliasCandidate,
    Authorisation,
    Bounds,
    CaseRequest,
    CaseResult,
    EvidenceItem,
    PackResult,
    PriorCase,
    Proposal,
    RedFlag,
    Stake,
    StepIn,
    TraceEdge,
    TraceNode,
    TraceResult,
)
from .authorise import authorise
from .brain import Action, Brain, BrainUnavailable
from .ports import ToolCallResult, ToolPort, ToolSpec

EXPLORABLE = {
    "entity_search",
    "exposure_trace",
    "ownership_stakes",
    "rulepack_evaluate",
    "alias_candidates",
    "red_flags",
    "neighborhood",
    "evidence_get",
    "case_history",
}


def MANDATORY(req: CaseRequest) -> list[tuple[str, dict[str, Any]]]:
    base = {"workspace": req.workspace, "entity_id": req.entity_id}
    auth = {"authorities": list(req.rulepacks)}
    return (
        [
            ("case_history", {**base, "as_of": req.as_of}),
            (
                "exposure_trace",
                {
                    **base,
                    "as_of": req.as_of,
                    "max_hops": req.max_hops,
                    "mode": "ownership",
                    **auth,
                },
            ),
        ]
        + [
            (
                "rulepack_evaluate",
                {
                    **base,
                    "as_of": req.as_of,
                    "rulepack": pack,
                    "max_hops": req.max_hops,
                    "exclude_keys": [],
                    "counterfactuals": True,
                },
            )
            for pack in req.rulepacks
        ]
        + [
            (
                "red_flags",
                {**base, "as_of": req.as_of, "max_hops": req.max_hops, **auth},
            ),
            ("alias_candidates", {**base, "limit": 10}),
            ("ownership_stakes", {**base, "as_of": req.as_of}),
        ]
    )


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()[:16]


def _evidence_keys(value: Any) -> list[str]:
    keys: set[str] = set()
    evidence_fields = {"k", "evidence_keys", "proof", "decisive", "presumptions", "designation_key"}

    def visit(item: Any, field: str | None = None) -> None:
        if isinstance(item, dict):
            for name, child in item.items():
                visit(child, name)
        elif isinstance(item, (list, tuple, set)):
            for child in item:
                visit(child, field)
        elif field in evidence_fields and isinstance(item, str) and item:
            keys.add(item)

    visit(value)
    return sorted(keys)


def _models(data: dict[str, Any] | None, field: str, model):
    if not isinstance(data, dict):
        return []
    values = data.get(field)
    if not isinstance(values, list):
        return []
    parsed = []
    for value in values:
        try:
            parsed.append(model.model_validate(value))
        except (ValidationError, TypeError, ValueError):
            continue
    return parsed


def _trace_result(
    response: ToolCallResult | None,
    evidence: dict[str, EvidenceItem],
    req: CaseRequest,
) -> TraceResult | None:
    if response is None or not response.ok or not isinstance(response.data, dict):
        return None
    data = response.data
    if not data.get("found"):
        return None
    designation_key = data.get("designation_key")
    if not isinstance(designation_key, str):
        return None
    designation = evidence.get(designation_key)
    try:
        return TraceResult(
            hops=int(data.get("hops") or 0),
            nodes=[TraceNode.model_validate(node) for node in data.get("nodes", [])],
            edges=[TraceEdge.model_validate(edge) for edge in data.get("edges", [])],
            designation_key=designation_key,
            authority=data["authority"],
            program=designation.to_name if designation is not None else "",
            listed_on=(
                designation.listed_on
                if designation is not None and designation.listed_on is not None
                else req.as_of
            ),
            mode="ownership",
            cypher=data.get("cypher") or "",
            latency_ms=response.latency_ms,
        )
    except (KeyError, TypeError, ValueError, ValidationError):
        return None


def _trace_node(graph, entity_id: str) -> tuple[str, TraceNode]:
    canon = canon_of(graph, entity_id)
    rows = ro(
        graph,
        """MATCH (e:Entity {id:$id})
           RETURN e.id AS id, e.name AS name, e.kind AS kind, e.country AS country""",
        {"id": entity_id},
    )
    if not rows:
        raise KeyError(entity_id)
    return canon, TraceNode.model_validate(rows[0])


def _view(req, steps_left, calls_left, calls):
    return {
        "case": {
            "entity_id": req.entity_id,
            "as_of": req.as_of,
            "rulepacks": list(req.rulepacks),
            "max_hops": req.max_hops,
        },
        "budget_left": {"steps": steps_left, "model_calls": calls_left},
        "evidence_so_far": [
            {
                "tool": name,
                "args": args,
                "summary": canonical_json(result.data)[:1500],
            }
            for name, args, result in calls
        ],
    }


async def run_case(
    req: CaseRequest,
    port: ToolPort,
    cases: CaseStore,
    brain: Brain | None,
    settings,
    snapshot: str,
    *,
    actor_override: str | None = None,
) -> CaseResult:
    started = time.monotonic()
    graph = cases.g
    canon, entity = _trace_node(graph, req.entity_id)
    case_id = cases.open(req, canon, snapshot)
    cases.append_step(
        case_id,
        StepIn(
            kind="intake",
            args=req.model_dump(),
            actor=actor_override or "system",
        ),
    )

    calls: list[tuple[str, dict[str, Any], ToolCallResult]] = []
    called: dict[tuple[str, str], ToolCallResult] = {}

    def remember(name: str, args: dict[str, Any], result: ToolCallResult) -> None:
        called[(name, canonical_json(args))] = result
        calls.append((name, args, result))

    async def call_tool(
        name: str,
        args: dict[str, Any],
        actor: str,
        rationale: str | None = None,
        probability: float | None = None,
        *,
        timeout_s: float | None = None,
    ) -> ToolCallResult:
        timeout = settings.tool_timeout_s if timeout_s is None else timeout_s
        call_started = time.monotonic()
        try:
            result = await asyncio.wait_for(port.call(name, args), timeout=timeout)
        except asyncio.TimeoutError:
            result = ToolCallResult(
                False,
                None,
                "timeout",
                int((time.monotonic() - call_started) * 1000),
            )
        remember(name, args, result)
        keys = _evidence_keys(result.data) if result.ok else []
        cases.append_step(
            case_id,
            StepIn(
                kind="tool",
                tool=name,
                args=args,
                result_digest=_digest(result.data),
                evidence_keys=keys,
                probability=probability,
                rationale=rationale,
                latency_ms=result.latency_ms,
                actor=actor_override or actor,
                fallback_reason=(
                    None
                    if result.ok
                    else ("timeout" if result.error == "timeout" else "tool_error")
                ),
            ),
        )
        return result

    tool_specs: list[ToolSpec] = []
    if req.mode == "agent" and brain is not None:
        try:
            tool_specs = await asyncio.wait_for(
                port.list_tools(), timeout=settings.tool_timeout_s
            )
        except Exception:
            tool_specs = []

        wall_deadline = started + settings.budget_wall_s
        steps_used = 0
        model_calls = 0
        max_steps = max(0, int(settings.budget_steps))
        max_model_calls = max(0, int(settings.budget_model_calls))
        while steps_used < max_steps and model_calls < max_model_calls:
            remaining = wall_deadline - time.monotonic()
            if remaining <= 0:
                cases.append_step(
                    case_id,
                    StepIn(
                        kind="decision",
                        actor=actor_override or brain.model_id,
                        rationale="The exploration wall-clock budget was exhausted.",
                        fallback_reason="budget_exhausted",
                    ),
                )
                break
            model_calls += 1
            try:
                action = await asyncio.wait_for(
                    brain.next_action(
                        _view(
                            req,
                            max_steps - steps_used,
                            max_model_calls - model_calls,
                            calls,
                        ),
                        tool_specs,
                    ),
                    timeout=remaining,
                )
            except BrainUnavailable as exc:
                cases.append_step(
                    case_id,
                    StepIn(
                        kind="decision",
                        actor=actor_override or brain.model_id,
                        rationale=str(exc),
                        fallback_reason="brain_unavailable",
                    ),
                )
                break
            except asyncio.TimeoutError:
                cases.append_step(
                    case_id,
                    StepIn(
                        kind="decision",
                        actor=actor_override or brain.model_id,
                        rationale="The reasoning call exceeded the wall-clock budget.",
                        fallback_reason="budget_exhausted",
                    ),
                )
                break

            steps_used += 1
            if action.kind == "stop":
                cases.append_step(
                    case_id,
                    StepIn(
                        kind="decision",
                        actor=actor_override or brain.model_id,
                        rationale=action.rationale,
                        probability=action.probability,
                    ),
                )
                break
            if (
                action.kind != "tool"
                or action.tool not in EXPLORABLE
                or not isinstance(action.args, dict)
                or action.args.get("workspace") != req.workspace
            ):
                cases.append_step(
                    case_id,
                    StepIn(
                        kind="decision",
                        actor=actor_override or brain.model_id,
                        args=action.args if isinstance(action.args, dict) else {},
                        rationale=action.rationale,
                        probability=action.probability,
                        fallback_reason="tool_not_allowed",
                    ),
                )
                continue

            remaining = wall_deadline - time.monotonic()
            if remaining <= 0:
                cases.append_step(
                    case_id,
                    StepIn(
                        kind="decision",
                        actor=actor_override or brain.model_id,
                        rationale="The exploration wall-clock budget was exhausted.",
                        fallback_reason="budget_exhausted",
                    ),
                )
                break
            result = await call_tool(
                action.tool,
                action.args,
                brain.model_id,
                action.rationale,
                action.probability,
                timeout_s=min(settings.tool_timeout_s, remaining),
            )
            brain.observe(action, result)

    elif req.mode == "agent" and brain is None:
        cases.append_step(
            case_id,
            StepIn(
                kind="decision",
                actor=actor_override or "policy",
                rationale="No reasoning brain is configured; deterministic policy completion will continue.",
                fallback_reason="brain_unavailable",
            ),
        )

    policy_actor = actor_override or (
        "playbook" if req.mode == "playbook" else "policy"
    )
    for name, args in MANDATORY(req):
        key = (name, canonical_json(args))
        if key in called:
            continue
        await call_tool(name, args, policy_actor, rationale="mandatory policy completion")

    # The target-only candidate listing in MANDATORY preserves the shared tool
    # contract. This dated scope query also finds pending aliases on upstream
    # owners, which can affect the case disposition even when the target itself
    # has no candidate edge.
    scoped_alias_args = {
        "workspace": req.workspace,
        "entity_id": req.entity_id,
        "limit": 10,
        "as_of": req.as_of,
        "max_hops": req.max_hops,
        "authorities": list(req.rulepacks),
    }
    scoped_alias_key = ("alias_candidates", canonical_json(scoped_alias_args))
    if scoped_alias_key not in called:
        await call_tool(
            "alias_candidates",
            scoped_alias_args,
            policy_actor,
            rationale="check pending aliases across the dated ownership scope",
        )

    def result_for(name: str, args: dict[str, Any]) -> ToolCallResult | None:
        return called.get((name, canonical_json(args)))

    mandatory = dict(MANDATORY(req))
    pack_results: dict[str, PackResult] = {}
    unevaluated: list[str] = []
    for pack_id in req.rulepacks:
        response = result_for("rulepack_evaluate", next(
            args for name, args in MANDATORY(req)
            if name == "rulepack_evaluate" and args["rulepack"] == pack_id
        ))
        parsed = None
        if response is not None and response.ok and isinstance(response.data, dict):
            try:
                parsed = PackResult.model_validate(response.data)
            except (ValidationError, TypeError, ValueError):
                parsed = None
        if parsed is None or parsed.rulepack != pack_id:
            if pack_id not in unevaluated:
                unevaluated.append(pack_id)
        else:
            pack_results[pack_id] = parsed

    def response_data(name: str) -> tuple[dict[str, Any] | None, ToolCallResult | None]:
        response = result_for(name, mandatory[name])
        return (
            response.data if response is not None and response.ok else None,
            response,
        )

    history_data, _ = response_data("case_history")
    trace_data, trace_response = response_data("exposure_trace")
    flags_data, _ = response_data("red_flags")
    aliases_data, _ = response_data("alias_candidates")
    stakes_data, _ = response_data("ownership_stakes")

    prior_cases = _models(history_data, "prior_cases", PriorCase)
    red_flags = _models(flags_data, "flags", RedFlag)
    candidates = _models(aliases_data, "candidates", AliasCandidate)
    scoped_alias_response = called.get(scoped_alias_key)
    if scoped_alias_response is not None and scoped_alias_response.ok:
        candidates.extend(
            _models(scoped_alias_response.data, "candidates", AliasCandidate)
        )
    candidates = list(
        {
            tuple(sorted((candidate.a_id, candidate.b_id))): candidate
            for candidate in candidates
        }.values()
    )
    stakes = _models(stakes_data, "stakes", Stake)

    evidence_keys: set[str] = set()
    for pack in pack_results.values():
        evidence_keys.update(pack.proof)
        evidence_keys.update(pack.decisive)
        evidence_keys.update(pack.presumptions)
    for flag in red_flags:
        evidence_keys.update(flag.evidence_keys)
    if isinstance(trace_data, dict) and trace_data.get("found"):
        evidence_keys.update(_evidence_keys(trace_data))

    evidence: dict[str, EvidenceItem] = {}
    ordered_keys = sorted(evidence_keys)
    for start_index in range(0, len(ordered_keys), 20):
        chunk = ordered_keys[start_index : start_index + 20]
        response = await call_tool(
            "evidence_get",
            {"workspace": req.workspace, "keys": chunk},
            "policy",
            rationale="collect evidence for the deterministic decision",
        )
        if response.ok:
            for item in _models(response.data, "items", EvidenceItem):
                evidence[item.k] = item

    trace_result = _trace_result(trace_response, evidence, req)
    pending = [
        candidate
        for candidate in candidates
        if candidate.state == "pending" and candidate.touches_designated
    ]
    scope_sizes = [pack.scope_size for pack in pack_results.values()]
    bounds = Bounds(
        as_of=req.as_of,
        max_hops=req.max_hops,
        rel_scope=["OWNS", "CONTROLS", "SAME_AS (accepted)"],
        rulepacks=list(req.rulepacks),
        snapshot=snapshot,
        scope_nodes=max(scope_sizes, default=0),
        truncated=any(pack.scope_truncated for pack in pack_results.values()),
    )
    auth = authorise(
        pack_results,
        red_flags,
        pending,
        evidence,
        bounds,
        unevaluated,
    )

    proposal: Proposal | None = None
    if req.mode == "playbook":
        proposal = Proposal(
            disposition=auth.disposition,
            rationale="playbook",
            confidence=1.0,
            evidence_keys=sorted(
                {key for reason in auth.reasons for key in reason.evidence_keys}
            ),
        )
    elif brain is not None:
        if model_calls >= max_model_calls:
            cases.append_step(
                case_id,
                StepIn(
                    kind="decision",
                    actor=actor_override or brain.model_id,
                    rationale="The model-call budget was exhausted before proposal.",
                    fallback_reason="budget_exhausted",
                ),
            )
        else:
            try:
                remaining = max(0.001, wall_deadline - time.monotonic())
                model_calls += 1
                proposal = await asyncio.wait_for(
                    brain.propose(
                        _view(
                            req,
                            max(0, max_steps - steps_used),
                            max(0, max_model_calls - model_calls),
                            calls,
                        )
                    ),
                    timeout=remaining,
                )
                proposal = Proposal.model_validate(proposal)
            except BrainUnavailable as exc:
                cases.append_step(
                    case_id,
                    StepIn(
                        kind="decision",
                        actor=actor_override or brain.model_id,
                        rationale=str(exc),
                        fallback_reason="brain_unavailable",
                    ),
                )
            except (asyncio.TimeoutError, ValidationError, TypeError, ValueError):
                cases.append_step(
                    case_id,
                    StepIn(
                        kind="decision",
                        actor=actor_override or brain.model_id,
                        rationale="The reasoning model could not produce a valid proposal within budget.",
                        fallback_reason="brain_unavailable",
                    ),
                )

    proposal_overridden = proposal is not None and proposal.disposition != auth.disposition
    if proposal is not None:
        proposal_actor = actor_override or (
            brain.model_id
            if brain is not None and req.mode == "agent"
            else "playbook"
        )
        cases.append_step(
            case_id,
            StepIn(
                kind="proposal",
                actor=proposal_actor,
                args={"disposition": proposal.disposition},
                evidence_keys=proposal.evidence_keys,
                probability=proposal.confidence,
                rationale=proposal.rationale,
                result_digest=_digest(proposal.model_dump()),
            ),
        )

    cases.append_step(
        case_id,
        StepIn(
            kind="authorise",
            actor=actor_override or "policy",
            args={"disposition": auth.disposition},
            evidence_keys=sorted(
                {key for reason in auth.reasons for key in reason.evidence_keys}
            ),
            rationale=auth.reasons[0].detail if auth.reasons else "Deterministic authorisation completed.",
            result_digest=_digest(auth.model_dump()),
        ),
    )

    result = CaseResult(
        case_id=case_id,
        workspace=req.workspace,
        entity=entity,
        as_of=req.as_of,
        max_hops=req.max_hops,
        rulepacks=list(req.rulepacks),
        mode=req.mode,
        actor_model=actor_override
        or (
            brain.model_id
            if brain is not None and req.mode == "agent"
            else ("playbook" if req.mode == "playbook" else "policy")
        ),
        disposition=auth.disposition,
        reasons=auth.reasons,
        proposal=proposal,
        proposal_overridden=proposal_overridden,
        packs=pack_results,
        trace=trace_result,
        red_flags=red_flags,
        alias_candidates=candidates,
        prior_cases=prior_cases,
        stakes=stakes,
        evidence=evidence,
        bounds=bounds,
        steps=cases.steps(case_id),
        latency_ms=int((time.monotonic() - started) * 1000),
        snapshot=snapshot,
    )
    cases.finish(case_id, result)
    return result
