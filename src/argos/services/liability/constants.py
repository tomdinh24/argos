"""Versioned constants for the Liability workflow.

v1 seeds calibrated against the 2026-06-01 multi-dimensional research workflow.
All numeric values here are ProgramConfig-overridable per CHA — defaults ship
for the demo + unit tests only. Real TPA onboarding tunes against settled-claim
outcomes.

VERSION strings are emitted into the templated rationale, so changes here are
visible in the audit trail and roll forward as new constant generations.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import NamedTuple

from argos.schemas.workflows.liability import (
    AuthorityTier,
    EvidenceWeightClass,
    FactPattern,
    ProgramConfig,
    VarianceFlag,
)


VERSION = "v1.2026-06-01"


# =============================================================================
# Fact-pattern anchors (per LiabilityInputs.fact_pattern)
# =============================================================================


class FactPatternAnchorSeed(NamedTuple):
    anchor_pct: Decimal
    anchor_party_role: str
    controlling_authority: str
    notes: str


FACT_PATTERN_ANCHORS_V1: dict[FactPattern, FactPatternAnchorSeed] = {
    "rear_end": FactPatternAnchorSeed(
        anchor_pct=Decimal("95"),
        anchor_party_role="rear_driver",
        controlling_authority=(
            "Birge v. Charron, 107 So. 3d 350 (Fla. 2012); "
            "Pierce v. Progressive Am. Ins. Co.; Eppler v. Tarmac"
        ),
        notes="Rebuttable presumption — four named rebuttal categories in Birge.",
    ),
    "left_turn_across_traffic": FactPatternAnchorSeed(
        anchor_pct=Decimal("90"),
        anchor_party_role="turning_driver",
        controlling_authority="FL Std. Jury Instr. 401; §316.122",
        notes="Turning driver duty to yield to oncoming traffic.",
    ),
    "uncontrolled_intersection": FactPatternAnchorSeed(
        anchor_pct=Decimal("50"),
        anchor_party_role="insured_driver",
        controlling_authority="§316.121 (right-of-way)",
        notes="50/50 baseline; evidence shifts ±20.",
    ),
    "controlled_intersection": FactPatternAnchorSeed(
        anchor_pct=Decimal("85"),
        anchor_party_role="violator",
        controlling_authority="§316.075 / §316.123",
        notes="Light/sign violator carries anchor; citation strongly corroborates.",
    ),
    "lane_change": FactPatternAnchorSeed(
        anchor_pct=Decimal("80"),
        anchor_party_role="lane_changing_driver",
        controlling_authority="§316.085",
        notes="Lane-changing driver bears duty to ensure safe movement.",
    ),
    "parked_pullout": FactPatternAnchorSeed(
        anchor_pct=Decimal("80"),
        anchor_party_role="pulling_out_driver",
        controlling_authority="§316.195",
        notes="Driver entering roadway from parked position bears duty.",
    ),
    "sideswipe": FactPatternAnchorSeed(
        anchor_pct=Decimal("60"),
        anchor_party_role="lane_changing_driver",
        controlling_authority="§316.089",
        notes="Departing-driver-presumed; evidence can split close.",
    ),
    "pedestrian_in_crosswalk": FactPatternAnchorSeed(
        anchor_pct=Decimal("80"),
        anchor_party_role="striking_driver",
        controlling_authority="§316.130",
        notes="Driver duty heightened in crosswalk.",
    ),
    "pedestrian_mid_block": FactPatternAnchorSeed(
        anchor_pct=Decimal("60"),
        anchor_party_role="claimant_pedestrian",
        controlling_authority="§316.130(10)",
        notes="Pedestrian outside crosswalk bears greater share.",
    ),
    "chain_reaction": FactPatternAnchorSeed(
        anchor_pct=Decimal("50"),
        anchor_party_role="insured_driver",
        controlling_authority="Fabre v. Marin, 623 So. 2d 1182 (Fla. 1993)",
        notes="Per-event single pie; matrix view required.",
    ),
    "parking_lot": FactPatternAnchorSeed(
        anchor_pct=Decimal("50"),
        anchor_party_role="insured_driver",
        controlling_authority="case-by-case — no controlling anchor",
        notes="Forces human review; calculator emits low confidence.",
    ),
    "cyclist": FactPatternAnchorSeed(
        anchor_pct=Decimal("70"),
        anchor_party_role="striking_driver",
        controlling_authority="§316.2065",
        notes="Driver bears heightened duty; cyclist comparative-fault factors apply.",
    ),
    "other": FactPatternAnchorSeed(
        anchor_pct=Decimal("50"),
        anchor_party_role="insured_driver",
        controlling_authority="no anchor — escalate to human review",
        notes="Routes to roundtable; calculator emits low confidence.",
    ),
}


# =============================================================================
# Evidence weights (per EvidenceItem.weight_class)
# =============================================================================


class EvidenceWeightSeed(NamedTuple):
    min_points: Decimal
    max_points: Decimal


EVIDENCE_WEIGHTS_V1: dict[EvidenceWeightClass, EvidenceWeightSeed] = {
    "hard_data": EvidenceWeightSeed(Decimal("20"), Decimal("25")),
    "independent": EvidenceWeightSeed(Decimal("10"), Decimal("15")),
    "party_admission": EvidenceWeightSeed(Decimal("15"), Decimal("15")),
    "rebuttable_signal": EvidenceWeightSeed(Decimal("5"), Decimal("10")),
    "credibility_only": EvidenceWeightSeed(Decimal("0"), Decimal("5")),
}


# =============================================================================
# Doctrine registry
# =============================================================================


class DoctrineSeed(NamedTuple):
    doctrine_id: str
    statute_or_case_cite: str
    description: str


FL_DOCTRINE_REGISTRY_V1: dict[str, DoctrineSeed] = {
    "hb_837_51_bar": DoctrineSeed(
        "hb_837_51_bar",
        "§768.81(6); HB 837 (eff. 2023-03-24)",
        "Modified-comparative 51% bar for non-medical-negligence accruing after 2023-03-24.",
    ),
    "pure_comparative_pre_hb837": DoctrineSeed(
        "pure_comparative_pre_hb837",
        "§768.81 (pre-amendment)",
        "Pure comparative for accruals before 2023-03-24.",
    ),
    "med_mal_pure_comparative": DoctrineSeed(
        "med_mal_pure_comparative",
        "§768.81 carve-out",
        "Medical-malpractice line remains pure comparative.",
    ),
    "fabre_apportionment": DoctrineSeed(
        "fabre_apportionment",
        "Fabre v. Marin, 623 So. 2d 1182 (Fla. 1993); Nash v. Wells Fargo",
        "Non-party fault apportioned if factually supported AND pled per Rule 1.110(d).",
    ),
    "joint_several_abolished": DoctrineSeed(
        "joint_several_abolished",
        "§768.81(3)",
        "Joint-and-several liability abolished for negligence.",
    ),
    "dangerous_instrumentality": DoctrineSeed(
        "dangerous_instrumentality",
        "Aurbach v. Gallina; Hertz v. Jackson",
        "Vehicle owner vicariously liable; theft breaks chain.",
    ),
    "natural_person_owner_cap": DoctrineSeed(
        "natural_person_owner_cap",
        "§324.021(9)(b)3",
        "Vicarious exposure capped $100K/$300K BI + $50K PD + conditional $500K econ.",
    ),
    "negligent_entrustment_uncapped": DoctrineSeed(
        "negligent_entrustment_uncapped",
        "§324.021(9)(b)3 closing sentence",
        "Uncapped direct theory if owner had knowledge of risk.",
    ),
    "graves_preemption": DoctrineSeed(
        "graves_preemption",
        "49 USC §30106; Vargas v. Enterprise",
        "Commercial lessor removed; exception for negligent maintenance / rental.",
    ),
    "intoxication_bar_768_36": DoctrineSeed(
        "intoxication_bar_768_36",
        "§768.36",
        "Recovery bar: BAC≥0.08 OR impairment AND >50% fault-from-impairment causation.",
    ),
    "rear_end_rebuttable_presumption": DoctrineSeed(
        "rear_end_rebuttable_presumption",
        "Birge v. Charron; Pierce; Eppler; Douglas-Seibert",
        "Rear driver presumed at fault unless four named rebuttals evidenced.",
    ),
    "sudden_emergency_eliminated": DoctrineSeed(
        "sudden_emergency_eliminated",
        "Birge v. Charron",
        "Sudden Emergency doctrine eliminated; medical emergency / unconsciousness survives.",
    ),
    "last_clear_chance_abolished": DoctrineSeed(
        "last_clear_chance_abolished",
        "Hoffman v. Jones (1973)",
        "Last Clear Chance abolished.",
    ),
    "accident_report_privilege_316_066": DoctrineSeed(
        "accident_report_privilege_316_066",
        "§316.066(4); §316.1934 chemical-test carveout",
        "Per-datum classification: privileged statements vs physical-evidence carveout vs chemical-test carveout.",
    ),
    "good_faith_duty_harvey": DoctrineSeed(
        "good_faith_duty_harvey",
        "Boston Old Colony; Berges; Harvey v. GEICO; Allstate v. Ruiz",
        "Procedural-diligence trail discoverable; sets ledger requirements.",
    ),
    "powell_duty_to_initiate": DoctrineSeed(
        "powell_duty_to_initiate",
        "Powell v. Prudential",
        "Insurer duty to initiate settlement when liability clear + excess-judgment likely.",
    ),
}


# =============================================================================
# Statutory + step-function thresholds
# =============================================================================

HB_837_EFFECTIVE_DATE = date(2023, 3, 24)

NATURAL_PERSON_OWNER_CAP_PER_PERSON = Decimal("100000")
NATURAL_PERSON_OWNER_CAP_PER_OCCURRENCE = Decimal("300000")
NATURAL_PERSON_OWNER_CAP_PD = Decimal("50000")
NATURAL_PERSON_OWNER_CAP_ECONOMIC_CONDITIONAL = Decimal("500000")

INTOXICATION_BAC_THRESHOLD = Decimal("0.08")
INTOXICATION_FAULT_PCT_THRESHOLD = Decimal("50")  # >50% per §768.36

# Variance-zone thresholds
NEAR_BAR_WINDOW_PCT = Decimal("5")  # ±5 of 50% triggers near_50_pct_bar
APPORTIONMENT_DELTA_BAND_PCT = Decimal("15")
POWELL_HIGH_FAULT_PCT_THRESHOLD = Decimal("70")
EVIDENCE_GAP_FNOL_DAYS = 21


# =============================================================================
# Authority routing defaults
# =============================================================================


AUTHORITY_TIER_ORDER: tuple[AuthorityTier, ...] = (
    "examiner",
    "senior_examiner",
    "supervisor",
    "manager",
    "roundtable",
    "carrier_consent",
    "reinsurer_consultation",
)


# Variance flags that MUST escalate above examiner regardless of dollars.
# Programs can extend via ProgramConfig.mandatory_referral_variance_flags.
MANDATORY_ESCALATION_VARIANCE_FLAGS: tuple[VarianceFlag, ...] = (
    "near_50_pct_bar",
    "powell_duty_clarity",
    "safe_harbor_clock_decision_required",
    "intoxication_bar_candidate",
    "apportionment_delta_exceeds_examiner_band",
)


# =============================================================================
# Default ProgramConfig (demo / unit tests only)
# =============================================================================


DEFAULT_PROGRAM = ProgramConfig(
    program_id="default_demo_v1",
    examiner_authority_dollars=Decimal("50000"),
    senior_examiner_authority_dollars=Decimal("150000"),
    supervisor_authority_dollars=Decimal("500000"),
    manager_authority_dollars=Decimal("2000000"),
    roundtable_threshold_dollars=Decimal("1000000"),
    mandatory_referral_variance_flags=list(MANDATORY_ESCALATION_VARIANCE_FLAGS),
)
