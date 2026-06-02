"""Diligence-ledger enrichment + rationale-rendering tests."""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from argos.schemas.workflows.closure import (
    CrnRecord,
    LienRecord,
    MultiClaimantState,
    Section_627_4137_AffidavitState,
)
from argos.services.closure import (
    DEFAULT_PROGRAM,
    apply_fl_closure_gates,
    build_closure_assessment,
    enrich_diligence_ledger,
    finalize_assessment,
)
from tests.services.closure._fixtures import EVAL_TODAY, make_inputs, make_upstream


def _assess(inputs, upstream=None):
    upstream = upstream or make_upstream()
    doc = apply_fl_closure_gates(inputs, upstream, DEFAULT_PROGRAM, today=EVAL_TODAY)
    return build_closure_assessment(
        inputs, upstream, DEFAULT_PROGRAM, doc,
        request_id="REQ-test",
        today=EVAL_TODAY,
        reviewed_as_of=datetime(2026, 6, 2, 10, 0, tzinfo=timezone.utc),
    )


def test_ledger_enrichment_picks_oldest_crn():
    crn_old = CrnRecord(
        crn_id="CRN-old",
        dfs_filing_date=date(2026, 1, 1),
        days_since_dfs_filing=150,
        alleged_statutory_violations=["§624.155(1)(b)1"],
        cure_status="uncured",
    )
    crn_new = CrnRecord(
        crn_id="CRN-new",
        dfs_filing_date=date(2026, 5, 1),
        days_since_dfs_filing=30,
        cure_status="uncured",
    )
    inputs = make_inputs(open_crns=[crn_new, crn_old])
    assessment = _assess(inputs)
    ledger = enrich_diligence_ledger(assessment, inputs)
    assert ledger.crn_state is not None
    assert ledger.crn_state.crn_id == "CRN-old"


def test_ledger_enrichment_lists_lien_records():
    liens = [
        LienRecord(kind="medicare_conditional_payment", release_letter_on_file=False),
        LienRecord(kind="florida_medicaid", release_letter_on_file=True),
    ]
    inputs = make_inputs(liens=liens)
    assessment = _assess(inputs)
    ledger = enrich_diligence_ledger(assessment, inputs)
    assert len(ledger.lien_resolution_records) == 2
    assert any(l.release_letter_on_file for l in ledger.lien_resolution_records)


def test_ledger_enrichment_logs_multi_claimant_artifacts():
    mc = MultiClaimantState(
        is_multi_claimant=True,
        global_tender_letter_sent_to_all_claimants=True,
        per_claimant_responses_logged=True,
        priority_memo_on_file=False,
        insured_notice_of_strategy_on_file=True,
    )
    inputs = make_inputs(multi_claimant_state=mc)
    assessment = _assess(inputs)
    ledger = enrich_diligence_ledger(assessment, inputs)
    assert ledger.multi_claimant_artifacts is not None
    assert ledger.multi_claimant_artifacts.priority_memo_on_file is False


def test_ledger_enrichment_records_4137_affidavit():
    aff = Section_627_4137_AffidavitState(
        claimant_written_request_on_file=True,
        claimant_request_date=date(2026, 4, 1),
        affidavit_delivered=True,
        affidavit_delivery_date=date(2026, 4, 20),
    )
    inputs = make_inputs(section_627_4137_state=aff)
    assessment = _assess(inputs)
    ledger = enrich_diligence_ledger(assessment, inputs)
    kinds = [n.notice_kind for n in ledger.notice_delivery_audit]
    assert "section_627_4137_affidavit" in kinds


def test_rationale_text_includes_version_and_recommendation():
    inputs = make_inputs()
    assessment = _assess(inputs)
    final = finalize_assessment(assessment)
    assert "v1." in final.rationale_text
    assert "Ready to close" in final.rationale_text
    assert "Authority required" in final.rationale_text


def test_rationale_text_lists_blocking_defects():
    inputs = make_inputs(
        coverage_decision="uncommitted",
        medicare_beneficiary_identified=True,
        settlement_amount=Decimal("5000"),
    )
    upstream = make_upstream(coverage_committed=False, coverage_decision="uncommitted")
    assessment = _assess(inputs, upstream)
    final = finalize_assessment(assessment)
    assert "Blocking defects" in final.rationale_text
    assert "coverage_decision_uncommitted" in final.rationale_text


def test_ledger_rationale_records_gate_counts():
    inputs = make_inputs()
    assessment = _assess(inputs)
    final = finalize_assessment(assessment)
    assert "Gates evaluated:" in final.diligence_ledger.decision_rationale
    assert "pass=" in final.diligence_ledger.decision_rationale
