"""Calculator — recommendation lattice + authority routing tests."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from argos.schemas.workflows.closure import (
    LienRecord,
    PowellAnalysis,
)
from argos.services.closure import (
    DEFAULT_PROGRAM,
    apply_fl_closure_gates,
    build_closure_assessment,
)
from tests.services.closure._fixtures import EVAL_TODAY, make_inputs, make_upstream


def _build(inputs, upstream=None):
    upstream = upstream or make_upstream()
    doc = apply_fl_closure_gates(inputs, upstream, DEFAULT_PROGRAM, today=EVAL_TODAY)
    return build_closure_assessment(
        inputs,
        upstream,
        DEFAULT_PROGRAM,
        doc,
        request_id="REQ-test",
        today=EVAL_TODAY,
        reviewed_as_of=datetime(2026, 6, 2, 10, 0, tzinfo=timezone.utc),
    )


def test_clean_path_recommends_ready_to_close_with_payment():
    assessment = _build(make_inputs())
    assert assessment.recommendation == "ready_to_close_with_payment"
    assert assessment.ready_probability >= 0.9
    assert assessment.indemnity_status == "ready"
    assert assessment.oir_classification == "closed_with_payment"


def test_ready_probability_capped_by_tier_a_failure():
    inputs = make_inputs(coverage_decision="uncommitted")
    upstream = make_upstream(coverage_committed=False, coverage_decision="uncommitted")
    assessment = _build(inputs, upstream)
    assert assessment.ready_probability <= 0.10
    assert any(d.tier == "A" for d in assessment.blocking_defects)


def test_blocked_by_defects_when_tier_a_fails():
    inputs = make_inputs(coverage_decision="uncommitted")
    upstream = make_upstream(coverage_committed=False, coverage_decision="uncommitted")
    assessment = _build(inputs, upstream)
    assert assessment.recommendation in {"blocked_by_defects", "requires_senior_review"}


def test_soft_close_pending_medicare_final_demand():
    inputs = make_inputs(
        medicare_beneficiary_identified=True,
        settlement_amount=Decimal("5000"),
    )
    assessment = _build(inputs)
    # Only Medicare gate fails on clean path → soft-close
    assert assessment.recommendation == "soft_close_pending_medicare_final_demand"
    assert assessment.indemnity_status == "soft_closed_pending"


def test_soft_close_pending_lien_release_letter():
    # FL Medicaid identified, no release on file — only lien gate fails.
    inputs = make_inputs(
        medicaid_beneficiary_identified=True,
        liens=[LienRecord(kind="florida_medicaid", release_letter_on_file=False)],
    )
    assessment = _build(inputs)
    assert assessment.recommendation == "soft_close_pending_lien_release_letter"


def test_closed_with_open_recovery_when_recovery_pursued():
    inputs = make_inputs()
    upstream = make_upstream(recovery_pursuit="pursue", recovery_committed=True)
    assessment = _build(inputs, upstream)
    assert assessment.recommendation == "closed_with_open_recovery"
    assert assessment.indemnity_status == "closed"


def test_authority_routing_examiner_path():
    inputs = make_inputs(settlement_amount=Decimal("15000"))
    assessment = _build(inputs)
    assert assessment.authority_tier_required.required_tier == "examiner"
    assert assessment.authority_tier_required.committable_at_examiner


def test_authority_routing_supervisor_band():
    inputs = make_inputs(settlement_amount=Decimal("100000"))
    upstream = make_upstream()
    assessment = _build(inputs, upstream)
    # $100k > examiner ($25k) and > senior ($75k), <= supervisor ($250k)
    assert assessment.authority_tier_required.required_tier == "supervisor"
    assert not assessment.authority_tier_required.committable_at_examiner


def test_open_defense_track_bifurcates_indemnity_defense():
    inputs = make_inputs(
        interpleader_indemnity_deposited=True,
        underlying_tort_actions_unresolved=True,
    )
    assessment = _build(inputs)
    # legal review override fires when open_defense_track gate is set
    assert assessment.recommendation == "requires_legal_review"
    assert assessment.indemnity_status == "closed"
    assert assessment.defense_status == "open"


def test_powell_unfulfilled_routes_to_legal_review():
    inputs = make_inputs(
        powell_analysis=PowellAnalysis(
            liability_clear=True,
            damages_plausibly_exceed_limits=True,
            affirmative_policy_limits_offer_made=False,
            why_powell_does_not_apply_memo_on_file=False,
        ),
    )
    assessment = _build(inputs)
    assert assessment.recommendation == "requires_legal_review"


def test_blocking_defects_ranked_a_before_b():
    # Combine an A failure (coverage uncommitted) with a B failure (Medicare).
    inputs = make_inputs(
        coverage_decision="uncommitted",
        medicare_beneficiary_identified=True,
        settlement_amount=Decimal("5000"),
    )
    upstream = make_upstream(coverage_committed=False, coverage_decision="uncommitted")
    assessment = _build(inputs, upstream)
    if assessment.blocking_defects:
        tiers = [d.tier for d in assessment.blocking_defects]
        # First failure tier should be A (or whichever is earliest in rank).
        assert tiers[0] == "A"
