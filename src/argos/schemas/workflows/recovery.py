"""Recovery workflow schemas.

The workflow is split into four stages (see docs/specs/recovery-workflow.md):

  A. Extractor (LLM, Software 3.0) reads FNOL packet, policy declarations,
     police / crash report, repair / medical bill registers, EOBs, and
     any rental / fleet / loaner agreement. Emits RecoveryInputs — 20
     fields covering tortfeasor counterparty state, insured-side rosters,
     subrogation lane, recovery-extinguishing signals, evidence artifacts,
     and external-event triggers.
  B1. Policy engine (Python, Software 1.0) applies 15 FL doctrines as
      step-function gates and emits DoctrineResolution.
  B2. Apportionment calculator (Python, Software 1.0) computes
      recoverable basis + 5 layered targets + net economics + deadline
      countdowns.
  C. Diligence ledger (templated, byte-reproducible) — the
     Allstate v. Boecher + Ruiz-discoverable artifact and Harvey
     procedural-diligence defense.

Recovery never auto-commits. Output is a recommendation literal
(pursue / route_to_af / route_to_litigation / route_to_negotiated_demand /
abstain / senior_review_required) plus per-gate evidence + per-layer
apportionment + deadline calendar + preservation hold + diligence ledger.
The adjuster commits.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator


# =============================================================================
# Enums / Literal types
# =============================================================================


VehicleClassification = Literal[
    "private_passenger", "commercial", "taxicab", "unknown",
]

OwnerType = Literal[
    "natural_person",
    "commercial_lessor_graves",
    "business_not_in_leasing",
    "self_insured_fleet",
]

OmnibusRole = Literal[
    "named", "permissive", "resident_relative", "additional",
]

CoverageSection = Literal[
    "liability", "collision", "comprehensive", "um", "pip", "medpay",
]

SubrogationLaneId = Literal[
    "legal", "equitable", "contractual",
    "627_7405_pip_commercial", "768_76_collateral_source",
]

CollateralSourceType = Literal[
    "pip", "medpay", "health", "employer", "workers_comp",
    "medicare", "medicaid",
]

VehicleStatus = Literal[
    "in_storage_yard", "with_insured", "released_to_salvage",
    "totaled_held", "scrapped", "unknown",
]

ReleaseSignalType = Literal[
    "release_executed", "settlement_letter", "demand_response_release",
    "covenant_not_to_sue", "unknown",
]

OwnerKnowledgeIndicatorKind = Literal[
    "suspended_dl", "dui_history", "prior_crash_history",
    "owner_operator_comms", "unknown",
]

Recommendation = Literal[
    "pursue",
    "route_to_af",
    "route_to_litigation",
    "route_to_negotiated_demand",
    "abstain",
    "senior_review_required",
]

ForumRecommendation = Literal[
    "arbitration_forums",
    "litigation",
    "negotiated_demand",
    "abstain",
    "tbd_signatory_check_pending",
]

VarianceFlag = Literal[
    "comparative_fault_cliff_buffer",
    "commercial_vehicle_classification_ambiguity",
    "anti_subrogation_per_coverage_section_ambiguity",
    "sol_accrual_vs_filing_split",
    "made_whole_with_partial_settlement",
    "deny_plus_subrogate",
    "af_signatory_unverifiable",
    "products_liability_repose_boundary",
    "release_or_pre_tender_settlement_detected",
    "non_fl_loss_routed_to_abstain",
    "senior_review_recommended",
    "preservation_hold_unacknowledged",
]

AuthorityTier = Literal[
    "examiner",
    "senior_examiner",
    "supervisor",
    "manager",
    "roundtable",
    "carrier_consent",
    "large_loss_committee",
]

AfSignatoryStatus = Literal[
    "signatory", "non_signatory", "unverifiable",
]

GateResult = Literal[
    "pass", "fail", "n_a", "ambiguous_routed_to_senior",
]


# =============================================================================
# Input — extractor output
# =============================================================================


class PolicyLimits(BaseModel):
    bi_per_person: Decimal
    bi_per_incident: Decimal
    pd: Decimal


class OwnerOperatorSplit(BaseModel):
    owner_id: str
    operator_id: str
    are_same: bool
    owner_type: OwnerType


class OwnerKnowledgeIndicator(BaseModel):
    indicator: OwnerKnowledgeIndicatorKind
    source_doc_id: str
    quoted_span: str


class OmnibusPartyEntry(BaseModel):
    """Per-coverage-section roster entry — drives anti-subrogation gate."""

    name: str
    role: OmnibusRole
    coverage_section_paid_under: CoverageSection


class PolicySubrogationLanguage(BaseModel):
    has_made_whole_waiver: bool
    waiver_text: str = ""
    source_doc_id: str | None = None


class ReleaseSettlementSignal(BaseModel):
    type: ReleaseSignalType
    party: str
    signal_date: date | None = None
    source_doc_id: str
    quoted_span: str


class CollateralSourcePayment(BaseModel):
    payer: str
    amount: Decimal
    type: CollateralSourceType
    has_subro_right: bool
    notice_sent_date: date | None = None  # §768.76(7) 30-day clock anchor


class VerbalThresholdEvidence(BaseModel):
    """§627.737 threshold — BI tort right for non-economic damages."""

    permanency_opinion: bool = False
    scarring: bool = False
    significant_function_loss: bool = False
    mri_findings: bool = False
    source_doc_ids: list[str] = Field(default_factory=list)


class EvidenceArtifacts(BaseModel):
    vehicle_status: VehicleStatus
    edr_pulled: bool = False
    scene_photos: bool = False
    witness_contacts: list[str] = Field(default_factory=list)
    dashcam: bool = False


class ExternalEventTriggers(BaseModel):
    """The deadline anchors. Each starts a hard external clock."""

    liability_carrier_offer_date: date | None = None  # §627.727(6) 30-day UM
    section_768_76_notice_date: date | None = None     # §768.76 30-day collateral source
    af_dismissal_date: date | None = None              # AF 60-day refile window


class FabreCandidate(BaseModel):
    party: str
    evidence_basis: str
    estimated_fault_share: Decimal


class RentalFleetLoanerAgreement(BaseModel):
    exists: bool
    signatories: list[str] = Field(default_factory=list)
    indemnity_clause_text: str = ""


class CoverageDenialStatus(BaseModel):
    denied: bool
    basis: str = ""
    date_denied: date | None = None


class RecoveryInputs(BaseModel):
    """Structured facts the LLM extractor emits.

    Each field anchors to source documents for per-field anchor-pair eval.
    See docs/specs/recovery-workflow.md §RecoveryInputs schema.
    """

    # Statute-version gating
    loss_date: date
    loss_state: Literal["FL", "other"]
    claim_filing_date: date | None = None

    # Tortfeasor counterparty state
    tortfeasor_vehicle_classification: VehicleClassification
    tortfeasor_vehicle_vin: str | None = None
    tortfeasor_carrier_naic: str | None = None
    tortfeasor_policy_limits: PolicyLimits | None = None

    # Owner / operator structure
    owner_operator_split: OwnerOperatorSplit
    owner_knowledge_indicators: list[OwnerKnowledgeIndicator] = Field(default_factory=list)

    # Insured-side rosters (anti-subrogation)
    named_insured_and_omnibus_roster: list[OmnibusPartyEntry] = Field(default_factory=list)
    policy_subrogation_language: PolicySubrogationLanguage = Field(
        default_factory=lambda: PolicySubrogationLanguage(has_made_whole_waiver=False),
    )

    # Doctrinal lane
    subrogation_lane: SubrogationLaneId

    # Extinguishing signals
    release_or_settlement_signals: list[ReleaseSettlementSignal] = Field(default_factory=list)
    collateral_source_payments: list[CollateralSourcePayment] = Field(default_factory=list)

    # §627.737 verbal threshold
    verbal_threshold_evidence: VerbalThresholdEvidence | None = None

    # Evidence preservation
    evidence_artifacts: EvidenceArtifacts

    # External event triggers (deadline anchors)
    external_event_triggers: ExternalEventTriggers | None = None

    # Apportionment context
    fabre_candidate_nonparties: list[FabreCandidate] = Field(default_factory=list)

    # Contractual lanes
    rental_fleet_loaner_agreement: RentalFleetLoanerAgreement | None = None

    # Cross-stream
    coverage_denial_status: CoverageDenialStatus | None = None


# =============================================================================
# Upstream context — what Recovery consumes from Liability + Reserve + Coverage
# =============================================================================


class UpstreamLiabilitySnapshot(BaseModel):
    """Fault percentages + regime + bar status from LiabilityAssessment."""

    apportionment_by_party_id: dict[str, Decimal] = Field(
        description="party_id → fault_pct in [0, 100]",
    )
    insured_fault_pct: Decimal | None = None
    claimant_fault_pct: Decimal | None = None
    operator_party_id: str | None = None
    owner_party_id: str | None = None
    regime_statute: str
    recovery_bar_triggered: bool
    bar_basis: str
    calibration_confidence: float = Field(ge=0.0, le=1.0, default=0.7)


class UpstreamReserveSnapshot(BaseModel):
    """Paid + outstanding indemnity from ReserveAnalysis."""

    paid_indemnity_by_component: dict[str, Decimal] = Field(default_factory=dict)
    outstanding_indemnity_by_component: dict[str, Decimal] = Field(default_factory=dict)
    total_economic_loss: Decimal = Decimal("0")


class UpstreamCoverageSnapshot(BaseModel):
    """Coverage status + omnibus roster from CoverageReport."""

    status: Literal["granted", "denied", "under_investigation", "ror"]
    denial_basis: str = ""
    omnibus_roster: list[OmnibusPartyEntry] = Field(default_factory=list)
    cooperation_defense_window_open: bool = False


class RecoveryUpstreamContext(BaseModel):
    """Bundle of upstream snapshots Recovery consumes.

    Kept as small typed shapes so Recovery doesn't drag full
    Liability/Reserve/Coverage schemas into its policy engine + calculator.
    """

    liability: UpstreamLiabilitySnapshot | None = None
    reserve: UpstreamReserveSnapshot | None = None
    coverage: UpstreamCoverageSnapshot | None = None


# =============================================================================
# Policy engine output (intermediate)
# =============================================================================


class DoctrineGateResult(BaseModel):
    """One gate's evaluation outcome — for the diligence ledger + rationale."""

    gate_id: str
    result: GateResult
    statute_or_case_cite: str
    effect_if_fired: str
    evidence_ref: str = ""
    variance_flag_emitted: VarianceFlag | None = None


class ApplicableSolRegime(BaseModel):
    """HB 837 SOL selector outcome."""

    statute_version: Literal["pre_hb837_4yr", "post_hb837_2yr", "pd_4yr", "products_12yr"]
    statute_cite: str
    sol_deadline: date
    days_remaining: int


class DoctrineResolution(BaseModel):
    """Policy engine output. Feeds calculator + variance flagging."""

    gates: list[DoctrineGateResult]
    sol_regime: ApplicableSolRegime
    recovery_barred: bool
    bar_basis: str  # e.g. "hb_837_51_bar", "anti_subrogation", "sol_expired"
    variance_flags: list[VarianceFlag] = Field(default_factory=list)


# =============================================================================
# Calculator + ledger nested outputs
# =============================================================================


class SubrogationLane(BaseModel):
    lane_id: SubrogationLaneId
    cite: str
    defense_checklist_anchor: str


class LayeredTarget(BaseModel):
    """One recovery layer with apportioned share + net economics."""

    layer_id: Literal[
        "operator_policy",
        "owner_vicarious_cap_324_021",
        "owner_negligent_entrustment_uncapped",
        "fabre_non_party",
        "product_defect_recall",
    ]
    target_party_id: str | None = None
    apportioned_fault_pct: Decimal = Field(ge=0, le=100)
    apportioned_share: Decimal = Field(description="$ apportioned-share before cap")
    cap_applied: Decimal | None = None
    gross_recoverable: Decimal = Field(description="apportioned_share, post-cap")
    probability_of_recovery: float = Field(ge=0.0, le=1.0)
    expected_value: Decimal
    evidence_completeness: float = Field(ge=0.0, le=1.0)


class RecoverableBasis(BaseModel):
    section_768_0427_capped_damages: Decimal
    pip_collateral_source_stripped: Decimal
    made_whole_shortfall: Decimal
    basis: Decimal = Field(description="capped − stripped − shortfall")


class NetEconomics(BaseModel):
    gross_recoverable_total: Decimal
    fee_drag: Decimal
    fee_shifting_exposure: Decimal
    net_total: Decimal
    fee_model: Literal["af_flat", "vendor_contingency", "internal_blended"]


class ForumRouting(BaseModel):
    recommendation: ForumRecommendation
    af_signatory_check: AfSignatoryStatus
    company_paid_damages: Decimal
    af_cap_dollars: Decimal
    within_af_cap: bool
    basis: str


class DeadlineEntry(BaseModel):
    deadline_id: Literal[
        "sol_drop_dead",
        "af_60_day_refile",
        "section_768_76_30_day",
        "section_627_727_6_30_day",
        "products_repose_12yr",
    ]
    deadline_date: date
    days_remaining: int
    statute_or_rule_cite: str


class DeadlineCalendar(BaseModel):
    entries: list[DeadlineEntry] = Field(default_factory=list)


class PreservationHold(BaseModel):
    issued: bool
    hold_scope: list[Literal[
        "vehicle", "edr_acm", "scene_photos", "witness_statements", "dashcam",
    ]] = Field(default_factory=list)
    storage_yard_letter_text: str = ""
    blocks_salvage_release: bool = True
    acknowledgment_status: Literal["pending", "acknowledged", "not_required"] = "pending"


# =============================================================================
# Diligence ledger — Boecher/Ruiz-discoverable, co-equal artifact
# =============================================================================


class AfSignatoryCheckRecord(BaseModel):
    naic: str | None
    source: str
    lookup_timestamp: datetime
    result: AfSignatoryStatus
    fallback_action: str = ""


class AntiSubroCrossReference(BaseModel):
    omnibus_roster_snapshot: list[OmnibusPartyEntry]
    per_coverage_section_overlap: dict[str, list[str]] = Field(
        default_factory=dict,
        description="coverage_section → list[party names overlapping]",
    )


class MadeWholeComputation(BaseModel):
    paid_to_insured: Decimal
    total_economic_loss: Decimal
    shortfall: Decimal
    waiver_status: Literal["waived", "not_waived", "absent"]
    rationale: str


class SourceCitation(BaseModel):
    statute_or_case: str
    claim_doc_id: str | None = None
    quoted_span: str = ""


class OpenRequest(BaseModel):
    request_type: str
    requested_date: date
    age_days: int
    target_party: str


class EvidenceNotObtained(BaseModel):
    evidence_kind: str
    reason_declined: str
    date_decision: date


class SupervisorDisagreement(BaseModel):
    date_recorded: date
    dissent_recommendation: Recommendation
    dissent_basis: str


class GateEvaluationLedgerEntry(BaseModel):
    """One ledger entry per gate — with timestamp for Boecher discovery."""

    gate_id: str
    result: GateResult
    cite: str
    evidence_ref: str
    evaluated_at: datetime


class RecoveryDiligenceLedger(BaseModel):
    gates_evaluated: list[GateEvaluationLedgerEntry] = Field(default_factory=list)
    af_signatory_check: AfSignatoryCheckRecord | None = None
    anti_subrogation_cross_reference: AntiSubroCrossReference | None = None
    made_whole_computation: MadeWholeComputation | None = None
    decision_rationale: str
    preservation_hold_status: PreservationHold
    sources_cited: list[SourceCitation] = Field(default_factory=list)
    open_requests: list[OpenRequest] = Field(default_factory=list)
    evidence_not_obtained: list[EvidenceNotObtained] = Field(default_factory=list)
    supervisor_disagreement_record: list[SupervisorDisagreement] = Field(default_factory=list)


# =============================================================================
# Cross-stream + authority
# =============================================================================


class CrossStreamConflicts(BaseModel):
    coverage_denial_recovery_pursuit_interlock: Literal[
        "no_conflict", "active_conflict_senior_review_required", "n_a",
    ] = "no_conflict"
    anti_subrogation_omnibus_overlap: list[str] = Field(default_factory=list)
    section_627_426_2_cooperation_window_open: bool = False


class AuthorityRouting(BaseModel):
    committable_at_examiner: bool
    required_tier: AuthorityTier
    net_apportioned_recoverable: Decimal
    basis_for_tier: str


# =============================================================================
# Top-level output
# =============================================================================


class RecoveryAssessment(BaseModel):
    """Final Recovery workflow output.

    Composed of: the recommendation literal, subrogation lane, ordered
    doctrinal gate results, ranked layered targets with per-layer net
    economics, recoverable-basis math, deadline calendar, preservation
    hold, diligence ledger (co-equal), variance flags, cross-stream
    conflicts, and authority routing. Never auto-commits — adjuster
    commits based on this surface.
    """

    request_id: str
    reviewed_as_of: datetime

    # The recommendation
    recommendation: Recommendation
    subrogation_lane: SubrogationLane

    # Doctrinal evaluation
    doctrinal_gates: list[DoctrineGateResult]
    sol_regime: ApplicableSolRegime

    # Layered targets + math
    layered_targets: list[LayeredTarget] = Field(default_factory=list)
    recoverable_basis: RecoverableBasis
    net_economics: NetEconomics

    # Forum + deadlines + preservation
    forum_routing: ForumRouting
    deadline_calendar: DeadlineCalendar
    preservation_hold: PreservationHold

    # Audit trail (co-equal with recommendation)
    diligence_ledger: RecoveryDiligenceLedger
    rationale_text: str = Field(
        default="",
        description=(
            "Templated audit-trail string from render_recovery_rationale. "
            "Byte-reproducible from inputs + intermediates + upstream context."
        ),
    )

    # Routing surfaces
    variance_flags: list[VarianceFlag] = Field(default_factory=list)
    authority_tier_required: AuthorityRouting
    cross_stream_conflicts: CrossStreamConflicts

    @model_validator(mode="after")
    def gates_carry_cite(self) -> RecoveryAssessment:
        for g in self.doctrinal_gates:
            if g.result != "n_a" and not g.statute_or_case_cite:
                raise ValueError(
                    f"Gate {g.gate_id} fired without statute_or_case_cite — "
                    f"diligence ledger requires per-gate citation.",
                )
        return self


# =============================================================================
# Program config (per-CHA overrides)
# =============================================================================


class ProgramConfig(BaseModel):
    """Per-CHA authority bands + AF cap + per-layer P(recovery) scalars.

    Loaded from program registry at runtime; constants.py ships
    DEFAULT_PROGRAM only for tests and demo fixture.
    """

    program_id: str
    examiner_authority_dollars: Decimal
    senior_examiner_authority_dollars: Decimal
    supervisor_authority_dollars: Decimal
    manager_authority_dollars: Decimal
    roundtable_threshold_dollars: Decimal
    af_compulsory_cap_dollars: Decimal = Decimal("100000")
    fee_drag_internal_hourly_rate: Decimal = Decimal("80")
    fee_drag_internal_hours_per_file: Decimal = Decimal("8")
    fee_drag_vendor_contingency_pct: Decimal = Decimal("0.25")
    fee_drag_af_flat: Decimal = Decimal("42")
    p_recovery_operator_policy: float = 0.85
    p_recovery_vicarious_cap: float = 0.70
    p_recovery_negligent_entrustment: float = 0.55
    p_recovery_fabre_non_party: float = 0.40
    p_recovery_products_defect: float = 0.30
    mandatory_referral_variance_flags: list[VarianceFlag] = Field(default_factory=list)
