"""Liability workflow schemas.

The workflow is split into four stages (see docs/specs/liability-workflow.md):

  A. Extractor (LLM, Software 3.0) reads documents + claim state and emits
     LiabilityInputs — fact pattern, parties, evidence items with quoted
     spans, FL-specific facts.
  B1. Policy engine (Python, Software 1.0) applies FL doctrine gates and
      emits DoctrineResolution (regime, ceiling, bar flags, branch path).
  B2. Apportionment calculator (Python, Software 1.0) takes inputs +
      resolution and emits per-party-pair scalars with confidence bands.
  C. Diligence ledger (templated, byte-reproducible) — the Allstate v. Ruiz
     discoverable artifact and Harvey procedural-diligence defense.

Liability never auto-commits. Output surfaces evidence + recommended
apportionment + variance flags + authority tier. The adjuster commits.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from argos.schemas.contract import EvidenceCitation


# =============================================================================
# Enums / Literal types
# =============================================================================


FactPattern = Literal[
    "rear_end",
    "left_turn_across_traffic",
    "lane_change",
    "uncontrolled_intersection",
    "controlled_intersection",
    "parked_pullout",
    "sideswipe",
    "chain_reaction",
    "pedestrian_in_crosswalk",
    "pedestrian_mid_block",
    "cyclist",
    "parking_lot",
    "other",
]

LineOfBusiness = Literal[
    "auto_bi", "med_mal", "commercial_auto", "trucking", "rideshare", "other",
]

PartyRole = Literal[
    "insured_driver",
    "insured_owner",
    "claimant_driver",
    "claimant_passenger",
    "claimant_pedestrian",
    "claimant_cyclist",
    "fabre_non_party",
]

OwnerType = Literal[
    "natural_person",
    "commercial_lessor_graves",  # Graves Amendment-eligible
    "business_not_in_leasing",
    "self_insured_fleet",
]

EvidenceKind = Literal[
    "police_report_field",
    "police_report_narrative",
    "recorded_statement_insured",
    "recorded_statement_claimant",
    "recorded_statement_witness",
    "scene_photo",
    "edr_download",
    "surveillance_video",
    "expert_report_recon",
    "expert_report_biomech",
    "expert_report_medical_causation",
    "er_record_mechanism",
    "damage_appraisal",
    "citation_issued",
    "mvr_record",
    "deposition_transcript",
    "party_admission",
]

FLAdmissibility = Literal[
    "admissible",
    "privileged_316_066",          # accident-report privilege on statements
    "physical_evidence_carveout",  # skid marks, debris, measurements
    "chemical_test_carveout",      # §316.1934 BAC results
]

FaultDirection = Literal[
    "insured_more_fault", "claimant_more_fault", "neutral",
]

EvidenceWeightClass = Literal[
    "hard_data",          # EDR, video, physical evidence — ±20-25
    "independent",        # witness, citation — ±10-15
    "party_admission",    # ±15
    "rebuttable_signal",  # police-report contributing factor — ±5-10
    "credibility_only",   # demeanor, prior crashes — ±0-5
]

ApplicableRegimeStatute = Literal[
    "pure_comparative_pre_hb837",
    "modified_51_bar_hb837",
    "med_mal_pure_comparative",
]

RecoveryBarBasis = Literal[
    "none", "hb837_51_pct", "768_36_intoxication",
]

VarianceFlag = Literal[
    "near_50_pct_bar",
    "multi_party_matrix_required",
    "fabre_non_party_unpled",
    "powell_duty_clarity",
    "safe_harbor_clock_decision_required",
    "roundtable_recommended",
    "siu_referral_recommended",
    "expert_retention_recommended",
    "evidence_gap_blocks_initial_call",
    "er_mechanism_contradicts_claimant",
    "damage_vs_mechanism_contradiction",
    "apportionment_delta_exceeds_examiner_band",
    "intoxication_bar_candidate",
    "graves_vs_negligent_entrustment_branch",
]

AuthorityTier = Literal[
    "examiner",
    "senior_examiner",
    "supervisor",
    "manager",
    "roundtable",
    "carrier_consent",
    "reinsurer_consultation",
]

ConsistencyResult = Literal["consistent", "gap", "contradiction"]


# =============================================================================
# Input shape (Extractor output / Policy engine + Calculator input)
# =============================================================================


class Party(BaseModel):
    party_id: str
    role: PartyRole
    identity_evidence_cite: str = Field(
        description="Document id + locator establishing identity",
    )


class OwnerRelationship(BaseModel):
    """Dangerous Instrumentality + Graves + §324.021(9)(b)3 inputs."""

    driver_is_owner: bool
    owner_type: OwnerType
    permissive_use_evidence_cite: str | None = None
    theft_evidence_cite: str | None = None  # Hertz v. Jackson exception
    permissive_user_coverage_limits: Decimal | None = None


class NegligentEntrustment(BaseModel):
    """§324.021(9)(b)3 closing sentence — uncapped path."""

    driver_unlicensed: bool = False
    driver_dui_history: bool = False
    driver_known_intoxicated_at_handoff: bool = False
    owner_knowledge_evidence_cites: list[str] = Field(default_factory=list)


class IntoxicationEvidence(BaseModel):
    """§768.36 dual-prong: BAC/impairment AND causation."""

    bac_value: Decimal | None = None
    bac_source: Literal["blood", "breath", "urine", "none"] = "none"
    impairment_observed: bool = False
    causation_to_fault_evidence_cites: list[str] = Field(default_factory=list)
    chemical_test_admissible: bool = False  # §316.1934 carveout


class RearEndRebuttal(BaseModel):
    """Birge / Pierce four-category rebuttal of the rear-end presumption."""

    category: Literal[
        "mechanical_failure",
        "sudden_stop_unexpected_place",
        "sudden_lane_change_by_lead",
        "illegal_improper_stop_by_lead",
        "none",
    ] = "none"
    evidence_cites: list[str] = Field(default_factory=list)


class PoliceReportFields(BaseModel):
    """FL HSMV 90010S structured fields."""

    driver_action_codes_per_party: dict[str, list[int]] = Field(
        default_factory=dict,
        description="party_id → list[int] (max 4 each); FL HSMV 90010S codes",
    )
    citation_issued_to: list[str] = Field(
        default_factory=list,
        description="party_ids cited at the scene",
    )
    area_of_initial_impact_per_party: dict[str, str] = Field(default_factory=dict)
    officer_narrative_text: str = ""
    diagram_image_ref: str | None = None
    privileged_statements: list[dict[str, str]] = Field(
        default_factory=list,
        description="[{party_id, quoted_text}] — §316.066(4) privilege flagged",
    )


class ConsistencyChecks(BaseModel):
    er_mechanism_vs_claimant_statement: ConsistencyResult = "consistent"
    damage_pattern_vs_claimed_mechanism: ConsistencyResult = "consistent"
    police_poi_vs_claimant_statement: ConsistencyResult = "consistent"
    details: list[dict[str, str]] = Field(
        default_factory=list,
        description="[{check, finding, evidence_cite}]",
    )


class DemandState(BaseModel):
    demand_present: bool
    demand_amount: Decimal | None = None
    demand_deadline: date | None = None
    sufficient_evidence_assessment: Literal["sufficient", "insufficient", "borderline"] = "insufficient"
    sufficient_evidence_reasoning: str = ""
    safe_harbor_clock_start_date: date | None = None


class RorCrnState(BaseModel):
    """§627.426(2) cooperation defense windows + §624.155(3) CRN cure."""

    ror_sent_date: date | None = None
    ror_method: Literal["certified", "registered", "hand_delivery", "none"] = "none"
    non_waiver_or_independent_counsel_date: date | None = None
    crn_filed_date: date | None = None
    crn_alleged_violations: list[str] = Field(default_factory=list)
    cure_deadline: date | None = None


class PostureSnapshot(BaseModel):
    """Prior apportionment posture at a point in time."""

    eval_date: date
    posture_by_party_id: dict[str, Decimal] = Field(
        description="party_id → fault_pct as Decimal in [0, 100]",
    )
    basis_summary: str


class EvidenceItem(BaseModel):
    """One evidence datum the calculator weights into the apportionment.

    Every percentage point in the final apportionment walks from a published
    anchor through these items to the final number — see DiligenceLedger.
    """

    kind: EvidenceKind
    source_doc_id: str
    quoted_span: str = Field(
        description="Verbatim from source — Ruiz discoverability",
    )
    contemporaneity_hours_from_loss: int | None = None
    fl_admissibility: FLAdmissibility
    represented_by_counsel_at_capture: bool | None = None
    fault_direction: FaultDirection
    weight_class: EvidenceWeightClass


class LiabilityInputs(BaseModel):
    """Structured facts the LLM extractor pulls from claim documents.

    Each field anchors to source documents for per-field anchor-pair eval.
    See docs/specs/liability-workflow.md §LiabilityInputs schema.
    """

    # HB 837 regime gating
    accrual_date: date
    line_of_business: LineOfBusiness

    # Parties — N from day one
    parties: list[Party] = Field(min_length=1)

    # Fact-pattern classification (drives anchor selection)
    fact_pattern: FactPattern

    # FL-specific facts
    owner_relationship: OwnerRelationship
    negligent_entrustment_indicators: NegligentEntrustment = Field(
        default_factory=NegligentEntrustment,
    )
    intoxication_evidence: IntoxicationEvidence = Field(
        default_factory=IntoxicationEvidence,
    )
    rear_end_rebuttal_evidence: RearEndRebuttal = Field(
        default_factory=RearEndRebuttal,
    )

    # Evidence items (the load-bearing field)
    evidence_items: list[EvidenceItem] = Field(default_factory=list)

    # Police report structured fields (FL HSMV 90010S)
    police_report_structured_fields: PoliceReportFields | None = None

    # Consistency checks
    consistency_checks: ConsistencyChecks = Field(default_factory=ConsistencyChecks)

    # Demand state (for §624.155(4) sufficient-evidence assessment)
    demand_received: DemandState | None = None

    # ROR + CRN state (§627.426(2) windows; §624.155(3) cure)
    ror_and_crn_state: RorCrnState | None = None

    # Prior posture history (for delta detection)
    prior_posture_history: list[PostureSnapshot] = Field(default_factory=list)


# =============================================================================
# Policy engine output (intermediate)
# =============================================================================


class ApplicableRegime(BaseModel):
    """Which apportionment regime applies + bar status."""

    statute: ApplicableRegimeStatute
    recovery_bar_triggered: bool
    bar_basis: RecoveryBarBasis
    date_of_loss_governing: date
    explanation: str


class ExposureCeiling(BaseModel):
    """Vicarious caps + negligent-entrustment path."""

    vicarious_cap_applies: bool
    vicarious_cap_value: Decimal | None = None
    conditional_econ_layer: Decimal | None = None
    negligent_entrustment_uncapped_path_available: bool
    graves_lessor_removed: bool
    fabre_defendants: list[str] = Field(default_factory=list)


class DoctrineResolution(BaseModel):
    """Policy engine output — feeds the apportionment calculator."""

    applicable_regime: ApplicableRegime
    exposure_ceiling: ExposureCeiling
    doctrines_applied: list[str] = Field(
        default_factory=list,
        description="Named doctrine ids that fired (e.g. 'hb_837_51_bar', 'graves_preemption')",
    )


# =============================================================================
# Calculator + ledger nested outputs
# =============================================================================


class ApportionmentEntry(BaseModel):
    """Per-party apportionment with band + confidence."""

    fault_pct: Decimal = Field(ge=0, le=100)
    fault_pct_band_low: Decimal = Field(ge=0, le=100)
    fault_pct_band_high: Decimal = Field(ge=0, le=100)
    confidence: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def band_ordered(self) -> ApportionmentEntry:
        if not (self.fault_pct_band_low <= self.fault_pct <= self.fault_pct_band_high):
            raise ValueError(
                f"Band must be ordered low ≤ pct ≤ high; "
                f"got [{self.fault_pct_band_low}, {self.fault_pct}, {self.fault_pct_band_high}]"
            )
        return self


class EvidenceAdjustment(BaseModel):
    evidence_item_idx: int = Field(
        description="Index into LiabilityInputs.evidence_items",
    )
    direction: FaultDirection
    magnitude_points: Decimal
    basis: str


class DoctrineGateApplied(BaseModel):
    doctrine_id: str
    effect: str
    statute_or_case_cite: str


class FactPatternAnchor(BaseModel):
    pattern: FactPattern
    anchor_pct: Decimal
    anchor_party_role: PartyRole | Literal[
        "rear_driver", "turning_driver", "lane_changing_driver",
        "pulling_out_driver", "striking_driver", "violator",
    ]
    controlling_authority: str


class LiabilityRationale(BaseModel):
    """Anchor → evidence walk → doctrine gates → net apportionment walk."""

    fact_pattern_anchor: FactPatternAnchor
    evidence_adjustments: list[EvidenceAdjustment] = Field(default_factory=list)
    doctrine_gates_applied: list[DoctrineGateApplied] = Field(default_factory=list)
    net_apportionment_walk: str


class BasisEvidenceEntry(BaseModel):
    source_doc_id: str
    quoted_span: str
    weight_class: EvidenceWeightClass


class OpenRequest(BaseModel):
    request_type: str
    requested_date: date
    age_days: int
    target_party: str


class EvidenceNotObtained(BaseModel):
    """Positive record of declined-or-blocked evidence collection.

    Harvey defense: silent absence reads as cover-up; declined-with-reason
    reads as documented judgment.
    """

    evidence_kind: EvidenceKind
    reason_declined: str
    date_decision: date


class SupervisorDisagreement(BaseModel):
    date_recorded: date
    dissent_pct_by_party: dict[str, Decimal]
    dissent_basis: str


class PriorPostureDelta(BaseModel):
    prior_pct_by_party: dict[str, Decimal]
    prior_date: date
    what_changed_evidence_idx: int | None = Field(
        default=None,
        description="Index into evidence_items that justified the delta",
    )


class DiligenceLedger(BaseModel):
    """The Allstate v. Ruiz discoverable + Harvey procedural-diligence defense.

    Co-equal artifact with apportionment, not a side effect.
    """

    posture_percent_by_party: dict[str, Decimal]
    basis_evidence: list[BasisEvidenceEntry] = Field(default_factory=list)
    change_conditions: list[str] = Field(default_factory=list)
    next_review_date: date
    next_review_trigger: str
    prior_posture_delta: PriorPostureDelta | None = None
    open_requests: list[OpenRequest] = Field(default_factory=list)
    evidence_not_obtained: list[EvidenceNotObtained] = Field(default_factory=list)
    supervisor_disagreement_record: list[SupervisorDisagreement] = Field(
        default_factory=list,
    )


class EvidencePackClassification(BaseModel):
    """Per-datum §316.066(4) admissibility classification — defense-counsel trial pack."""

    reserve_only_evidence_idx: list[int] = Field(default_factory=list)
    trial_admissible_evidence_idx: list[int] = Field(default_factory=list)
    privileged_316_066_excluded_idx: list[int] = Field(default_factory=list)
    physical_evidence_carveout_admissible_idx: list[int] = Field(default_factory=list)
    chemical_test_carveout_admissible_idx: list[int] = Field(default_factory=list)


class AuthorityRouting(BaseModel):
    committable_at_examiner: bool
    required_tier: AuthorityTier
    gross_exposure: Decimal
    net_apportioned_exposure: Decimal
    basis_for_tier: str


class SubroReferral(BaseModel):
    recommended: bool
    recoverable_third_party_id: str | None = None
    basis_apportionment_used: dict[str, Decimal] = Field(default_factory=dict)
    supporting_evidence_idxs: list[int] = Field(default_factory=list)


# =============================================================================
# Top-level output
# =============================================================================


class LiabilityAssessment(BaseModel):
    """Final Liability workflow output.

    Composed of: per-party apportionment, doctrine resolution, evidence-anchored
    rationale, the diligence ledger (Ruiz discoverable), variance flags,
    authority routing, evidence pack classification. Never auto-commits — the
    adjuster commits based on this surface.
    """

    request_id: str
    reviewed_as_of: datetime

    # The number Reserve actually consumes
    apportionment: dict[str, ApportionmentEntry] = Field(
        description="party_id → apportionment entry; pie sums to 100",
    )

    # Doctrine resolution
    applicable_regime: ApplicableRegime
    exposure_ceiling: ExposureCeiling

    # The audit trail (co-equal with apportionment)
    rationale: LiabilityRationale
    diligence_ledger: DiligenceLedger
    rationale_text: str = Field(
        default="",
        description=(
            "Templated audit-trail string from render_liability_rationale. "
            "Byte-reproducible from inputs + intermediates."
        ),
    )

    # Surfaces for downstream routing
    variance_flags: list[VarianceFlag] = Field(default_factory=list)
    authority_tier_required: AuthorityRouting
    evidence_pack_classification: EvidencePackClassification

    # Side handoffs
    subro_referral: SubroReferral | None = None

    @model_validator(mode="after")
    def apportionment_pie_sums_to_100(self) -> LiabilityAssessment:
        total = sum(e.fault_pct for e in self.apportionment.values())
        if not (Decimal("99") <= total <= Decimal("101")):
            raise ValueError(
                f"Apportionment pie must sum to 100 across all parties "
                f"(named + Fabre); got {total}"
            )
        return self


class ProgramConfig(BaseModel):
    """Per-CHA authority bands + evidence weight overrides.

    Loaded from program registry at runtime; constants.py ships DEFAULT_PROGRAM
    only for tests and the demo fixture.
    """

    program_id: str
    examiner_authority_dollars: Decimal
    senior_examiner_authority_dollars: Decimal
    supervisor_authority_dollars: Decimal
    manager_authority_dollars: Decimal
    roundtable_threshold_dollars: Decimal
    mandatory_referral_variance_flags: list[VarianceFlag] = Field(default_factory=list)
