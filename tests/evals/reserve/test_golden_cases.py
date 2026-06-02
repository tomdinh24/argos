"""Reserve — golden eval cases (15 scenarios).

Run with:
  uv run pytest tests/evals/reserve/ -m eval -q

Pass criteria: docs/evals/reserve-thresholds.md.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from argos.schemas.workflows.reserve import (
    LitStatus,
    MedicalBill,
    PermanencyStatus,
    PipStatus,
    PolicyLimits,
    RepStatus,
    ReserveInputs,
    ReserveSnapshot,
    WageLoss,
)
from tests.evals.reserve._harness import (
    POST_HB837,
    PRE_HB837,
    ReserveEvalCase,
    assert_case,
    run_case,
)


# ---------------------------------------------------------------------------
# Fixture builder — clean minor soft-tissue baseline (insured 100% liable)
# ---------------------------------------------------------------------------


def _inputs(**overrides) -> ReserveInputs:
    defaults: dict = dict(
        accrual_date=POST_HB837,
        filing_date=None,
        fnol_date=POST_HB837,
        actual_notice_date=None,
        venue_county="hillsborough",  # neutral 1.00x
        policy_limits=PolicyLimits(
            per_person=Decimal("100000"),
            per_occurrence=Decimal("300000"),
            property=Decimal("50000"),
        ),
        uim_um_coverage=None,
        self_insured_retention=None,
        claimant_count=1,
        insured_liability_pct=Decimal("100"),
        tortfeasor_pip_compliant=True,
        pip_status=PipStatus(
            cap_applicable=10000,
            paid_to_date=Decimal("8000"),
            exhausted=False,
            emc_determination=True,
            treatment_within_14_days=True,
        ),
        permanency_status=PermanencyStatus(
            opinion_present=True,
            rating_pct=Decimal("5"),
            mmi_date=date(2025, 12, 1),
            scarring_disfigurement=False,
            fatality=False,
        ),
        medical_specials=[
            MedicalBill(
                billed=Decimal("8000"),
                paid=Decimal("3500"),
                payer="health_ins",
                provider="St. Lukes ER",
                lop_flag=False,
                date_of_service=date(2025, 6, 2),
            ),
        ],
        wage_loss=WageLoss(
            documented_to_date=Decimal("2000"),
            claimed_future=None,
            occupation="server",
            employer_verified=True,
        ),
        injury_bucket="minor_soft_tissue",
        catastrophic_indicators=[],
        representation_status=RepStatus(represented=False),
        litigation_status=LitStatus(phase="pre_suit"),
        crn_status=None,
        prior_reserve_history=[],
    )
    defaults.update(overrides)
    return ReserveInputs(**defaults)


# ---------------------------------------------------------------------------
# GC-01 — Minor soft-tissue clean baseline
# specials=5500, generals=7700, indemnity=13200, no ALAE, no notices, handler
# ---------------------------------------------------------------------------

GC_01 = ReserveEvalCase(
    case_id="GC-01",
    description="Minor soft-tissue clean (pre-suit, insured 100%, permanency present)",
    inputs=_inputs(),
    expected_paid_satisfied=Decimal("3500.00"),
    expected_lop_equivalent=Decimal("0.00"),
    expected_wage_loss=Decimal("2000.00"),
    expected_specials_total=Decimal("5500.00"),
    expected_multiplier_central=Decimal("1.4"),
    expected_venue_factor=Decimal("1.00"),
    expected_threshold_discount_pct=Decimal("100"),
    expected_generals_low=Decimal("5500.00"),
    expected_generals_central=Decimal("7700.00"),
    expected_generals_high=Decimal("9900.00"),
    expected_indemnity_recommended=Decimal("13200.00"),
    expected_alae_p50=Decimal("0"),
    expected_authority="handler",
    expected_notice_types=set(),
    expected_bad_faith_markers_exact=set(),
    expected_stair_step_flagged=False,
    expected_no_change_warranted=False,  # no prior history
)


# ---------------------------------------------------------------------------
# GC-02 — Surgical recovering, depositions, insured 100%
# specials = paid 25000 + wage 10000 = 35000
# generals central = 35000 × 2.75 × 1.0 × 1.0 = 96250
# indemnity central = 131250, recommended = 131250 (not in variance zone)
# ALAE depositions central = 2500+5000+9000 = 16500
# recommended_total = 131250 + 16500 = 147750 → manager
# Excess fires (proximity 131% ≥ 50%, insured 100%)
# Bad-faith: proximity ≥ 70% + clear liability + represented
# ---------------------------------------------------------------------------

GC_02 = ReserveEvalCase(
    case_id="GC-02",
    description="Surgical recovering, depositions phase, insured 100%, represented",
    inputs=_inputs(
        filing_date=date(2024, 1, 15),
        medical_specials=[
            MedicalBill(
                billed=Decimal("50000"), paid=Decimal("25000"), payer="health_ins",
                provider="Mercy Surgical", lop_flag=False, date_of_service=POST_HB837,
            ),
        ],
        wage_loss=WageLoss(
            documented_to_date=Decimal("10000"), claimed_future=None,
            occupation="warehouse", employer_verified=True,
        ),
        injury_bucket="surgical_recovering",
        litigation_status=LitStatus(phase="depositions"),
        representation_status=RepStatus(represented=True, firm_name="Morgan & Morgan"),
    ),
    expected_specials_total=Decimal("35000.00"),
    expected_multiplier_central=Decimal("2.75"),
    expected_generals_central=Decimal("96250.00"),
    expected_indemnity_central=Decimal("131250.00"),
    expected_indemnity_recommended=Decimal("131250.00"),
    expected_alae_p50=Decimal("16500"),
    expected_alae_p10=Decimal("9500"),
    expected_alae_p90=Decimal("27000"),
    expected_authority="manager",
    expected_notice_types={"excess_carrier"},
    expected_notice_days_by_type={"excess_carrier": 15},
    expected_bad_faith_marker_substrings=[
        "reserve_at_", "represented_by_counsel",
    ],
)


# ---------------------------------------------------------------------------
# GC-03 — Catastrophic TBI single indicator, post-HB-837
# Catastrophic branch: TBI band p10=800K p50=3M p90=10M; capped at per_person limit 100K
# So all three → 100K. recommended = high = 100K. Categorical referral → manager.
# Reinsurance fires (categorical), LLC fires (categorical, mapped to "client").
# ---------------------------------------------------------------------------

GC_03 = ReserveEvalCase(
    case_id="GC-03",
    description="Catastrophic TBI, post-HB-837, single-indicator capped at limits",
    inputs=_inputs(
        injury_bucket="catastrophic",
        catastrophic_indicators=["tbi"],
        permanency_status=PermanencyStatus(
            opinion_present=True, fatality=False,
            mmi_date=None, scarring_disfigurement=True,
        ),
    ),
    expected_indemnity_low=Decimal("100000.00"),
    expected_indemnity_central=Decimal("100000.00"),
    expected_indemnity_high=Decimal("100000.00"),
    expected_indemnity_recommended=Decimal("100000.00"),
    expected_comparative_status_substr="catastrophic",
    expected_authority="manager",
    expected_notice_types={"reinsurer", "client", "excess_carrier"},
    expected_notice_days_by_type={
        "reinsurer": 30, "client": 7, "excess_carrier": 15,
    },
    expected_bad_faith_marker_substrings=["catastrophic_injury:tbi"],
)


# ---------------------------------------------------------------------------
# GC-04 — Catastrophic multiple indicators (fatality + sci); max band wins
# Per per_person 100K limit, all capped to 100K regardless of band — but the
# branch logic still chooses the max-of-indicators bands BEFORE capping.
# ---------------------------------------------------------------------------

GC_04 = ReserveEvalCase(
    case_id="GC-04",
    description="Catastrophic — fatality + sci, max band wins, capped at limits",
    inputs=_inputs(
        policy_limits=PolicyLimits(
            per_person=Decimal("1000000"),  # higher limit to expose max-band math
            per_occurrence=Decimal("3000000"),
            property=Decimal("50000"),
        ),
        injury_bucket="catastrophic",
        catastrophic_indicators=["fatality", "sci"],
        permanency_status=PermanencyStatus(
            opinion_present=False, fatality=True,
            mmi_date=None, scarring_disfigurement=False,
        ),
    ),
    # p10: max(fatality 250K, sci 1.8M) = 1.8M, capped to 1M
    # p50: max(fatality 1.2M, sci 3.5M) = 3.5M, capped to 1M
    # p90: max(fatality 5M, sci 5.4M) = 5.4M, capped to 1M
    # all three pinned to 1M by cap
    expected_indemnity_low=Decimal("1000000.00"),
    expected_indemnity_central=Decimal("1000000.00"),
    expected_indemnity_high=Decimal("1000000.00"),
    expected_indemnity_recommended=Decimal("1000000.00"),
    expected_authority="manager",
)


# ---------------------------------------------------------------------------
# GC-05 — Pre-HB-837 (accrual 2022), claimant 60% fault, pure comparative
# Should NOT be barred. insured_pct=40, claimant=60, hb_837_comparative=False
# specials/generals identical to GC-01; indemnity scaled by 0.40
# Variance zone (40 in [40,55]) but pre-HB-837 path bypasses the variance bump
# ---------------------------------------------------------------------------

GC_05 = ReserveEvalCase(
    case_id="GC-05",
    description="Pre-HB-837 accrual, claimant 60% fault, pure comparative — NOT barred",
    inputs=_inputs(
        accrual_date=PRE_HB837,
        fnol_date=PRE_HB837,
        # NB: filing_date=None falls back to accrual_date for HB 837 branch
        insured_liability_pct=Decimal("40"),
    ),
    expected_specials_total=Decimal("5500.00"),
    expected_generals_central=Decimal("7700.00"),
    expected_indemnity_central=Decimal("5280.00"),  # 13200 × 0.40
    expected_indemnity_recommended=Decimal("5280.00"),  # central, no variance bump
    expected_comparative_status_substr="pre-HB-837",
    expected_authority="handler",
)


# ---------------------------------------------------------------------------
# GC-06 — Post-HB-837, claimant 60% fault, modified-51 bar fires
# All bands → $0, comparative_status contains "barred"
# ---------------------------------------------------------------------------

GC_06 = ReserveEvalCase(
    case_id="GC-06",
    description="Post-HB-837, claimant 60% — §768.81 modified-51 bar fires",
    inputs=_inputs(
        filing_date=date(2024, 1, 1),
        insured_liability_pct=Decimal("40"),
    ),
    expected_indemnity_low=Decimal("0"),
    expected_indemnity_central=Decimal("0"),
    expected_indemnity_high=Decimal("0"),
    expected_indemnity_recommended=Decimal("0"),
    expected_comparative_status_substr="barred",
    expected_authority="handler",
)


# ---------------------------------------------------------------------------
# GC-07 — Variance zone (insured 50%, hb_837), recommended bumped toward p90
# specials 5500, generals central 7700, high 9900
# gross central = 13200; gross high = 15400
# pct_factor = 0.50 → low=(11000)*0.5=5500, central=13200*0.5=6600, high=15400*0.5=7700
# variance bump: recommended = (central+high)/2 = (6600+7700)/2 = 7150
# ---------------------------------------------------------------------------

GC_07 = ReserveEvalCase(
    case_id="GC-07",
    description="Variance zone (insured 50%, post-HB-837) — recommended toward p90",
    inputs=_inputs(
        filing_date=date(2024, 1, 1),
        insured_liability_pct=Decimal("50"),
    ),
    expected_indemnity_low=Decimal("5500.00"),
    expected_indemnity_central=Decimal("6600.00"),
    expected_indemnity_high=Decimal("7700.00"),
    expected_indemnity_recommended=Decimal("7150.00"),
    expected_comparative_status_substr="HIGH VARIANCE",
    expected_authority="handler",
)


# ---------------------------------------------------------------------------
# GC-08 — Venue calibrator: Miami-Dade (1.20×) — same minor soft-tissue facts
# generals central = 5500 × 1.4 × 1.20 × 1.0 = 9240
# indemnity central = 5500 + 9240 = 14740
# ---------------------------------------------------------------------------

GC_08 = ReserveEvalCase(
    case_id="GC-08",
    description="Venue calibrator — Miami-Dade vs neutral; generals scale by 1.20×",
    inputs=_inputs(venue_county="miami_dade"),
    expected_venue_factor=Decimal("1.20"),
    expected_generals_central=Decimal("9240.00"),
    expected_indemnity_central=Decimal("14740.00"),
    expected_authority="handler",
)


# ---------------------------------------------------------------------------
# GC-09 — ALAE cumulative through trial_prep
# 0 + 2500 + 5000 + 9000 + 6500 + 3500 + 38000 = 64500 central
# low: 0+1500+3000+5000+4000+2000+20000 = 35500
# high: 0+4000+8000+15000+10000+5000+60000 = 102000
# ---------------------------------------------------------------------------

GC_09 = ReserveEvalCase(
    case_id="GC-09",
    description="ALAE cumulative through trial_prep phase",
    inputs=_inputs(litigation_status=LitStatus(phase="trial_prep")),
    expected_alae_p10=Decimal("35500"),
    expected_alae_p50=Decimal("64500"),
    expected_alae_p90=Decimal("102000"),
)


# ---------------------------------------------------------------------------
# GC-10 — Excess-carrier notice fires (recommended_total ≥ 50% of per-person + clear liability)
# Bump specials so recommended crosses 50K (50% of 100K limit).
# Use moderate_ortho_non_surgical: 2.0× central, permanency present → no discount
# specials 30000 → generals central 60000 → indemnity 90000 → > 50K threshold
# ---------------------------------------------------------------------------

GC_10 = ReserveEvalCase(
    case_id="GC-10",
    description="Excess-carrier notice fires at proximity ≥ 50%, insured 80%+",
    inputs=_inputs(
        filing_date=date(2024, 1, 1),
        medical_specials=[
            MedicalBill(
                billed=Decimal("50000"), paid=Decimal("25000"), payer="health_ins",
                provider="Mercy", lop_flag=False, date_of_service=POST_HB837,
            ),
        ],
        wage_loss=WageLoss(
            documented_to_date=Decimal("5000"), claimed_future=None,
            occupation="electrician", employer_verified=True,
        ),
        injury_bucket="moderate_ortho_non_surgical",
        insured_liability_pct=Decimal("80"),  # exactly the clear-liability floor
    ),
    expected_notice_types={"excess_carrier"},
    expected_notice_days_by_type={"excess_carrier": 15},
)


# ---------------------------------------------------------------------------
# GC-11 — Reinsurance notice on $250K dollar threshold
# Severe permanent (4.0×); specials 60000 → generals 240000 → indemnity 300000 > 250K
# ---------------------------------------------------------------------------

GC_11 = ReserveEvalCase(
    case_id="GC-11",
    description="Reinsurance notice fires on $250K dollar threshold",
    inputs=_inputs(
        filing_date=date(2024, 1, 1),
        policy_limits=PolicyLimits(
            per_person=Decimal("1000000"),  # avoid limit-proximity bad-faith noise
            per_occurrence=Decimal("3000000"),
            property=Decimal("50000"),
        ),
        medical_specials=[
            MedicalBill(
                billed=Decimal("100000"), paid=Decimal("50000"), payer="health_ins",
                provider="Mt Sinai", lop_flag=False, date_of_service=POST_HB837,
            ),
        ],
        wage_loss=WageLoss(
            documented_to_date=Decimal("10000"), claimed_future=None,
            occupation="contractor", employer_verified=True,
        ),
        injury_bucket="severe_permanent",
    ),
    # specials = 50000 + 10000 = 60000
    # generals central = 60000 × 4.0 × 1.0 × 1.0 = 240000
    # indemnity central = 60000 + 240000 = 300000, recommended = 300000 (insured 100%)
    expected_specials_total=Decimal("60000.00"),
    expected_generals_central=Decimal("240000.00"),
    expected_indemnity_recommended=Decimal("300000.00"),
    # LLC $250K dollar trigger fires (mapped to notice_type="client"); reinsurance
    # $250K dollar trigger fires; excess does NOT fire (300K / 1M = 30% < 50%).
    expected_notice_types={"reinsurer", "client"},
    expected_notice_days_by_type={"reinsurer": 30, "client": 7},
    expected_authority="client",  # 300000 > carrier_escalation 250000
)


# ---------------------------------------------------------------------------
# GC-12 — Authority routing across all four tiers
# We test one at a time via parametrize-style splits below; here we do
# the manager tier specifically (between supervisor 75K and manager 250K).
# specials 30000 + wage 5000 = 35000; surgical 2.75× → generals 96250
# indemnity = 131250. Recommended_total ALAE pre_suit = 0 → 131250. → manager.
# ---------------------------------------------------------------------------

GC_12 = ReserveEvalCase(
    case_id="GC-12",
    description="Authority routing — manager tier (131K)",
    inputs=_inputs(
        filing_date=date(2024, 1, 1),
        policy_limits=PolicyLimits(
            per_person=Decimal("1000000"),  # avoid bad-faith proximity noise
            per_occurrence=Decimal("3000000"),
            property=Decimal("50000"),
        ),
        medical_specials=[
            MedicalBill(
                billed=Decimal("50000"), paid=Decimal("30000"), payer="health_ins",
                provider="Mercy", lop_flag=False, date_of_service=POST_HB837,
            ),
        ],
        wage_loss=WageLoss(
            documented_to_date=Decimal("5000"), claimed_future=None,
            occupation="warehouse", employer_verified=True,
        ),
        injury_bucket="surgical_recovering",
    ),
    expected_indemnity_recommended=Decimal("131250.00"),
    expected_authority="manager",
)


# ---------------------------------------------------------------------------
# GC-13 — §768.0427 paid-vs-billed: health-ins paid + LOP self-pay
# filing_date post-HB-837 → paid anchor applies
# Bill 1: health_ins billed 8000 paid 3500 → paid_satisfied += 3500
# Bill 2: lop, lop_flag, billed 12000 paid 0 → lop_equivalent += 12000 (billed)
# wage 2000 → total = 3500 + 12000 + 2000 = 17500
# ---------------------------------------------------------------------------

GC_13 = ReserveEvalCase(
    case_id="GC-13",
    description="§768.0427 paid-vs-billed — paid anchor for health-ins, billed for LOP",
    inputs=_inputs(
        filing_date=date(2024, 1, 1),
        medical_specials=[
            MedicalBill(
                billed=Decimal("8000"), paid=Decimal("3500"), payer="health_ins",
                provider="St Lukes", lop_flag=False, date_of_service=POST_HB837,
            ),
            MedicalBill(
                billed=Decimal("12000"), paid=Decimal("0"), payer="lop",
                provider="LOP Chiropractic", lop_flag=True,
                date_of_service=POST_HB837,
            ),
        ],
    ),
    expected_paid_satisfied=Decimal("3500.00"),
    expected_lop_equivalent=Decimal("12000.00"),
    expected_wage_loss=Decimal("2000.00"),
    expected_specials_total=Decimal("17500.00"),
)


# ---------------------------------------------------------------------------
# GC-14 — Bad-faith markers stack
# - policy_limits_demand=True
# - represented=True
# - reserve at ≥ 70% of per_person limit with clear liability
# - actual_notice 100 days ago (> 90) → safe_harbor_clock_expired
# Severe (4.0×); specials 30K → generals 120K → indemnity 150K vs limit 100K (150% proximity)
# ---------------------------------------------------------------------------

GC_14 = ReserveEvalCase(
    case_id="GC-14",
    description="Bad-faith markers — policy-limits demand + clear liability + safe-harbor expired",
    inputs=_inputs(
        filing_date=date(2026, 1, 1),
        actual_notice_date=date(2026, 2, 22),  # 100 days before REVIEW_AS_OF (2026-06-02)
        medical_specials=[
            MedicalBill(
                billed=Decimal("50000"), paid=Decimal("25000"), payer="health_ins",
                provider="Mt Sinai", lop_flag=False, date_of_service=POST_HB837,
            ),
        ],
        wage_loss=WageLoss(
            documented_to_date=Decimal("5000"), claimed_future=None,
            occupation="contractor", employer_verified=True,
        ),
        injury_bucket="severe_permanent",
        representation_status=RepStatus(
            represented=True, firm_name="M&M",
            policy_limits_demand=True, demand_date=date(2026, 2, 22),
            demand_amount=Decimal("100000"),
        ),
    ),
    expected_bad_faith_marker_substrings=[
        "policy_limits_demand_received",
        "represented_by_counsel",
        "safe_harbor_clock_expired",
        "reserve_at_",  # proximity marker
    ],
)


# ---------------------------------------------------------------------------
# GC-15 — Stair-step detected: 3 prior reserve snapshots, each <20% upward, in 90d
# REVIEW_AS_OF = 2026-06-02; window_start = 2026-03-04
# snapshots at 2026-03-05, 2026-04-05, 2026-05-05; each up ~15% from prior
# Need 3+ revisions in window AND ≥ 2 small upward pairs (small_upward >= STAIR_STEP_MIN_REVISIONS-1 = 2)
# ---------------------------------------------------------------------------

GC_15 = ReserveEvalCase(
    case_id="GC-15",
    description="Stair-step detected — 3 small upward revisions in 90 days",
    inputs=_inputs(
        prior_reserve_history=[
            ReserveSnapshot(
                eval_date=date(2026, 3, 5),
                indemnity=Decimal("10000"),
                alae=Decimal("0"),
                basis="initial",
            ),
            ReserveSnapshot(
                eval_date=date(2026, 4, 5),
                indemnity=Decimal("11500"),  # +15%
                alae=Decimal("0"),
                basis="re-eval",
            ),
            ReserveSnapshot(
                eval_date=date(2026, 5, 5),
                indemnity=Decimal("13200"),  # +14.8%
                alae=Decimal("0"),
                basis="re-eval",
            ),
        ],
    ),
    expected_stair_step_flagged=True,
    expected_stair_step_revisions=3,
)


GOLDEN_CASES = [
    GC_01, GC_02, GC_03, GC_04, GC_05, GC_06, GC_07, GC_08,
    GC_09, GC_10, GC_11, GC_12, GC_13, GC_14, GC_15,
]


@pytest.mark.eval
@pytest.mark.parametrize("case", GOLDEN_CASES, ids=[c.case_id for c in GOLDEN_CASES])
def test_golden(case: ReserveEvalCase) -> None:
    analysis, ctx = run_case(case)
    assert_case(case, analysis, ctx)
