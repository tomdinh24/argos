"""Policy engine — per-gate evaluation tests."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from argos.schemas.workflows.closure import (
    CrnRecord,
    DenialLetterAudit,
    LienRecord,
    MultiClaimantState,
    OutboundRequestRef,
    PowellAnalysis,
    Section_627_4137_AffidavitState,
)
from argos.services.closure import DEFAULT_PROGRAM, apply_fl_closure_gates
from tests.services.closure._fixtures import EVAL_TODAY, make_inputs, make_upstream


def _gate(doc, gate_id):
    for g in doc.gates:
        if g.gate_id == gate_id:
            return g
    raise AssertionError(f"gate {gate_id} not found")


def test_clean_path_no_tier_a_failures():
    inputs = make_inputs()
    upstream = make_upstream()
    doc = apply_fl_closure_gates(inputs, upstream, DEFAULT_PROGRAM, today=EVAL_TODAY)
    assert doc.any_tier_a_failure is False
    # Most A gates pass or are n_a on the clean path.
    fails_a = [g for g in doc.gates if g.tier == "A" and g.result == "fail"]
    assert fails_a == []


def test_coverage_decision_uncommitted_fails():
    inputs = make_inputs(coverage_decision="uncommitted")
    upstream = make_upstream(coverage_committed=False, coverage_decision="uncommitted")
    doc = apply_fl_closure_gates(inputs, upstream, DEFAULT_PROGRAM, today=EVAL_TODAY)
    g = _gate(doc, "coverage_decision_uncommitted")
    assert g.result == "fail"
    assert doc.any_tier_a_failure


def test_denial_letter_deficient_when_closing_without_payment():
    inputs = make_inputs(
        intended_closure_intent="without_payment",
        denial_letter_audit=DenialLetterAudit(
            on_file=True,
            cites_policy_provision=True,
            cites_facts=False,  # missing
            cites_applicable_law=True,
        ),
        settlement_amount=Decimal("0"),
        settlement_agreement_date=None,
        release_executed_date=None,
        check_tendered_date=None,
    )
    upstream = make_upstream(coverage_decision="denied")
    doc = apply_fl_closure_gates(inputs, upstream, DEFAULT_PROGRAM, today=EVAL_TODAY)
    g = _gate(doc, "denial_letter_deficient")
    assert g.result == "fail"


def test_denial_letter_n_a_when_closing_with_payment():
    inputs = make_inputs()
    doc = apply_fl_closure_gates(inputs, make_upstream(), DEFAULT_PROGRAM, today=EVAL_TODAY)
    g = _gate(doc, "denial_letter_deficient")
    assert g.result == "n_a"


def test_open_crn_in_cure_window_blocks():
    crn = CrnRecord(
        crn_id="CRN-1",
        dfs_filing_date=EVAL_TODAY - timedelta(days=15),
        days_since_dfs_filing=15,
        alleged_statutory_violations=["§624.155(1)(b)1"],
        cure_status="uncured",
    )
    inputs = make_inputs(open_crns=[crn])
    doc = apply_fl_closure_gates(inputs, make_upstream(), DEFAULT_PROGRAM, today=EVAL_TODAY)
    g = _gate(doc, "open_crn_within_cure_window")
    assert g.result == "fail"


def test_third_party_safe_harbor_window_expired_unotendered():
    notice = EVAL_TODAY - timedelta(days=120)  # past 90-day window
    inputs = make_inputs(
        powell_analysis=PowellAnalysis(
            liability_clear=True,
            damages_plausibly_exceed_limits=True,
        ),
    )
    inputs.third_party_safe_harbor_tender_made = False
    inputs.claim_first_actual_notice_date = notice
    doc = apply_fl_closure_gates(inputs, make_upstream(), DEFAULT_PROGRAM, today=EVAL_TODAY)
    g = _gate(doc, "third_party_safe_harbor_window_expiring_unotendered")
    assert g.result == "fail"


def test_multi_claimant_no_safe_harbor_invoked_fails_after_window():
    mc = MultiClaimantState(
        is_multi_claimant=True,
        competing_demands_exceed_aggregate=True,
        days_since_competing_claims_notice=120,
        interpleader_filed=False,
        binding_arbitration_submitted=False,
    )
    inputs = make_inputs(multi_claimant_state=mc)
    doc = apply_fl_closure_gates(inputs, make_upstream(), DEFAULT_PROGRAM, today=EVAL_TODAY)
    g = _gate(doc, "multi_claimant_safe_harbor_not_invoked")
    assert g.result == "fail"


def test_section_627_4137_affidavit_missing():
    aff = Section_627_4137_AffidavitState(
        claimant_written_request_on_file=True,
        claimant_request_date=EVAL_TODAY - timedelta(days=60),
        affidavit_delivered=False,
    )
    inputs = make_inputs(section_627_4137_state=aff)
    doc = apply_fl_closure_gates(inputs, make_upstream(), DEFAULT_PROGRAM, today=EVAL_TODAY)
    g = _gate(doc, "section_627_4137_affidavit_missing_or_stale")
    assert g.result == "fail"


def test_section_627_4265_tender_window_violated():
    inputs = make_inputs(
        settlement_agreement_date=EVAL_TODAY - timedelta(days=30),
        check_tendered_date=None,
    )
    doc = apply_fl_closure_gates(inputs, make_upstream(), DEFAULT_PROGRAM, today=EVAL_TODAY)
    g = _gate(doc, "section_627_4265_tender_window_violated")
    assert g.result == "fail"


def test_medicare_msp_unresolved_blocks():
    inputs = make_inputs(
        medicare_beneficiary_identified=True,
        settlement_amount=Decimal("5000"),
    )
    doc = apply_fl_closure_gates(inputs, make_upstream(), DEFAULT_PROGRAM, today=EVAL_TODAY)
    g = _gate(doc, "medicare_msp_unresolved")
    assert g.result == "fail"


def test_medicare_msp_n_a_below_threshold():
    inputs = make_inputs(
        medicare_beneficiary_identified=True,
        settlement_amount=Decimal("500"),
    )
    doc = apply_fl_closure_gates(inputs, make_upstream(), DEFAULT_PROGRAM, today=EVAL_TODAY)
    g = _gate(doc, "medicare_msp_unresolved")
    assert g.result == "n_a"


def test_outstanding_obr_with_legal_weight_fails():
    obr = OutboundRequestRef(obr_id="OBR-1", legal_weight="legally_required", days_open=10)
    inputs = make_inputs(open_obrs=[obr])
    doc = apply_fl_closure_gates(inputs, make_upstream(), DEFAULT_PROGRAM, today=EVAL_TODAY)
    g = _gate(doc, "outstanding_obr_with_legal_weight")
    assert g.result == "fail"


def test_outstanding_obr_informational_passes():
    obr = OutboundRequestRef(obr_id="OBR-1", legal_weight="informational", days_open=10)
    inputs = make_inputs(open_obrs=[obr])
    doc = apply_fl_closure_gates(inputs, make_upstream(), DEFAULT_PROGRAM, today=EVAL_TODAY)
    g = _gate(doc, "outstanding_obr_with_legal_weight")
    assert g.result == "pass"


def test_settlement_authority_exceeded_when_above_examiner():
    inputs = make_inputs(settlement_amount=Decimal("100000"))
    doc = apply_fl_closure_gates(inputs, make_upstream(), DEFAULT_PROGRAM, today=EVAL_TODAY)
    g = _gate(doc, "settlement_authority_exceeded")
    assert g.result == "fail"


def test_open_defense_track_post_interpleader():
    inputs = make_inputs(
        interpleader_indemnity_deposited=True,
        underlying_tort_actions_unresolved=True,
    )
    doc = apply_fl_closure_gates(inputs, make_upstream(), DEFAULT_PROGRAM, today=EVAL_TODAY)
    g = _gate(doc, "open_defense_track_post_interpleader")
    assert g.result == "fail"


def test_preservation_until_far_in_future():
    inputs = make_inputs(loss_date=date(2025, 6, 2))
    doc = apply_fl_closure_gates(inputs, make_upstream(), DEFAULT_PROGRAM, today=EVAL_TODAY)
    # FL admin code floor: today + 3y → 2029
    assert doc.preservation_until_date is not None
    assert doc.preservation_until_date >= date(2029, 1, 1)


def test_florida_medicaid_lien_resolved():
    lien = LienRecord(kind="florida_medicaid", release_letter_on_file=True)
    inputs = make_inputs(medicaid_beneficiary_identified=True, liens=[lien])
    doc = apply_fl_closure_gates(inputs, make_upstream(), DEFAULT_PROGRAM, today=EVAL_TODAY)
    g = _gate(doc, "florida_medicaid_lien_unresolved")
    assert g.result == "pass"


def test_florida_medicaid_lien_unresolved_fails():
    inputs = make_inputs(medicaid_beneficiary_identified=True)
    doc = apply_fl_closure_gates(inputs, make_upstream(), DEFAULT_PROGRAM, today=EVAL_TODAY)
    g = _gate(doc, "florida_medicaid_lien_unresolved")
    assert g.result == "fail"
