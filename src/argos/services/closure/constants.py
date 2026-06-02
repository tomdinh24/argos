"""Closure workflow — constants registry.

Versioned. Update VERSION on every doctrine/cite/threshold change so the
templated rationale stamps the right snapshot.

Spec: docs/specs/closure-workflow.md.
"""
from __future__ import annotations

from decimal import Decimal
from typing import NamedTuple

from argos.schemas.workflows.closure import ClosureProgramConfig


VERSION = "v1.2026-06-02"


# =============================================================================
# Federal MSP thresholds + windows
# =============================================================================


SECTION_111_TPOC_THRESHOLD_DOLLARS = Decimal("750")  # Verisk 2025 retained $750
SECTION_111_REPORT_WINDOW_DAYS = 135
SECTION_111_CMP_PER_DAY_DOLLARS = Decimal("1000")  # 42 C.F.R. §402.1(c)

MEDICARE_FINAL_DEMAND_PAY_WINDOW_DAYS = 60
MEDICARE_FINAL_DEMAND_APPEAL_WINDOW_DAYS = 120
MEDICARE_FINAL_DEMAND_MIN_DELAY_DAYS = 60
MEDICARE_FINAL_DEMAND_MAX_DELAY_DAYS = 180


# =============================================================================
# Florida statutory windows
# =============================================================================


CRN_CURE_WINDOW_DAYS = 60  # §624.155(3)
HB_837_THIRD_PARTY_SAFE_HARBOR_DAYS = 90  # §624.155(4)
HB_837_MULTI_CLAIMANT_SAFE_HARBOR_DAYS = 90  # §624.155(6)
SECTION_627_4137_AFFIDAVIT_DELIVERY_DAYS = 30
SECTION_627_4265_TENDER_WINDOW_DAYS = 20
SECTION_627_4265_LATE_INTEREST_PCT = Decimal("12")
SECTION_627_736_PIP_BILL_WINDOW_DAYS = 30
SECTION_768_76_COLLATERAL_SOURCE_WAIVER_DAYS = 30


# =============================================================================
# FL SOL (post-HB-837)
# =============================================================================


SOL_NEGLIGENCE_YEARS_POST_HB837 = 2  # §95.11(5)(a) post-2023-03-24
SOL_NEGLIGENCE_YEARS_PRE_HB837 = 4
SOL_TOLLING_OUTER_BOUND_YEARS = 7  # §95.031 cap


# =============================================================================
# Retention floors
# =============================================================================


FL_ADMIN_CODE_RECORD_RETENTION_YEARS = 3  # 69O-191.074
NAIC_902_RETENTION_YEARS = 2  # current + 2 preceding
HIPAA_RETENTION_YEARS = 6  # 45 C.F.R. §164.530(j)(2)
TPA_CONTRACT_RETENTION_YEARS_AFTER_TERMINATION = 5  # §626.884
MSP_RECOVERY_TAIL_YEARS = 6  # post-close CMS recovery window


# =============================================================================
# Gate registry
# =============================================================================


class GateSeed(NamedTuple):
    """One closure gate's registry entry."""

    gate_id: str
    tier: str  # "A" / "B" / "C" / "D" / "E" / "F"
    statute_or_case_cite: str
    description: str


FL_CLOSURE_GATE_REGISTRY_V1: dict[str, GateSeed] = {
    # Tier A — Statutory FL + bad-faith
    "coverage_decision_uncommitted": GateSeed(
        "coverage_decision_uncommitted", "A",
        "Fla. Stat. §626.9541(1)(i)3",
        "Coverage decision not committed by adjuster.",
    ),
    "liability_apportionment_uncommitted": GateSeed(
        "liability_apportionment_uncommitted", "A",
        "Berges v. Infinity Ins. Co., 896 So.2d 665 (Fla. 2004)",
        "Liability fault percentages not committed.",
    ),
    "denial_letter_deficient": GateSeed(
        "denial_letter_deficient", "A",
        "Fla. Stat. §626.9541(1)(i)3.f",
        "Closure-without-payment requires written denial letter citing "
        "policy provision + facts + applicable law.",
    ),
    "open_crn_within_cure_window": GateSeed(
        "open_crn_within_cure_window", "A",
        "Fla. Stat. §624.155(3); Allstate Indemnity Co. v. Ruiz, 899 So.2d 1121",
        "Live CRN inside the 60-day cure window with no documented cure.",
    ),
    "third_party_safe_harbor_window_expiring_unotendered": GateSeed(
        "third_party_safe_harbor_window_expiring_unotendered", "A",
        "Fla. Stat. §624.155(4) (HB 837, 2023)",
        "Third-party BI past 90-day actual-notice clock with evidence supporting demand "
        "and no policy-limits tender on file.",
    ),
    "multi_claimant_safe_harbor_not_invoked": GateSeed(
        "multi_claimant_safe_harbor_not_invoked", "A",
        "Fla. Stat. §624.155(6) (HB 837, 2023); Farinas v. Fla. Farm Bureau "
        "Gen. Ins. Co., 850 So.2d 555 (Fla. 4th DCA 2003); Shuster v. South "
        "Broward Hosp. Dist., 591 So.2d 174 (Fla. 1992)",
        "Multi-claimant occurrence with competing demands exceeding aggregate, "
        "no Rule 1.240 interpleader filed and no binding-arbitration submission "
        "within 90 days of competing-claims notice.",
    ),
    "section_627_4137_affidavit_missing_or_stale": GateSeed(
        "section_627_4137_affidavit_missing_or_stale", "A",
        "Fla. Stat. §627.4137(1)-(2)",
        "Affidavit of coverage not delivered within 30 days of written request "
        "OR not amended for aggregate-limit erosion from sibling claimants.",
    ),
    "pip_exposure_not_drained": GateSeed(
        "pip_exposure_not_drained", "A",
        "Fla. Stat. §627.736(4)(b)",
        "PIP bill on file neither paid nor formally denied within its own 30-day window.",
    ),
    "section_627_4265_tender_window_violated": GateSeed(
        "section_627_4265_tender_window_violated", "A",
        "Fla. Stat. §627.4265",
        "Settlement agreement signed but check not tendered within 20 days; "
        "or release executed but check not tendered within 20 days. "
        "12% statutory interest accruing.",
    ),
    "open_exposure_at_any_coverage_section": GateSeed(
        "open_exposure_at_any_coverage_section", "A",
        "Guidewire ClaimCenter Cloud API — exposure-level closure validation",
        "Any individual exposure (BI/PD/MP/PIP/UM) not closed/denied/paid.",
    ),
    "boston_old_colony_diligence_incomplete": GateSeed(
        "boston_old_colony_diligence_incomplete", "A",
        "Boston Old Colony Ins. Co. v. Gutierrez, 386 So.2d 783, 785 (Fla. 1980)",
        "At least one Boston Old Colony precondition unmet "
        "(insured-notified / excess-warning / investigation / fair-consideration / "
        "reasonable-prudent-person).",
    ),
    "powell_duty_unfulfilled": GateSeed(
        "powell_duty_unfulfilled", "A",
        "Powell v. Prudential Property & Cas. Ins. Co., 584 So.2d 12, 14 (Fla. 3d DCA 1991)",
        "Liability clear + damages plausibly exceed limits + no affirmative "
        "policy-limits offer made and no documented why-Powell-doesn't-apply memo.",
    ),
    "harvey_communication_delay": GateSeed(
        "harvey_communication_delay", "A",
        "Harvey v. GEICO Gen. Ins. Co., 259 So.3d 1, 7 (Fla. 2018)",
        "Claimant communication received pre-close not answered AND/OR not "
        "relayed to insured.",
    ),
    "macola_settlement_after_excess_trajectory": GateSeed(
        "macola_settlement_after_excess_trajectory", "A",
        "Macola v. Gov't Employees Ins. Co., 953 So.2d 451 (Fla. 2006)",
        "Powell duty arguably triggered earlier + tender came only after suit "
        "or demand pressure + close memo treats payment as resolution.",
    ),
    # Tier B — Federal lien / MSP
    "medicare_msp_unresolved": GateSeed(
        "medicare_msp_unresolved", "B",
        "42 U.S.C. §1395y(b)(2)(B)(iii) + (b)(3)(A); 42 C.F.R. §411.24(g)+(i)",
        "Medicare beneficiary + settlement ≥ $750 + no Final Demand satisfied "
        "and no active dispute on file. Double-damages exposure.",
    ),
    "section_111_tpoc_unreported": GateSeed(
        "section_111_tpoc_unreported", "B",
        "42 U.S.C. §1395y(b)(8); 42 C.F.R. §402.1(c)",
        "Settlement ≥ $750 + no Section 111 TPOC transmit-success log "
        "within 135-day window. $1,000/claim/day CMP exposure.",
    ),
    "florida_medicaid_lien_unresolved": GateSeed(
        "florida_medicaid_lien_unresolved", "B",
        "Fla. Stat. §409.910(11)(f); Gallardo v. Marstiller, 596 U.S. 420 (2022)",
        "Medicaid beneficiary identified + no FAHCA satisfaction letter and "
        "no §409.910(17)(b) DOAH reduction order. Past + future medicals.",
    ),
    "workers_comp_lien_unsatisfied": GateSeed(
        "workers_comp_lien_unsatisfied", "B",
        "Fla. Stat. §440.39(3)(a); Aetna Ins. Co. v. Norman, 468 So.2d 226 (Fla. 1985)",
        "Claimant in scope of employment + no §440.39 lien statement or waiver. "
        "BI vs UM allocation must be documented (lien excludes UM).",
    ),
    "erisa_self_funded_lien_unresolved": GateSeed(
        "erisa_self_funded_lien_unresolved", "B",
        "US Airways v. McCutchen, 569 U.S. 88 (2013); Sereboff v. Mid Atl. Med. "
        "Servs., 547 U.S. 356 (2006); 29 U.S.C. §1132(a)(3); §1144(b)(2)(B)",
        "Self-funded ERISA plan identified + no plan-status confirmation OR no "
        "written reimbursement agreement OR release without hold-harmless. "
        "§768.76 waiver does NOT apply to ERISA.",
    ),
    "hospital_lien_unresolved": GateSeed(
        "hospital_lien_unresolved", "B",
        "Shands Teaching Hosp. v. Mercury Ins. Co. of Fla., 97 So.3d 204 (Fla. 2012)",
        "County-specific hospital lien recorded + no recorded release. "
        "Must run COUNTY-of-treatment search (§713.50 struck down).",
    ),
    "va_tricare_recovery_pending": GateSeed(
        "va_tricare_recovery_pending", "B",
        "38 U.S.C. §1729; 10 U.S.C. §1095; 32 C.F.R. §199.12",
        "Veteran or active-duty/dependent claimant + no VA Form 10-7959f-1 or "
        "TRICARE HHC zero-balance letter.",
    ),
    # Tier C — Release evidence
    "missing_signed_release": GateSeed(
        "missing_signed_release", "C",
        "WQBA (general FL release doctrine); Fla. Stat. §627.4265 tender clock",
        "Settlement agreed but no signed release on file.",
    ),
    "release_does_not_address_known_liens": GateSeed(
        "release_does_not_address_known_liens", "C",
        "Sereboff v. Mid Atl. Med. Servs., 547 U.S. 356 (2006)",
        "Settlement with identified lien holders + release lacks hold-harmless "
        "for known liens.",
    ),
    "section_768_76_window_open": GateSeed(
        "section_768_76_window_open", "C",
        "Fla. Stat. §768.76(6)+(7); Mercury Ins. v. Emergency Physicians of "
        "Cent. Fla., 182 So.3d 661 (Fla. 5th DCA 2015)",
        "Collateral source notice sent + 30-day waiver window not expired + "
        "no responding lien resolved.",
    ),
    "outstanding_obr_with_legal_weight": GateSeed(
        "outstanding_obr_with_legal_weight", "C",
        "Fla. Stat. §627.4137; Fla. Stat. §627.736",
        "Open OutboundRequest tagged legally_required (sworn statement, EUO, "
        "reasonable-proof request).",
    ),
    # Tier D — Audit + authority
    "agent_action_ledger_incomplete": GateSeed(
        "agent_action_ledger_incomplete", "D",
        "Allstate Indemnity Co. v. Ruiz, 899 So.2d 1121 (Fla. 2005)",
        "Workflow runs without corresponding AgentAction rows. v1: warning, "
        "not block. Promoted to block after AgentAction writes ship.",
    ),
    "settlement_authority_exceeded": GateSeed(
        "settlement_authority_exceeded", "D",
        "TPA practice — examiner authority tied to reserve",
        "Examiner authority dollars < settlement amount with no documented "
        "escalation to next tier.",
    ),
    "record_classification_missing": GateSeed(
        "record_classification_missing", "D",
        "FL OIR market-conduct examination frame; NAIC Model Reg. 902 §5",
        "Closure not classified into closed_with_payment / "
        "closed_without_payment / reopened.",
    ),
    # Tier E — Defense-track bifurcation
    "open_defense_track_post_interpleader": GateSeed(
        "open_defense_track_post_interpleader", "E",
        "Fla. Stat. §624.155(6)(a) (HB 837, 2023)",
        "Interpleader filed + limits deposited (indemnity sub-file closeable) "
        "BUT underlying tort actions vs insured unresolved.",
    ),
    # Tier F — Preservation
    "spoliation_preservation_hold_pre_sol_expiry": GateSeed(
        "spoliation_preservation_hold_pre_sol_expiry", "F",
        "Pub. Health Trust of Dade Cnty. v. Valcin, 507 So.2d 596 (Fla. 1987); "
        "Martino v. Wal-Mart Stores, 908 So.2d 342 (Fla. 2005); Fla. Stat. "
        "§626.884; 45 C.F.R. §164.530(j)(2)",
        "Auto-purge attempted on file with SOL not expired or retention "
        "floors not satisfied.",
    ),
}


# =============================================================================
# Mandatory-escalation variance flags
# =============================================================================


MANDATORY_ESCALATION_VARIANCE_FLAGS: tuple[str, ...] = (
    "medicare_eligibility_check_skipped",
    "erisa_funding_type_undetermined",
    "multi_claimant_competing_limits_ambiguity",
    "powell_duty_arguably_triggered",
    "macola_post_excess_trajectory_pattern",
    "boecher_ruiz_artifact_destruction_risk",
)


# =============================================================================
# Tier weighting for ready_probability cap
# =============================================================================


# Cap on ready_probability when any gate of the listed tier fails.
TIER_FAILURE_PROBABILITY_CAP: dict[str, float] = {
    "A": 0.05,
    "B": 0.25,
    "C": 0.50,
    "D": 0.70,
    "E": 0.70,
    "F": 0.85,
}


# =============================================================================
# Default program config
# =============================================================================


DEFAULT_PROGRAM = ClosureProgramConfig(
    program_id="DEFAULT_FL_SPECIALTY_AUTO_BI",
    closure_examiner_authority_dollars=Decimal("25000"),
    closure_senior_examiner_authority_dollars=Decimal("75000"),
    closure_supervisor_authority_dollars=Decimal("250000"),
    closure_manager_authority_dollars=Decimal("1000000"),
    soft_close_max_days_pending_final_demand=180,
    soft_close_max_days_pending_section_111=135,
    powell_clear_liability_threshold_pct=80,
    auto_close_enabled=False,
    record_retention_floor_years=3,
    hipaa_retention_years=6,
    tpa_contract_retention_years_after_termination=5,
)
