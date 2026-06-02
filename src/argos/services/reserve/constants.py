"""Reserve calculator constants — versioned, FL auto BI seed defaults.

Source: docs/specs/reserve-workflow.md §Calculator constants, calibrated via
the 2026-06-01 multi-dimensional research workflow (66 findings across
methodology, severity distributions, adjuster mechanics, specialty-TPA
practice, authority bands, FL regulatory).

These are SEED DEFAULTS — every TPA customer overrides via ProgramConfig
loaded at runtime. Hardcoded values would be wrong for every customer.

Versioning: any change to multiplier bands or notice thresholds is a NEW
constant (e.g., MULTIPLIER_TABLE_V2) — never edit V1 in place. Old runs must
remain reproducible.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from argos.schemas.workflows.reserve import (
    CatastrophicIndicator,
    InjuryBucket,
    ProgramConfig,
    VenueCounty,
)


VERSION = "v1.2026-06-01"

# Tortfeasor-coverage cutover: FL HB 837 §768.81 modified comparative (51% bar)
# applies to causes of action accruing on or after this date.
HB_837_EFFECTIVE_DATE = date(2023, 3, 24)

COMPARATIVE_BAR_PCT = Decimal("50")  # claimant > 50% at fault recovers nothing
COMPARATIVE_VARIANCE_LOW = Decimal("40")
COMPARATIVE_VARIANCE_HIGH = Decimal("55")

# §624.155(4) post-HB-837 safe harbor (90 days)
SAFE_HARBOR_DAYS = 90
# §624.155(3) CRN cure window (60 days)
CRN_CURE_DAYS = 60


# =============================================================================
# Severity tiers (FL auto BI, post-HB 837)
# =============================================================================


@dataclass(frozen=True)
class SeverityTier:
    name: InjuryBucket
    multiplier_low: Decimal   # generals = specials × multiplier_low (p10)
    multiplier_central: Decimal  # p50
    multiplier_high: Decimal  # p90
    specials_range_low: Decimal
    specials_range_high: Decimal
    typical_indemnity_low: Decimal
    typical_indemnity_high: Decimal
    criteria_summary: str


MULTIPLIER_TABLE_V1: dict[InjuryBucket, SeverityTier] = {
    "minor_soft_tissue": SeverityTier(
        name="minor_soft_tissue",
        multiplier_low=Decimal("1.0"),
        multiplier_central=Decimal("1.4"),
        multiplier_high=Decimal("1.8"),
        specials_range_low=Decimal("2500"),
        specials_range_high=Decimal("15000"),
        typical_indemnity_low=Decimal("5000"),
        typical_indemnity_high=Decimal("25000"),
        criteria_summary=(
            "Strain/sprain/whiplash, conservative care only, no MRI findings, "
            "no permanency opinion, full clinical resolution"
        ),
    ),
    "moderate_ortho_non_surgical": SeverityTier(
        name="moderate_ortho_non_surgical",
        multiplier_low=Decimal("1.5"),
        multiplier_central=Decimal("2.0"),
        multiplier_high=Decimal("2.5"),
        specials_range_low=Decimal("10000"),
        specials_range_high=Decimal("40000"),
        typical_indemnity_low=Decimal("25000"),
        typical_indemnity_high=Decimal("110000"),
        criteria_summary=(
            "Confirmed disc bulge/herniation, fracture without surgery, "
            "sustained PT >12 weeks, possible permanency at MMI"
        ),
    ),
    "surgical_recovering": SeverityTier(
        name="surgical_recovering",
        multiplier_low=Decimal("2.0"),
        multiplier_central=Decimal("2.75"),
        multiplier_high=Decimal("3.5"),
        specials_range_low=Decimal("40000"),
        specials_range_high=Decimal("200000"),
        typical_indemnity_low=Decimal("100000"),
        typical_indemnity_high=Decimal("500000"),
        criteria_summary=(
            "Surgical fixation, fusion, ORIF; documented permanency rating; "
            "MMI achieved"
        ),
    ),
    "severe_permanent": SeverityTier(
        name="severe_permanent",
        multiplier_low=Decimal("3.0"),
        multiplier_central=Decimal("4.0"),
        multiplier_high=Decimal("5.0"),
        specials_range_low=Decimal("100000"),
        specials_range_high=Decimal("500000"),
        typical_indemnity_low=Decimal("400000"),
        typical_indemnity_high=Decimal("2000000"),
        criteria_summary=(
            "Permanent significant impairment, multi-level fusion, RSD/CRPS, "
            "significant scarring/disfigurement"
        ),
    ),
    "catastrophic": SeverityTier(
        name="catastrophic",
        # Catastrophic routes to life-care-plan estimator — multipliers are
        # not used. Stored as zero to signal "do not multiply specials"; the
        # calculator branches on injury_bucket to use a different path.
        multiplier_low=Decimal("0"),
        multiplier_central=Decimal("0"),
        multiplier_high=Decimal("0"),
        specials_range_low=Decimal("0"),
        specials_range_high=Decimal("0"),
        typical_indemnity_low=Decimal("800000"),
        typical_indemnity_high=Decimal("15000000"),
        criteria_summary=(
            "Fatality, TBI moderate-severe, SCI, amputation, severe burns "
            ">20% BSA, permanent total disability — routed to life-care-plan "
            "estimator, not multiplier method"
        ),
    ),
}


# Catastrophic-tier reserve anchors (NSCISC + named-source-derived, see spec
# §Calculator constants). Reserve posted at policy limits with overlay flag
# when catastrophic indicators present; band reflects realistic lifetime cost.
CATASTROPHIC_BANDS_V1: dict[CatastrophicIndicator, tuple[Decimal, Decimal, Decimal]] = {
    # (p10, p50, p90) lifetime nominal — used only when limits exceed band
    "fatality": (Decimal("250000"), Decimal("1200000"), Decimal("5000000")),
    "tbi": (Decimal("800000"), Decimal("3000000"), Decimal("10000000")),
    "sci": (Decimal("1800000"), Decimal("3500000"), Decimal("5400000")),
    "amputation": (Decimal("500000"), Decimal("1500000"), Decimal("4000000")),
    "severe_burn": (Decimal("400000"), Decimal("1200000"), Decimal("5000000")),
    "multiple_fracture": (Decimal("200000"), Decimal("600000"), Decimal("2000000")),
    "permanent_total_disability": (
        Decimal("600000"), Decimal("2000000"), Decimal("6000000"),
    ),
}


# =============================================================================
# Venue calibrator (FL counties)
# =============================================================================
#
# Public sources support directional ranking only; no auditable multiplier
# exists publicly. These are seed defaults — derive from carrier
# loss-development data per venue before production.

VENUE_GENERALS_MULTIPLIER_V1: dict[VenueCounty, Decimal] = {
    "miami_dade": Decimal("1.20"),
    "broward": Decimal("1.15"),
    "palm_beach": Decimal("1.10"),
    "hillsborough": Decimal("1.00"),
    "orange": Decimal("1.00"),
    "duval": Decimal("0.90"),
    "other_fl": Decimal("0.95"),
    "other_state": Decimal("1.00"),
}


# =============================================================================
# ALAE — defense phase budgets (per-phase, FL auto BI defense)
# =============================================================================
#
# Practitioner estimates, NOT a citable industry standard. Must be tuned per
# program from actual TPA billing data. Pre-suit files have $0 phase budget.


@dataclass(frozen=True)
class PhaseBudget:
    phase: str
    low: Decimal
    central: Decimal
    high: Decimal


DEFENSE_PHASE_BUDGETS_V1: dict[str, PhaseBudget] = {
    "pre_suit": PhaseBudget("pre_suit", Decimal("0"), Decimal("0"), Decimal("0")),
    "answer": PhaseBudget("answer", Decimal("1500"), Decimal("2500"), Decimal("4000")),
    "written_discovery": PhaseBudget(
        "written_discovery", Decimal("3000"), Decimal("5000"), Decimal("8000"),
    ),
    "depositions": PhaseBudget(
        "depositions", Decimal("5000"), Decimal("9000"), Decimal("15000"),
    ),
    "dispositive_motions": PhaseBudget(
        "dispositive_motions", Decimal("4000"), Decimal("6500"), Decimal("10000"),
    ),
    "mediation": PhaseBudget(
        "mediation", Decimal("2000"), Decimal("3500"), Decimal("5000"),
    ),
    "trial_prep": PhaseBudget(
        "trial_prep", Decimal("20000"), Decimal("38000"), Decimal("60000"),
    ),
    "trial": PhaseBudget(
        "trial", Decimal("30000"), Decimal("55000"), Decimal("100000"),
    ),
    "post_judgment": PhaseBudget(
        "post_judgment", Decimal("3000"), Decimal("8000"), Decimal("20000"),
    ),
}


# Cumulative ALAE budget = sum of all phases up to and including current phase.
DEFENSE_PHASE_ORDER = [
    "pre_suit", "answer", "written_discovery", "depositions",
    "dispositive_motions", "mediation", "trial_prep", "trial", "post_judgment",
]


# =============================================================================
# Notice thresholds + bad-faith risk markers
# =============================================================================


@dataclass(frozen=True)
class NoticeThreshold:
    name: str
    dollar_trigger: Decimal | None
    categorical_triggers: tuple[CatastrophicIndicator, ...]
    notice_days: int


NOTICE_THRESHOLDS_V1: dict[str, NoticeThreshold] = {
    "reinsurance": NoticeThreshold(
        name="reinsurance",
        dollar_trigger=Decimal("250000"),  # IRMI common-example anchor
        categorical_triggers=(
            "fatality", "tbi", "sci", "amputation", "severe_burn",
            "multiple_fracture", "permanent_total_disability",
        ),
        notice_days=30,
    ),
    "excess_carrier": NoticeThreshold(
        name="excess_carrier",
        # Excess notice typically at 50-75% of attachment; we use limit-proximity
        # check separately in the calculator, so dollar_trigger is None here.
        dollar_trigger=None,
        categorical_triggers=(),
        notice_days=15,
    ),
    "large_loss_committee": NoticeThreshold(
        name="large_loss_committee",
        dollar_trigger=Decimal("250000"),
        categorical_triggers=(
            "fatality", "tbi", "sci", "amputation",
        ),
        notice_days=7,
    ),
}


# Excess-carrier notice fires when reserve crosses this fraction of per-person
# limits with clear liability.
EXCESS_NOTICE_LIMIT_PCT = Decimal("0.50")

# Bad-faith risk overlay activates when:
# - reserve > BAD_FAITH_LIMIT_PROXIMITY_PCT of per-person limits AND clear liability
# - OR §624.155(4) clock expired without tender + sufficient-evidence demand
# - OR ≥ BAD_FAITH_MARKER_THRESHOLD markers active per the FL trilogy
BAD_FAITH_LIMIT_PROXIMITY_PCT = Decimal("0.70")
BAD_FAITH_MARKER_THRESHOLD = 3


# =============================================================================
# Default program config (test/demo only — real customers override)
# =============================================================================


DEFAULT_PROGRAM = ProgramConfig(
    program_id="default-demo",
    examiner_reserve_authority=Decimal("25000"),
    supervisor_reserve_authority=Decimal("75000"),
    manager_reserve_authority=Decimal("250000"),
    carrier_escalation_threshold=Decimal("250000"),
    reinsurance_notice_threshold=Decimal("250000"),
    settlement_authority=Decimal("50000"),
    mandatory_referral_categories=[
        "fatality", "tbi", "sci", "amputation", "permanent_total_disability",
    ],
    reporting_cadence_days=90,
)


# =============================================================================
# Stair-step detector
# =============================================================================
#
# Per IRMI: "the ultimate cost is the amount that should be shown on the
# reserves at all times." Stair-step pattern = 3+ small upward revisions
# within 90 days without new evidence. Defensibility risk per CLM.

STAIR_STEP_WINDOW_DAYS = 90
STAIR_STEP_MIN_REVISIONS = 3
# A "small" revision = <20% of prior reserve. Three small upward revisions
# without new-fact basis = flag for supervisor review.
STAIR_STEP_SMALL_REVISION_PCT = Decimal("0.20")
