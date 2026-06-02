"""Tests for the Document Reader specialist.

No live API calls in pytest — those go in scripts. These tests cover:

- RelevanceCall schema invariants (excerpt iff relevant,
  posture iff relevant).
- User-body rendering shape (the model sees what we think it sees).
- Anchor-pair fixture shape (4 pairs, one per posture, A/B body
  differs by the added sentence).
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from argos.ontology.document_reader_anchors import (
    PAIR1_LIABILITY,
    PAIR2_COVERAGE,
    PAIR3_DAMAGES,
    PAIR4_RESERVE,
    all_pairs,
)
from argos.schemas.workflows.document_reader import RelevanceCall
from argos.workflows.document_reader import (
    ClaimContext,
    DocumentInput,
    _render_user_body,
)


# --- Schema invariants ----------------------------------------------------


class TestRelevanceCallSchema:
    def test_relevant_true_requires_excerpt(self):
        with pytest.raises(ValidationError, match="text_excerpt"):
            RelevanceCall(
                document_id="d1",
                relevant=True,
                posture_changed="liability",
                reason="r",
                text_excerpt="",  # empty — must fail
            )

    def test_relevant_false_forbids_excerpt(self):
        with pytest.raises(ValidationError, match="text_excerpt"):
            RelevanceCall(
                document_id="d1",
                relevant=False,
                posture_changed=None,
                reason="r",
                text_excerpt="something",  # non-empty — must fail
            )

    def test_relevant_true_requires_posture(self):
        with pytest.raises(ValidationError, match="posture_changed"):
            RelevanceCall(
                document_id="d1",
                relevant=True,
                posture_changed=None,  # missing — must fail
                reason="r",
                text_excerpt="q",
            )

    def test_relevant_false_forbids_posture(self):
        with pytest.raises(ValidationError, match="posture_changed"):
            RelevanceCall(
                document_id="d1",
                relevant=False,
                posture_changed="liability",  # set — must fail
                reason="r",
                text_excerpt="",
            )

    def test_minimal_relevant_true(self):
        call = RelevanceCall(
            document_id="d1",
            relevant=True,
            posture_changed="reserve",
            reason="new diagnosis",
            text_excerpt="MRI reveals herniation",
        )
        assert call.posture_changed == "reserve"
        assert call.text_excerpt == "MRI reveals herniation"

    def test_minimal_relevant_false(self):
        call = RelevanceCall(
            document_id="d1",
            relevant=False,
            posture_changed=None,
            reason="routine status update",
            text_excerpt="",
        )
        assert call.relevant is False
        assert call.posture_changed is None

    def test_posture_enum_rejects_unknown_value(self):
        with pytest.raises(ValidationError):
            RelevanceCall(
                document_id="d1",
                relevant=True,
                posture_changed="bankruptcy",  # not in enum
                reason="r",
                text_excerpt="q",
            )

    def test_reason_max_length_enforced(self):
        with pytest.raises(ValidationError):
            RelevanceCall(
                document_id="d1",
                relevant=False,
                posture_changed=None,
                reason="x" * 301,
                text_excerpt="",
            )


# --- User-body rendering --------------------------------------------------


class TestRendering:
    def _ctx(self) -> ClaimContext:
        return ClaimContext(
            claim_id="CLM-T-001",
            severity_tier="serious",
            current_reserve_amount=120_500.0,
            paid_to_date=8_500.0,
            litigation_flag=True,
            rep_flag=True,
            complaint_flag=False,
            open_coverage_status="pending",
            loss_facts="Two-car collision at intersection.",
        )

    def _doc(self) -> DocumentInput:
        return DocumentInput(
            document_id="DOC-T-1",
            document_type="police_report",
            source="law_enforcement",
            received_date="2026-04-25",
            body_text="...body text here...",
        )

    def test_renders_all_context_fields(self):
        body = _render_user_body(self._doc(), self._ctx())
        assert "CLM-T-001" in body
        assert "serious" in body
        assert "120,500.00" in body
        assert "8,500.00" in body
        assert "litigation_flag: True" in body
        assert "rep_flag: True" in body
        assert "complaint_flag: False" in body
        assert "open_coverage_status: pending" in body

    def test_renders_document_metadata_and_body(self):
        body = _render_user_body(self._doc(), self._ctx())
        assert "DOC-T-1" in body
        assert "police_report" in body
        assert "law_enforcement" in body
        assert "2026-04-25" in body
        assert "...body text here..." in body

    def test_loss_facts_present(self):
        body = _render_user_body(self._doc(), self._ctx())
        assert "Two-car collision at intersection." in body


# --- Anchor-pair fixture shape -------------------------------------------


class TestAnchorPairs:
    def test_all_pairs_returns_four(self):
        pairs = all_pairs()
        assert len(pairs) == 4

    def test_one_pair_per_posture(self):
        pairs = all_pairs()
        postures = sorted(p.posture for p in pairs)
        assert postures == ["coverage", "damages", "liability", "reserve"]

    def test_variant_b_body_contains_added_sentence(self):
        for pair in all_pairs():
            assert pair.added_sentence in pair.variant_b.body_text, (
                f"{pair.pair_id}: added_sentence not found verbatim in "
                f"variant_b.body_text"
            )

    def test_variant_a_body_does_not_contain_added_sentence(self):
        for pair in all_pairs():
            assert pair.added_sentence not in pair.variant_a.body_text, (
                f"{pair.pair_id}: added_sentence leaked into variant_a "
                f"(would invalidate the paired-delta test)"
            )

    def test_variant_a_and_b_share_context(self):
        for pair in all_pairs():
            # Same ClaimContext (single instance, ensure no accidental fork)
            assert pair.variant_a.document_type == pair.variant_b.document_type
            assert pair.variant_a.source == pair.variant_b.source
            assert pair.variant_a.received_date == pair.variant_b.received_date

    def test_pair_ids_unique(self):
        pair_ids = [p.pair_id for p in all_pairs()]
        assert len(pair_ids) == len(set(pair_ids))

    def test_individual_pairs_accessible_by_name(self):
        # Smoke check the four pinned exports are individually importable
        assert PAIR1_LIABILITY.posture == "liability"
        assert PAIR2_COVERAGE.posture == "coverage"
        assert PAIR3_DAMAGES.posture == "damages"
        assert PAIR4_RESERVE.posture == "reserve"
