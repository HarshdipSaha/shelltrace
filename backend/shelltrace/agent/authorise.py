from __future__ import annotations

from datetime import date
from typing import Mapping

from ..models import (
    AliasCandidate,
    Authorisation,
    Bounds,
    EvidenceItem,
    PackResult,
    Reason,
    RedFlag,
)


def _parse_date(value: str | None) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def proof_is_valid(
    pack: PackResult,
    evidence: Mapping[str, EvidenceItem],
    as_of: str,
) -> bool:
    """Check that every proof edge is cited, sourced, and valid on the given date."""
    as_of_date = _parse_date(as_of)
    if as_of_date is None or pack.as_of != as_of or not pack.proof:
        return False

    for key in pack.proof:
        item = evidence.get(key)
        if (
            item is None
            or item.k != key
            or item.src is None
            or item.snapshot is None
        ):
            return False

        if item.type == "DESIGNATED":
            listed_on = _parse_date(item.listed_on)
            delisted_on = _parse_date(item.delisted_on)
            if listed_on is None or listed_on > as_of_date:
                return False
            if item.delisted_on is not None and (
                delisted_on is None or as_of_date >= delisted_on
            ):
                return False
            continue

        valid_from = _parse_date(item.valid_from)
        valid_to = _parse_date(item.valid_to)
        if item.valid_from is not None and (valid_from is None or valid_from > as_of_date):
            return False
        if item.valid_to is not None and (valid_to is None or valid_to < as_of_date):
            return False

    return True


def bounds_sentence(b: Bounds) -> str:
    """Describe the date, graph scope, and snapshot covered by a clear result."""
    return (
        f"No qualifying ownership or control finding under {', '.join(b.rulepacks)} "
        f"as of {b.as_of} within {b.max_hops} hops over {', '.join(b.rel_scope)} "
        f"(snapshot {b.snapshot}, {b.scope_nodes} entities examined)."
    )


def _ordered_unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def authorise(
    packs: dict[str, PackResult],
    flags: list[RedFlag],
    pending: list[AliasCandidate],
    evidence: dict[str, EvidenceItem],
    bounds: Bounds,
    unevaluated: list[str],
) -> Authorisation:
    """Apply deterministic rules; uncertainty always prevents a clear result."""
    pack_order = _ordered_unique(bounds.rulepacks)
    requested = set(pack_order)
    available = {
        pack_id: pack
        for pack_id in pack_order
        if (pack := packs.get(pack_id)) is not None and pack.rulepack == pack_id
    }

    unevaluated_set = set(unevaluated)
    unevaluated_set.update(requested - available.keys())
    unevaluated_set.update(
        pack_id
        for pack_id, pack in available.items()
        if pack.as_of != bounds.as_of or pack.max_hops != bounds.max_hops
    )
    unevaluated_order = [pack_id for pack_id in pack_order if pack_id in unevaluated_set]
    unevaluated_order.extend(sorted(unevaluated_set - requested))

    exposed: list[Reason] = []
    escalate: list[Reason] = []

    if not pack_order:
        escalate.append(
            Reason(
                code="no_rulepacks",
                detail="No rulepacks were selected for evaluation.",
            )
        )

    for pack_id in pack_order:
        pack = available.get(pack_id)
        if pack is None or pack_id in unevaluated_set:
            continue
        if pack.verdict == "BLOCKED":
            if proof_is_valid(pack, evidence, bounds.as_of):
                exposed.append(
                    Reason(
                        code=f"blocked:{pack_id}",
                        detail=f"{pack_id} has a blocked result with valid sourced proof.",
                        evidence_keys=list(pack.proof),
                    )
                )
            else:
                escalate.append(
                    Reason(
                        code=f"proof_invalid:{pack_id}",
                        detail=(
                            f"{pack_id} reported BLOCKED, but its proof is missing, "
                            "unsourced, stale, or incomplete."
                        ),
                        evidence_keys=list(pack.proof),
                    )
                )
        elif pack.verdict == "INDETERMINATE":
            escalate.append(
                Reason(
                    code=f"indeterminate:{pack_id}",
                    detail=f"{pack_id} returned an indeterminate ownership result.",
                    evidence_keys=list(pack.decisive),
                )
            )
        elif pack.verdict == "PRESUMED_CONTROLLED":
            # Control presumptions are contextual escalation signals; they do
            # not change the ownership arithmetic used by a rule pack.
            escalate.append(
                Reason(
                    code=f"presumed_control:{pack_id}",
                    detail=f"{pack_id} has a rebuttable control presumption.",
                    evidence_keys=list(pack.presumptions),
                )
            )

    for flag in flags:
        escalate.append(
            Reason(
                code=f"red_flag:{flag.kind}",
                detail=flag.detail,
                evidence_keys=list(flag.evidence_keys),
            )
        )

    for candidate in pending:
        if candidate.state != "pending":
            continue
        escalate.append(
            Reason(
                code="pending_alias",
                detail=(
                    f"Alias candidate between {candidate.a_id} ({candidate.a_name}) "
                    f"and {candidate.b_id} ({candidate.b_name}) is pending review."
                ),
            )
        )

    truncated_packs = [
        pack_id
        for pack_id in pack_order
        if pack_id in available
        and pack_id not in unevaluated_set
        and available[pack_id].scope_truncated
    ]
    for pack_id in truncated_packs:
        pack = available[pack_id]
        escalate.append(
            Reason(
                code=f"scope_truncated:{pack_id}",
                detail=(
                    f"The {pack_id} evaluation scope was truncated at "
                    f"{pack.scope_size} entities."
                ),
            )
        )
    if bounds.truncated and not truncated_packs:
        escalate.append(
            Reason(
                code="scope_truncated",
                detail="The investigation scope was truncated.",
            )
        )

    for pack_id in unevaluated_order:
        escalate.append(
            Reason(
                code=f"pack_not_evaluated:{pack_id}",
                detail=f"Rulepack {pack_id} was not evaluated.",
            )
        )

    reasons = [*exposed, *escalate]
    if exposed:
        disposition = "EXPOSED"
    elif escalate:
        disposition = "ESCALATE"
    else:
        disposition = "CLEAR_WITHIN_BOUNDS"
        reasons = [
            Reason(code="clear_within_bounds", detail=bounds_sentence(bounds))
        ]

    return Authorisation(disposition=disposition, reasons=reasons, bounds=bounds)
