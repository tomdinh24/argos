"""Tests for the DraftOutreach orchestration wire.

Covers:
- Happy path: pending_draft outbound → drafted state, body filled,
  drafted_at stamped, result populated.
- Pre-call hard errors: wrong status, missing claim — raised, not
  escalated (programmer error).
- Soft escalations: no open questions (returns outcome, parser not
  called); drafter empty-body (returns outcome with reason).
- apply_outcome: drafted replaces only target outbound, input
  unmutated; escalation outcomes are no-ops.

No live API calls — stubs the OpenAI client identical to the
Outreach Drafter test pattern.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

import pytest

from argos.ontology.types import (
    Caseload,
    Claim,
    CoverageRequest,
    OutboundRequest,
)
from argos.services.orchestrator.draft_handler import (
    apply_outcome,
    handle_pending_draft,
)


_NOW = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
_LATER = datetime(2026, 6, 2, 9, 30, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Stub OpenAI client (mirrors tests/workflows/test_outreach_drafter.py)
# ---------------------------------------------------------------------------


@dataclass
class _StubMessage:
    content: str


@dataclass
class _StubChoice:
    message: _StubMessage
    finish_reason: str = "stop"


@dataclass
class _StubUsage:
    prompt_tokens: int = 4500
    completion_tokens: int = 130


@dataclass
class _StubResponse:
    choices: list[_StubChoice]
    model: str = "gpt-5.5-2026-04-23"
    usage: _StubUsage = field(default_factory=_StubUsage)


class _StubChatCompletions:
    def __init__(self, queued_bodies: list[str]):
        self.queued = list(queued_bodies)
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        body = self.queued.pop(0)
        return _StubResponse(choices=[_StubChoice(message=_StubMessage(content=body))])


class _StubChat:
    def __init__(self, completions: _StubChatCompletions):
        self.completions = completions


class _StubClient:
    def __init__(self, queued_bodies: list[str]):
        self.chat = _StubChat(_StubChatCompletions(queued_bodies))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


_PASSING_BODY = (
    "We received your acknowledgment of representation 22 days ago. "
    "However, the initial case evaluation has not yet arrived.\n\n"
    "When you have a chance, please send the report within ten business "
    "days. Include any updates to liability and exposure.\n\n"
    "This request does not waive any coverage position. The claim "
    "remains subject to a complete reservation of rights, including all "
    "policy defenses and conditions."
)


def _outbound(
    *,
    request_id: str = "OBR-001",
    claim_id: str = "CLM-007",
    status: str = "pending_draft",
    recipient_party: str = "claimant_counsel",
    recipient_name: str = "Marisol Trent, Esq.",
    letter_purpose: str = (
        "Follow up with defense counsel; initial case evaluation not "
        "yet received after 22 days."
    ),
    question_ids: list[str] | None = None,
) -> OutboundRequest:
    base: dict[str, Any] = dict(
        request_id=request_id,
        claim_id=claim_id,
        recipient_party=recipient_party,
        recipient_name=recipient_name,
        letter_purpose=letter_purpose,
        question_ids_asked=question_ids or ["Q-LIA-001", "Q-LIA-002"],
        status=status,
    )
    if status in ("sent", "overdue", "replied"):
        base["sent_at"] = _NOW
        base["channel"] = "email"
        base["drafted_at"] = _NOW
        base["draft_body"] = "Existing body."
    if status in ("drafted",):
        base["drafted_at"] = _NOW
        base["draft_body"] = "Existing body."
    if status == "replied":
        base["replied_at"] = _NOW
        base["reply_doc_id"] = "DOC-X"
    return OutboundRequest(**base)


def _caseload(
    outbounds: list[OutboundRequest],
    *,
    claimant_name: str | None = "Robert Caro",
    insured_name: str | None = "Stellar Logistics, LLC",
) -> Caseload:
    return Caseload(
        as_of=_NOW,
        claims=[Claim(
            claim_id="CLM-007",
            policy_period_id="PP-1",
            opened_date=date(2026, 5, 10),
            claimant_name=claimant_name,
            insured_name=insured_name,
        )],
        requests=[CoverageRequest(
            request_id="REQ-007", claim_id="CLM-007", coverage_id="COV-1",
        )],
        outbound_requests=outbounds,
    )


# ---------------------------------------------------------------------------
# handle_pending_draft — happy path
# ---------------------------------------------------------------------------


class TestHandlePendingDraft:
    def test_pending_draft_transitions_to_drafted(self):
        cs = _caseload([_outbound()])
        client = _StubClient([_PASSING_BODY])

        outcome = handle_pending_draft(
            cs.outbound_requests[0],
            cs,
            now=_LATER,
            _client=client,  # type: ignore[arg-type]
        )

        assert outcome.outcome == "drafted"
        assert outcome.updated_outbound is not None
        assert outcome.updated_outbound.status == "drafted"
        assert outcome.updated_outbound.drafted_at == _LATER
        assert outcome.updated_outbound.draft_body == _PASSING_BODY
        assert outcome.result is not None
        assert outcome.result.body_text == _PASSING_BODY
        assert outcome.open_question_ids  # non-empty for claimant_counsel
        # Drafter was actually called
        assert len(client.chat.completions.calls) == 1

    def test_open_question_ids_surfaced_on_drafted_outcome(self):
        """Caller (orchestrator, UI) needs to know which IDs the draft
        is asking about so the next step can update claim Q-state."""
        cs = _caseload([_outbound()])
        outcome = handle_pending_draft(
            cs.outbound_requests[0],
            cs,
            now=_LATER,
            _client=_StubClient([_PASSING_BODY]),  # type: ignore[arg-type]
        )
        assert outcome.outcome == "drafted"
        assert all(qid.startswith("Q-") for qid in outcome.open_question_ids)


# ---------------------------------------------------------------------------
# Pre-call hard errors (programmer error — raised, not escalated)
# ---------------------------------------------------------------------------


class TestPreCallErrors:
    def test_non_pending_draft_status_raises(self):
        cs = _caseload([_outbound(status="drafted")])
        client = _StubClient([_PASSING_BODY])

        with pytest.raises(ValueError, match="expected 'pending_draft'"):
            handle_pending_draft(
                cs.outbound_requests[0],
                cs,
                now=_LATER,
                _client=client,  # type: ignore[arg-type]
            )
        # Drafter was NOT called
        assert client.chat.completions.calls == []

    def test_sent_status_raises(self):
        cs = _caseload([_outbound(status="sent")])
        with pytest.raises(ValueError, match="expected 'pending_draft'"):
            handle_pending_draft(
                cs.outbound_requests[0],
                cs,
                now=_LATER,
                _client=_StubClient([_PASSING_BODY]),  # type: ignore[arg-type]
            )

    def test_missing_claim_raises(self):
        """Outbound references claim_id not in caseload — programmer
        error, not a runtime escalation."""
        cs = _caseload([])  # no outbounds, no claims (besides the seeded one)
        stray = _outbound(claim_id="CLM-UNKNOWN")
        with pytest.raises(ValueError, match="not present in caseload"):
            handle_pending_draft(
                stray,
                cs,
                now=_LATER,
                _client=_StubClient([_PASSING_BODY]),  # type: ignore[arg-type]
            )


# ---------------------------------------------------------------------------
# Soft escalations
# ---------------------------------------------------------------------------


class TestSoftEscalations:
    def test_unhydrated_claim_escalates_without_calling_drafter(self):
        """Claim is missing claimant_name and/or insured_name → drafter
        cannot render letter. Soft escalate so the orchestrator can
        route to intake_reader or human hydration."""
        cs = _caseload([_outbound()], claimant_name=None, insured_name=None)
        client = _StubClient([_PASSING_BODY])

        outcome = handle_pending_draft(
            cs.outbound_requests[0],
            cs,
            now=_LATER,
            _client=client,  # type: ignore[arg-type]
        )

        assert outcome.outcome == "escalate_claim_unhydrated"
        assert outcome.updated_outbound is None
        assert outcome.result is None
        assert "claimant_name" in outcome.reason
        assert "insured_name" in outcome.reason
        assert client.chat.completions.calls == []

    def test_partial_hydration_still_escalates(self):
        """Missing just one of the two names is enough to escalate —
        the drafter input schema requires both."""
        cs = _caseload([_outbound()], claimant_name="Robert Caro", insured_name=None)
        outcome = handle_pending_draft(
            cs.outbound_requests[0],
            cs,
            now=_LATER,
            _client=_StubClient([_PASSING_BODY]),  # type: ignore[arg-type]
        )
        assert outcome.outcome == "escalate_claim_unhydrated"
        assert "insured_name" in outcome.reason
        assert "claimant_name" not in outcome.reason

    def test_no_open_questions_escalates_without_calling_drafter(self):
        """Recipient party with no questions in the info map → drafter
        would ask for nothing. Skip the LLM call."""
        cs = _caseload([_outbound(recipient_party="party_with_no_questions")])
        client = _StubClient([_PASSING_BODY])

        outcome = handle_pending_draft(
            cs.outbound_requests[0],
            cs,
            now=_LATER,
            _client=client,  # type: ignore[arg-type]
        )

        assert outcome.outcome == "escalate_no_open_questions"
        assert outcome.updated_outbound is None
        assert outcome.result is None
        assert outcome.open_question_ids == []
        assert "No open questions" in outcome.reason
        # Drafter was NOT called
        assert client.chat.completions.calls == []

    def test_drafter_empty_body_escalates(self):
        """Drafter raises on empty body (reasoning tokens consumed the
        budget). Handler catches and surfaces as soft escalation."""
        cs = _caseload([_outbound()])
        client = _StubClient([""])  # empty body triggers RuntimeError

        outcome = handle_pending_draft(
            cs.outbound_requests[0],
            cs,
            now=_LATER,
            _client=client,  # type: ignore[arg-type]
        )

        assert outcome.outcome == "escalate_drafter_failed"
        assert outcome.updated_outbound is None
        assert outcome.result is None
        assert "Outreach Drafter failed" in outcome.reason
        assert outcome.open_question_ids  # populated; we know what we tried to ask


# ---------------------------------------------------------------------------
# apply_outcome
# ---------------------------------------------------------------------------


class TestApplyOutcome:
    def test_drafted_replaces_only_target_outbound(self):
        cs = _caseload([
            _outbound(request_id="OBR-1"),
            _outbound(request_id="OBR-2", question_ids=["Q-LIA-005"]),
        ])
        outcome = handle_pending_draft(
            cs.outbound_requests[0],
            cs,
            now=_LATER,
            _client=_StubClient([_PASSING_BODY]),  # type: ignore[arg-type]
        )
        new_cs = apply_outcome(cs, outcome)

        ob1 = next(o for o in new_cs.outbound_requests if o.request_id == "OBR-1")
        assert ob1.status == "drafted"
        assert ob1.draft_body == _PASSING_BODY
        # OBR-2 unchanged
        ob2 = next(o for o in new_cs.outbound_requests if o.request_id == "OBR-2")
        assert ob2.status == "pending_draft"
        assert ob2.draft_body is None

    def test_input_caseload_not_mutated(self):
        cs = _caseload([_outbound()])
        outcome = handle_pending_draft(
            cs.outbound_requests[0],
            cs,
            now=_LATER,
            _client=_StubClient([_PASSING_BODY]),  # type: ignore[arg-type]
        )
        new_cs = apply_outcome(cs, outcome)
        assert new_cs is not cs
        # Original still pending_draft, no body
        assert cs.outbound_requests[0].status == "pending_draft"
        assert cs.outbound_requests[0].draft_body is None

    def test_no_open_questions_outcome_is_noop(self):
        cs = _caseload([_outbound(recipient_party="party_with_no_questions")])
        outcome = handle_pending_draft(
            cs.outbound_requests[0],
            cs,
            now=_LATER,
            _client=_StubClient([_PASSING_BODY]),  # type: ignore[arg-type]
        )
        assert outcome.outcome == "escalate_no_open_questions"
        new_cs = apply_outcome(cs, outcome)
        ob = next(o for o in new_cs.outbound_requests if o.request_id == "OBR-001")
        assert ob.status == "pending_draft"
        assert ob.draft_body is None

    def test_drafter_failed_outcome_is_noop(self):
        cs = _caseload([_outbound()])
        outcome = handle_pending_draft(
            cs.outbound_requests[0],
            cs,
            now=_LATER,
            _client=_StubClient([""]),  # type: ignore[arg-type]
        )
        assert outcome.outcome == "escalate_drafter_failed"
        new_cs = apply_outcome(cs, outcome)
        ob = next(o for o in new_cs.outbound_requests if o.request_id == "OBR-001")
        assert ob.status == "pending_draft"
        assert ob.draft_body is None
