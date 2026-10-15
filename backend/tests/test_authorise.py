from shelltrace.models import (
    AliasCandidate,
    Bounds,
    EvidenceItem,
    PackResult,
    RedFlag,
)
from shelltrace.agent.authorise import authorise, bounds_sentence, proof_is_valid
from shelltrace.rulepacks import get_pack
import pytest


def pr(
    pack,
    verdict,
    *,
    proof=(),
    decisive=(),
    presumptions=(),
    truncated=False,
):
    return PackResult(
        rulepack=pack,
        version=get_pack(pack).version,
        entity_id="target",
        canon="target",
        as_of="2024-01-01",
        max_hops=6,
        verdict=verdict,
        lo=(100.0 if verdict == "BLOCKED" else 0.0),
        hi=(100.0 if verdict in ("BLOCKED", "INDETERMINATE") else 0.0),
        threshold=get_pack(pack).threshold,
        inclusive=get_pack(pack).inclusive,
        proof=list(proof),
        decisive=list(decisive),
        decisive_kind="none" if not decisive else "unknown_or_conflict",
        presumptions=list(presumptions),
        seeds=[],
        scope_size=2,
        scope_truncated=truncated,
        data_errors=[],
        caveats=[],
        economic_exposure=None,
        rounds=1,
        latency_ms=1,
    )


def ev(
    key,
    *,
    src="synthetic",
    snapshot="synthetic-v1",
    valid_from=None,
    valid_to=None,
    type="OWNS",
    listed_on=None,
    delisted_on=None,
):
    return EvidenceItem(
        k=key,
        type=type,
        from_id="owner",
        from_name="Owner",
        to_id="target",
        to_name="Target",
        pct=80.0,
        basis="shareholding",
        role=None,
        valid_from=valid_from,
        valid_to=valid_to,
        listed_on=listed_on,
        delisted_on=delisted_on,
        src=src,
        src_record=f"record:{key}",
        snapshot=snapshot,
        licence=None,
        url=None,
    )


def bounds(*, rulepacks=("OFAC",), truncated=False):
    return Bounds(
        as_of="2024-01-01",
        max_hops=6,
        rel_scope=["OWNS", "CONTROLS"],
        rulepacks=list(rulepacks),
        snapshot="synthetic-v1",
        scope_nodes=2,
        truncated=truncated,
    )


def test_blocked_with_valid_proof_is_exposed():
    pack = pr("OFAC", "BLOCKED", proof=["own-1", "designation"])

    result = authorise(
        {"OFAC": pack}, [], [], {
            "own-1": ev("own-1"),
            "designation": ev("designation", type="DESIGNATED", listed_on="2020-01-01"),
        }, bounds(), []
    )

    assert result.disposition == "EXPOSED"
    assert result.reasons[0].code == "blocked:OFAC"
    assert result.reasons[0].evidence_keys == ["own-1", "designation"]


def test_blocked_with_missing_source_escalates():
    pack = pr("OFAC", "BLOCKED", proof=["own-1", "designation"])

    result = authorise(
        {"OFAC": pack},
        [],
        [],
        {
            "own-1": ev("own-1", src=None),
            "designation": ev("designation", type="DESIGNATED", listed_on="2020-01-01"),
        },
        bounds(),
        [],
    )

    assert result.disposition == "ESCALATE"
    assert result.reasons[0].code == "proof_invalid:OFAC"


def test_blocked_with_expired_proof_edge_escalates():
    pack = pr("OFAC", "BLOCKED", proof=["own-1", "designation"])

    result = authorise(
        {"OFAC": pack},
        [],
        [],
        {
            "own-1": ev("own-1", valid_to="2023-12-31"),
            "designation": ev("designation", type="DESIGNATED", listed_on="2020-01-01"),
        },
        bounds(),
        [],
    )

    assert result.disposition == "ESCALATE"
    assert result.reasons[0].code == "proof_invalid:OFAC"


def test_blocked_without_proof_escalates():
    result = authorise(
        {"OFAC": pr("OFAC", "BLOCKED")}, [], [], {}, bounds(), []
    )

    assert result.disposition == "ESCALATE"
    assert result.reasons[0].code == "proof_invalid:OFAC"


def test_blocked_result_for_another_date_escalates():
    pack = pr("OFAC", "BLOCKED", proof=["own-1"]).model_copy(
        update={"as_of": "2023-12-31"}
    )

    result = authorise(
        {"OFAC": pack}, [], [], {"own-1": ev("own-1")}, bounds(), []
    )

    assert result.disposition == "ESCALATE"
    assert result.reasons[0].code == "pack_not_evaluated:OFAC"


def test_not_blocked_result_for_another_date_cannot_clear():
    pack = pr("OFAC", "NOT_BLOCKED").model_copy(
        update={"as_of": "2023-12-31"}
    )

    result = authorise({"OFAC": pack}, [], [], {}, bounds(), [])

    assert result.disposition == "ESCALATE"
    assert result.reasons[0].code == "pack_not_evaluated:OFAC"


def test_not_blocked_result_with_different_hop_bound_cannot_clear():
    pack = pr("OFAC", "NOT_BLOCKED").model_copy(update={"max_hops": 3})

    result = authorise({"OFAC": pack}, [], [], {}, bounds(), [])

    assert result.disposition == "ESCALATE"
    assert result.reasons[0].code == "pack_not_evaluated:OFAC"


def test_ownership_proof_validity_includes_both_endpoints():
    pack = pr("OFAC", "BLOCKED", proof=["own-1", "designation"])
    evidence = {
        "own-1": ev(
            "own-1",
            valid_from="2024-01-01",
            valid_to="2024-01-01",
        ),
        "designation": ev("designation", type="DESIGNATED", listed_on="2020-01-01"),
    }

    assert proof_is_valid(pack, evidence, "2024-01-01") is True


def test_proof_key_missing_from_evidence_is_invalid():
    pack = pr("OFAC", "BLOCKED", proof=["missing"])

    assert proof_is_valid(pack, {}, "2024-01-01") is False


def test_evidence_mapping_key_must_match_item_key():
    pack = pr("OFAC", "BLOCKED", proof=["own-1"])

    assert proof_is_valid(
        pack, {"own-1": ev("different-key")}, "2024-01-01"
    ) is False


def test_designation_proof_valid_between_listing_and_delisting():
    pack = pr("OFAC", "BLOCKED", proof=["designation"])
    evidence = {
        "designation": ev(
            "designation",
            type="DESIGNATED",
            listed_on="2020-01-01",
            delisted_on="2024-01-02",
        )
    }

    assert proof_is_valid(pack, evidence, "2024-01-01") is True


def test_designation_proof_uses_listing_and_exclusive_delisting_dates():
    pack = pr("OFAC", "BLOCKED", proof=["designation"])
    evidence = {
        "designation": ev(
            "designation",
            type="DESIGNATED",
            listed_on="2024-01-01",
            delisted_on="2024-01-01",
        )
    }

    assert proof_is_valid(pack, evidence, "2024-01-01") is False


def test_indeterminate_escalates_with_decisive_keys():
    pack = pr("OFAC", "INDETERMINATE", decisive=["unknown-1"])

    result = authorise({"OFAC": pack}, [], [], {}, bounds(), [])

    assert result.disposition == "ESCALATE"
    assert result.reasons[0].code == "indeterminate:OFAC"
    assert result.reasons[0].evidence_keys == ["unknown-1"]


def test_presumed_control_escalates_with_presumption_keys():
    pack = pr("EU", "PRESUMED_CONTROLLED", presumptions=["control-1"])

    result = authorise({"EU": pack}, [], [], {}, bounds(rulepacks=("EU",)), [])

    assert result.disposition == "ESCALATE"
    assert result.reasons[0].code == "presumed_control:EU"
    assert result.reasons[0].evidence_keys == ["control-1"]


def test_red_flag_escalates_clear():
    flag = RedFlag(
        kind="divestment_near_listing",
        entity_ids=["owner", "target"],
        evidence_keys=["stake-1"],
        detail="Stake ended near listing.",
    )

    result = authorise(
        {"OFAC": pr("OFAC", "NOT_BLOCKED")}, [flag], [], {}, bounds(), []
    )

    assert result.disposition == "ESCALATE"
    assert result.reasons[0].code == "red_flag:divestment_near_listing"
    assert result.reasons[0].evidence_keys == ["stake-1"]


def test_pending_alias_escalates():
    alias = AliasCandidate(
        a_id="a",
        a_name="A",
        b_id="b",
        b_name="B",
        score=0.8,
        state="pending",
        reason="possible match",
        touches_designated=False,
    )

    result = authorise(
        {"OFAC": pr("OFAC", "NOT_BLOCKED")}, [], [alias], {}, bounds(), []
    )

    assert result.disposition == "ESCALATE"
    assert result.reasons[0].code == "pending_alias"


def test_reasons_follow_rule_and_pack_order():
    packs = {
        "EU": pr("EU", "PRESUMED_CONTROLLED", presumptions=["presume-eu"], truncated=True),
        "OFAC": pr("OFAC", "INDETERMINATE", decisive=["unknown-ofac"], truncated=True),
        "UK": pr("UK", "BLOCKED", proof=["bad-uk"], truncated=True),
    }
    flag = RedFlag(
        kind="circular_ownership",
        entity_ids=["a", "b"],
        evidence_keys=["cycle"],
        detail="Cycle.",
    )
    alias = AliasCandidate(
        a_id="a",
        a_name="A",
        b_id="b",
        b_name="B",
        score=0.8,
        state="pending",
        reason="possible match",
        touches_designated=False,
    )

    result = authorise(
        packs,
        [flag],
        [alias],
        {"bad-uk": ev("bad-uk", snapshot=None)},
        bounds(rulepacks=("UK", "OFAC", "EU"), truncated=True),
        [],
    )

    assert result.disposition == "ESCALATE"
    assert [reason.code for reason in result.reasons] == [
        "proof_invalid:UK",
        "indeterminate:OFAC",
        "presumed_control:EU",
        "red_flag:circular_ownership",
        "pending_alias",
        "scope_truncated:UK",
        "scope_truncated:OFAC",
        "scope_truncated:EU",
    ]


def test_escalation_category_order_precedes_pack_order():
    packs = {
        "EU": pr("EU", "PRESUMED_CONTROLLED", presumptions=["presume-eu"]),
        "OFAC": pr("OFAC", "INDETERMINATE", decisive=["unknown-ofac"]),
        "UK": pr("UK", "BLOCKED"),
    }

    result = authorise(
        packs,
        [],
        [],
        {},
        bounds(rulepacks=("EU", "OFAC", "UK")),
        [],
    )

    assert result.disposition == "ESCALATE"
    assert [reason.code for reason in result.reasons] == [
        "proof_invalid:UK",
        "indeterminate:OFAC",
        "presumed_control:EU",
    ]


def test_unevaluated_pack_escalates_instead_of_returning_clear():
    result = authorise(
        {"OFAC": pr("OFAC", "NOT_BLOCKED")},
        [],
        [],
        {},
        bounds(rulepacks=("OFAC", "UK")),
        ["UK"],
    )

    assert result.disposition == "ESCALATE"
    assert [reason.code for reason in result.reasons] == ["pack_not_evaluated:UK"]


def test_bounds_level_truncation_prevents_clear():
    result = authorise(
        {"OFAC": pr("OFAC", "NOT_BLOCKED")},
        [],
        [],
        {},
        bounds(truncated=True),
        [],
    )

    assert result.disposition == "ESCALATE"
    assert [reason.code for reason in result.reasons] == ["scope_truncated"]


def test_exposed_keeps_escalation_reasons():
    packs = {
        "UK": pr("UK", "INDETERMINATE", decisive=["unknown-uk"]),
        "OFAC": pr("OFAC", "BLOCKED", proof=["own-1", "designation"]),
    }

    result = authorise(
        packs,
        [],
        [],
        {
            "own-1": ev("own-1"),
            "designation": ev("designation", type="DESIGNATED", listed_on="2020-01-01"),
        },
        bounds(rulepacks=("OFAC", "UK")),
        [],
    )

    assert result.disposition == "EXPOSED"
    assert [reason.code for reason in result.reasons] == [
        "blocked:OFAC",
        "indeterminate:UK",
    ]


def test_clear_states_exact_bounds_sentence():
    requested = bounds(rulepacks=("OFAC", "EU"))

    result = authorise(
        {pack: pr(pack, "NOT_BLOCKED") for pack in requested.rulepacks},
        [],
        [],
        {},
        requested,
        [],
    )

    expected = (
        "No qualifying ownership or control finding under OFAC, EU as of 2024-01-01 "
        "within 6 hops over OWNS, CONTROLS (snapshot synthetic-v1, 2 entities examined)."
    )
    assert result.disposition == "CLEAR_WITHIN_BOUNDS"
    assert result.reasons[0].code == "clear_within_bounds"
    assert result.reasons[0].detail == expected
    assert len(result.reasons) == 1
    assert bounds_sentence(requested) == expected


def test_missing_requested_pack_never_returns_clear():
    result = authorise(
        {"OFAC": pr("OFAC", "NOT_BLOCKED")},
        [],
        [],
        {},
        bounds(rulepacks=("OFAC", "EU")),
        [],
    )

    assert result.disposition == "ESCALATE"
    assert [reason.code for reason in result.reasons] == ["pack_not_evaluated:EU"]


def test_empty_rulepack_bounds_never_returns_clear():
    result = authorise({}, [], [], {}, bounds(rulepacks=()), [])

    assert result.disposition == "ESCALATE"
    assert [reason.code for reason in result.reasons] == ["no_rulepacks"]


@pytest.mark.parametrize("field,value", [
    ("version", "wrong-version"),
    ("threshold", 49.0),
    ("inclusive", False),
])
def test_pack_policy_metadata_mismatch_is_unevaluated(field, value):
    pack = pr("OFAC", "NOT_BLOCKED").model_copy(update={field: value})

    result = authorise({"OFAC": pack}, [], [], {}, bounds(), [])

    assert result.disposition == "ESCALATE"
    assert [reason.code for reason in result.reasons] == ["pack_not_evaluated:OFAC"]


@pytest.mark.parametrize(
    "other_entity,other_canon",
    [("entity-b", "canon-a"), ("entity-a", "canon-b"), ("entity-b", "canon-b")],
)
def test_mixed_entity_id_or_canon_results_are_all_unevaluated(other_entity, other_canon):
    packs = {
        "OFAC": pr("OFAC", "BLOCKED", proof=["designation"]).model_copy(
            update={"entity_id": "entity-a", "canon": "canon-a"}
        ),
        "EU": pr("EU", "NOT_BLOCKED").model_copy(
            update={"entity_id": other_entity, "canon": other_canon}
        ),
    }

    result = authorise(
        packs,
        [],
        [],
        {"designation": ev("designation", type="DESIGNATED", listed_on="2020-01-01")},
        bounds(rulepacks=("OFAC", "EU")),
        [],
    )

    assert result.disposition == "ESCALATE"
    assert [reason.code for reason in result.reasons] == [
        "pack_not_evaluated:OFAC",
        "pack_not_evaluated:EU",
    ]


@pytest.mark.parametrize("updates", [
    {"lo": float("nan"), "hi": 100.0},
    {"lo": 0.0, "hi": float("inf")},
    {"lo": 80.0, "hi": 20.0},
    {"lo": -1.0, "hi": 20.0},
    {"lo": 20.0, "hi": 101.0},
    {"lo": None, "hi": 20.0},
])
def test_nonfinite_or_out_of_range_or_reversed_intervals_are_unevaluated(updates):
    pack = pr("OFAC", "NOT_BLOCKED").model_copy(update=updates)

    result = authorise({"OFAC": pack}, [], [], {}, bounds(), [])

    assert result.disposition == "ESCALATE"
    assert [reason.code for reason in result.reasons] == ["pack_not_evaluated:OFAC"]


@pytest.mark.parametrize("verdict,lo,hi", [
    ("BLOCKED", 49.0, 100.0),
    ("NOT_BLOCKED", 0.0, 50.0),
    ("INDETERMINATE", 50.0, 80.0),
    ("INDETERMINATE", 0.0, 49.0),
    ("PRESUMED_CONTROLLED", 0.0, 50.0),
])
def test_verdict_inconsistent_with_interval_is_unevaluated(verdict, lo, hi):
    pack = pr("OFAC", verdict).model_copy(update={"lo": lo, "hi": hi})

    result = authorise({"OFAC": pack}, [], [], {}, bounds(), [])

    assert result.disposition == "ESCALATE"
    assert [reason.code for reason in result.reasons] == ["pack_not_evaluated:OFAC"]


@pytest.mark.parametrize("rel_type", ["REGISTERED_AT", "CONTROLS", "OFFICER_OF", "SAME_AS"])
def test_contextual_evidence_cannot_support_blocked_proof(rel_type):
    pack = pr("OFAC", "BLOCKED", proof=["designation", "context"])
    evidence = {
        "designation": ev("designation", type="DESIGNATED", listed_on="2020-01-01"),
        "context": ev("context", type=rel_type),
    }

    assert proof_is_valid(pack, evidence, "2024-01-01") is False


def test_ownership_proof_requires_active_designation_dependency():
    pack = pr("OFAC", "BLOCKED", proof=["own-1"])

    assert proof_is_valid(pack, {"own-1": ev("own-1")}, "2024-01-01") is False


def test_ownership_proof_with_active_designation_dependency_is_valid():
    pack = pr("OFAC", "BLOCKED", proof=["own-1", "designation"])
    evidence = {
        "own-1": ev("own-1"),
        "designation": ev("designation", type="DESIGNATED", listed_on="2020-01-01"),
    }

    assert proof_is_valid(pack, evidence, "2024-01-01") is True


def test_uk_strict_threshold_boundary_matches_pack_policy():
    at_threshold = pr("UK", "NOT_BLOCKED").model_copy(update={"hi": 50.0})
    result = authorise(
        {"UK": at_threshold}, [], [], {}, bounds(rulepacks=("UK",)), []
    )
    assert result.disposition == "CLEAR_WITHIN_BOUNDS"

    straddling = pr("UK", "INDETERMINATE").model_copy(
        update={"lo": 50.0, "hi": 50.01}
    )
    result = authorise(
        {"UK": straddling}, [], [], {}, bounds(rulepacks=("UK",)), []
    )
    assert result.disposition == "ESCALATE"
    assert result.reasons[0].code == "indeterminate:UK"
