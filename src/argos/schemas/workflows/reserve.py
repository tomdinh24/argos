"""Reserve workflow schemas.

The workflow is split into two stages (see docs/specs/reserve-workflow.md):

  1. Extractor (LLM, Software 3.0) reads documents + coverage_posture and emits
     ReserveInputs — bounded, gradable, model-swappable.
  2. Calculator (Python, Software 1.0) is a pure function:
     (ReserveInputs, ClaimContext, ProgramConfig) -> ReserveAnalysis.
     All math lives in versioned constants; output is byte-reproducible.

Rationale strings are templated by render_reserve_rationale; never LLM-generated.

ReserveAnalysis preserves the band (p10/p50/p90) per component shape from the
original spec — the adjuster picks the point.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from argos.schemas.contract import EvidenceCitation


# =============================================================================
# Output shape (Calculator output / ReserveAnalysis — unchanged contract)
# =============================================================================


ReserveComponent = Literal[
    "indemnity", "ALAE", "ULAE", "ALE", "expert_fees", "defense", "mitigation"
]

NoticeType = Literal[
    "excess_carrier", "reinsurer", "client", "DOI", "Medicare_Section_111"
]

AuthorityLevel = Literal["handler", "supervisor", "manager", "client"]


class ReserveBand(BaseModel):
    p10: float = Field(ge=0)
    p50: float = Field(ge=0)
    p90: float = Field(ge=0)

    @model_validator(mode="after")
    def ordered(self) -> ReserveBand:
        if not (self.p10 <= self.p50 <= self.p90):
            raise ValueError(f"Band must be ordered p10 ≤ p50 ≤ p90; got {self}")
        return self


class TriggerFired(BaseModel):
    """A material event from SpecialistConfig that fired on this exposure."""

    trigger_id: str = Field(
        description="Reference to material_event_definitions in SpecialistConfig"
    )
    evidence_citations: list[EvidenceCitation] = Field(min_length=1)


class ReserveComponentAnalysis(BaseModel):
    component: ReserveComponent
    current_outstanding: float = Field(ge=0)
    recommended_outstanding_band: ReserveBand
    rationale: str
    triggers_fired: list[TriggerFired] = Field(default_factory=list)
    evidence_citations: list[EvidenceCitation] = Field(
        min_length=1,
        description="Supports the band itself, distinct from triggers",
    )


class NoticeObligationTriggered(BaseModel):
    notice_type: NoticeType
    probability: float = Field(ge=0.0, le=1.0)
    reasoning: str
    required_by_date: datetime
    evidence_citations: list[EvidenceCitation] = Field(min_length=1)


class ReserveAnalysis(BaseModel):
    request_id: str
    reviewed_as_of: datetime

    per_component: list[ReserveComponentAnalysis] = Field(min_length=1)
    notice_obligations_triggered: list[NoticeObligationTriggered] = Field(
        default_factory=list
    )

    authority_required_level: AuthorityLevel
    no_change_warranted: bool = False
    rationale: str = Field(
        default="",
        description=(
            "Templated audit-trail string from render_reserve_rationale. "
            "Byte-reproducible from ReserveInputs + calculator intermediates."
        ),
    )


# =============================================================================
# Input shape (Extractor output / Calculator input — new in this refactor)
# =============================================================================

InjuryBucket = Literal[
    "minor_soft_tissue",
    "moderate_ortho_non_surgical",
    "surgical_recovering",
    "severe_permanent",
    "catastrophic",
]

CatastrophicIndicator = Literal[
    "fatality", "tbi", "sci", "amputation",
    "severe_burn", "multiple_fracture", "permanent_total_disability",
]

VenueCounty = Literal[
    "miami_dade", "broward", "palm_beach",
    "hillsborough", "orange", "duval",
    "other_fl", "other_state",
]

LitigationPhase = Literal[
    "pre_suit", "answer", "written_discovery", "depositions",
    "dispositive_motions", "mediation", "trial_prep", "trial", "post_judgment",
]

MedicalPayer = Literal[
    "health_ins", "medicare", "medicaid", "pip", "lop", "self_pay", "unknown"
]


class PolicyLimits(BaseModel):
    per_person: Decimal
    per_occurrence: Decimal
    property: Decimal


class PipStatus(BaseModel):
    """FL §627.736 mechanics."""

    cap_applicable: Literal[2500, 10000]
    paid_to_date: Decimal
    exhausted: bool
    emc_determination: bool | None = None
    treatment_within_14_days: bool


class PermanencyStatus(BaseModel):
    """FL §627.737 verbal threshold gating."""

    opinion_present: bool
    rating_pct: Decimal | None = None
    mmi_date: date | None = None
    scarring_disfigurement: bool = False
    fatality: bool = False


class MedicalBill(BaseModel):
    """Single medical specials line. Paid-vs-billed handling post-§768.0427."""

    billed: Decimal
    paid: Decimal
    payer: MedicalPayer
    provider: str
    lop_flag: bool
    date_of_service: date


class WageLoss(BaseModel):
    documented_to_date: Decimal
    claimed_future: Decimal | None = None
    occupation: str
    employer_verified: bool


class RepStatus(BaseModel):
    represented: bool
    firm_name: str | None = None
    rep_date: date | None = None
    demand_received: bool = False
    demand_date: date | None = None
    demand_amount: Decimal | None = None
    policy_limits_demand: bool = False
    time_demand_deadline: date | None = None


class LitStatus(BaseModel):
    phase: LitigationPhase
    suit_served_date: date | None = None
    defense_counsel_assigned: str | None = None


class CrnStatus(BaseModel):
    """§624.155(3) Civil Remedy Notice. 60-day cure window starts at DFS filing."""

    filed_date: date
    alleged_violation: str
    demanded_amount: Decimal
    cure_deadline: date


class ReserveSnapshot(BaseModel):
    """Prior reserve at a point in time — used by stair-step detector."""

    eval_date: date
    indemnity: Decimal
    alae: Decimal
    basis: str


class ProgramConfig(BaseModel):
    """Per-CHA authority bands, phase budgets, escalation thresholds.

    Loaded from program registry at runtime — NOT hardcoded. Each TPA
    customer's CHA overrides defaults. The calculator reads these to decide
    authority routing and notice triggers; constants.py ships DEFAULT_PROGRAM
    only for tests and the demo fixture.
    """

    program_id: str
    examiner_reserve_authority: Decimal
    supervisor_reserve_authority: Decimal
    manager_reserve_authority: Decimal
    carrier_escalation_threshold: Decimal
    reinsurance_notice_threshold: Decimal
    settlement_authority: Decimal
    mandatory_referral_categories: list[str] = Field(default_factory=list)
    reporting_cadence_days: int = 90


class ReserveInputs(BaseModel):
    """Structured facts the LLM extractor pulls from claim documents.

    Source of truth: docs/specs/reserve-workflow.md (§ReserveInputs schema).
    Each field is anchored to source documents so per-field anchor-pair eval
    can grade extraction independently.
    """

    # Temporal anchors (HB 837 branching)
    accrual_date: date
    filing_date: date | None = None
    fnol_date: date
    actual_notice_date: date | None = None

    # Venue / coverage context
    venue_county: VenueCounty
    policy_limits: PolicyLimits
    uim_um_coverage: Decimal | None = None
    self_insured_retention: Decimal | None = None

    # Liability
    claimant_count: int = Field(ge=1)
    insured_liability_pct: Decimal = Field(ge=0, le=100)
    tortfeasor_pip_compliant: bool = True

    # PIP / threshold
    pip_status: PipStatus
    permanency_status: PermanencyStatus

    # Specials
    medical_specials: list[MedicalBill] = Field(default_factory=list)
    wage_loss: WageLoss | None = None

    # Severity
    injury_bucket: InjuryBucket
    catastrophic_indicators: list[CatastrophicIndicator] = Field(default_factory=list)

    # Representation / litigation
    representation_status: RepStatus
    litigation_status: LitStatus
    crn_status: CrnStatus | None = None

    # Stair-step detector input
    prior_reserve_history: list[ReserveSnapshot] = Field(default_factory=list)

    @model_validator(mode="after")
    def catastrophic_consistency(self) -> ReserveInputs:
        if self.injury_bucket == "catastrophic" and not self.catastrophic_indicators:
            raise ValueError(
                "injury_bucket='catastrophic' requires at least one "
                "catastrophic_indicators entry"
            )
        return self
