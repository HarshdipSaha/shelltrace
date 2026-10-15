import pytest
from pydantic import ValidationError

from shelltrace.models import CaseRequest, RulePack
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
