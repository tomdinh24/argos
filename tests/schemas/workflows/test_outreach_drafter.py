"""Tests for the Outreach Drafter workflow schemas.

Covers pure-schema invariants on `OutreachDrafterInput`,
`OutreachDrafterResult`, and `OutreachThreadTurn`. Runtime-layer
behavior (LLM call, lint integration) is covered in
`tests/workflows/test_outreach_drafter.py`.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from argos.schemas.workflows.outreach_drafter import (
    OpenQuestionRef,
    OutreachDrafterInput,
    OutreachDrafterResult,
    OutreachThreadTurn,
)


_DOL = date(2026, 2, 18)
_NOW = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)


def _valid_input(**overrides) -> OutreachDrafterInput:
    base = dict(
        claim_id="CLM-007",
        recipient_party="defense_counsel",
        recipient_name="Marisol Trent, Esq.",
        claimant_name="Robert Caro",
        insured_name="Stellar Logistics, LLC",
        date_of_loss=_DOL,
        letter_purpose=(
            "Follow up with defense counsel; initial case evaluation "
            "not yet received after 22 days."
        ),
        open_questions=[
            OpenQuestionRef(id="Q-LIA-001", description="counsel's initial liability assessment"),
            OpenQuestionRef(id="Q-LIA-002", description="any expected motion practice"),
        ],
    )
    base.update(overrides)
    return OutreachDrafterInput(**base)


class TestOutreachThreadTurn:
    def test_sent_turn_valid(self):
        t = OutreachThreadTurn(
            direction="sent",
            turn_date=date(2026, 5, 10),
            summary="Requested initial case evaluation, ROR posture noted.",
            question_ids_asked=["Q-LIA-001", "Q-LIA-002"],
        )
        assert t.direction == "sent"
        assert t.question_ids_answered == []
        assert t.question_ids_unanswered == []

    def test_received_turn_valid(self):
        t = OutreachThreadTurn(
            direction="received",
            turn_date=date(2026, 5, 20),
            summary="Counsel acknowledged appearance; full evaluation pending.",
            question_ids_answered=["Q-LIA-001"],
            question_ids_unanswered=["Q-LIA-002"],
        )
        assert t.direction == "received"
        assert t.question_ids_asked == []

    def test_summary_must_be_non_empty(self):
        with pytest.raises(ValidationError):
            OutreachThreadTurn(
                direction="sent",
                turn_date=date(2026, 5, 10),
                summary="",
            )

    def test_invalid_direction_rejected(self):
        with pytest.raises(ValidationError):
            OutreachThreadTurn(
                direction="forwarded",  # not in the literal type
                turn_date=date(2026, 5, 10),
                summary="x",
            )


class TestOutreachDrafterInput:
    def test_minimal_first_letter_input_valid(self):
        inp = _valid_input()
        assert inp.conversation_history == []
        assert inp.older_history_summary is None

    def test_letter_purpose_required_non_empty(self):
        with pytest.raises(ValidationError):
            _valid_input(letter_purpose="")

    def test_thread_history_round_trips(self):
        inp = _valid_input(
            conversation_history=[
                OutreachThreadTurn(
                    direction="sent",
                    turn_date=date(2026, 5, 10),
                    summary="Initial request.",
                    question_ids_asked=["Q-LIA-001"],
                ),
                OutreachThreadTurn(
                    direction="received",
                    turn_date=date(2026, 5, 20),
                    summary="Partial reply.",
                    question_ids_answered=["Q-LIA-001"],
                    question_ids_unanswered=[],
                ),
            ]
        )
        assert len(inp.conversation_history) == 2
        assert inp.conversation_history[0].direction == "sent"
        assert inp.conversation_history[1].direction == "received"

    def test_older_history_summary_optional(self):
        inp = _valid_input(
            older_history_summary=(
                "Prior exchanges from 2025-11-04 to 2026-02-12 resolved "
                "Q-LIA-001, Q-DAM-002."
            )
        )
        assert inp.older_history_summary is not None

    def test_open_questions_can_be_empty_for_non_question_letter(self):
        # An acknowledgement-of-representation letter may carry zero asks.
        inp = _valid_input(open_questions=[])
        assert inp.open_questions == []

    def test_open_question_ref_description_required(self):
        with pytest.raises(ValidationError):
            OpenQuestionRef(id="Q-LIA-001", description="")

    def test_coverage_posture_defaults_to_under_investigation(self):
        """Backwards-compat: existing call sites that don't set the
        field get the most permissive default (no special framing)."""
        inp = _valid_input()
        assert inp.coverage_posture == "under_investigation"

    def test_coverage_posture_accepts_known_values(self):
        for posture in (
            "under_investigation", "ROR_issued", "denied", "accepted"
        ):
            inp = _valid_input(coverage_posture=posture)
            assert inp.coverage_posture == posture

    def test_coverage_posture_rejects_unknown_values(self):
        with pytest.raises(ValidationError):
            _valid_input(coverage_posture="reservation_issued")  # typo of ROR_issued


class TestOutreachDrafterResult:
    def test_minimal_result_valid(self):
        r = OutreachDrafterResult(
            body_text="One paragraph. Two sentences.",
            lint_metrics={"passes": True, "word_count": 4},
            lint_passes=True,
            model="gpt-5.5-2026-04-23",
            drafted_at=_NOW,
            input_tokens=4500,
            output_tokens=120,
        )
        assert r.lint_passes is True
        assert r.input_tokens == 4500

    def test_body_text_required_non_empty(self):
        with pytest.raises(ValidationError):
            OutreachDrafterResult(
                body_text="",
                lint_metrics={"passes": False},
                lint_passes=False,
                model="gpt-5.5",
                drafted_at=_NOW,
                input_tokens=100,
                output_tokens=0,
            )

    def test_token_counts_non_negative(self):
        with pytest.raises(ValidationError):
            OutreachDrafterResult(
                body_text="x",
                lint_metrics={"passes": True},
                lint_passes=True,
                model="gpt-5.5",
                drafted_at=_NOW,
                input_tokens=-1,
                output_tokens=10,
            )
