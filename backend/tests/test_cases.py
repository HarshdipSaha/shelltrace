from concurrent.futures import ThreadPoolExecutor
from time import sleep
from uuid import uuid4

import pytest
from pydantic import ValidationError

from shelltrace.db import rw
from shelltrace.graph.ownership import evaluate
from shelltrace.graph.trace import trace
from shelltrace.memory import cases as cases_module
from shelltrace.memory.cases import CaseStore, FourEyesRequired
from shelltrace.models import Bounds, CaseRequest, CaseResult, ReviewIn, StepIn, TraceNode
from shelltrace.rulepacks import get_pack
from shelltrace.seed.synthetic import load_synthetic


@pytest.fixture
def case_workspace(store):
    """Keep workflow-node writes out of the shared fact-provenance fixture."""
    workspace = f"c_{uuid4().hex[:8]}"
    store.provision(workspace, seeder=load_synthetic)
    try:
        yield workspace
    finally:
        store.drop(workspace)


def _request(workspace, entity_id="c_nordharbor"):
    return CaseRequest(workspace=workspace, entity_id=entity_id, as_of="2024-01-01", max_hops=6,
                       rulepacks=["OFAC", "EU", "UK"], mode="playbook")


def _result(case_id, workspace, entity_id, disposition):
    return CaseResult(
        case_id=case_id,
        workspace=workspace,
        entity=TraceNode(id=entity_id, name=entity_id, kind="Company"),
        as_of="2024-01-01",
        max_hops=6,
        rulepacks=["OFAC", "EU", "UK"],
        mode="playbook",
        actor_model="playbook",
        disposition=disposition,
        reasons=[],
        proposal=None,
        proposal_overridden=False,
        packs={},
        trace=None,
        red_flags=[],
        alias_candidates=[],
        prior_cases=[],
        stakes=[],
        evidence={},
        bounds=Bounds(as_of="2024-01-01", max_hops=6,
                      rel_scope=["OWNS", "CONTROLS", "SAME_AS (accepted)"],
                      rulepacks=["OFAC", "EU", "UK"], snapshot="synthetic-v1",
                      scope_nodes=1, truncated=False),
        steps=[],
        latency_ms=0,
        snapshot="synthetic-v1",
    )


def _step(number):
    return StepIn(kind="tool", tool="ownership_stakes", args={"round": number},
                  result_digest=f"digest-{number}", evidence_keys=[f"syn:{number}"],
                  actor="playbook", rationale=f"step {number}")


def test_steps_are_hash_chained_and_tampering_is_detected(store, case_workspace):
    g = store.workspace(case_workspace)
    cases = CaseStore(g)
    case_id = cases.open(_request(case_workspace), "c_nordharbor", "synthetic-v1")
    for number in range(1, 4):
        cases.append_step(case_id, _step(number))

    steps = cases.steps(case_id)
    assert [step.seq for step in steps] == [1, 2, 3]
    assert steps[0].prev_hash == "GENESIS"
    assert cases.verify_chain(case_id) is True

    rw(g, "MATCH (s:Step {id:$id}) SET s.rationale='tampered'", {"id": f"{case_id}:002"})
    assert cases.verify_chain(case_id) is False


def test_concurrent_steps_are_serialized_into_one_chain(store, case_workspace, monkeypatch):
    cases = CaseStore(store.workspace(case_workspace))
    case_id = cases.open(_request(case_workspace), "c_nordharbor", "synthetic-v1")
    write = cases_module.rw

    def delayed_write(*args, **kwargs):
        # Widen the read/write window so overlapping appends expose duplicate seqs.
        sleep(0.05)
        return write(*args, **kwargs)

    monkeypatch.setattr(cases_module, "rw", delayed_write)
    with ThreadPoolExecutor(max_workers=6) as workers:
        list(workers.map(cases.append_step, [case_id] * 6, [_step(i) for i in range(6)]))

    steps = cases.steps(case_id)
    assert [step.seq for step in steps] == list(range(1, 7))
    assert cases.verify_chain(case_id) is True



def test_review_is_rejected_before_case_finalization(store, case_workspace):
    cases = CaseStore(store.workspace(case_workspace))
    case_id = cases.open(_request(case_workspace), "c_nordharbor", "synthetic-v1")

    with pytest.raises(ValueError, match="finalized"):
        cases.review(case_id, ReviewIn(reviewer="analyst-a", code="CONFIRMED_CLEAR", reason="clear after review"))


def test_case_cannot_be_refinalized_after_a_review(store, case_workspace):
    cases = CaseStore(store.workspace(case_workspace))
    case_id = cases.open(_request(case_workspace), "c_nordharbor", "synthetic-v1")
    cases.finish(case_id, _result(case_id, case_workspace, "c_nordharbor", "CLEAR_WITHIN_BOUNDS"))
    cases.review(case_id, ReviewIn(reviewer="analyst-a", code="CONFIRMED_CLEAR", reason="reviewed clear result"))

    with pytest.raises(ValueError, match="already finalized"):
        cases.finish(case_id, _result(case_id, case_workspace, "c_nordharbor", "EXPOSED"))
    assert cases.get(case_id).disposition == "CLEAR_WITHIN_BOUNDS"

def test_four_eyes_are_required_to_remove_exposure(store, case_workspace):
    cases = CaseStore(store.workspace(case_workspace))
    case_id = cases.open(_request(case_workspace), "c_nordharbor", "synthetic-v1")
    cases.finish(case_id, _result(case_id, case_workspace, "c_nordharbor", "EXPOSED"))

    with pytest.raises(FourEyesRequired):
        cases.review(case_id, ReviewIn(reviewer="analyst-a", code="CONFIRMED_CLEAR", reason="clear after review"))
    with pytest.raises(FourEyesRequired):
        cases.review(case_id, ReviewIn(reviewer="analyst-a", second_reviewer="analyst-a",
                                      code="OVERRIDDEN", reason="remove the exposure"))

    accepted = cases.review(case_id, ReviewIn(reviewer="analyst-a", second_reviewer="analyst-b",
                                               code="CONFIRMED_CLEAR", reason="clear after independent review"))
    assert accepted["second_reviewer"] == "analyst-b"

    exposed_case = cases.open(_request(case_workspace), "c_nordharbor", "synthetic-v1")
    cases.finish(exposed_case, _result(exposed_case, case_workspace, "c_nordharbor", "EXPOSED"))
    confirmed = cases.review(exposed_case, ReviewIn(reviewer="analyst-a", code="CONFIRMED_EXPOSED",
                                                     reason="evidence confirms exposure"))
    assert confirmed["code"] == "CONFIRMED_EXPOSED"


def test_review_reason_must_meet_model_minimum():
    with pytest.raises(ValidationError):
        ReviewIn(reviewer="ab", code="OVERRIDDEN", reason="short")


def test_recall_uses_graph_overlap_and_can_exclude_a_case(store, case_workspace):
    cases = CaseStore(store.workspace(case_workspace))
    case_id = cases.open(_request(case_workspace), "c_nordharbor", "synthetic-v1")
    cases.finish(case_id, _result(case_id, case_workspace, "c_nordharbor", "CLEAR_WITHIN_BOUNDS"))
    assert cases.get(case_id).disposition == "CLEAR_WITHIN_BOUNDS"

    recalled = cases.recall(["c_bluelagoon", "c_nordharbor"])
    assert case_id in {case.case_id for case in recalled}
    assert case_id not in {case.case_id for case in cases.recall(["c_bluelagoon", "c_nordharbor"],
                                                                 exclude_case=case_id)}


def test_watch_and_event_notifications_are_deduplicated(store, case_workspace, monkeypatch):
    cases = CaseStore(store.workspace(case_workspace))
    fixed_at = "2026-10-15T12:00:00.000000+00:00"
    monkeypatch.setattr(cases_module, "_now", lambda **kwargs: fixed_at)
    case_id = cases.open(_request(case_workspace, "c_aegean"), "c_aegean", "synthetic-v1")
    cases.finish(case_id, _result(case_id, case_workspace, "c_aegean", "CLEAR_WITHIN_BOUNDS"))

    watch = cases.set_watch(case_id, True)
    assert watch["active"] is True
    watched = cases.watched_cases(["c_aegean"])
    assert any(case["case_id"] == case_id for case in watched)
    cases.set_watch(case_id, False)
    assert not any(case["case_id"] == case_id for case in cases.watched_cases(["c_aegean"]))
    assert cases.record_event("event-1", "designation", {"entity_id": "p_nikos"}) is True
    assert cases.record_event("event-1", "designation", {"entity_id": "p_nikos"}) is False
    assert cases.notify("event-1", case_id, "CLEAR_WITHIN_BOUNDS", "EXPOSED", {"proof": ["k1"]}) is True
    assert cases.notify("event-1", case_id, "CLEAR_WITHIN_BOUNDS", "EXPOSED", {"proof": ["k1"]}) is False
    notifications = cases.notifications()
    assert len([item for item in notifications if item["case_id"] == case_id]) == 1


def test_workflow_edges_never_create_trace_or_ownership_findings(store, case_workspace):
    g = store.workspace(case_workspace)
    cases = CaseStore(g)
    case_id = cases.open(_request(case_workspace, "c_aegean"), "c_aegean", "synthetic-v1")
    cases.append_step(case_id, StepIn(kind="intake", actor="playbook", rationale="Opened case"))
    cases.append_step(case_id, StepIn(kind="decision", actor="playbook", rationale="No additional findings"))

    assert trace(g, "c_aegean", "2024-01-01", 6, ["OFAC", "EU", "UK"]) is None
    assert evaluate(g, "c_aegean", "2024-01-01", get_pack("OFAC")).verdict == "NOT_BLOCKED"
