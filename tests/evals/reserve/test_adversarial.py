"""Reserve — adversarial boundary probes (8 off-by-one seam tests).

Each case sits one click away from a doctrinal threshold and asserts
the threshold fires on the correct side.
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
    REVIEW_AS_OF,
    ReserveEvalCase,
    assert_case,
    run_case,
)


def _inputs(**overrides) -> ReserveInputs:
    defaults: dict = dict(
        accrual_date=POST_HB837,
        filing_date=None,
        fnol_date=POST_HB837,
        actual_notice_date=None,
        venue_county="hillsborough",
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
                billed=Decimal("8000"), paid=Decimal("3500"), payer="health_ins",
                provider="St Lukes", lop_flag=False, date_of_service=POST_HB837,
            ),
        ],
        wage_loss=WageLoss(
            documented_to_date=Decimal("2000"), claimed_future=None,
            occupation="server", employer_verified=True,
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
# ADV-01 — HB 837 filing boundary
# 2023-03-23 → pre-HB-837, no bar (claimant 60% recoverable under pure comparative)
# 2023-03-24 → modified-51 bar fires
# ---------------------------------------------------------------------------

ADV_01a = ReserveEvalCase(
    case_id="ADV-01a",
    description="HB 837 filing boundary: 2023-03-23 — pre-HB-837, no bar",
    inputs=_inputs(
        accrual_date=date(2023, 3, 23),
        filing_date=date(2023, 3, 23),
        fnol_date=date(2023, 3, 23),
        insured_liability_pct=Decimal("40"),  # claimant 60%
    ),
    expected_comparative_status_substr="pre-HB-837",
    # Pre-HB-837 filings skip §768.0427 paid-anchor → specials use billed.
    # specials = 8000 (billed) + 2000 (wage) = 10000
    # generals central = 10000 × 1.4 × 1.0 × 1.0 = 14000
    # gross central = 24000 × 0.40 = 9600
    expected_indemnity_recommended=Decimal("9600.00"),
)

ADV_01b = ReserveEvalCase(
    case_id="ADV-01b",
    description="HB 837 filing boundary: 2023-03-24 — bar fires",
    inputs=_inputs(
        accrual_date=date(2023, 3, 24),
        filing_date=date(2023, 3, 24),
        fnol_date=date(2023, 3, 24),
        insured_liability_pct=Decimal("40"),
    ),
    expected_comparative_status_substr="barred",
    expected_indemnity_recommended=Decimal("0"),
)


# ---------------------------------------------------------------------------
# ADV-02 — Comparative bar edge: strict > 50, not ≥
# claimant exactly 50.00% (insured 50%) → NOT barred
# claimant 51% (insured 49%) → barred
# ---------------------------------------------------------------------------

ADV_02a = ReserveEvalCase(
    case_id="ADV-02a",
    description="Comparative bar edge: claimant exactly 50.00% — NOT barred",
    inputs=_inputs(
        filing_date=date(2024, 1, 1),
        insured_liability_pct=Decimal("50"),  # claimant 50%
    ),
    expected_comparative_status_substr="HIGH VARIANCE",  # 50 in [40,55]
    expected_indemnity_recommended=Decimal("7150.00"),  # variance-bumped
)

ADV_02b = ReserveEvalCase(
    case_id="ADV-02b",
    description="Comparative bar edge: claimant 51% — barred",
    inputs=_inputs(
        filing_date=date(2024, 1, 1),
        insured_liability_pct=Decimal("49"),  # claimant 51% > 50% bar
    ),
    expected_comparative_status_substr="barred",
    expected_indemnity_recommended=Decimal("0"),
)


# ---------------------------------------------------------------------------
# ADV-03 — Variance zone edges (40 in, 39 out)
# In: variance bump fires → recommended ≠ central
# Out: no bump → recommended = central
# ---------------------------------------------------------------------------

ADV_03a = ReserveEvalCase(
    case_id="ADV-03a",
    description="Variance zone edge: insured 55% — top of zone, bump fires",
    inputs=_inputs(
        filing_date=date(2024, 1, 1),
        insured_liability_pct=Decimal("55"),
    ),
    # gross central = 13200, gross high = 15400; pct 0.55
    # central = 7260, high = 8470; bumped = (7260+8470)/2 = 7865
    expected_indemnity_central=Decimal("7260.00"),
    expected_indemnity_high=Decimal("8470.00"),
    expected_indemnity_recommended=Decimal("7865.00"),
    expected_comparative_status_substr="HIGH VARIANCE",
)

ADV_03b = ReserveEvalCase(
    case_id="ADV-03b",
    description="Variance zone edge: insured 56% — just out of zone, no bump",
    inputs=_inputs(
        filing_date=date(2024, 1, 1),
        insured_liability_pct=Decimal("56"),
    ),
    # pct 0.56: central = 7392, high = 8624
    # NOT in zone → recommended = central
    expected_indemnity_central=Decimal("7392.00"),
    expected_indemnity_high=Decimal("8624.00"),
    expected_indemnity_recommended=Decimal("7392.00"),
    expected_comparative_status_substr="within recovery",
)


# ---------------------------------------------------------------------------
# ADV-04 — Safe harbor exact 90 vs 91 days; only fires with policy-limits demand
# REVIEW_AS_OF = 2026-06-02
# 2026-03-04 = 90 days back, 2026-03-03 = 91 days back
# Calculator uses `elapsed > SAFE_HARBOR_DAYS` (strict), so 90 → not expired, 91 → expired
# ---------------------------------------------------------------------------

ADV_04a = ReserveEvalCase(
    case_id="ADV-04a",
    description="Safe harbor: 90 days elapsed + demand — not yet expired (strict >)",
    inputs=_inputs(
        actual_notice_date=date(2026, 3, 4),  # exactly 90 days back
        representation_status=RepStatus(
            represented=True, policy_limits_demand=True,
        ),
    ),
    # marker should NOT include "safe_harbor_clock_expired_without_tender"
    expected_bad_faith_marker_substrings=["policy_limits_demand_received"],
)

ADV_04b = ReserveEvalCase(
    case_id="ADV-04b",
    description="Safe harbor: 91 days elapsed + demand — expired",
    inputs=_inputs(
        actual_notice_date=date(2026, 3, 3),  # 91 days back
        representation_status=RepStatus(
            represented=True, policy_limits_demand=True,
        ),
    ),
    expected_bad_faith_marker_substrings=[
        "safe_harbor_clock_expired_without_tender",
    ],
)


# ---------------------------------------------------------------------------
# ADV-05 — Excess-carrier proximity threshold
# Per-person limit 100K; trigger at proximity ≥ 50% AND insured ≥ 80%
# Make recommended_total land on the boundary.
#
# minor_soft_tissue at insured 80%: specials 5500, generals central 7700;
# gross central 13200 × 0.80 = 10560 — too low.
# Bump severity: moderate (2.0×); specials 30000+5000=35000; generals 70000;
# gross 105000 × 0.80 = 84000 → proximity 84%. Fires.
# Lower insured to 79% → does NOT fire (clear-liability floor unmet).
# ---------------------------------------------------------------------------

ADV_05a = ReserveEvalCase(
    case_id="ADV-05a",
    description="Excess fires: proximity ≥ 50%, insured exactly 80%",
    inputs=_inputs(
        filing_date=date(2024, 1, 1),
        medical_specials=[
            MedicalBill(
                billed=Decimal("50000"), paid=Decimal("30000"), payer="health_ins",
                provider="Mercy", lop_flag=False, date_of_service=POST_HB837,
            ),
        ],
        wage_loss=WageLoss(
            documented_to_date=Decimal("5000"), claimed_future=None,
            occupation="electrician", employer_verified=True,
        ),
        injury_bucket="moderate_ortho_non_surgical",
        insured_liability_pct=Decimal("80"),
    ),
    expected_notice_types={"excess_carrier"},
)

ADV_05b = ReserveEvalCase(
    case_id="ADV-05b",
    description="Excess does NOT fire: insured 79% — clear-liability floor unmet",
    inputs=_inputs(
        filing_date=date(2024, 1, 1),
        medical_specials=[
            MedicalBill(
                billed=Decimal("50000"), paid=Decimal("30000"), payer="health_ins",
                provider="Mercy", lop_flag=False, date_of_service=POST_HB837,
            ),
        ],
        wage_loss=WageLoss(
            documented_to_date=Decimal("5000"), claimed_future=None,
            occupation="electrician", employer_verified=True,
        ),
        injury_bucket="moderate_ortho_non_surgical",
        insured_liability_pct=Decimal("79"),
    ),
    # Bad-faith proximity also requires insured ≥ 80 → no marker either
    expected_notice_types=set(),
)


# ---------------------------------------------------------------------------
# ADV-06 — Authority tier edges
# Examiner upper bound: recommended_total = 25000 → handler (≤)
# +$1 over: 25001 → supervisor
# Use pre_suit so ALAE=0 and recommended_total = indemnity.recommended
# minor_soft_tissue, insured 100%, build specials so indemnity = 25000 exactly
# 13200 came from 5500 × (1 + 1.4 × 1.0 × 1.0). Need indemnity = 25000:
# gross = specials × (1 + 1.4) = specials × 2.4 = 25000 → specials = 10416.67
# That's awkward. Just bump specials enough to land near tier edges.
#
# Easier: target supervisor = 75000 exactly via specials 31250 (×2.4=75000).
# specials 31250 = paid 29250 + wage 2000 = 31250.
# But still hard to hit 25000 exactly without fractions. Skip exact-edge for
# handler; do supervisor edge using carefully built numbers.
# ---------------------------------------------------------------------------

ADV_06a = ReserveEvalCase(
    case_id="ADV-06a",
    description="Authority edge: recommended_total = 75000 exactly → supervisor",
    inputs=_inputs(
        # specials = 31250 → gross = 31250 × 2.4 = 75000 → indemnity = 75000
        medical_specials=[
            MedicalBill(
                billed=Decimal("29250"), paid=Decimal("29250"), payer="health_ins",
                provider="Mercy", lop_flag=False, date_of_service=POST_HB837,
            ),
        ],
        wage_loss=WageLoss(
            documented_to_date=Decimal("2000"), claimed_future=None,
            occupation="warehouse", employer_verified=True,
        ),
    ),
    expected_indemnity_recommended=Decimal("75000.00"),
    expected_authority="supervisor",  # ≤ supervisor_authority 75K
)

ADV_06b = ReserveEvalCase(
    case_id="ADV-06b",
    description="Authority edge: recommended_total = 75001 → manager (one over)",
    inputs=_inputs(
        medical_specials=[
            MedicalBill(
                # specials 29250.42 + wage 2000 = 31250.42 → gross 75001.008
                billed=Decimal("29250.42"), paid=Decimal("29250.42"),
                payer="health_ins", provider="Mercy",
                lop_flag=False, date_of_service=POST_HB837,
            ),
        ],
        wage_loss=WageLoss(
            documented_to_date=Decimal("2000"), claimed_future=None,
            occupation="warehouse", employer_verified=True,
        ),
    ),
    expected_authority="manager",  # just above supervisor authority
)


# ---------------------------------------------------------------------------
# ADV-07 — Stair-step edges
# 2 revisions → not flagged (need ≥ 3 revisions for window check)
# 3 revisions but one is exactly 20% → "small" is strict <20%, so that pair
# does NOT count → only 1 small upward → not flagged
# ---------------------------------------------------------------------------

ADV_07a = ReserveEvalCase(
    case_id="ADV-07a",
    description="Stair-step: only 2 revisions in window — not flagged",
    inputs=_inputs(
        prior_reserve_history=[
            ReserveSnapshot(
                eval_date=date(2026, 4, 5), indemnity=Decimal("10000"),
                alae=Decimal("0"), basis="initial",
            ),
            ReserveSnapshot(
                eval_date=date(2026, 5, 5), indemnity=Decimal("11500"),
                alae=Decimal("0"), basis="re-eval",
            ),
        ],
    ),
    expected_stair_step_flagged=False,
    expected_stair_step_revisions=2,
)

ADV_07b = ReserveEvalCase(
    case_id="ADV-07b",
    description="Stair-step: 3 revisions, one delta = exactly 20% — not flagged (strict <)",
    inputs=_inputs(
        prior_reserve_history=[
            ReserveSnapshot(
                eval_date=date(2026, 3, 5), indemnity=Decimal("10000"),
                alae=Decimal("0"), basis="initial",
            ),
            ReserveSnapshot(
                eval_date=date(2026, 4, 5), indemnity=Decimal("12000"),  # +20% exact
                alae=Decimal("0"), basis="re-eval",
            ),
            ReserveSnapshot(
                eval_date=date(2026, 5, 5), indemnity=Decimal("14400"),  # +20% exact
                alae=Decimal("0"), basis="re-eval",
            ),
        ],
    ),
    expected_stair_step_flagged=False,  # neither pair counts as "small" (<20%)
    expected_stair_step_revisions=3,
)


# ---------------------------------------------------------------------------
# ADV-08 — Catastrophic + post-HB-837 + claimant 60% → still barred
# Branch goes through _compute_catastrophic_indemnity which applies its own bar
# ---------------------------------------------------------------------------

ADV_08 = ReserveEvalCase(
    case_id="ADV-08",
    description="Catastrophic + post-HB-837 + claimant 60% — bar fires even on life-care-plan branch",
    inputs=_inputs(
        filing_date=date(2024, 1, 1),
        injury_bucket="catastrophic",
        catastrophic_indicators=["tbi"],
        insured_liability_pct=Decimal("40"),
        permanency_status=PermanencyStatus(
            opinion_present=True, fatality=False,
            mmi_date=None, scarring_disfigurement=True,
        ),
    ),
    expected_indemnity_low=Decimal("0"),
    expected_indemnity_central=Decimal("0"),
    expected_indemnity_high=Decimal("0"),
    expected_indemnity_recommended=Decimal("0"),
    expected_comparative_status_substr="barred",
)


ADVERSARIAL_CASES = [
    ADV_01a, ADV_01b,
    ADV_02a, ADV_02b,
    ADV_03a, ADV_03b,
    ADV_04a, ADV_04b,
    ADV_05a, ADV_05b,
    ADV_06a, ADV_06b,
    ADV_07a, ADV_07b,
    ADV_08,
]


@pytest.mark.eval
@pytest.mark.parametrize("case", ADVERSARIAL_CASES, ids=[c.case_id for c in ADVERSARIAL_CASES])
def test_adversarial(case: ReserveEvalCase) -> None:
    analysis, ctx = run_case(case)
    assert_case(case, analysis, ctx)


# Reference: REVIEW_AS_OF used at top-of-module so safe-harbor day-deltas match.
_ = REVIEW_AS_OF
