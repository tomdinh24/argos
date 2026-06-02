"""Closure workflow schemas.

Spec: docs/specs/closure-workflow.md.

Closure is the sixth and terminating analytical workflow. It consumes
committed Coverage / Liability / Reserve / Recovery assessments and
evaluates ~25 deterministic gates organized into 6 tiers (statutory
FL + federal lien/MSP + release evidence + audit/authority +
defense-track bifurcation + preservation/retention). Surfaces a
ready-to-close probability + ranked blocking defects + remediation
hints. Recommendation execution is always human.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator


# =============================================================================
# Enums (controlled literals)
# =============================================================================


CoverageDecision = Literal[
    "granted", "ror", "denied", "uncommitted",
]

RecoveryPursuitDecision = Literal[
    "pursue", "route_to_af", "route_to_litigation",
    "route_to_negotiated_demand", "abstain", "senior_review_required",
    "uncommitted",
]

PipBillStatusKind = Literal[
    "paid_within_30", "denied_within_30", "open_within_30",
    "open_past_30", "eob_issued",
]

CrnCureStatus = Literal[
    "no_open_crn", "cured", "uncured", "partial_cure",
]

LienKind = Literal[
    "medicare_conditional_payment",
    "section_111_tpoc_report",
    "florida_medicaid",
    "workers_compensation",
    "erisa_self_funded",
    "hospital_county_specific",
    "veterans_affairs",
    "tricare",
]

LienResolutionStatus = Literal[
    "not_applicable",
    "identified_no_action",
    "notice_sent_window_open",
    "notice_sent_window_expired_no_response",
    "response_received_pending_resolution",
    "release_letter_on_file",
    "active_dispute",
    "unknown",
]

ObrLegalWeight = Literal[
    "legally_required", "informational", "n_a",
]

OirClassification = Literal[
    "closed_with_payment",
    "closed_without_payment",
    "reopened",
    "not_yet_classifiable",
]

DefenseStatus = Literal[
    "n_a", "open", "closed_after_indemnity",
]

IndemnityStatus = Literal[
    "open", "ready", "soft_closed_pending", "closed",
]

HospitalLienSearchStatus = Literal[
    "pending", "searched_clean", "searched_lien_found", "not_applicable",
]

DefectTier = Literal["A", "B", "C", "D", "E", "F"]

Recommendation = Literal[
    "ready_to_close_with_payment",
    "ready_to_close_without_payment",
    "closed_with_open_recovery",
    "soft_close_pending_medicare_final_demand",
    "soft_close_pending_section_111_confirmation",
    "soft_close_pending_lien_release_letter",
    "soft_close_pending_release_execution",
    "blocked_by_defects",
    "requires_senior_review",
    "requires_legal_review",
    "recommend_reopen",
]

AuthorityTier = Literal[
    "examiner", "senior_examiner", "supervisor", "manager", "roundtable",
]

VarianceFlag = Literal[
    "medicare_eligibility_check_skipped",
    "erisa_funding_type_undetermined",
    "multi_claimant_competing_limits_ambiguity",
    "hospital_lien_county_search_pending",
    "powell_duty_arguably_triggered",
    "macola_post_excess_trajectory_pattern",
    "agent_action_ledger_warning_only",  # v1 warning, not block
    "recovery_subro_only_state",
    "preservation_hold_floor_undeterminable",
    "release_executed_but_tender_pending",
    "boecher_ruiz_artifact_destruction_risk",
]

GateResult = Literal["pass", "fail", "n_a"]


# =============================================================================
# Input nested types
# =============================================================================


class PipBillStatus(BaseModel):
    """One PIP bill's drain status per §627.736(4)(b)."""

    bill_id: str
    billed_amount: Decimal
    received_date: date
    status: PipBillStatusKind
    days_since_received: int = 0


class DenialLetterAudit(BaseModel):
    """Per §626.9541(1)(i)3 — letter must cite policy provision + facts + applicable law."""

    on_file: bool = False
    cites_policy_provision: bool = False
    cites_facts: bool = False
    cites_applicable_law: bool = False
    letter_doc_id: str | None = None


class CrnRecord(BaseModel):
    """One open CRN's state per §624.155(3)."""

    crn_id: str
    dfs_filing_date: date
    days_since_dfs_filing: int
    alleged_statutory_violations: list[str] = Field(default_factory=list)
    cure_status: CrnCureStatus = "uncured"
    cure_documentation_doc_ids: list[str] = Field(default_factory=list)


class Section111TpocLog(BaseModel):
    """Section 111 MMSEA transmit-success record."""

    tpoc_date: date
    tpoc_amount: Decimal
    transmit_success: bool = False
    transmit_confirmation_id: str | None = None
    transmit_date: date | None = None


class LienRecord(BaseModel):
    """Per-lien per-payer resolution state."""

    kind: LienKind
    payer_name: str | None = None
    claimed_amount: Decimal | None = None
    notice_sent_date: date | None = None
    notice_sent_certified_mail: bool = False
    response_received_date: date | None = None
    release_letter_on_file: bool = False
    release_letter_doc_id: str | None = None
    satisfaction_amount: Decimal | None = None
    status: LienResolutionStatus = "unknown"
    county: str | None = None  # for hospital_county_specific


class OutboundRequestRef(BaseModel):
    """Open OutboundRequest with legal-weight classification."""

    obr_id: str
    legal_weight: ObrLegalWeight
    cite: str = ""
    days_open: int = 0


class SettlementInfo(BaseModel):
    """Settlement state for §627.4265 + release-on-file checks."""

    agreement_date: date | None = None
    agreement_amount: Decimal | None = None
    release_executed_date: date | None = None
    release_doc_id: str | None = None
    release_includes_hold_harmless_for_liens: bool = False
    check_tendered_date: date | None = None
    check_amount: Decimal | None = None
    days_since_agreement: int | None = None
    days_since_release: int | None = None


class MultiClaimantState(BaseModel):
    """Per-claimant multi-claimant tracking + §624.155(6) safe-harbor compliance."""

    occurrence_id: str | None = None
    is_multi_claimant: bool = False
    competing_demands_exceed_aggregate: bool = False
    days_since_competing_claims_notice: int | None = None
    interpleader_filed: bool = False
    interpleader_filing_date: date | None = None
    binding_arbitration_submitted: bool = False
    binding_arbitration_submission_date: date | None = None
    global_tender_letter_sent_to_all_claimants: bool = False
    per_claimant_responses_logged: bool = False
    priority_memo_on_file: bool = False
    insured_notice_of_strategy_on_file: bool = False


class Section_627_4137_AffidavitState(BaseModel):
    """§627.4137 affidavit-of-coverage state."""

    claimant_written_request_on_file: bool = False
    claimant_request_date: date | None = None
    affidavit_delivered: bool = False
    affidavit_delivery_date: date | None = None
    amended_for_aggregate_erosion: bool = False


class CommunicationLog(BaseModel):
    """Per Harvey: claimant communications received pre-close + insured-relay status."""

    received_count: int = 0
    answered_count: int = 0
    relayed_to_insured_count: int = 0


class BostonOldColonyDiligence(BaseModel):
    """Five fiduciary preconditions at close per Boston Old Colony 386 So.2d 783."""

    insured_notified_of_settlement_opportunities: bool = False
    insured_warned_of_excess_exposure: bool = False
    facts_investigated: bool = False
    settlement_offers_received_fair_consideration: bool = False
    decision_reflects_reasonable_prudent_person: bool = False


class PowellAnalysis(BaseModel):
    """Powell 584 So.2d 12 — affirmative duty to initiate settlement."""

    liability_clear: bool = False
    damages_plausibly_exceed_limits: bool = False
    affirmative_policy_limits_offer_made: bool = False
    why_powell_does_not_apply_memo_on_file: bool = False


class MacolaSignals(BaseModel):
    """Macola 953 So.2d 451 — payment doesn't cure prior bad-faith failure."""

    powell_duty_arguably_triggered_earlier: bool = False
    tender_came_only_after_suit_or_demand_pressure: bool = False
    close_memo_treats_payment_as_resolution: bool = False


class ExposureClosureState(BaseModel):
    """Per-coverage-section closure status (ClaimCenter exposure-level model)."""

    bi: bool = False
    pd: bool = False
    mp: bool = False
    pip: bool = False
    um: bool = False


class ClosureInputs(BaseModel):
    """Structured facts the LLM extractor emits.

    Each field anchors to source documents (claim record + upstream
    assessment JSON files + uploaded docs). See spec §4 for gate
    consumption.
    """

    # Lifecycle posture
    claim_first_actual_notice_date: date | None = None
    loss_date: date
    intended_closure_intent: Literal[
        "with_payment", "without_payment", "tbd",
    ] = "tbd"

    # Coverage decision audit (Tier A: A1, A3)
    coverage_decision: CoverageDecision = "uncommitted"
    denial_letter_audit: DenialLetterAudit = Field(default_factory=DenialLetterAudit)

    # Liability commitment + Powell / Harvey / Boston Old Colony signals (Tier A: A2, A11–A14)
    liability_apportionment_committed: bool = False
    boston_old_colony_diligence: BostonOldColonyDiligence = Field(
        default_factory=BostonOldColonyDiligence,
    )
    powell_analysis: PowellAnalysis = Field(default_factory=PowellAnalysis)
    macola_signals: MacolaSignals = Field(default_factory=MacolaSignals)
    harvey_communication_log: CommunicationLog = Field(default_factory=CommunicationLog)

    # CRN + safe-harbor windows (Tier A: A4, A5)
    open_crns: list[CrnRecord] = Field(default_factory=list)
    third_party_safe_harbor_tender_made: bool = False

    # Multi-claimant + §627.4137 (Tier A: A6, A7)
    multi_claimant_state: MultiClaimantState = Field(default_factory=MultiClaimantState)
    section_627_4137_state: Section_627_4137_AffidavitState = Field(
        default_factory=Section_627_4137_AffidavitState,
    )

    # PIP drain (Tier A: A8)
    pip_bill_ledger: list[PipBillStatus] = Field(default_factory=list)

    # Settlement + §627.4265 (Tier A: A9, Tier C: C1, C2)
    settlement: SettlementInfo = Field(default_factory=SettlementInfo)

    # Per-coverage-section exposure status (Tier A: A10)
    exposure_status: ExposureClosureState = Field(default_factory=ExposureClosureState)

    # Lien resolution (Tier B: B1–B7)
    liens: list[LienRecord] = Field(default_factory=list)
    section_111_log: Section111TpocLog | None = None
    medicare_beneficiary_identified: bool = False
    medicaid_beneficiary_identified: bool = False
    in_scope_of_employment_at_loss: bool = False
    erisa_self_funded_plan_identified: bool = False
    erisa_plan_funding_type_confirmed: bool = False
    veteran_or_tricare_beneficiary: bool = False
    hospital_lien_county_search_status: HospitalLienSearchStatus = "not_applicable"
    hospital_lien_search_county: str | None = None

    # Collateral source §768.76 (Tier C: C3)
    collateral_source_notice_sent_date: date | None = None
    collateral_source_responses_logged: bool = False

    # Open OBRs (Tier C: C4)
    open_obrs: list[OutboundRequestRef] = Field(default_factory=list)

    # Audit (Tier D: D1, D3)
    agent_action_ledger_complete: bool = False
    examiner_id: str = "system"

    # Defense track (Tier E: E1)
    interpleader_indemnity_deposited: bool = False
    underlying_tort_actions_unresolved: bool = False

    # Preservation (Tier F: F1)
    last_cms_cpn_date: date | None = None
    last_phi_authorization_end_date: date | None = None
    tpa_contract_termination_date: date | None = None
    sol_outer_bound_date: date | None = None


# =============================================================================
# Upstream context (Closure consumes from every prior analytical workflow)
# =============================================================================


class UpstreamCoverageSnapshotForClosure(BaseModel):
    decision_committed: bool = False
    decision: CoverageDecision = "uncommitted"
    denial_letter_on_file: bool = False
    denial_letter_cites_policy_provision: bool = False
    denial_letter_cites_facts: bool = False
    denial_letter_cites_law: bool = False
    omnibus_roster_size: int = 0


class UpstreamLiabilitySnapshotForClosure(BaseModel):
    apportionment_committed: bool = False
    regime_statute: str = "unknown"
    insured_fault_pct: Decimal | None = None
    claimant_fault_pct: Decimal | None = None
    multi_claimant_occurrence: bool = False
    competing_demands_exceed_aggregate: bool = False
    first_actual_notice_date: date | None = None
    powell_duty_potentially_triggered: bool = False
    tender_made: bool = False


class UpstreamReserveSnapshotForClosure(BaseModel):
    paid_indemnity_by_component: dict[str, Decimal] = Field(default_factory=dict)
    outstanding_indemnity_by_component: dict[str, Decimal] = Field(default_factory=dict)
    total_paid: Decimal = Decimal("0")
    reserve_balance: Decimal = Decimal("0")
    pip_bill_ledger: list[PipBillStatus] = Field(default_factory=list)


class UpstreamRecoverySnapshotForClosure(BaseModel):
    pursuit_decision_committed: bool = False
    decision: RecoveryPursuitDecision = "uncommitted"
    subro_only_file_state: bool = False


class UpstreamBriefSnapshotForClosure(BaseModel):
    open_obrs_with_legal_weight: int = 0
    open_obrs_informational: int = 0
    agent_action_count: int = 0
    claim_first_notice_date: date | None = None


class ClosureUpstreamContext(BaseModel):
    """Bundle of upstream snapshots Closure consumes."""

    coverage: UpstreamCoverageSnapshotForClosure | None = None
    liability: UpstreamLiabilitySnapshotForClosure | None = None
    reserve: UpstreamReserveSnapshotForClosure | None = None
    recovery: UpstreamRecoverySnapshotForClosure | None = None
    brief: UpstreamBriefSnapshotForClosure | None = None


# =============================================================================
# Policy engine output (intermediate)
# =============================================================================


class ClosureGateResult(BaseModel):
    """One gate's evaluation outcome — for the diligence ledger + rationale."""

    gate_id: str
    tier: DefectTier
    result: GateResult
    statute_or_case_cite: str
    evidence_ref: str = ""
    defect_emitted: bool = False
    remediation_action: str = ""


class DoctrineResolution(BaseModel):
    """Bundled output of apply_fl_closure_gates."""

    gates: list[ClosureGateResult] = Field(default_factory=list)
    variance_flags: list[VarianceFlag] = Field(default_factory=list)
    preservation_until_date: date | None = None
    oir_classification: OirClassification = "not_yet_classifiable"
    any_tier_a_failure: bool = False
    any_tier_b_failure: bool = False
    any_tier_c_failure: bool = False


# =============================================================================
# Calculator output
# =============================================================================


class BlockingDefect(BaseModel):
    """A gate-fail surfaced as a closure-blocking defect with remediation."""

    gate_id: str
    tier: DefectTier
    description: str
    statute_or_case_cite: str
    evidence_ref: str = ""
    remediation_action: str = ""


class LienResolutionRecord(BaseModel):
    """Per-lien resolution audit entry for the diligence ledger."""

    kind: LienKind
    identified: bool
    notice_sent: bool = False
    response_status: str = ""
    release_letter_on_file: bool = False
    satisfaction_amount: Decimal | None = None


class CrnStateRecord(BaseModel):
    """One open-CRN state record for the diligence ledger."""

    crn_id: str
    dfs_filing_date: date
    days_since_dfs_filing: int
    alleged_violations: list[str] = Field(default_factory=list)
    cure_status: CrnCureStatus


class NoticeDeliveryRecord(BaseModel):
    """One statutory-notice delivery audit record."""

    notice_kind: str  # e.g., "section_627_4137_affidavit", "section_768_76", "denial_letter"
    delivered: bool
    delivery_date: date | None = None
    content_audit_pass: bool = False
    cite: str = ""


class MultiClaimantArtifactCheck(BaseModel):
    """Per Farinas / Shuster — four artifacts required at sequential close."""

    global_tender_letter_sent: bool
    per_claimant_responses_logged: bool
    priority_memo_on_file: bool
    insured_notice_of_strategy_on_file: bool


class PreservationPlan(BaseModel):
    """Computed retention floor + data-source hold list (Valcin/Martino + §626.884 + HIPAA)."""

    preservation_until_date: date | None = None
    floor_components: dict[str, date] = Field(default_factory=dict)
    data_sources_held: list[str] = Field(default_factory=list)


class AuthorityRouting(BaseModel):
    """Tier ladder for the closure decision; keyed off settlement amount."""

    committable_at_examiner: bool
    required_tier: AuthorityTier
    settlement_amount: Decimal = Decimal("0")
    basis_for_tier: str = ""


# =============================================================================
# Diligence ledger (Boecher/Ruiz-discoverable, co-equal artifact)
# =============================================================================


class ClosureDiligenceLedger(BaseModel):
    """Boecher/Ruiz-discoverable artifact. Co-equal with the recommendation."""

    gates_evaluated: list[ClosureGateResult] = Field(default_factory=list)
    lien_resolution_records: list[LienResolutionRecord] = Field(default_factory=list)
    crn_state: CrnStateRecord | None = None
    notice_delivery_audit: list[NoticeDeliveryRecord] = Field(default_factory=list)
    multi_claimant_artifacts: MultiClaimantArtifactCheck | None = None
    preservation_plan: PreservationPlan = Field(default_factory=PreservationPlan)
    record_classification: OirClassification = "not_yet_classifiable"
    decision_rationale: str = ""


# =============================================================================
# Top-level output
# =============================================================================


class ClosureAssessment(BaseModel):
    """Final Closure workflow output.

    Composed of: ready_to_close probability, ranked blocking defects,
    recommendation literal, bifurcated indemnity/defense status, OIR
    classification, preservation plan, diligence ledger (co-equal),
    variance flags, authority routing. Never auto-applies the close —
    adjuster commits via apply_closure_decision.
    """

    request_id: str
    reviewed_as_of: datetime

    # Recommendation surface
    recommendation: Recommendation
    ready_probability: float = Field(ge=0.0, le=1.0)
    blocking_defects: list[BlockingDefect] = Field(default_factory=list)

    # Bifurcated status per §624.155(6)(a)
    indemnity_status: IndemnityStatus = "open"
    defense_status: DefenseStatus = "n_a"

    # Regulatory bucket
    oir_classification: OirClassification = "not_yet_classifiable"

    # Doctrinal evaluation
    doctrinal_gates: list[ClosureGateResult] = Field(default_factory=list)

    # Preservation
    preservation_plan: PreservationPlan = Field(default_factory=PreservationPlan)

    # Audit trail
    diligence_ledger: ClosureDiligenceLedger
    rationale_text: str = ""

    # Routing
    variance_flags: list[VarianceFlag] = Field(default_factory=list)
    authority_tier_required: AuthorityRouting

    @model_validator(mode="after")
    def gates_carry_cite(self) -> ClosureAssessment:
        for g in self.doctrinal_gates:
            if g.result != "n_a" and not g.statute_or_case_cite:
                raise ValueError(
                    f"Gate {g.gate_id} fired without statute_or_case_cite — "
                    f"diligence ledger requires per-gate citation.",
                )
        return self


# =============================================================================
# Program config (per-CHA closure parameters)
# =============================================================================


class ClosureProgramConfig(BaseModel):
    """Per-CHA authority bands + soft-close windows + Powell calibration."""

    program_id: str
    closure_examiner_authority_dollars: Decimal = Decimal("25000")
    closure_senior_examiner_authority_dollars: Decimal = Decimal("75000")
    closure_supervisor_authority_dollars: Decimal = Decimal("250000")
    closure_manager_authority_dollars: Decimal = Decimal("1000000")
    soft_close_max_days_pending_final_demand: int = 180  # CMS max
    soft_close_max_days_pending_section_111: int = 135
    powell_clear_liability_threshold_pct: int = 80
    auto_close_enabled: bool = False
    record_retention_floor_years: int = 3  # FL Admin Code 69O-191.074 baseline
    hipaa_retention_years: int = 6  # 45 CFR §164.530(j)(2)
    tpa_contract_retention_years_after_termination: int = 5  # §626.884


# =============================================================================
# Back-compat aliases — keep old names callable for any in-flight imports
# =============================================================================


# The pre-2026-06-02 minimal scaffold exported these names. Keep them as
# aliases so any in-flight imports (Brief reads ClosureAnalysis off disk)
# don't break during the migration.
ClosureAnalysis = ClosureAssessment
ClosureDefect = BlockingDefect
DefectKind = Literal[
    "outstanding_reserve", "open_recovery", "open_lien",
    "missing_release", "missing_required_document", "pending_litigation",
    "pending_section_111", "pending_authority_decision",
    "client_checklist_item",
]
