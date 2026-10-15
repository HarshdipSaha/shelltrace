from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field


IsoDate = Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$")]
PackId = Literal["OFAC", "EU", "UK"]
Verdict = Literal["BLOCKED", "INDETERMINATE", "PRESUMED_CONTROLLED", "NOT_BLOCKED"]
Disposition = Literal["EXPOSED", "ESCALATE", "CLEAR_WITHIN_BOUNDS"]
ReviewCode = Literal["CONFIRMED_EXPOSED", "CONFIRMED_CLEAR", "FALSE_POSITIVE_ALIAS", "ESCALATED_RED_FLAG", "OVERRIDDEN"]
FlagKind = Literal["divestment_near_listing", "circular_ownership", "mass_registration_address", "control_by_designated"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RulePack(Strict):
    id: PackId
    version: str
    authorities: tuple[str, ...]
    threshold: float
    inclusive: bool
    aggregate: bool
    control_limb: bool
    basis_accepted: tuple[str, ...]
    citations: tuple[str, ...]
    interpretation_note: str | None = None


class PackResult(Strict):
    rulepack: PackId
    version: str
    entity_id: str
    canon: str
    as_of: str
    max_hops: int
    verdict: Verdict
    lo: float
    hi: float
    threshold: float
    inclusive: bool
    proof: list[str]
    decisive: list[str]
    decisive_kind: Literal["none", "unknown_or_conflict", "counterfactual"]
    presumptions: list[str]
    seeds: list[str]
    scope_size: int
    scope_truncated: bool
    data_errors: list[str]
    caveats: list[str]
    economic_exposure: float | None
    rounds: int
    latency_ms: int
    interpretation_note: str | None = None


class TraceNode(Strict):
    id: str
    name: str
    kind: str
    country: str | None = None


class TraceEdge(Strict):
    k: str
    type: str
    from_id: str
    to_id: str
    pct: float | None = None
    basis: str | None = None
    role: str | None = None
    valid_from: str | None = None
    valid_to: str | None = None
    src: str | None = None
    src_record: str | None = None


class TraceResult(Strict):
    hops: int
    nodes: list[TraceNode]
    edges: list[TraceEdge]
    designation_key: str
    authority: str
    program: str
    listed_on: str
    mode: Literal["ownership", "context"]
    cypher: str
    latency_ms: int


class RedFlag(Strict):
    kind: FlagKind
    entity_ids: list[str]
    evidence_keys: list[str]
    detail: str


class AliasCandidate(Strict):
    a_id: str
    a_name: str
    b_id: str
    b_name: str
    score: float
    state: Literal["pending", "rejected", "accepted"]
    reason: str
    touches_designated: bool
    features: dict[str, Any] = Field(default_factory=dict)


class EvidenceItem(Strict):
    k: str
    type: str
    from_id: str
    from_name: str
    to_id: str
    to_name: str
    pct: float | None = None
    basis: str | None = None
    role: str | None = None
    valid_from: str | None = None
    valid_to: str | None = None
    listed_on: str | None = None
    delisted_on: str | None = None
    src: str | None = None
    src_record: str | None = None
    snapshot: str | None = None
    licence: str | None = None
    url: str | None = None


class Stake(Strict):
    owner_id: str
    owner_name: str
    pct: float | None
    basis: str | None
    valid_from: str | None
    valid_to: str | None
    k: str


class Bounds(Strict):
    as_of: str
    max_hops: int
    rel_scope: list[str]
    rulepacks: list[str]
    snapshot: str
    scope_nodes: int
    truncated: bool


class Reason(Strict):
    code: str
    detail: str
    evidence_keys: list[str] = Field(default_factory=list)


class Authorisation(Strict):
    disposition: Disposition
    reasons: list[Reason]
    bounds: Bounds


class Proposal(Strict):
    disposition: Disposition
    rationale: str
    confidence: float
    evidence_keys: list[str]


StepKind = Literal["intake", "tool", "decision", "proposal", "authorise", "report", "review", "watch", "recheck"]


class StepIn(Strict):
    kind: StepKind
    tool: str | None = None
    args: dict[str, Any] = Field(default_factory=dict)
    result_digest: str | None = None
    evidence_keys: list[str] = Field(default_factory=list)
    probability: float | None = None
    rationale: str | None = None
    latency_ms: int = 0
    actor: str
    fallback_reason: str | None = None


class StepOut(StepIn):
    seq: int
    prev_hash: str
    hash: str
    at: str


class CaseRequest(Strict):
    workspace: Annotated[str, Field(pattern=r"^[a-z0-9_]{1,32}$")] = "demo"
    entity_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9_:\-.]{1,80}$")]
    as_of: IsoDate
    max_hops: Annotated[int, Field(ge=1, le=6)] = 6
    rulepacks: list[PackId] = Field(default_factory=lambda: ["OFAC", "EU", "UK"])
    mode: Literal["agent", "playbook"] = "agent"


class PriorCase(Strict):
    case_id: str
    entity_id: str
    as_of: str
    disposition: str | None
    opened_at: str


class CaseResult(Strict):
    case_id: str
    workspace: str
    entity: TraceNode
    as_of: str
    max_hops: int
    rulepacks: list[PackId]
    mode: str
    actor_model: str
    disposition: Disposition
    reasons: list[Reason]
    proposal: Proposal | None
    proposal_overridden: bool
    packs: dict[str, PackResult]
    trace: TraceResult | None
    red_flags: list[RedFlag]
    alias_candidates: list[AliasCandidate]
    prior_cases: list[PriorCase]
    stakes: list[Stake]
    evidence: dict[str, EvidenceItem]
    bounds: Bounds
    steps: list[StepOut]
    latency_ms: int
    snapshot: str


class ReviewIn(Strict):
    reviewer: Annotated[str, Field(min_length=2)]
    code: ReviewCode
    reason: Annotated[str, Field(min_length=10)]
    second_reviewer: str | None = None


class DesignationEvent(Strict):
    workspace: Annotated[str, Field(pattern=r"^[a-z0-9_]{1,32}$")] = "demo"
    entity_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9_:\-.]{1,80}$")]
    authority: PackId
    program: str
    listed_on: IsoDate
    source: str
    source_url: str | None = None
