import pytest
from pydantic import TypeAdapter, ValidationError

from shelltrace.models import (
    Bounds,
    CaseRequest,
    CaseResult,
    DesignationEvent,
    EvidenceItem,
    IsoDate,
    PackResult,
    PriorCase,
    RulePack,
    Stake,
    StepOut,
    TraceEdge,
    TraceResult,
)
from shelltrace.rulepacks import EU, OFAC, PACKS, UK, get_pack


def test_pack_values_follow_documented_interpretations():
    assert (OFAC.threshold, OFAC.inclusive, OFAC.aggregate, OFAC.control_limb) == (50.0, True, True, False)
    assert (EU.threshold, EU.inclusive, EU.aggregate, EU.control_limb) == (50.0, True, True, True)
    assert (UK.threshold, UK.inclusive, UK.aggregate, UK.control_limb) == (50.0, False, False, True)
    assert OFAC.authorities == ("OFAC",) and EU.authorities == ("EU",) and UK.authorities == ("UK",)
    assert "accounting_consolidation" in OFAC.basis_accepted
    assert get_pack("UK") is UK
    assert PACKS == {"OFAC": OFAC, "EU": EU, "UK": UK}


def test_rulepacks_preserve_official_sources_and_interpretation_notes():
    assert any("ofac.treasury.gov/faqs/401" in citation for citation in OFAC.citations)
    assert any("eur-lex.europa.eu/eli/reg/2025/2037" in citation for citation in EU.citations)
    assert any("11623-2024" in citation for citation in EU.citations)
    assert any("financial-sanctions-general-guidance" in citation for citation in UK.citations)
    assert OFAC.interpretation_note
    assert EU.interpretation_note and "interpretation" in EU.interpretation_note.lower()
    assert UK.interpretation_note and "not simply aggregated" in UK.interpretation_note.lower()


def test_rulepack_contract_forbids_extra_fields():
    with pytest.raises(ValidationError):
        RulePack(
            id="OFAC", version="v1", authorities=("OFAC",), threshold=50,
            inclusive=True, aggregate=True, control_limb=False,
            basis_accepted=("synthetic",), citations=("source",), invented=True,
        )


def test_case_request_bounds_are_enforced():
    with pytest.raises(ValidationError):
        CaseRequest(entity_id="c_elm", as_of="2026-10-15", max_hops=7)


def test_iso_date_rejects_impossible_calendar_day():
    with pytest.raises(ValidationError):
        TypeAdapter(IsoDate).validate_python("2026-02-31")


def test_iso_date_accepts_real_day_and_serializes_as_string():
    adapter = TypeAdapter(IsoDate)
    value = adapter.validate_python("2024-02-29")

    assert value == "2024-02-29"
    assert type(value) is str
    assert adapter.dump_json(value) == b'"2024-02-29"'


def test_case_request_rejects_impossible_calendar_day():
    with pytest.raises(ValidationError):
        CaseRequest(entity_id="c_elm", as_of="2026-02-31")


def test_designation_request_rejects_impossible_calendar_day():
    with pytest.raises(ValidationError):
        DesignationEvent(
            entity_id="c_elm",
            authority="OFAC",
            program="fixture",
            listed_on="2026-02-31",
            source="synthetic fixture",
        )


def _valid_payload_for_date_model(model):
    if model is PackResult:
        return {
            "rulepack": "OFAC", "version": "v1", "entity_id": "c_elm",
            "canon": "c_elm", "as_of": "2026-10-15", "max_hops": 1,
            "verdict": "NOT_BLOCKED", "lo": 0, "hi": 0, "threshold": 50,
            "inclusive": True, "proof": [], "decisive": [],
            "decisive_kind": "none", "presumptions": [], "seeds": [],
            "scope_size": 1, "scope_truncated": False, "data_errors": [],
            "caveats": [], "economic_exposure": None, "rounds": 0,
            "latency_ms": 0,
        }
    if model is TraceEdge:
        return {"k": "edge_1", "type": "OWNS", "from_id": "a", "to_id": "b"}
    if model is TraceResult:
        return {
            "hops": 1, "nodes": [], "edges": [], "designation_key": "d_1",
            "authority": "OFAC", "program": "fixture", "listed_on": "2026-10-15",
            "mode": "ownership", "cypher": "RETURN 1", "latency_ms": 0,
        }
    if model is EvidenceItem:
        return {
            "k": "edge_1", "type": "OWNS", "from_id": "a", "from_name": "A",
            "to_id": "b", "to_name": "B",
        }
    if model is Stake:
        return {
            "owner_id": "a", "owner_name": "A", "pct": None, "basis": None,
            "valid_from": None, "valid_to": None, "k": "edge_1",
        }
    if model is Bounds:
        return {
            "as_of": "2026-10-15", "max_hops": 1, "rel_scope": [],
            "rulepacks": [], "snapshot": "synthetic-v1", "scope_nodes": 1,
            "truncated": False,
        }
    if model is PriorCase:
        return {
            "case_id": "case_1", "entity_id": "c_elm", "as_of": "2026-10-15",
            "disposition": None, "opened_at": "2026-10-15T12:00:00Z",
        }
    if model is CaseResult:
        return {
            "case_id": "case_1", "workspace": "demo",
            "entity": {"id": "c_elm", "name": "Elm", "kind": "company"},
            "as_of": "2026-10-15", "max_hops": 1, "rulepacks": [],
            "mode": "agent", "actor_model": "none", "disposition": "ESCALATE",
            "reasons": [], "proposal": None, "proposal_overridden": False,
            "packs": {}, "trace": None, "red_flags": [], "alias_candidates": [],
            "prior_cases": [], "stakes": [], "evidence": {},
            "bounds": {
                "as_of": "2026-10-15", "max_hops": 1, "rel_scope": [],
                "rulepacks": [], "snapshot": "synthetic-v1", "scope_nodes": 1,
                "truncated": False,
            },
            "steps": [], "latency_ms": 0, "snapshot": "synthetic-v1",
        }
    raise AssertionError(f"No valid payload defined for {model.__name__}")


@pytest.mark.parametrize(
    ("model", "date_fields", "nullable_fields"),
    [
        (PackResult, ("as_of",), ()),
        (TraceEdge, ("valid_from", "valid_to"), ("valid_from", "valid_to")),
        (TraceResult, ("listed_on",), ()),
        (
            EvidenceItem,
            ("valid_from", "valid_to", "listed_on", "delisted_on"),
            ("valid_from", "valid_to", "listed_on", "delisted_on"),
        ),
        (Stake, ("valid_from", "valid_to"), ("valid_from", "valid_to")),
        (Bounds, ("as_of",), ()),
        (PriorCase, ("as_of",), ()),
        (CaseResult, ("as_of",), ()),
    ],
)
def test_response_date_fields_reject_impossible_days_and_keep_nullable_fields(
    model, date_fields, nullable_fields
):
    for field in date_fields:
        payload = _valid_payload_for_date_model(model)
        payload[field] = "2026-02-31"
        with pytest.raises(ValidationError, match=field):
            model.model_validate(payload)

        if field in nullable_fields:
            payload[field] = None
            assert getattr(model.model_validate(payload), field) is None


def test_timestamp_fields_remain_strings():
    assert PriorCase.model_fields["opened_at"].annotation is str
    assert StepOut.model_fields["at"].annotation is str
