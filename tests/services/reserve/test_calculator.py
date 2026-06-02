"""Unit tests for the Reserve calculator.

Each test fixes inputs by hand and asserts on calculator outputs. Same inputs
must give same outputs byte-for-byte across runs — determinism is the load-
bearing property the architecture buys us.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest

from argos.schemas.workflows.reserve import (
    CrnStatus,
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
from argos.services.reserve.calculator import compute_reserve
from argos.services.reserve.constants import DEFAULT_PROGRAM


# =============================================================================
# Fixture builder — defaults a clean, minor soft-tissue, pre-suit FL claim
# =============================================================================


def _make_inputs(**overrides) -> ReserveInputs:
    defaults: dict = dict(
        accrual_date=date(2025, 6, 1),
        filing_date=None,
        fnol_date=date(2025, 6, 2),
        actual_notice_date=None,
        venue_county="hillsborough",  # neutral 1.00x venue
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


REVIEW_DATE = datetime(2026, 1, 15, 10, 0, 0)


# =============================================================================
# Minor soft-tissue clean case
# =============================================================================


def test_minor_soft_tissue_clean_case():
    inputs = _make_inputs()
    analysis, ctx = compute_reserve(
        inputs, DEFAULT_PROGRAM,
        request_id="REQ-001", reviewed_as_of=REVIEW_DATE,
    )
    # Specials: paid 3500 + wage 2000 = 5500
    assert ctx.specials.paid_satisfied == Decimal("3500.00")
    assert ctx.specials.wage_loss == Decimal("2000.00")
    assert ctx.specials.total == Decimal("5500.00")
    # Minor tier central multiplier = 1.4, venue = 1.0, threshold = 1.0 (permanency present)
    # generals central = 5500 * 1.4 * 1.0 * 1.0 = 7700
    assert ctx.generals.central == Decimal("7700.00")
    # Indemnity central (insured 100% at fault): 5500 + 7700 = 13200
    assert ctx.indemnity.central == Decimal("13200.00")
    # Pre-suit → no ALAE
    assert ctx.alae_band.p50 == 0.0
    # Within examiner authority (25K)
    assert analysis.authority_required_level == "handler"


def test_minor_no_permanency_threshold_discount():
    inputs = _make_inputs(
        permanency_status=PermanencyStatus(
            opinion_present=False,
            rating_pct=None,
            mmi_date=None,  # pre-MMI
            scarring_disfigurement=False,
            fatality=False,
        ),
    )
    analysis, ctx = compute_reserve(
        inputs, DEFAULT_PROGRAM,
        request_id="REQ-002", reviewed_as_of=REVIEW_DATE,
    )
    # Minor_soft_tissue pre-MMI gets 25% threshold discount
    assert ctx.generals.threshold_discount_pct == Decimal("25")
    # generals central = 5500 * 1.4 * 1.0 * 0.25 = 1925.00
    assert ctx.generals.central == Decimal("1925.00")


def test_mmi_reached_without_permanency_zeros_generals():
    inputs = _make_inputs(
        permanency_status=PermanencyStatus(
            opinion_present=False,
            rating_pct=None,
            mmi_date=date(2025, 12, 1),
            scarring_disfigurement=False,
            fatality=False,
        ),
    )
    analysis, ctx = compute_reserve(
        inputs, DEFAULT_PROGRAM,
        request_id="REQ-003", reviewed_as_of=REVIEW_DATE,
    )
    assert ctx.generals.threshold_discount_pct == Decimal("0")
    assert ctx.generals.central == Decimal("0.00")


def test_non_pip_compliant_tortfeasor_full_multiplier():
    """§627.737(1) carve-out: non-PIP-compliant loses threshold immunity."""
    inputs = _make_inputs(
        tortfeasor_pip_compliant=False,
        permanency_status=PermanencyStatus(
            opinion_present=False,
            mmi_date=date(2025, 12, 1),  # MMI without permanency
            scarring_disfigurement=False,
            fatality=False,
        ),
    )
    analysis, ctx = compute_reserve(
        inputs, DEFAULT_PROGRAM,
        request_id="REQ-004", reviewed_as_of=REVIEW_DATE,
    )
    assert ctx.generals.threshold_discount_pct == Decimal("100")
    assert ctx.generals.central > Decimal("0")


# =============================================================================
# Comparative bar (HB 837 §768.81)
# =============================================================================


def test_comparative_bar_fires_post_hb_837():
    """Claimant > 50% at fault on post-HB-837 filing → reserve = 0."""
    inputs = _make_inputs(
        accrual_date=date(2024, 6, 1),  # post-HB-837
        filing_date=date(2025, 1, 1),
        insured_liability_pct=Decimal("40"),  # claimant 60% — barred
    )
    analysis, ctx = compute_reserve(
        inputs, DEFAULT_PROGRAM,
        request_id="REQ-005", reviewed_as_of=REVIEW_DATE,
    )
    assert ctx.indemnity.recommended == Decimal("0")
    assert "barred" in ctx.indemnity.comparative_status


def test_comparative_pre_hb_837_no_bar():
    """Pre-HB-837 cause of action uses pure comparative — no bar."""
    inputs = _make_inputs(
        accrual_date=date(2022, 6, 1),  # pre-HB-837
        filing_date=date(2022, 12, 1),
        insured_liability_pct=Decimal("30"),  # claimant 70% — not barred pre-reform
    )
    analysis, ctx = compute_reserve(
        inputs, DEFAULT_PROGRAM,
        request_id="REQ-006", reviewed_as_of=REVIEW_DATE,
    )
    assert ctx.indemnity.recommended > Decimal("0")
    assert "pre-HB-837" in ctx.indemnity.comparative_status


def test_comparative_variance_zone_bumps_recommended():
    """40-55% liability zone → recommended posted higher (toward p90)."""
    inputs = _make_inputs(
        accrual_date=date(2024, 6, 1),
        filing_date=date(2025, 1, 1),
        insured_liability_pct=Decimal("52"),  # within variance zone
    )
    analysis, ctx = compute_reserve(
        inputs, DEFAULT_PROGRAM,
        request_id="REQ-007", reviewed_as_of=REVIEW_DATE,
    )
    # Recommended should be (central + high) / 2, between central and high
    assert ctx.indemnity.central < ctx.indemnity.recommended < ctx.indemnity.high
    assert "HIGH VARIANCE" in ctx.indemnity.comparative_status


# =============================================================================
# Specials anchoring (§768.0427 paid-vs-billed)
# =============================================================================


def test_lop_bill_anchored_at_billed_when_no_paid():
    inputs = _make_inputs(
        filing_date=date(2025, 1, 1),  # post-HB-837 — rule applies
        medical_specials=[
            MedicalBill(
                billed=Decimal("20000"),
                paid=Decimal("0"),
                payer="lop",
                provider="LOP Chiropractic",
                lop_flag=True,
                date_of_service=date(2024, 8, 1),
            ),
        ],
    )
    analysis, ctx = compute_reserve(
        inputs, DEFAULT_PROGRAM,
        request_id="REQ-008", reviewed_as_of=REVIEW_DATE,
    )
    assert ctx.specials.lop_equivalent == Decimal("20000.00")
    assert ctx.specials.paid_satisfied == Decimal("0.00")


def test_health_ins_anchored_at_paid_post_hb_837():
    inputs = _make_inputs(
        filing_date=date(2025, 1, 1),
        medical_specials=[
            MedicalBill(
                billed=Decimal("50000"),
                paid=Decimal("12000"),
                payer="health_ins",
                provider="Hospital",
                lop_flag=False,
                date_of_service=date(2024, 8, 1),
            ),
        ],
        wage_loss=None,
    )
    analysis, ctx = compute_reserve(
        inputs, DEFAULT_PROGRAM,
        request_id="REQ-009", reviewed_as_of=REVIEW_DATE,
    )
    assert ctx.specials.paid_satisfied == Decimal("12000.00")
    assert ctx.specials.total == Decimal("12000.00")


# =============================================================================
# ALAE phase budgets
# =============================================================================


def test_pre_suit_no_alae():
    inputs = _make_inputs()
    analysis, ctx = compute_reserve(
        inputs, DEFAULT_PROGRAM,
        request_id="REQ-010", reviewed_as_of=REVIEW_DATE,
    )
    assert ctx.alae_band.p50 == 0.0
    # Should not appear in per_component output
    component_names = [c.component for c in analysis.per_component]
    assert "ALAE" not in component_names


def test_alae_cumulates_through_phase():
    """ALAE at depositions = sum(answer + written_discovery + depositions)."""
    inputs = _make_inputs(
        litigation_status=LitStatus(
            phase="depositions",
            suit_served_date=date(2025, 9, 1),
            defense_counsel_assigned="Defense Firm LLP",
        ),
    )
    analysis, ctx = compute_reserve(
        inputs, DEFAULT_PROGRAM,
        request_id="REQ-011", reviewed_as_of=REVIEW_DATE,
    )
    # answer central 2500 + written 5000 + depositions 9000 = 16500
    assert ctx.alae_band.p50 == 16500.0
    component_names = [c.component for c in analysis.per_component]
    assert "ALAE" in component_names


# =============================================================================
# Catastrophic branch
# =============================================================================


def test_catastrophic_sci_capped_at_limits():
    inputs = _make_inputs(
        injury_bucket="catastrophic",
        catastrophic_indicators=["sci"],
        policy_limits=PolicyLimits(
            per_person=Decimal("500000"),
            per_occurrence=Decimal("1000000"),
            property=Decimal("50000"),
        ),
    )
    analysis, ctx = compute_reserve(
        inputs, DEFAULT_PROGRAM,
        request_id="REQ-012", reviewed_as_of=REVIEW_DATE,
    )
    # SCI band is 1.8M-5.4M — should cap at 500K per-person
    assert ctx.indemnity.recommended <= Decimal("500000")
    assert ctx.indemnity.high == Decimal("500000.00")
    assert "catastrophic" in ctx.indemnity.comparative_status
    # Catastrophic + fatality category triggers manager+
    inputs_with_fatality = _make_inputs(
        injury_bucket="catastrophic",
        catastrophic_indicators=["fatality"],
        policy_limits=inputs.policy_limits,
    )
    analysis_f, _ = compute_reserve(
        inputs_with_fatality, DEFAULT_PROGRAM,
        request_id="REQ-012b", reviewed_as_of=REVIEW_DATE,
    )
    assert analysis_f.authority_required_level == "manager"


# =============================================================================
# Notice obligations
# =============================================================================


def test_categorical_injury_triggers_reinsurance_notice():
    inputs = _make_inputs(
        injury_bucket="severe_permanent",
        catastrophic_indicators=["sci"],
        medical_specials=[
            MedicalBill(
                billed=Decimal("150000"), paid=Decimal("80000"),
                payer="health_ins", provider="Trauma Center",
                lop_flag=False, date_of_service=date(2025, 7, 1),
            ),
        ],
    )
    analysis, ctx = compute_reserve(
        inputs, DEFAULT_PROGRAM,
        request_id="REQ-013", reviewed_as_of=REVIEW_DATE,
    )
    notice_types = [n.notice_type for n in analysis.notice_obligations_triggered]
    assert "reinsurer" in notice_types


def test_dollar_threshold_triggers_reinsurance_notice():
    """Severe_permanent claim with high specials should cross $250K threshold."""
    inputs = _make_inputs(
        injury_bucket="severe_permanent",
        medical_specials=[
            MedicalBill(
                billed=Decimal("200000"), paid=Decimal("120000"),
                payer="health_ins", provider="Hospital",
                lop_flag=False, date_of_service=date(2025, 7, 1),
            ),
        ],
        wage_loss=WageLoss(
            documented_to_date=Decimal("30000"),
            occupation="laborer", employer_verified=True,
        ),
    )
    analysis, ctx = compute_reserve(
        inputs, DEFAULT_PROGRAM,
        request_id="REQ-014", reviewed_as_of=REVIEW_DATE,
    )
    # 120K specials + 30K wage = 150K. Generals central = 150K * 4.0 * 1.0 = 600K.
    # Indemnity central = 750K → way over $250K threshold.
    assert ctx.indemnity.recommended > Decimal("250000")
    notice_types = [n.notice_type for n in analysis.notice_obligations_triggered]
    assert "reinsurer" in notice_types
    assert "excess_carrier" in notice_types  # also fires on limit proximity


def test_no_notice_when_reserve_small_and_no_categorical():
    inputs = _make_inputs()  # minor case, $13K central
    analysis, _ = compute_reserve(
        inputs, DEFAULT_PROGRAM,
        request_id="REQ-015", reviewed_as_of=REVIEW_DATE,
    )
    assert len(analysis.notice_obligations_triggered) == 0


# =============================================================================
# Bad-faith markers
# =============================================================================


def test_policy_limits_demand_marker():
    inputs = _make_inputs(
        representation_status=RepStatus(
            represented=True,
            firm_name="Plaintiff Firm",
            rep_date=date(2025, 8, 1),
            demand_received=True,
            demand_date=date(2025, 9, 1),
            demand_amount=Decimal("100000"),
            policy_limits_demand=True,
            time_demand_deadline=date(2025, 10, 1),
        ),
    )
    _, ctx = compute_reserve(
        inputs, DEFAULT_PROGRAM,
        request_id="REQ-016", reviewed_as_of=REVIEW_DATE,
    )
    assert "policy_limits_demand_received" in ctx.bad_faith_markers.active
    assert "time_demand_with_deadline" in ctx.bad_faith_markers.active
    assert "represented_by_counsel" in ctx.bad_faith_markers.active


def test_crn_filed_cure_window_countdown():
    crn = CrnStatus(
        filed_date=date(2026, 1, 5),
        alleged_violation="failure to tender within safe harbor",
        demanded_amount=Decimal("100000"),
        cure_deadline=date(2026, 3, 6),  # 60 days from filing
    )
    inputs = _make_inputs(crn_status=crn)
    # Reviewing on 2026-01-15 → 50 days remaining
    _, ctx = compute_reserve(
        inputs, DEFAULT_PROGRAM,
        request_id="REQ-017", reviewed_as_of=REVIEW_DATE,
    )
    assert "crn_filed" in ctx.bad_faith_markers.active
    assert ctx.bad_faith_markers.crn_days_remaining == 50
    assert "50 days remaining" in ctx.bad_faith_markers.crn_status


def test_safe_harbor_clock_expired():
    inputs = _make_inputs(
        actual_notice_date=date(2025, 9, 1),  # 136 days before REVIEW_DATE
        representation_status=RepStatus(
            represented=True,
            policy_limits_demand=True,
        ),
    )
    _, ctx = compute_reserve(
        inputs, DEFAULT_PROGRAM,
        request_id="REQ-018", reviewed_as_of=REVIEW_DATE,
    )
    assert "safe_harbor_clock_expired_without_tender" in ctx.bad_faith_markers.active
    assert "EXPIRED" in ctx.bad_faith_markers.safe_harbor_status


# =============================================================================
# Stair-step detector
# =============================================================================


def test_stair_step_detected():
    """3+ small upward revisions in 90 days → flag."""
    snapshots = [
        ReserveSnapshot(
            eval_date=date(2025, 11, 1), indemnity=Decimal("10000"),
            alae=Decimal("0"), basis="initial reserve",
        ),
        ReserveSnapshot(
            eval_date=date(2025, 11, 15), indemnity=Decimal("11000"),
            alae=Decimal("0"), basis="new bill received",
        ),
        ReserveSnapshot(
            eval_date=date(2025, 12, 1), indemnity=Decimal("12000"),
            alae=Decimal("0"), basis="new bill received",
        ),
        ReserveSnapshot(
            eval_date=date(2025, 12, 20), indemnity=Decimal("13000"),
            alae=Decimal("0"), basis="new bill received",
        ),
    ]
    inputs = _make_inputs(prior_reserve_history=snapshots)
    _, ctx = compute_reserve(
        inputs, DEFAULT_PROGRAM,
        request_id="REQ-019", reviewed_as_of=REVIEW_DATE,
    )
    assert ctx.stair_step.flagged
    assert "stair-step" in ctx.stair_step.reason.lower() or "small upward" in ctx.stair_step.reason


def test_large_revisions_not_flagged_as_stair_step():
    snapshots = [
        ReserveSnapshot(
            eval_date=date(2025, 11, 1), indemnity=Decimal("10000"),
            alae=Decimal("0"), basis="initial",
        ),
        ReserveSnapshot(
            eval_date=date(2025, 12, 1), indemnity=Decimal("50000"),
            alae=Decimal("0"), basis="surgery scheduled",
        ),
        ReserveSnapshot(
            eval_date=date(2026, 1, 1), indemnity=Decimal("100000"),
            alae=Decimal("0"), basis="MMI declared with permanency",
        ),
    ]
    inputs = _make_inputs(prior_reserve_history=snapshots)
    _, ctx = compute_reserve(
        inputs, DEFAULT_PROGRAM,
        request_id="REQ-020", reviewed_as_of=REVIEW_DATE,
    )
    assert not ctx.stair_step.flagged


# =============================================================================
# Authority routing
# =============================================================================


def test_authority_handler_for_small_reserve():
    inputs = _make_inputs()  # $13K central
    analysis, _ = compute_reserve(
        inputs, DEFAULT_PROGRAM,
        request_id="REQ-021", reviewed_as_of=REVIEW_DATE,
    )
    assert analysis.authority_required_level == "handler"


def test_authority_supervisor_band():
    """Reserve $25K-$75K → supervisor band."""
    inputs = _make_inputs(
        injury_bucket="moderate_ortho_non_surgical",
        medical_specials=[
            MedicalBill(
                billed=Decimal("18000"), paid=Decimal("18000"),
                payer="health_ins", provider="Ortho",
                lop_flag=False, date_of_service=date(2025, 7, 1),
            ),
        ],
        wage_loss=None,
    )
    analysis, ctx = compute_reserve(
        inputs, DEFAULT_PROGRAM,
        request_id="REQ-022", reviewed_as_of=REVIEW_DATE,
    )
    # 18000 * 2.0 = 36000 generals; +18000 = 54000 indemnity
    assert Decimal("25000") < ctx.indemnity.recommended < Decimal("75000")
    assert analysis.authority_required_level == "supervisor"


def test_authority_client_level_for_limits_exposed():
    inputs = _make_inputs(
        injury_bucket="severe_permanent",
        catastrophic_indicators=["amputation"],  # in mandatory_referral
    )
    analysis, _ = compute_reserve(
        inputs, DEFAULT_PROGRAM,
        request_id="REQ-023", reviewed_as_of=REVIEW_DATE,
    )
    # Categorical mandatory referral overrides dollar bands
    assert analysis.authority_required_level == "manager"


# =============================================================================
# Determinism
# =============================================================================


def test_same_inputs_same_outputs_byte_for_byte():
    inputs = _make_inputs()
    a1, _ = compute_reserve(
        inputs, DEFAULT_PROGRAM,
        request_id="REQ-024", reviewed_as_of=REVIEW_DATE,
    )
    a2, _ = compute_reserve(
        inputs, DEFAULT_PROGRAM,
        request_id="REQ-024", reviewed_as_of=REVIEW_DATE,
    )
    assert a1.model_dump_json() == a2.model_dump_json()


# =============================================================================
# No-change detection
# =============================================================================


def test_no_change_warranted_when_delta_small_and_quiet():
    """Small delta + no notices + no markers → no_change_warranted=True."""
    inputs = _make_inputs(
        prior_reserve_history=[
            ReserveSnapshot(
                eval_date=date(2025, 12, 1),
                indemnity=Decimal("13000"),
                alae=Decimal("0"),
                basis="prior eval — minor recovery on track",
            ),
        ],
    )
    analysis, _ = compute_reserve(
        inputs, DEFAULT_PROGRAM,
        request_id="REQ-025", reviewed_as_of=REVIEW_DATE,
    )
    assert analysis.no_change_warranted is True
