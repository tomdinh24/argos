"""Tests for the inbound-reply orchestration wire.

Covers:
- Escalates with `escalate_no_candidates` when no open outbounds exist.
- Calls Reply Parser with the open outbounds and the inbound doc.
- Produces a `matched` outcome with an updated outbound (sent → replied,
  reply_doc_id, replied_at) on a successful parse.
- Escalates with `escalate_low_confidence` when parser confidence falls
  below threshold.
- `apply_outcome` replaces only the matched outbound, leaves others
  untouched, and returns a new caseload (input unmutated).
- `apply_outcome` is a no-op on escalation outcomes.

No live API calls — stubs the Anthropic client identical to the
Reply Parser test pattern.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

import pytest

from argos.ontology.types import (
    Caseload,
    Claim,
    CoverageRequest,
    Document,
    OutboundRequest,
)
from argos.services.orchestrator.reply_handler import (
    DEFAULT_MIN_CONFIDENCE,
    apply_outcome,
    handle_inbound_reply,
)


_NOW = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
_LATER = datetime(2026, 6, 2, 9, 30, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _outbound(
    *,
    request_id: str = "OBR-001",
    claim_id: str = "CLM-007",
    status: str = "sent",
    question_ids: list[str] | None = None,
) -> OutboundRequest:
    base: dict[str, Any] = dict(
        request_id=request_id,
        claim_id=claim_id,
        recipient_party="medical_provider",
        recipient_name="St. Anthony's Medical Records Desk",
        letter_purpose="Request medical records for the claimant.",
        question_ids_asked=question_ids or ["Q-DAM-001", "Q-DAM-002"],
        status=status,
    )
    if status in ("sent", "overdue", "replied"):
        base["sent_at"] = _NOW
        base["channel"] = "email"
        base["drafted_at"] = _NOW
        base["draft_body"] = "Please send the records."
    if status == "drafted":
        base["drafted_at"] = _NOW
        base["draft_body"] = "Please send the records."
    return OutboundRequest(**base)


def _inbound(*, doc_id: str = "DOC-INBOUND-1", claim_id: str = "CLM-007") -> Document:
    return Document(
        document_id=doc_id,
        claim_id=claim_id,
        document_type="medical_records",
        received_date=date(2026, 6, 2),
        source="St. Anthony's Hospital records desk",
        body_text=(
            "Enclosed are the medical records: ER admit note, MRI report, "
            "attending physician summary."
        ),
    )


def _caseload(outbounds: list[OutboundRequest]) -> Caseload:
    return Caseload(
        as_of=_NOW,
        claims=[Claim(
            claim_id="CLM-007", policy_period_id="PP-1", opened_date=_NOW.date(),
        )],
        requests=[CoverageRequest(
            request_id="REQ-007", claim_id="CLM-007", coverage_id="COV-1",
        )],
        outbound_requests=outbounds,
    )


def _valid_payload(**overrides: Any) -> dict[str, Any]:
    base = dict(
        matched_outbound_id="OBR-001",
        answered_question_ids=["Q-DAM-001", "Q-DAM-002"],
        unanswered_question_ids=[],
        partial=False,
        confidence=0.92,
        text_excerpt="Enclosed are the medical records",
        reason="Records desk responded with the requested files.",
    )
    return {**base, **overrides}


# ---------------------------------------------------------------------------
# Stub LLM client
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
    def __init__(self, queued: list[dict[str, Any]]):
        self.queued = list(queued)
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _StubResponse(content=[
            _StubToolBlock(type="tool_use", input=self.queued.pop(0))
        ])


class _StubClient:
    def __init__(self, queued: list[dict[str, Any]]):
        self.messages = _StubMessages(queued)


# ---------------------------------------------------------------------------
# handle_inbound_reply
# ---------------------------------------------------------------------------


class TestHandleInboundReply:
    def test_no_open_outbounds_escalates_without_calling_parser(self):
        cs = _caseload([])  # no outbounds at all
        client = _StubClient([_valid_payload()])  # would never be popped

        outcome = handle_inbound_reply(
            _inbound(),
            cs,
            now=_LATER,
            _client=client,  # type: ignore[arg-type]
        )

        assert outcome.outcome == "escalate_no_candidates"
        assert outcome.updated_outbound is None
        assert outcome.parsed is None
        assert "No open outbounds" in outcome.reason
        # Parser was NOT called
        assert client.messages.calls == []

    def test_only_closed_outbounds_treated_as_no_candidates(self):
        cs = _caseload([
            _outbound(request_id="OBR-1", status="pending_draft"),
            _outbound(request_id="OBR-2", status="drafted"),
        ])
        outcome = handle_inbound_reply(
            _inbound(),
            cs,
            now=_LATER,
            _client=_StubClient([_valid_payload()]),  # type: ignore[arg-type]
        )
        assert outcome.outcome == "escalate_no_candidates"

    def test_successful_match_produces_updated_outbound(self):
        cs = _caseload([_outbound()])
        outcome = handle_inbound_reply(
            _inbound(),
            cs,
            now=_LATER,
            _client=_StubClient([_valid_payload()]),  # type: ignore[arg-type]
        )

        assert outcome.outcome == "matched"
        assert outcome.parsed is not None
        assert outcome.parsed.result.matched_outbound_id == "OBR-001"
        assert outcome.updated_outbound is not None
        assert outcome.updated_outbound.status == "replied"
        assert outcome.updated_outbound.replied_at == _LATER
        assert outcome.updated_outbound.reply_doc_id == "DOC-INBOUND-1"
        assert outcome.answered_question_ids == ["Q-DAM-001", "Q-DAM-002"]
        assert outcome.unanswered_question_ids == []

    def test_low_confidence_escalates(self):
        cs = _caseload([_outbound()])
        payload = _valid_payload(confidence=0.3)
        outcome = handle_inbound_reply(
            _inbound(),
            cs,
            now=_LATER,
            _client=_StubClient([payload]),  # type: ignore[arg-type]
        )

        assert outcome.outcome == "escalate_low_confidence"
        assert outcome.parsed is not None
        assert outcome.parsed.result.confidence == pytest.approx(0.3)
        assert outcome.updated_outbound is None
        assert "below threshold" in outcome.reason

    def test_custom_min_confidence_threshold(self):
        """A higher threshold can promote a parse-success to an escalation."""
        cs = _caseload([_outbound()])
        payload = _valid_payload(confidence=0.6)  # above default, below custom
        outcome = handle_inbound_reply(
            _inbound(),
            cs,
            now=_LATER,
            min_confidence=0.85,
            _client=_StubClient([payload]),  # type: ignore[arg-type]
        )
        assert outcome.outcome == "escalate_low_confidence"

    def test_default_threshold_constant(self):
        """Default threshold is 0.5 — flag if accidentally changed."""
        assert DEFAULT_MIN_CONFIDENCE == 0.5

    def test_partial_reply_still_matches(self):
        """Partial replies (subset answered) still produce a matched
        outcome — the partition tells downstream what's still open."""
        cs = _caseload([_outbound()])
        partial = _valid_payload(
            answered_question_ids=["Q-DAM-001"],
            unanswered_question_ids=["Q-DAM-002"],
            partial=True,
        )
        outcome = handle_inbound_reply(
            _inbound(),
            cs,
            now=_LATER,
            _client=_StubClient([partial]),  # type: ignore[arg-type]
        )
        assert outcome.outcome == "matched"
        assert outcome.answered_question_ids == ["Q-DAM-001"]
        assert outcome.unanswered_question_ids == ["Q-DAM-002"]

    def test_only_open_outbounds_passed_to_parser(self):
        """A claim with mixed-status outbounds passes only the open
        ones (sent + overdue) to the parser."""
        already_replied = OutboundRequest(
            request_id="OBR-3", claim_id="CLM-007",
            recipient_party="claimant_counsel",
            recipient_name="Marisol Trent, Esq.",
            letter_purpose="Request initial case evaluation.",
            question_ids_asked=["Q-FOO-001"],
            status="replied", sent_at=_NOW, replied_at=_NOW,
            reply_doc_id="DOC-PRIOR",
        )
        cs = _caseload([
            _outbound(request_id="OBR-1", status="pending_draft"),
            _outbound(request_id="OBR-2", status="sent"),
            already_replied,
        ])
        outcome = handle_inbound_reply(
            _inbound(),
            cs,
            now=_LATER,
            _client=_StubClient([_valid_payload(matched_outbound_id="OBR-2")]),  # type: ignore[arg-type]
        )
        assert outcome.outcome == "matched"
        assert outcome.updated_outbound is not None
        assert outcome.updated_outbound.request_id == "OBR-2"


# ---------------------------------------------------------------------------
# apply_outcome
# ---------------------------------------------------------------------------


class TestApplyOutcome:
    def test_matched_outcome_replaces_only_target_outbound(self):
        cs = _caseload([
            _outbound(request_id="OBR-1"),
            _outbound(request_id="OBR-2", question_ids=["Q-LIA-001"]),
        ])
        outcome = handle_inbound_reply(
            _inbound(),
            cs,
            now=_LATER,
            _client=_StubClient([_valid_payload(matched_outbound_id="OBR-1")]),  # type: ignore[arg-type]
        )
        new_cs = apply_outcome(cs, outcome)

        # OBR-1 is now replied
        ob1 = next(o for o in new_cs.outbound_requests if o.request_id == "OBR-1")
        assert ob1.status == "replied"
        assert ob1.reply_doc_id == "DOC-INBOUND-1"
        # OBR-2 unchanged
        ob2 = next(o for o in new_cs.outbound_requests if o.request_id == "OBR-2")
        assert ob2.status == "sent"

    def test_matched_outcome_ingests_inbound_doc(self):
        """Document ingestion is the loop-closure mechanism: once the
        inbound doc lands in `caseload.documents`, the next
        deterministic `is_answered()` pass sees the evidence and the
        next drafter call treats those questions as closed."""
        cs = _caseload([_outbound()])
        assert cs.documents == []
        outcome = handle_inbound_reply(
            _inbound(),
            cs,
            now=_LATER,
            _client=_StubClient([_valid_payload()]),  # type: ignore[arg-type]
        )
        new_cs = apply_outcome(cs, outcome)
        assert len(new_cs.documents) == 1
        assert new_cs.documents[0].document_id == "DOC-INBOUND-1"
        assert new_cs.documents[0].document_type == "medical_records"

    def test_doc_ingestion_idempotent(self):
        """Applying the same outcome twice doesn't duplicate the doc."""
        cs = _caseload([_outbound()])
        outcome = handle_inbound_reply(
            _inbound(),
            cs,
            now=_LATER,
            _client=_StubClient([_valid_payload()]),  # type: ignore[arg-type]
        )
        once = apply_outcome(cs, outcome)
        twice = apply_outcome(once, outcome)
        assert len(twice.documents) == 1

    def test_input_caseload_not_mutated(self):
        cs = _caseload([_outbound()])
        outcome = handle_inbound_reply(
            _inbound(),
            cs,
            now=_LATER,
            _client=_StubClient([_valid_payload()]),  # type: ignore[arg-type]
        )
        new_cs = apply_outcome(cs, outcome)
        assert new_cs is not cs
        # Original caseload still has the sent outbound and no documents
        assert cs.outbound_requests[0].status == "sent"
        assert cs.outbound_requests[0].reply_doc_id is None
        assert cs.documents == []

    def test_escalation_still_ingests_doc_but_no_outbound_change(self):
        """Escalation outcomes still ingest the inbound doc (the record
        arrived; the file should reflect it), but leave outbounds
        untouched (the human queue resolves the unmatched reply)."""
        cs = _caseload([])
        outcome = handle_inbound_reply(
            _inbound(),
            cs,
            now=_LATER,
            _client=_StubClient([_valid_payload()]),  # type: ignore[arg-type]
        )
        assert outcome.outcome == "escalate_no_candidates"
        new_cs = apply_outcome(cs, outcome)
        # Outbounds untouched
        assert new_cs.outbound_requests == cs.outbound_requests
        # But the doc is now in the file
        assert len(new_cs.documents) == 1
        assert new_cs.documents[0].document_id == "DOC-INBOUND-1"

    def test_low_confidence_still_ingests_doc_but_outbound_unchanged(self):
        cs = _caseload([_outbound()])
        outcome = handle_inbound_reply(
            _inbound(),
            cs,
            now=_LATER,
            _client=_StubClient([_valid_payload(confidence=0.2)]),  # type: ignore[arg-type]
        )
        assert outcome.outcome == "escalate_low_confidence"
        new_cs = apply_outcome(cs, outcome)
        # Outbound stays in sent (parser wasn't confident enough)
        ob = next(o for o in new_cs.outbound_requests if o.request_id == "OBR-001")
        assert ob.status == "sent"
        assert ob.reply_doc_id is None
        # But the inbound doc still lands in the file
        assert len(new_cs.documents) == 1
        assert new_cs.documents[0].document_id == "DOC-INBOUND-1"


# ---------------------------------------------------------------------------
# End-to-end loop closure — the load-bearing behavior
# ---------------------------------------------------------------------------


class TestLoopClosure:
    """Prove that IngestReply actually shrinks the open-question set.

    The deterministic `is_answered()` check in brief/answer_detector
    is what the Outreach Drafter (and Brief assembler) consult when
    deciding which questions are still open. IngestReply closes the
    loop by ensuring the inbound document ends up in
    `caseload.documents` — which is exactly what `is_answered()`
    reads. No separate Q-state object needed.
    """

    def test_question_flips_from_open_to_answered_after_ingest(self):
        from argos.services.info_map import INFO_MAP_AUTO_BI_FL
        from argos.workflows.brief.answer_detector import is_answered

        # Q-DAM-001 is answered by a medical_records document on file.
        q = next(q for q in INFO_MAP_AUTO_BI_FL.questions if q.id == "Q-DAM-001")
        cs = _caseload([_outbound(question_ids=["Q-DAM-001"])])
        claim = cs.claims[0]

        # Before: no documents → question is still open.
        assert not is_answered(q, claim, cs.documents)

        # IngestReply: parser matches; apply_outcome ingests doc.
        outcome = handle_inbound_reply(
            _inbound(),  # document_type='medical_records'
            cs,
            now=_LATER,
            _client=_StubClient([_valid_payload(
                answered_question_ids=["Q-DAM-001"],
                unanswered_question_ids=[],
            )]),  # type: ignore[arg-type]
        )
        new_cs = apply_outcome(cs, outcome)

        # After: the deterministic check sees the medical_records doc
        # and reports the question as answered. Loop closed.
        assert is_answered(q, claim, new_cs.documents)

    def test_loop_closes_even_on_low_confidence_escalation(self):
        """Even when the parser doesn't confidently match, the doc
        still lands in the file — so deterministic detection picks
        up the evidence. The escalation only blocks the OUTBOUND
        state transition, not the doc ingestion."""
        from argos.services.info_map import INFO_MAP_AUTO_BI_FL
        from argos.workflows.brief.answer_detector import is_answered

        q = next(q for q in INFO_MAP_AUTO_BI_FL.questions if q.id == "Q-DAM-001")
        cs = _caseload([_outbound(question_ids=["Q-DAM-001"])])
        claim = cs.claims[0]

        outcome = handle_inbound_reply(
            _inbound(),
            cs,
            now=_LATER,
            _client=_StubClient([_valid_payload(
                confidence=0.2,
                answered_question_ids=["Q-DAM-001"],
                unanswered_question_ids=[],
            )]),  # type: ignore[arg-type]
        )
        new_cs = apply_outcome(cs, outcome)

        assert outcome.outcome == "escalate_low_confidence"
        # Outbound still in sent — but the question is now answered
        # because the document is in the file.
        assert is_answered(q, claim, new_cs.documents)
