"""Rationale renderer tests — determinism + structural shape.

The full golden-file diff lives in test_rationale_golden.py; here we assert
on the structural skeleton + key sections to catch regressions cheaply.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from argos.schemas.workflows.reserve import (
    LitStatus,
    MedicalBill,
    PermanencyStatus,
    PipStatus,
    PolicyLimits,
    RepStatus,
    ReserveInputs,
    WageLoss,
)
from argos.services.reserve.calculator import compute_reserve
from argos.services.reserve.constants import DEFAULT_PROGRAM
from argos.services.reserve.rationale import render_reserve_rationale


REVIEW_DATE = datetime(2026, 1, 15, 10, 0, 0)


def _baseline_inputs() -> ReserveInputs:
    return ReserveInputs(
        accrual_date=date(2025, 6, 1),
        filing_date=None,
        fnol_date=date(2025, 6, 2),
        actual_notice_date=None,
        venue_county="hillsborough",
        policy_limits=PolicyLimits(
            per_person=Decimal("100000"),
            per_occurrence=Decimal("300000"),
            property=Decimal("50000"),
        ),
        claimant_count=1,
        insured_liability_pct=Decimal("100"),
        tortfeasor_pip_compliant=True,
        pip_status=PipStatus(
            cap_applicable=10000, paid_to_date=Decimal("8000"),
            exhausted=False, emc_determination=True,
            treatment_within_14_days=True,
        ),
        permanency_status=PermanencyStatus(
            opinion_present=True, rating_pct=Decimal("5"),
            mmi_date=date(2025, 12, 1),
            scarring_disfigurement=False, fatality=False,
        ),
        medical_specials=[
            MedicalBill(
                billed=Decimal("8000"), paid=Decimal("3500"),
                payer="health_ins", provider="St. Lukes ER",
                lop_flag=False, date_of_service=date(2025, 6, 2),
            ),
        ],
        wage_loss=WageLoss(
            documented_to_date=Decimal("2000"),
            occupation="server", employer_verified=True,
        ),
        injury_bucket="minor_soft_tissue",
        representation_status=RepStatus(represented=False),
        litigation_status=LitStatus(phase="pre_suit"),
    )


def test_rationale_contains_required_sections():
    inputs = _baseline_inputs()
    _, ctx = compute_reserve(
        inputs, DEFAULT_PROGRAM,
        request_id="REQ-R1", reviewed_as_of=REVIEW_DATE,
    )
    out = render_reserve_rationale(
        ctx, claim_id="CLM-001", eval_seq=1,
        trigger_name="FNOL_INITIAL_RESERVE",
        trigger_event_date=datetime(2025, 6, 2, 9, 0, 0),
        examiner_id="EXM-42",
    )
    # Header sections
    assert "RESERVE EVALUATION — Claim CLM-001" in out
    assert "Eval #1" in out
    assert "TRIGGER: FNOL_INITIAL_RESERVE" in out
    # Required sections
    for section in [
        "LIABILITY:", "PIP/THRESHOLD:", "SPECIALS",
        "GENERALS:", "INDEMNITY RESERVE", "ALAE",
        "ULAE: not allocated",
        "AUTHORITY:", "BAD-FAITH RISK MARKERS",
        "§624.155(4) 90-day safe harbor",
        "§624.155(3) 60-day CRN cure",
    ]:
        assert section in out, f"missing section: {section!r}"


def test_rationale_is_deterministic():
    inputs = _baseline_inputs()
    _, ctx = compute_reserve(
        inputs, DEFAULT_PROGRAM,
        request_id="REQ-R2", reviewed_as_of=REVIEW_DATE,
    )
    out1 = render_reserve_rationale(
        ctx, claim_id="CLM-001", eval_seq=1,
        trigger_name="FNOL_INITIAL_RESERVE",
        trigger_event_date=datetime(2025, 6, 2, 9, 0, 0),
    )
    out2 = render_reserve_rationale(
        ctx, claim_id="CLM-001", eval_seq=1,
        trigger_name="FNOL_INITIAL_RESERVE",
        trigger_event_date=datetime(2025, 6, 2, 9, 0, 0),
    )
    assert out1 == out2


def test_rationale_catastrophic_branch():
    inputs = _baseline_inputs()
    inputs = inputs.model_copy(update=dict(
        injury_bucket="catastrophic",
        catastrophic_indicators=["sci"],
    ))
    _, ctx = compute_reserve(
        inputs, DEFAULT_PROGRAM,
        request_id="REQ-R3", reviewed_as_of=REVIEW_DATE,
    )
    out = render_reserve_rationale(
        ctx, claim_id="CLM-CAT", eval_seq=1,
        trigger_name="CATASTROPHIC_INJURY_FLAG",
        trigger_event_date=datetime(2025, 6, 2, 9, 0, 0),
    )
    assert "catastrophic — life-care-plan estimator" in out
    assert "Catastrophic indicators: sci" in out
    # Reinsurance notice should fire on categorical
    assert "TRIGGERED" in out and "reinsurer" in out


def test_rationale_no_change_quiet():
    """Quiet reserve produces clean rationale without notice/marker noise."""
    inputs = _baseline_inputs()
    _, ctx = compute_reserve(
        inputs, DEFAULT_PROGRAM,
        request_id="REQ-R4", reviewed_as_of=REVIEW_DATE,
    )
    out = render_reserve_rationale(
        ctx, claim_id="CLM-001", eval_seq=1,
        trigger_name="CALENDAR_DIARY_90_DAY",
        trigger_event_date=datetime(2026, 1, 15, 0, 0, 0),
    )
    assert "Reinsurance/excess notice: not triggered" in out
    assert "BAD-FAITH RISK MARKERS (0 active): none" in out
