"""Versioned constants for the Recovery workflow.

v1 seeds calibrated against the 2026-06-02 multi-dimensional research workflow.
All numeric values here are ProgramConfig-overridable per CHA — defaults ship
for the demo + unit tests only. Real TPA onboarding tunes against
settled-outcome corpora.

VERSION strings are emitted into the templated rationale, so changes here are
visible in the audit trail and roll forward as new constant generations.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import NamedTuple

from argos.schemas.workflows.recovery import (
    AuthorityTier,
    ProgramConfig,
    VarianceFlag,
)


VERSION = "v1.2026-06-02"


# =============================================================================
# Statute-version anchors
# =============================================================================


HB_837_EFFECTIVE_DATE = date(2023, 3, 24)

# §95.11(4)(a) post-HB-837 negligence SOL
SOL_NEGLIGENCE_YEARS_POST_HB837 = 2
# Pre-HB-837 §95.11(3)(a)
SOL_NEGLIGENCE_YEARS_PRE_HB837 = 4
# §95.11(2)(b) written contract (rental / fleet / loaner — narrow application)
SOL_CONTRACT_YEARS = 5
# §95.031(2)(b) products liability repose
SOL_PRODUCTS_REPOSE_YEARS = 12
# §95.11(3) property damage (unchanged by HB 837)
SOL_PD_YEARS = 4


# =============================================================================
# Hard external clocks
# =============================================================================


# §627.727(6) UM preservation window when tortfeasor's carrier tenders offer
UM_PRESERVATION_DAYS = 30
# §768.76(7) collateral-source reimbursement assertion window
COLLATERAL_SOURCE_NOTICE_DAYS = 30
# AF post-dismissal refile window
AF_POST_DISMISSAL_REFILE_DAYS = 60


# =============================================================================
# Cap layer values (§324.021(9)(b)3)
# =============================================================================


NATURAL_PERSON_OWNER_CAP_PER_PERSON = Decimal("100000")
NATURAL_PERSON_OWNER_CAP_PER_OCCURRENCE = Decimal("300000")
NATURAL_PERSON_OWNER_CAP_PD = Decimal("50000")
NATURAL_PERSON_OWNER_CAP_ECONOMIC_CONDITIONAL = Decimal("500000")


# =============================================================================
# §768.0427 paid-not-billed defaults
# =============================================================================


# 120% Medicare benchmark for uninsured-paid medicals
PAID_NOT_BILLED_UNINSURED_MEDICARE_MULTIPLIER = Decimal("1.20")


# =============================================================================
# Variance zone thresholds
# =============================================================================


NEAR_BAR_WINDOW_PCT = Decimal("5")  # [45%, 55%] window around §768.81(6)
SOL_ACCRUAL_FILING_SPLIT_WINDOW_DAYS = 30  # ±30 days of 2023-03-24
PRODUCTS_REPOSE_PROXIMITY_MONTHS = 24
PIP_CAP_DOLLARS = Decimal("10000")  # §627.737 economic-damage threshold


# =============================================================================
# AF compulsory jurisdiction
# =============================================================================


AF_COMPULSORY_CAP_DOLLARS = Decimal("100000")
AF_FILING_FLAT_FEE_DOLLARS = Decimal("42")


# =============================================================================
# AF signatory roster (seeded — refreshed per AF publication)
# =============================================================================


# NAIC code → signatory status. Seed values for demo + tests.
# Real production needs a roster refresh mechanism (open question, spec §Open).
AF_SIGNATORY_ROSTER_V1: dict[str, bool] = {
    # Major auto carriers known signatory at time of v1 seed
    "25178": True,   # State Farm Mutual Auto
    "25941": True,   # Allstate Fire & Casualty
    "10650": True,   # GEICO Indemnity
    "21253": True,   # Progressive American
    "12203": True,   # Liberty Mutual Fire
    "16608": True,   # USAA
    "23035": True,   # Farmers Insurance Exchange
    "19232": True,   # Travelers Indemnity
    # Specialty / non-standard auto carriers typical non-signatories
    "11185": False,  # National General (representative — verify per file)
}


# =============================================================================
# FL doctrine registry
# =============================================================================


class DoctrineSeed(NamedTuple):
    doctrine_id: str
    statute_or_case_cite: str
    effect: str


FL_RECOVERY_DOCTRINE_REGISTRY_V1: dict[str, DoctrineSeed] = {
    "hb837_modified_comparative_bar": DoctrineSeed(
        "hb837_modified_comparative_bar",
        "Fla. Stat. §768.81(6) as amended by HB 837 (eff. 3/24/2023)",
        "Hard cliff: claimant >50% fault on post-3/24/2023 auto BI → abstain regardless of damages.",
    ),
    "hb837_negligence_sol": DoctrineSeed(
        "hb837_negligence_sol",
        "Fla. Stat. §95.11(4)(a) as amended by HB 837",
        "Statute-version selector: 2yr post-3/24/2023; 4yr pre. PD remains 4yr. Clock runs from loss date.",
    ),
    "anti_subrogation_rule": DoctrineSeed(
        "anti_subrogation_rule",
        "FL common-law anti-subrogation rule; policy omnibus / permissive-user construction",
        "Blocking gate, per coverage section: if tortfeasor target overlaps named / omnibus / resident-relative roster under SAME coverage section as paid loss, abstain and route to Coverage.",
    ),
    "made_whole_doctrine": DoctrineSeed(
        "made_whole_doctrine",
        "Schonau v. GEICO Gen. Ins. Co., 903 So. 2d 285 (Fla. 4th DCA 2005)",
        "Conditional gate: limited-fund + insured not made whole + no contractual waiver → cannot subrogate OUT of insured's recovery. Freestanding direct claim against tortfeasor NOT blocked.",
    ),
    "pip_subrogability_627_7405": DoctrineSeed(
        "pip_subrogability_627_7405",
        "Fla. Stat. §627.7405; §627.732(3); Amerisure v. State Farm, 897 So. 2d 1287 (Fla. 2005)",
        "PIP subro barred EXCEPT against commercial-motor-vehicle owners (taxicabs excluded). Classification per §627.732(3) body-type + primary-use, NOT weight.",
    ),
    "um_preservation_627_727_6": DoctrineSeed(
        "um_preservation_627_727_6",
        "Fla. Stat. §627.727(6)",
        "Hard 30-day gate when tortfeasor liability carrier tenders settlement: UM carrier consents OR advances offer within 30 days. Miss = extinguished.",
    ),
    "collateral_source_768_76": DoctrineSeed(
        "collateral_source_768_76",
        "Fla. Stat. §768.76(7)",
        "Hard 30-day gate on claimant's notice of tort action: collateral-source provider asserts reimbursement right in writing or waives. Medicare / Medicaid / WC statutorily excluded from 'collateral source'.",
    ),
    "vicarious_cap_324_021": DoctrineSeed(
        "vicarious_cap_324_021",
        "Fla. Stat. §324.021(9)(b)3",
        "Cap: natural-person owner vicarious BI capped $100K/$300K + $50K PD; conditional $500K econ-only if operator <$500K combined. Cap does NOT apply to direct-negligence (negligent entrustment) — uncapped separate layer.",
    ),
    "joint_several_abolition_768_81_3": DoctrineSeed(
        "joint_several_abolition_768_81_3",
        "Fla. Stat. §768.81(3) (2006); Fabre v. Marin, 623 So. 2d 1182 (Fla. 1993)",
        "Apportionment: recovery from each defendant capped at that defendant's percentage of fault; non-party Fabre defendants on verdict form.",
    ),
    "verbal_threshold_627_737": DoctrineSeed(
        "verbal_threshold_627_737",
        "Fla. Stat. §627.737",
        "BI tort right for non-economic damages: permanency / scarring / significant function loss. Economic damages above $10K PIP recoverable without threshold. Threshold does NOT apply if tortfeasor lacks PIP-compliant coverage.",
    ),
    "paid_not_billed_768_0427": DoctrineSeed(
        "paid_not_billed_768_0427",
        "Fla. Stat. §768.0427 (HB 837)",
        "Damages-basis: past medicals capped at amounts actually paid (or LOP contracted, or 120% Medicare for uninsured). Strips billed-amount basis. Filing-date triggered.",
    ),
    "af_compulsory_jurisdiction": DoctrineSeed(
        "af_compulsory_jurisdiction",
        "AF Reference Guide; AF Rule 1-2; AF Article Second",
        "Routing: both carriers signatory AND company-paid damages ≤$100K → compulsory arbitration. Non-signatory or over-cap → litigation or Special Forum. 60-day post-dismissal refile window.",
    ),
    "spoliation_valcin_martino": DoctrineSeed(
        "spoliation_valcin_martino",
        "Public Health Trust v. Valcin, 507 So. 2d 596 (Fla. 1987); Martino v. Wal-Mart, 908 So. 2d 342 (Fla. 2005)",
        "Preservation duty: subrogating carrier owes Valcin duty on vehicle / EDR / parts / photos. First-party spoliation tort abolished (Martino) but Valcin presumption + sanctions apply.",
    ),
    "deny_subrogate_interlock": DoctrineSeed(
        "deny_subrogate_interlock",
        "Fla. Stat. §624.155 as amended by HB 837; Harvey v. GEICO, 259 So. 3d 1 (Fla. 2018)",
        "Cross-stream: Coverage denied + Recovery pursuing same loss → senior review with mandatory made-whole accounting + denial rationale. HB 837 §624.155(4) safe harbor covers third-party tender only — does NOT extend to Recovery conduct.",
    ),
    "step_into_shoes_defenses": DoctrineSeed(
        "step_into_shoes_defenses",
        "Dade County School Bd. v. Radio Station WQBA, 731 So. 2d 638 (Fla. 1999)",
        "Subrogated carrier acquires no greater rights than insured. Pre-tender release / settlement / extinguishing act by insured against tortfeasor (with knowledge of perfected subro) defeats recovery.",
    ),
}


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
    "large_loss_committee",
)

# Variance flags that MUST escalate above examiner regardless of dollars.
MANDATORY_ESCALATION_VARIANCE_FLAGS: tuple[VarianceFlag, ...] = (
    "comparative_fault_cliff_buffer",
    "deny_plus_subrogate",
    "release_or_pre_tender_settlement_detected",
    "made_whole_with_partial_settlement",
    "af_signatory_unverifiable",
    "non_fl_loss_routed_to_abstain",
)


# =============================================================================
# Default ProgramConfig (demo / unit tests)
# =============================================================================


DEFAULT_PROGRAM = ProgramConfig(
    program_id="default_demo_v1",
    examiner_authority_dollars=Decimal("25000"),
    senior_examiner_authority_dollars=Decimal("75000"),
    supervisor_authority_dollars=Decimal("250000"),
    manager_authority_dollars=Decimal("1000000"),
    roundtable_threshold_dollars=Decimal("500000"),
    af_compulsory_cap_dollars=AF_COMPULSORY_CAP_DOLLARS,
    fee_drag_internal_hourly_rate=Decimal("80"),
    fee_drag_internal_hours_per_file=Decimal("8"),
    fee_drag_vendor_contingency_pct=Decimal("0.25"),
    fee_drag_af_flat=AF_FILING_FLAT_FEE_DOLLARS,
    p_recovery_operator_policy=0.85,
    p_recovery_vicarious_cap=0.70,
    p_recovery_negligent_entrustment=0.55,
    p_recovery_fabre_non_party=0.40,
    p_recovery_products_defect=0.30,
    mandatory_referral_variance_flags=list(MANDATORY_ESCALATION_VARIANCE_FLAGS),
)
