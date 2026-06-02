"""Closure — adversarial / boundary probes (8 sub-cases)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from argos.schemas.workflows.closure import (
    CrnRecord,
    LienRecord,
    PowellAnalysis,
)
from tests.evals.closure._harness import (
    EVAL_TODAY,
    ClosureEvalCase,
    assert_case,
    run_case,
)
from tests.services.closure._fixtures import make_inputs, make_upstream


# ---------------------------------------------------------------------------
# ADV-01 — Tier A fail → ready_probability = 0.05 (not 0.06)
# ---------------------------------------------------------------------------

ADV_01 = ClosureEvalCase(
    case_id="ADV-01",
    description="Tier A fail → ready_probability exactly 0.05",
    inputs=make_inputs(coverage_decision="uncommitted"),
    upstream=make_upstream(
        coverage_committed=False, coverage_decision="uncommitted",
    ),
    expected_ready_probability=0.05,
    expected_defect_tiers_include={"A"},
)


# ---------------------------------------------------------------------------
# ADV-02 — Tier B fail only (no A) → cap = 0.25
# Medicare beneficiary + settlement ≥ $750 + no Medicare release on file
# → both `medicare_msp_unresolved` and `section_111_tpoc_unreported` fire
# (both Tier B). No Tier A, no Tier C.
# ---------------------------------------------------------------------------

ADV_02 = ClosureEvalCase(
    case_id="ADV-02",
    description="Tier B fail only → cap = 0.25 (no Tier A)",
    inputs=make_inputs(medicare_beneficiary_identified=True),
    upstream=make_upstream(),
    expected_ready_probability=0.25,
    expected_defect_tiers_include={"B"},
    # Sanity: no Tier A failures
)
ADV_02.expected_defect_gate_ids_include = {
    "medicare_msp_unresolved",
    "section_111_tpoc_unreported",
}


# ---------------------------------------------------------------------------
# ADV-03 — Tier C fail only (no A/B) → cap = 0.50
# release_executed_date=None; agreement_date recent so §627.4265 stays pass
# (default check_tendered_date is set, so A9 logic skips both branches).
# ---------------------------------------------------------------------------

ADV_03 = ClosureEvalCase(
    case_id="ADV-03",
    description="Tier C fail only → cap = 0.50 (release missing, no §627.4265 fail)",
    inputs=make_inputs(release_executed_date=None),
    upstream=make_upstream(),
    expected_ready_probability=0.50,
    expected_defect_gate_ids={"missing_signed_release"},
    expected_defect_tiers_include={"C"},
    expected_recommendation="soft_close_pending_release_execution",
)


# ---------------------------------------------------------------------------
# ADV-04 — Tier A + Tier C fail → A wins (cap = 0.05)
# ---------------------------------------------------------------------------

ADV_04 = ClosureEvalCase(
    case_id="ADV-04",
    description="Tier A + Tier C fail → A wins (worst-tier ordering)",
    inputs=make_inputs(
        coverage_decision="uncommitted",
        release_executed_date=None,
    ),
    upstream=make_upstream(
        coverage_committed=False, coverage_decision="uncommitted",
    ),
    expected_ready_probability=0.05,
    expected_defect_tiers_include={"A", "C"},
    expected_recommendation="blocked_by_defects",
)


# ---------------------------------------------------------------------------
# ADV-05a — CRN cure-window day-edge: day 59 (in window → fail, strict `<`)
# ---------------------------------------------------------------------------

ADV_05a = ClosureEvalCase(
    case_id="ADV-05a",
    description="CRN at day 59 of cure window (strict `<` 60) → fail",
    inputs=make_inputs(
        open_crns=[
            CrnRecord(
                crn_id="CRN-1",
                dfs_filing_date=date(2026, 4, 4),  # ~59 days before 2026-06-02
                days_since_dfs_filing=59,
                cure_status="uncured",
            ),
        ],
    ),
    upstream=make_upstream(),
    expected_gate_results={"open_crn_within_cure_window": "fail"},
)


# ---------------------------------------------------------------------------
# ADV-05b — CRN cure-window day-edge: day 60 (boundary OUT of strict `<`)
# Code: `if crn.days_since_dfs_filing < CRN_CURE_WINDOW_DAYS` where window=60.
# 60 is NOT < 60 → gate should NOT fail.
# ---------------------------------------------------------------------------

ADV_05b = ClosureEvalCase(
    case_id="ADV-05b",
    description="CRN at day 60 (NOT strict `<` 60) → gate does NOT fail",
    inputs=make_inputs(
        open_crns=[
            CrnRecord(
                crn_id="CRN-2",
                dfs_filing_date=date(2026, 4, 3),
                days_since_dfs_filing=60,
                cure_status="uncured",
            ),
        ],
    ),
    upstream=make_upstream(),
    expected_gate_results={"open_crn_within_cure_window": "pass"},
)


# ---------------------------------------------------------------------------
# ADV-06 — Authority dollar boundary: settlement = exactly $25K (examiner cap)
# `_route_authority` uses `≤` → exactly $25K should be committable_at_examiner.
# ---------------------------------------------------------------------------

ADV_06 = ClosureEvalCase(
    case_id="ADV-06",
    description="Authority `≤` boundary: $25K exactly committable at examiner",
    inputs=make_inputs(settlement_amount=Decimal("25000")),
    upstream=make_upstream(),
    expected_authority_tier="examiner",
    expected_committable_at_examiner=True,
    expected_settlement_amount=Decimal("25000"),
)


# ---------------------------------------------------------------------------
# ADV-07 — Powell-unfulfilled fail → requires_legal_review precedence
# Triggered: liability_clear + damages exceed limits + no offer/memo.
# Even with no other defects, recommendation routes to legal review (lattice
# item 2 wins over senior-review, soft-close, ready-to-close).
# ---------------------------------------------------------------------------

ADV_07 = ClosureEvalCase(
    case_id="ADV-07",
    description="Powell-unfulfilled fail → requires_legal_review (lattice precedence)",
    inputs=make_inputs(
        powell_analysis=PowellAnalysis(
            liability_clear=True,
            damages_plausibly_exceed_limits=True,
            affirmative_policy_limits_offer_made=False,
            why_powell_does_not_apply_memo_on_file=False,
        ),
    ),
    upstream=make_upstream(),
    expected_recommendation="requires_legal_review",
    expected_defect_gate_ids_include={"powell_duty_unfulfilled"},
)


# ---------------------------------------------------------------------------
# ADV-08 — Medicare + lien (Florida Medicaid) both fail → mixed → blocked
# `medicare_only` is strict-subset of {medicare_msp_unresolved,
# section_111_tpoc_unreported}; lien gate is OUT-of-set → routes to
# blocked_by_defects, NOT to soft_close_pending_medicare_final_demand
# and NOT to soft_close_pending_lien_release_letter.
# ---------------------------------------------------------------------------

ADV_08 = ClosureEvalCase(
    case_id="ADV-08",
    description="Mixed Medicare + lien fail → NOT a soft-close path",
    inputs=make_inputs(
        medicare_beneficiary_identified=True,
        medicaid_beneficiary_identified=True,
        liens=[
            LienRecord(
                kind="florida_medicaid",
                payer_name="AHCA",
                status="response_received_pending_resolution",
            ),
        ],
    ),
    upstream=make_upstream(),
    expected_recommendation="blocked_by_defects",
    expected_defect_gate_ids_include={
        "medicare_msp_unresolved",
        "florida_medicaid_lien_unresolved",
    },
)


ADV_CASES = [
    ADV_01, ADV_02, ADV_03, ADV_04,
    ADV_05a, ADV_05b, ADV_06, ADV_07, ADV_08,
]


@pytest.mark.eval
@pytest.mark.parametrize("case", ADV_CASES, ids=[c.case_id for c in ADV_CASES])
def test_adversarial(case: ClosureEvalCase) -> None:
    a = run_case(case)
    assert_case(case, a)


_ = EVAL_TODAY
