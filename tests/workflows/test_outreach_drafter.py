"""Tests for the Outreach Drafter workflow.

No live API calls. Covers:

- `run_outreach_drafter` returns a structured result with lint
  metadata populated.
- Empty model output raises a helpful error (reasoning-tokens-ate-budget
  failure mode).
- User-prompt rendering includes CONVERSATION HISTORY when turns are
  present and "first letter on this thread" when empty.
- `build_drafter_input_for_outbound` slices open questions correctly,
  assembles thread turns from prior outbounds + matched replies, and
  summarizes older history when the thread exceeds the cap.
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
    Document,
    OutboundRequest,
)
from argos.schemas.workflows.outreach_drafter import (
    OpenQuestionRef,
    OutreachDrafterInput,
    OutreachDrafterResult,
    OutreachThreadTurn,
)
from argos.workflows.outreach_drafter import (
    SYSTEM_PROMPT,
    THREAD_HISTORY_CAP,
    _render_user_body,
    build_drafter_input_for_outbound,
    run_outreach_drafter,
)


_DOL = date(2026, 2, 18)
_NOW = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Stub OpenAI client
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


def _valid_input(**overrides: Any) -> OutreachDrafterInput:
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


_PASSING_BODY = (
    "We received your acknowledgment of representation 22 days ago. "
    "However, the initial case evaluation has not yet arrived.\n\n"
    "When you have a chance, please send the report within ten business "
    "days. Include any updates to liability and exposure.\n\n"
    "This request does not waive any coverage position. The claim "
    "remains subject to a complete reservation of rights, including all "
    "policy defenses and conditions."
)


# ---------------------------------------------------------------------------
# run_outreach_drafter
# ---------------------------------------------------------------------------


class TestRunOutreachDrafter:
    def test_returns_structured_result_with_lint_metadata(self):
        client = _StubClient([_PASSING_BODY])
        result = run_outreach_drafter(
            _valid_input(),
            now=_NOW,
            _client=client,  # type: ignore[arg-type]
        )
        assert isinstance(result, OutreachDrafterResult)
        assert result.body_text.startswith("We received your acknowledgment")
        assert result.drafted_at == _NOW
        assert result.input_tokens == 4500
        assert result.output_tokens == 130
        assert "passes" in result.lint_metrics
        assert "word_count" in result.lint_metrics
        # lint_passes mirrors the dict
        assert result.lint_passes == result.lint_metrics["passes"]

    def test_system_and_user_prompts_passed(self):
        client = _StubClient([_PASSING_BODY])
        run_outreach_drafter(
            _valid_input(),
            now=_NOW,
            _client=client,  # type: ignore[arg-type]
        )
        call = client.chat.completions.calls[0]
        messages = call["messages"]
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == SYSTEM_PROMPT
        assert messages[1]["role"] == "user"
        assert "claim_id: CLM-007" in messages[1]["content"]
        assert "OPEN QUESTIONS TO ADDRESS" in messages[1]["content"]

    def test_reasoning_effort_and_token_cap_passed(self):
        client = _StubClient([_PASSING_BODY])
        run_outreach_drafter(
            _valid_input(),
            now=_NOW,
            _client=client,  # type: ignore[arg-type]
        )
        call = client.chat.completions.calls[0]
        assert call["reasoning_effort"] == "low"
        assert call["max_completion_tokens"] == 1500

    def test_system_prompt_carries_ror_posture_rule(self):
        """Load-bearing sanity check: the COVERAGE POSTURE section in
        SYSTEM_PROMPT must mention ROR_issued, the reservation
        formula, and the required final-paragraph behavior. If a
        future prompt edit deletes it, this test fails loudly rather
        than silently regressing the ROR escalation behavior."""
        assert "COVERAGE POSTURE" in SYSTEM_PROMPT
        assert "ROR_issued" in SYSTEM_PROMPT
        # The reservation formula must be present verbatim.
        assert "complete reservation of rights" in SYSTEM_PROMPT
        assert "without waiving any defenses" in SYSTEM_PROMPT
        # All four posture values must be enumerated.
        for posture in (
            "under_investigation", "ROR_issued", "denied", "accepted"
        ):
            assert posture in SYSTEM_PROMPT

    def test_empty_body_raises_helpful_error(self):
        client = _StubClient([""])
        with pytest.raises(RuntimeError, match="reasoning tokens consumed"):
            run_outreach_drafter(
                _valid_input(),
                now=_NOW,
                _client=client,  # type: ignore[arg-type]
            )

    def test_overrides_threaded_through(self):
        client = _StubClient([_PASSING_BODY])
        run_outreach_drafter(
            _valid_input(),
            now=_NOW,
            model="gpt-5.5-mini",
            reasoning_effort="low",
            max_completion_tokens=2500,
            _client=client,  # type: ignore[arg-type]
        )
        call = client.chat.completions.calls[0]
        assert call["model"] == "gpt-5.5-mini"
        assert call["reasoning_effort"] == "low"
        assert call["max_completion_tokens"] == 2500


# ---------------------------------------------------------------------------
# User-prompt rendering
# ---------------------------------------------------------------------------


class TestRenderUserBody:
    def test_first_letter_indicates_no_history(self):
        body = _render_user_body(_valid_input())
        assert "first letter on this thread" in body

    def test_history_block_emitted_when_turns_present(self):
        inp = _valid_input(
            conversation_history=[
                OutreachThreadTurn(
                    direction="sent",
                    turn_date=date(2026, 5, 10),
                    summary="Requested initial case evaluation.",
                    question_ids_asked=["Q-LIA-001", "Q-LIA-002"],
                ),
                OutreachThreadTurn(
                    direction="received",
                    turn_date=date(2026, 5, 20),
                    summary="Acknowledged appearance; eval pending.",
                    question_ids_answered=[],
                    question_ids_unanswered=["Q-LIA-001", "Q-LIA-002"],
                ),
            ]
        )
        body = _render_user_body(inp)
        assert "CONVERSATION HISTORY" in body
        assert "[2026-05-10] SENT" in body
        assert "[2026-05-20] RECEIVED" in body
        assert "Q-LIA-001" in body

    def test_older_history_summary_emitted_when_set(self):
        inp = _valid_input(
            older_history_summary=(
                "Prior exchanges from 2025-11-04 to 2026-02-12 resolved "
                "Q-COV-001, Q-DAM-002."
            )
        )
        body = _render_user_body(inp)
        assert "Older history:" in body
        assert "Q-COV-001" in body

    def test_coverage_posture_surfaced_in_user_body(self):
        """The system prompt has an explicit COVERAGE POSTURE rule —
        for it to fire, the field must be visible in the user body."""
        inp = _valid_input(coverage_posture="ROR_issued")
        body = _render_user_body(inp)
        assert "coverage_posture: ROR_issued" in body

    def test_coverage_posture_default_visible(self):
        inp = _valid_input()  # default = under_investigation
        body = _render_user_body(inp)
        assert "coverage_posture: under_investigation" in body


# ---------------------------------------------------------------------------
# build_drafter_input_for_outbound
# ---------------------------------------------------------------------------


def _claim() -> Claim:
    return Claim(
        claim_id="CLM-007",
        policy_period_id="PP-1",
        opened_date=_DOL,
        claimant_name="Robert Caro",
        insured_name="Stellar Logistics, LLC",
    )


def _request() -> CoverageRequest:
    return CoverageRequest(
        request_id="REQ-007",
        claim_id="CLM-007",
        coverage_id="COV-1",
    )


def _caseload(
    outbounds: list[OutboundRequest] | None = None,
    documents: list[Document] | None = None,
) -> Caseload:
    return Caseload(
        as_of=_NOW,
        claims=[_claim()],
        requests=[_request()],
        documents=documents or [],
        outbound_requests=outbounds or [],
    )


_DEFAULT_RECIPIENT_NAME = "Marisol Trent, Esq."
_DEFAULT_LETTER_PURPOSE = "Follow up with counsel."


def _outbound(
    *,
    request_id: str,
    questions: list[str],
    sent_at: datetime,
    status: str = "sent",
    reply_doc_id: str | None = None,
    replied_at: datetime | None = None,
    body: str = "Please send the requested information.",
    recipient_party: str = "defense_counsel",
    recipient_name: str = _DEFAULT_RECIPIENT_NAME,
    letter_purpose: str = _DEFAULT_LETTER_PURPOSE,
) -> OutboundRequest:
    return OutboundRequest(
        request_id=request_id,
        claim_id="CLM-007",
        recipient_party=recipient_party,
        recipient_name=recipient_name,
        letter_purpose=letter_purpose,
        question_ids_asked=questions,
        status=status,
        drafted_at=sent_at,
        draft_body=body,
        sent_at=sent_at,
        channel="email",
        reply_doc_id=reply_doc_id,
        replied_at=replied_at,
    )


def _pending_target(
    *,
    request_id: str = "OBR-TARGET",
    questions: list[str] | None = None,
    recipient_party: str = "defense_counsel",
    recipient_name: str = _DEFAULT_RECIPIENT_NAME,
    letter_purpose: str = _DEFAULT_LETTER_PURPOSE,
) -> OutboundRequest:
    """The outbound currently being drafted — `pending_draft` state, no body."""
    return OutboundRequest(
        request_id=request_id,
        claim_id="CLM-007",
        recipient_party=recipient_party,
        recipient_name=recipient_name,
        letter_purpose=letter_purpose,
        question_ids_asked=questions or ["Q-LIA-001"],
    )


class TestBuildDrafterInputForOutbound:
    def test_first_letter_empty_history(self):
        target = _pending_target(
            letter_purpose="Initial info request to newly-appearing counsel.",
        )
        inp = build_drafter_input_for_outbound(
            outbound=target,
            caseload=_caseload(outbounds=[target]),
        )
        assert inp.conversation_history == []
        assert inp.older_history_summary is None
        # The target's own purpose flows through.
        assert "newly-appearing" in inp.letter_purpose
        # No documents on file → all by_party questions are still open
        # (or at least, open_questions is non-empty — depends on info map).
        # Just assert the field is populated and a list.
        assert isinstance(inp.open_questions, list)
        # Every entry has a non-empty description (helper populated from info map).
        for q in inp.open_questions:
            assert q.description and q.id.startswith("Q-")

    def test_coverage_posture_read_from_claim(self):
        """The helper reads `claim.coverage_posture` and threads it
        into the drafter input — same plumbing as claimant/insured
        names. The default propagates as `under_investigation`."""
        target = _pending_target()
        inp = build_drafter_input_for_outbound(
            outbound=target,
            caseload=_caseload(outbounds=[target]),
        )
        assert inp.coverage_posture == "under_investigation"

    def test_coverage_posture_propagates_when_ror_issued(self):
        target = _pending_target()
        # _claim() default builds the under_investigation claim;
        # construct one explicitly at ROR_issued for this case.
        ror_claim = Claim(
            claim_id="CLM-007",
            policy_period_id="PP-1",
            opened_date=_DOL,
            claimant_name="Robert Caro",
            insured_name="Stellar Logistics, LLC",
            coverage_posture="ROR_issued",
        )
        ror_caseload = Caseload(
            as_of=_NOW,
            claims=[ror_claim],
            requests=[_request()],
            documents=[],
            outbound_requests=[target],
        )
        inp = build_drafter_input_for_outbound(
            outbound=target,
            caseload=ror_caseload,
        )
        assert inp.coverage_posture == "ROR_issued"

    def test_thread_history_assembled_from_prior_outbounds(self):
        sent_at_1 = datetime(2026, 5, 10, 12, 0, tzinfo=timezone.utc)
        sent_at_2 = datetime(2026, 5, 25, 12, 0, tzinfo=timezone.utc)
        reply_doc = Document(
            document_id="DOC-REPLY-1",
            claim_id="CLM-007",
            document_type="letter",
            received_date=date(2026, 5, 20),
            source="Dornan & Lao LLP",
            body_text="We acknowledge representation; full evaluation pending.",
        )
        target = _pending_target(letter_purpose="Follow up on outstanding items.")
        outbounds = [
            _outbound(
                request_id="OBR-1",
                questions=["Q-LIA-001"],
                sent_at=sent_at_1,
                status="replied",
                reply_doc_id="DOC-REPLY-1",
                replied_at=datetime(2026, 5, 20, 9, 0, tzinfo=timezone.utc),
                body="Requested initial case evaluation and ROR posture noted.",
            ),
            _outbound(
                request_id="OBR-2",
                questions=["Q-LIA-002"],
                sent_at=sent_at_2,
                status="sent",
                body="Asked about expected motion practice.",
            ),
            target,
        ]
        inp = build_drafter_input_for_outbound(
            outbound=target,
            caseload=_caseload(outbounds=outbounds, documents=[reply_doc]),
        )
        # 2 outbounds → 3 thread turns: SENT, RECEIVED (reply), SENT
        assert len(inp.conversation_history) == 3
        assert [t.direction for t in inp.conversation_history] == ["sent", "received", "sent"]
        assert inp.conversation_history[1].turn_date == date(2026, 5, 20)
        assert inp.conversation_history[1].question_ids_answered == ["Q-LIA-001"]
        assert inp.older_history_summary is None

    def test_history_exceeding_cap_gets_summarized(self):
        target = _pending_target(
            letter_purpose="Continuing follow-up on long thread.",
        )
        # 7 priors + 1 target — the target is filtered out of history.
        outbounds = [
            _outbound(
                request_id=f"OBR-{i}",
                questions=[f"Q-LIA-{i:03d}"],
                sent_at=datetime(2026, 1, i + 1, 12, 0, tzinfo=timezone.utc),
                status="sent",
                body=f"Letter number {i}.",
            )
            for i in range(7)
        ] + [target]
        inp = build_drafter_input_for_outbound(
            outbound=target,
            caseload=_caseload(outbounds=outbounds),
        )
        assert len(inp.conversation_history) == THREAD_HISTORY_CAP
        assert inp.older_history_summary is not None
        assert "Prior exchanges from" in inp.older_history_summary

    def test_only_target_recipient_party_included(self):
        # An outbound to a DIFFERENT party should not leak into this
        # recipient's thread.
        sent_at = datetime(2026, 5, 10, 12, 0, tzinfo=timezone.utc)
        target = _pending_target()
        outbounds = [
            _outbound(
                request_id="OBR-1",
                questions=["Q-LIA-001"],
                sent_at=sent_at,
                status="sent",
                body="Defense counsel outbound.",
            ),
            OutboundRequest(
                request_id="OBR-MED",
                claim_id="CLM-007",
                recipient_party="medical_provider",
                recipient_name="St. Anthony's Medical Records Desk",
                letter_purpose="Request medical records.",
                question_ids_asked=["Q-DAM-001"],
                status="sent",
                drafted_at=sent_at,
                draft_body="Records request to provider.",
                sent_at=sent_at,
                channel="email",
            ),
            target,
        ]
        inp = build_drafter_input_for_outbound(
            outbound=target,
            caseload=_caseload(outbounds=outbounds),
        )
        # Only the defense_counsel outbound's SENT turn should be present.
        assert len(inp.conversation_history) == 1
        assert inp.conversation_history[0].question_ids_asked == ["Q-LIA-001"]
