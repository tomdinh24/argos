"""Tests for the Brief assembler — deterministic, no LLM."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from argos.ontology.caseload_with_realistic_docs import (
    build_caseload_with_realistic_docs,
)
from argos.ontology.synthetic_caseload import build_caseload
from argos.workflows.brief.assembler import assemble


# ---------------------------------------------------------------------------
# Base behavior
# ---------------------------------------------------------------------------


class TestAssembleBasics:
    def test_returns_draft_for_known_claim(self):
        caseload = build_caseload()
        draft = assemble(caseload, "CLM-013")
        assert draft.claim_id == "CLM-013"
        assert draft.request_id is not None
        assert draft.claim.claim_id == "CLM-013"

    def test_raises_on_unknown_claim(self):
        caseload = build_caseload()
        with pytest.raises(ValueError):
            assemble(caseload, "CLM-999")

    def test_documents_filtered_to_claim(self):
        caseload = build_caseload_with_realistic_docs()
        draft = assemble(caseload, "CLM-007")
        assert all(d.claim_id == "CLM-007" for d in draft.documents)
        assert len(draft.documents) >= 1

    def test_loss_facts_hint_mentions_claim_id_and_severity(self):
        caseload = build_caseload()
        draft = assemble(caseload, "CLM-013")
        assert "CLM-013" in draft.loss_facts_hint
        assert draft.claim.severity_tier_summary in draft.loss_facts_hint


# ---------------------------------------------------------------------------
# Status snapshot derivations
# ---------------------------------------------------------------------------


class TestStatusSnapshot:
    def test_litigation_flag_drives_litigation_status(self):
        caseload = build_caseload()
        # Find a claim with litigation_flag=True and one without
        litigated = next(c for c in caseload.claims if c.litigation_flag)
        non_litigated = next(c for c in caseload.claims if not c.litigation_flag)

        d1 = assemble(caseload, litigated.claim_id)
        d2 = assemble(caseload, non_litigated.claim_id)

        assert d1.status_snapshot.litigation_status == "suit_filed"
        assert d2.status_snapshot.litigation_status == "none"

    def test_rep_flag_drives_representation_status(self):
        caseload = build_caseload()
        rep = next(c for c in caseload.claims if c.rep_flag)
        no_rep = next(c for c in caseload.claims if not c.rep_flag)

        assert assemble(caseload, rep.claim_id).status_snapshot.representation_status == "represented"
        assert assemble(caseload, no_rep.claim_id).status_snapshot.representation_status == "unrepresented"

    def test_coverage_status_pulls_from_request_when_no_specialist_result(self):
        caseload = build_caseload()
        draft = assemble(caseload, "CLM-013")
        # CoverageRequest.coverage_status defaults to "pending"
        assert draft.status_snapshot.coverage_status == "pending"

    def test_recovery_status_defaults_to_not_screened(self):
        caseload = build_caseload()
        draft = assemble(caseload, "CLM-013")
        assert draft.status_snapshot.recovery_status == "not_screened"


# ---------------------------------------------------------------------------
# Financial snapshot
# ---------------------------------------------------------------------------


class TestFinancialSnapshot:
    def test_financial_snapshot_matches_caseload_helpers(self):
        caseload = build_caseload()
        for claim in caseload.claims:
            requests = [r for r in caseload.requests if r.claim_id == claim.claim_id]
            expected_paid = sum(caseload.paid_to_date(r.request_id) for r in requests)
            expected_reserve = sum(caseload.reserve_current(r.request_id) for r in requests)
            draft = assemble(caseload, claim.claim_id)
            assert draft.financial_snapshot.paid_indemnity == expected_paid
            assert draft.financial_snapshot.outstanding_indemnity == max(
                expected_reserve - expected_paid, 0.0
            )


# ---------------------------------------------------------------------------
# Since-last-touch is always empty (Changelog feature is separate)
# ---------------------------------------------------------------------------


class TestSinceLastTouchIsAlwaysEmpty:
    def test_no_last_touch_logged(self):
        caseload = build_caseload()
        draft = assemble(caseload, "CLM-013")
        assert draft.since_last_touch.last_touch_at is None
        assert draft.since_last_touch.diff_items == []


# ---------------------------------------------------------------------------
# Specialist recommendations pulled from results dir
# ---------------------------------------------------------------------------


class TestSpecialistRecommendations:
    def test_empty_when_no_results_dir(self):
        caseload = build_caseload()
        draft = assemble(caseload, "CLM-013")
        assert draft.workflow_recommendations == []

    def test_empty_when_results_dir_has_no_files_for_claim(self, tmp_path: Path):
        caseload = build_caseload()
        # No directory for this claim — should produce no headlines.
        draft = assemble(caseload, "CLM-013", results_root=tmp_path)
        assert draft.workflow_recommendations == []

    def test_picks_up_coverage_result_when_present(self, tmp_path: Path):
        caseload = build_caseload()
        coverage_dir = tmp_path / "CLM-013"
        coverage_dir.mkdir()
        (coverage_dir / "coverage.json").write_text(json.dumps({
            "claim_id": "CLM-013",
            "synthesis": {
                "outcomes": [
                    {"outcome": "Coverage applies", "probability": 0.87},
                    {"outcome": "Coverage denied", "probability": 0.13},
                ],
            },
        }))

        draft = assemble(caseload, "CLM-013", results_root=tmp_path)
        assert len(draft.workflow_recommendations) == 1
        rec = draft.workflow_recommendations[0]
        assert rec.workflow == "coverage"
        assert "87%" in rec.headline

    def test_skips_unknown_specialist_files(self, tmp_path: Path):
        caseload = build_caseload()
        d = tmp_path / "CLM-013"
        d.mkdir()
        (d / "unknownspecialist.json").write_text(json.dumps({"x": 1}))
        draft = assemble(caseload, "CLM-013", results_root=tmp_path)
        assert draft.workflow_recommendations == []


# ---------------------------------------------------------------------------
# Gap detection — deterministic rules
# ---------------------------------------------------------------------------


class TestGapDetection:
    """Gap detection now consults INFO_MAP_AUTO_BI_FL. Variables are
    question IDs (Q-COV-001 etc.); answered/open is determined by
    document signals from `answer_detector`."""

    def test_gap_variables_are_info_map_question_ids(self):
        caseload = build_caseload()
        draft = assemble(caseload, "CLM-013")
        assert draft.raw_gaps, "expected some open questions on a fresh claim"
        for g in draft.raw_gaps:
            assert g.variable.startswith(("Q-COV-", "Q-LIA-", "Q-DAM-")), (
                f"unexpected variable {g.variable!r}"
            )

    def test_declarations_signal_answers_coverage_questions(self):
        """Q-COV-001 et al. are answered when a declarations_page is on
        file (CLM-007 in the realistic-docs caseload). They surface as
        open on the synthetic caseload, which has none."""
        no_decs = build_caseload()
        with_decs = build_caseload_with_realistic_docs()

        draft_no_decs = assemble(no_decs, "CLM-013")
        draft_with_decs = assemble(with_decs, "CLM-007")
        variables_no_decs = {g.variable for g in draft_no_decs.raw_gaps}
        variables_with_decs = {g.variable for g in draft_with_decs.raw_gaps}

        assert "Q-COV-001" in variables_no_decs
        doc_types_with = {d.document_type for d in draft_with_decs.documents}
        if "declarations_page" in doc_types_with:
            assert "Q-COV-001" not in variables_with_decs
        else:
            assert "Q-COV-001" in variables_with_decs

    def test_police_report_signal_answers_liability_scene_questions(self):
        """Q-LIA-001/002/003/004/006/007 are all answered when a
        police_report is on file."""
        caseload = build_caseload_with_realistic_docs()
        draft = assemble(caseload, "CLM-007")
        doc_types = {d.document_type for d in draft.documents}
        police_qs = {"Q-LIA-001", "Q-LIA-002", "Q-LIA-003",
                     "Q-LIA-004", "Q-LIA-006", "Q-LIA-007"}
        variables = {g.variable for g in draft.raw_gaps}
        if "police_report" in doc_types:
            assert not (police_qs & variables), (
                f"police_report on file should answer {police_qs}, "
                f"still open: {police_qs & variables}"
            )
        else:
            assert police_qs <= variables

    def test_medical_records_signal_answers_diagnosis_and_treatment(self):
        """Q-DAM-001 (initial diagnosis) and Q-DAM-002 (treatment to
        date) are answered when medical_records are on file. Bills,
        future treatment, permanency, etc. need richer signals and
        stay open."""
        caseload = build_caseload_with_realistic_docs()
        draft = assemble(caseload, "CLM-007")
        doc_types = {d.document_type for d in draft.documents}
        variables = {g.variable for g in draft.raw_gaps}
        if "medical_records" in doc_types:
            assert "Q-DAM-001" not in variables
            assert "Q-DAM-002" not in variables
        else:
            assert "Q-DAM-001" in variables
            assert "Q-DAM-002" in variables

    def test_unmapped_questions_remain_open(self):
        """Questions without a doc-type signal (e.g., Q-DAM-013 HIPAA
        release, Q-DAM-012 demand letter, Q-COV-009 PIP coordination)
        stay open until richer detection is wired."""
        caseload = build_caseload_with_realistic_docs()
        draft = assemble(caseload, "CLM-007")
        variables = {g.variable for g in draft.raw_gaps}
        for never_answered in ("Q-DAM-013", "Q-DAM-012", "Q-COV-009"):
            assert never_answered in variables

    def test_requested_from_matches_info_map_source(self):
        """RawGap.requested_from echoes the question's highest-fidelity
        source party — Outreach Drafter relies on this routing."""
        from argos.services.info_map import INFO_MAP_AUTO_BI_FL

        caseload = build_caseload()
        draft = assemble(caseload, "CLM-013")
        for g in draft.raw_gaps:
            expected = INFO_MAP_AUTO_BI_FL.get(g.variable).sources[0].party
            assert g.requested_from == expected, (
                f"{g.variable}: requested_from={g.requested_from!r} "
                f"but info-map source[0].party={expected!r}"
            )

    def test_critical_path_ordering_preserved(self):
        """Gaps come out in info-map critical-path order: perishable
        first, then longest cycle desc. Q-LIA-011 (EDR) is the only
        perishable atom, so it sorts first when it's open."""
        caseload = build_caseload()
        draft = assemble(caseload, "CLM-013")
        variables = [g.variable for g in draft.raw_gaps]
        if "Q-LIA-011" in variables:
            assert variables[0] == "Q-LIA-011"


# ---------------------------------------------------------------------------
# Generated timestamp
# ---------------------------------------------------------------------------


class TestGeneratedAt:
    def test_generated_at_is_recent_utc(self):
        caseload = build_caseload()
        draft = assemble(caseload, "CLM-013")
        now = datetime.now(timezone.utc)
        assert abs((now - draft.generated_at).total_seconds()) < 5
        assert draft.generated_at.tzinfo is not None
