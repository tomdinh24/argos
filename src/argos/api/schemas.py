"""Wire-format schemas for the cockpit-facing FastAPI surface.

These are the shapes the Next.js cockpit (`web/lib/types.ts`) expects — kept
isolated from the internal ontology so the cockpit contract can evolve
without churning workflow-internal types. Mappers in `argos.api.mappers`
turn ontology objects + workflow results into these.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

TriageBand = Literal["green", "amber", "red"]
WorkflowName = Literal["coverage", "reserve", "liability", "recovery", "closure", "reopen"]
CitationSourceType = Literal["medical", "policy", "scene", "liability", "other"]
DecisionOutcome = Literal["approved", "modified", "rejected"]


class ClaimSummary(BaseModel):
    claim_id: str
    insured_name: str
    loss_type: str
    reported_at: str  # ISO 8601
    triage_band: TriageBand
    next_workflow: WorkflowName
    rationale: str
    reserve_total: float | None
    status: str


class PendingRecommendation(BaseModel):
    recommendation_id: str
    workflow: WorkflowName
    title: str
    posture: str
    rationale: str
    citations: int
    awaiting_approval: bool
    amount: float | None = None
    findings: list[str] = Field(default_factory=list)


class Citation(BaseModel):
    citation_id: str
    index: int
    source_type: CitationSourceType
    document: str
    excerpt: str
    # Full document text. The cockpit viewer renders this with `excerpt`
    # highlighted in context. Populated by joining the citation's document_id to
    # the ontology Document.body_text; None for rule/ledger-only citations.
    body: str | None = None


# ── Claim dossier — per-stage detail content (mirrors web/lib/types.ts) ──────
# These are display projections assembled by mappers.to_dossier() from the
# persisted workflow results + ontology objects. Field names match the cockpit
# TS types exactly so the wire format needs no translation layer.

StageKey = Literal["coverage", "reserve", "liability", "recovery", "closure"]


class NewInfoItem(BaseModel):
    when: str
    what: str
    cite: int | None = None
    note: str | None = None
    is_new: bool | None = None
    stage: StageKey | None = None


class Finding(BaseModel):
    text: str
    cite: int
    doc: str


class CoverageMap(BaseModel):
    accident: str
    provision: str
    cite: int


class DistRow(BaseModel):
    label: str
    p: float


class ReserveBand(BaseModel):
    name: str
    recommend: float
    low: float
    high: float
    carried: float


class StageCheck(BaseModel):
    label: str
    status: Literal["need", "ok"]
    title: str
    detail: str
    due: str | None = None
    action: str | None = None


class AllocRow(BaseModel):
    party: str
    pct: float
    meta: str
    primary: bool | None = None


class TodoItem(BaseModel):
    text: str
    sub: str
    done: bool | None = None
    due: str | None = None
    action: str | None = None


class Econ(BaseModel):
    gross: str
    drag: str
    net: str


class RecapRow(BaseModel):
    stage: str
    outcome: str


class CoverageSection(BaseModel):
    map: CoverageMap
    distribution: list[DistRow]
    decided_label: str


class ReserveSection(BaseModel):
    findings: list[Finding]
    bands: list[ReserveBand]
    checks: list[StageCheck]
    amount: float | None = None


class LiabilitySection(BaseModel):
    allocation: list[AllocRow]
    evidence: list[Finding]


class RecoverySection(BaseModel):
    status: str
    lane: str
    todo: list[TodoItem]
    econ: Econ


class ClosureSection(BaseModel):
    status: str
    readiness: float
    recap: list[RecapRow]
    amount: float | None = None


class ClaimDossier(BaseModel):
    brief: str
    new_info: list[NewInfoItem]
    coverage: CoverageSection
    reserve: ReserveSection
    liability: LiabilitySection
    recovery: RecoverySection
    closure: ClosureSection


class ClaimDetail(ClaimSummary):
    policy_number: str
    date_of_loss: str
    jurisdiction: str
    severity: str
    description: str
    pending_recommendations: list[PendingRecommendation]
    citations: list[Citation]
    dossier: ClaimDossier | None = None


class DashboardMetrics(BaseModel):
    adjuster_first_name: str
    active_claims: int
    active_delta_label: str
    awaiting_approval: int
    cycle_time_days: float
    cycle_band_days: float
    reserve_accuracy_pct: float
    reserve_target_pct: float
    approved_7d: int
    approved_avg_citations: float


class ExampleClaim(BaseModel):
    example_id: str
    label: str
    loss_type: str
    triage_band: TriageBand
    description: str


class SeedClaimRequest(BaseModel):
    example_id: str


class DecisionRequest(BaseModel):
    recommendation_id: str
    workflow: WorkflowName
    outcome: DecisionOutcome
    final_title: str = Field(description="Title as committed (post-modify if applicable)")
    reason: str | None = None


class DecisionResponse(BaseModel):
    ok: bool
    decision_id: str
    next_workflow: WorkflowName | None
