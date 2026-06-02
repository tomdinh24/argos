"""Tests for the Reply Parser workflow.

No live API calls. Covers:

- ReplyParseResult schema invariants (excerpt-when-answering,
  partial-consistent-with-answers, no-overlap partition, OBR-prefix).
- Runtime parses well-formed tool output.
- Runtime rejects matched_outbound_id not in candidate set + retries.
- Runtime rejects answered+unanswered partition mismatch + retries.
- Runtime raises on empty open_outbounds (caller-side bug).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

import pytest
from pydantic import ValidationError

from argos.ontology.types import Document, OutboundRequest
from argos.schemas.workflows.reply_parser import ReplyParseResult
from argos.workflows.reply_parser import run_reply_parser


_NOW = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)


def _outbound(
    *,
    request_id: str = "OBR-001",
    question_ids: list[str] | None = None,
) -> OutboundRequest:
    return OutboundRequest(
        request_id=request_id,
        claim_id="CLM-007",
        recipient_party="medical_provider",
        recipient_name="St. Anthony's Medical Records Desk",
        letter_purpose="Request medical records for the claimant.",
        question_ids_asked=question_ids or ["Q-DAM-001", "Q-DAM-002"],
        status="sent",
        sent_at=_NOW,
        channel="email",
        drafted_at=_NOW,
        draft_body="Please send the medical records.",
    )


def _inbound() -> Document:
    return Document(
        document_id="DOC-INBOUND-1",
        claim_id="CLM-007",
        document_type="medical_records",
        received_date=date(2026, 6, 1),
        source="St. Anthony's Hospital records desk",
        body_text=(
            "Enclosed are the medical records for the patient: ER admit "
            "note, MRI report, attending physician summary."
        ),
    )


def _valid_payload(**overrides: Any) -> dict[str, Any]:
    base = dict(
        matched_outbound_id="OBR-001",
        answered_question_ids=["Q-DAM-001", "Q-DAM-002"],
        unanswered_question_ids=[],
        partial=False,
        confidence=0.92,
        text_excerpt="Enclosed are the medical records for the patient",
        reason="Records desk responded with the requested files.",
    )
    return {**base, **overrides}


# ---------------------------------------------------------------------------
# Schema invariants
# ---------------------------------------------------------------------------


class TestReplyParseResultSchema:
    def test_full_answer_payload_valid(self):
        r = ReplyParseResult.model_validate(_valid_payload())
        assert r.matched_outbound_id == "OBR-001"
        assert r.answered_question_ids == ["Q-DAM-001", "Q-DAM-002"]
        assert r.partial is False

    def test_partial_with_answers_valid(self):
        r = ReplyParseResult.model_validate(
            _valid_payload(
                answered_question_ids=["Q-DAM-001"],
                unanswered_question_ids=["Q-DAM-002"],
                partial=True,
            )
        )
        assert r.partial is True
        assert len(r.answered_question_ids) == 1
        assert len(r.unanswered_question_ids) == 1

    def test_acknowledgement_only_valid(self):
        """No questions answered + partial=True + empty excerpt is OK."""
        r = ReplyParseResult.model_validate(
            _valid_payload(
                answered_question_ids=[],
                unanswered_question_ids=["Q-DAM-001", "Q-DAM-002"],
                partial=True,
                text_excerpt="",
                reason="Acknowledgement only.",
            )
        )
        assert r.partial is True
        assert r.answered_question_ids == []

    def test_outbound_id_must_start_with_obr_prefix(self):
        with pytest.raises(ValidationError, match="OBR-"):
            ReplyParseResult.model_validate(
                _valid_payload(matched_outbound_id="JOB-123")
            )

    def test_excerpt_required_when_answering(self):
        with pytest.raises(ValidationError, match="text_excerpt"):
            ReplyParseResult.model_validate(
                _valid_payload(text_excerpt="")
            )

    def test_partial_false_requires_some_answers(self):
        with pytest.raises(ValidationError, match="partial=False"):
            ReplyParseResult.model_validate(
                _valid_payload(
                    answered_question_ids=[],
                    unanswered_question_ids=["Q-DAM-001", "Q-DAM-002"],
                    partial=False,
                    text_excerpt="",
                )
            )

    def test_partial_false_forbids_unanswered(self):
        with pytest.raises(ValidationError, match="partial=False"):
            ReplyParseResult.model_validate(
                _valid_payload(
                    answered_question_ids=["Q-DAM-001"],
                    unanswered_question_ids=["Q-DAM-002"],
                    partial=False,
                )
            )

    def test_overlap_between_answered_and_unanswered_rejected(self):
        with pytest.raises(ValidationError, match="both answered and unanswered"):
            ReplyParseResult.model_validate(
                _valid_payload(
                    answered_question_ids=["Q-DAM-001", "Q-DAM-002"],
                    unanswered_question_ids=["Q-DAM-002"],
                    partial=True,
                )
            )

    def test_confidence_out_of_range_rejected(self):
        with pytest.raises(ValidationError):
            ReplyParseResult.model_validate(_valid_payload(confidence=1.5))


# ---------------------------------------------------------------------------
# Runtime — stub LLM
# ---------------------------------------------------------------------------


@dataclass
class _StubToolBlock:
    type: str
    input: dict[str, Any]


@dataclass
class _StubResponse:
    content: list
    model: str = "claude-sonnet-4-6"


class _StubMessages:
    def __init__(self, queued_inputs: list[dict[str, Any]]):
        self.queued = list(queued_inputs)
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        inp = self.queued.pop(0)
        return _StubResponse(content=[_StubToolBlock(type="tool_use", input=inp)])


class _StubClient:
    def __init__(self, queued_inputs: list[dict[str, Any]]):
        self.messages = _StubMessages(queued_inputs)


class TestRunReplyParser:
    def test_returns_validated_result(self):
        client = _StubClient([_valid_payload()])
        result = run_reply_parser(
            _inbound(),
            [_outbound()],
            _client=client,  # type: ignore[arg-type]
        )
        assert result.result.matched_outbound_id == "OBR-001"
        assert result.result.partial is False
        assert result.attempts == 1

    def test_rejects_unknown_outbound_id_and_retries(self):
        bad = _valid_payload(matched_outbound_id="OBR-999")
        good = _valid_payload()
        client = _StubClient([bad, good])

        result = run_reply_parser(
            _inbound(),
            [_outbound()],
            _client=client,  # type: ignore[arg-type]
        )
        assert result.attempts == 2
        second_system = client.messages.calls[1]["system"]
        assert "PRIOR ATTEMPT REJECTED" in second_system
        assert "OBR-999" in second_system

    def test_rejects_partition_mismatch_and_retries(self):
        """Model emits answered+unanswered that doesn't equal asked set."""
        bad = _valid_payload(
            answered_question_ids=["Q-DAM-001"],
            unanswered_question_ids=[],  # misses Q-DAM-002
            partial=True,
        )
        good = _valid_payload()
        client = _StubClient([bad, good])

        result = run_reply_parser(
            _inbound(),
            [_outbound()],
            _client=client,  # type: ignore[arg-type]
        )
        assert result.attempts == 2
        second_system = client.messages.calls[1]["system"]
        assert "partition" in second_system.lower() or "missing" in second_system.lower()

    def test_rejects_extra_question_ids(self):
        """Model emits a question ID not in the outbound's asked set."""
        bad = _valid_payload(
            answered_question_ids=["Q-DAM-001", "Q-DAM-002", "Q-DAM-099"],
            unanswered_question_ids=[],
        )
        good = _valid_payload()
        client = _StubClient([bad, good])

        result = run_reply_parser(
            _inbound(),
            [_outbound()],
            _client=client,  # type: ignore[arg-type]
        )
        assert result.attempts == 2

    def test_raises_on_empty_open_outbounds(self):
        with pytest.raises(ValueError, match="open_outbounds is empty"):
            run_reply_parser(
                _inbound(),
                [],
                _client=_StubClient([_valid_payload()]),  # type: ignore[arg-type]
            )

    def test_raises_when_retries_exhausted(self):
        bad = _valid_payload(matched_outbound_id="OBR-999")
        client = _StubClient([bad, bad])
        with pytest.raises(RuntimeError, match="after 2 attempts"):
            run_reply_parser(
                _inbound(),
                [_outbound()],
                _client=client,  # type: ignore[arg-type]
            )

    def test_acknowledgement_only_reply_accepted(self):
        """Reply answers nothing but parser still matches the outbound."""
        ack = _valid_payload(
            answered_question_ids=[],
            unanswered_question_ids=["Q-DAM-001", "Q-DAM-002"],
            partial=True,
            text_excerpt="",
            reason="Acknowledgement only.",
            confidence=0.85,
        )
        result = run_reply_parser(
            _inbound(),
            [_outbound()],
            _client=_StubClient([ack]),  # type: ignore[arg-type]
        )
        assert result.result.answered_question_ids == []
        assert result.result.partial is True

    def test_partial_reply_accepted_with_subset(self):
        """Reply answers some but not all asked questions."""
        partial = _valid_payload(
            answered_question_ids=["Q-DAM-001"],
            unanswered_question_ids=["Q-DAM-002"],
            partial=True,
        )
        result = run_reply_parser(
            _inbound(),
            [_outbound()],
            _client=_StubClient([partial]),  # type: ignore[arg-type]
        )
        assert result.result.answered_question_ids == ["Q-DAM-001"]
        assert result.result.unanswered_question_ids == ["Q-DAM-002"]

    def test_multiple_outbound_candidates_routed_by_id(self):
        """When two outbounds are in scope, parser picks one and only
        that one's asked set is used for partition validation."""
        ob1 = _outbound(request_id="OBR-001", question_ids=["Q-DAM-001", "Q-DAM-002"])
        ob2 = _outbound(request_id="OBR-002", question_ids=["Q-LIA-001"])
        # Model picks OBR-002 with its question set
        payload = _valid_payload(
            matched_outbound_id="OBR-002",
            answered_question_ids=["Q-LIA-001"],
            unanswered_question_ids=[],
            partial=False,
            text_excerpt="Witness statement from the scene",
            reason="Police report attached.",
        )
        result = run_reply_parser(
            _inbound(),
            [ob1, ob2],
            _client=_StubClient([payload]),  # type: ignore[arg-type]
        )
        assert result.result.matched_outbound_id == "OBR-002"
        assert result.result.answered_question_ids == ["Q-LIA-001"]
