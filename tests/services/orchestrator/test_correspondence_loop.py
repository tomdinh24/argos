"""Tests for the correspondence loop — one tick of the ask/answer cycle.

Covers:
- Empty claim, no inbound replies → InfoGap proposes, Drafter drafts
  each. Caseload ends with N drafted outbounds.
- Inbound reply queued → IngestReply runs FIRST (loop closure: doc
  lands in caseload.documents before InfoGap evaluates open Qs).
- Multi-tick convergence: tick → ingest answering doc → tick again
  produces a smaller proposal set.
- ID seeding: new outbounds get IDs that don't collide with existing
  ones.
- Different-claim inbound docs in the queue are ignored.
- Empty pending_draft list → drafter step is a no-op.

LLM clients are stubbed: same shape as the per-wire test stubs so
the integration test stays hermetic.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from argos.ontology.types import (
    Caseload,
    Claim,
    CoverageRequest,
    Document,
    OutboundRequest,
)
from argos.services.orchestrator.correspondence_loop import (
    CorrespondenceAdvanceReport,
    advance_correspondence,
)


_NOW = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
_LATER = datetime(2026, 6, 2, 9, 30, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Stub OpenAI client (mirrors test_outreach_drafter.py)
# ---------------------------------------------------------------------------


@dataclass
class _StubOAIMessage:
    content: str


@dataclass
class _StubOAIChoice:
    message: _StubOAIMessage
    finish_reason: str = "stop"


@dataclass
class _StubOAIUsage:
    prompt_tokens: int = 4500
    completion_tokens: int = 130


@dataclass
class _StubOAIResponse:
    choices: list[_StubOAIChoice]
    model: str = "gpt-5.5-2026-04-23"
    usage: _StubOAIUsage = field(default_factory=_StubOAIUsage)


class _StubOAICompletions:
    def __init__(self, body: str):
        self.body = body
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _StubOAIResponse(
            choices=[_StubOAIChoice(message=_StubOAIMessage(content=self.body))]
        )


class _StubOAIChat:
    def __init__(self, completions: _StubOAICompletions):
        self.completions = completions


class _StubOAIClient:
    """Returns the same passing body for every drafter call."""
    def __init__(self, body: str):
        self.chat = _StubOAIChat(_StubOAICompletions(body))


# ---------------------------------------------------------------------------
# Stub Anthropic client (mirrors test_reply_handler.py / test_reply_parser.py)
# ---------------------------------------------------------------------------


@dataclass
class _StubAnthroToolBlock:
    type: str
    input: dict[str, Any]


@dataclass
class _StubAnthroResponse:
    content: list
    model: str = "claude-sonnet-4-6"


class _StubAnthroMessages:
    def __init__(self, queued_payloads: list[dict[str, Any]]):
        self.queued = list(queued_payloads)
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _StubAnthroResponse(content=[
            _StubAnthroToolBlock(type="tool_use", input=self.queued.pop(0))
        ])


class _StubAnthroClient:
    def __init__(self, queued_payloads: list[dict[str, Any]]):
        self.messages = _StubAnthroMessages(queued_payloads)


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
# Fixtures
# ---------------------------------------------------------------------------


def _claim() -> Claim:
    return Claim(
        claim_id="CLM-007",
        policy_period_id="PP-1",
        opened_date=date(2026, 5, 10),
        claimant_name="Robert Caro",
        insured_name="Stellar Logistics, LLC",
    )


def _caseload(
    *,
    documents: list[Document] | None = None,
    outbounds: list[OutboundRequest] | None = None,
) -> Caseload:
    return Caseload(
        as_of=_NOW,
        claims=[_claim()],
        requests=[CoverageRequest(
            request_id="REQ-007", claim_id="CLM-007", coverage_id="COV-1",
        )],
        documents=documents or [],
        outbound_requests=outbounds or [],
    )


def _directory() -> dict[str, str]:
    return {
        "broker": "BrokerCo Underwriting Desk",
        "insured": "Stellar Logistics, LLC",
        "police_records_office": "FL Highway Patrol Records",
        "medical_provider": "St. Anthony's Medical Records",
        "claimant_counsel": "Marisol Trent, Esq.",
        "dmv": "Florida DMV Portal",
        "body_shop": "Premier Auto Body",
        "employer": "Stellar Logistics HR",
        "cms_msprp": "CMS MSPRP Portal",
        "iso_claim_search": "ISO ClaimSearch API Desk",
        "court_records": "Hillsborough County Clerk",
        "carrier_uw": "Carrier Underwriting",
        "fnol_system": "FNOL System Operator",
        "witness": "Witness on file",
        "pip_carrier": "PIP Carrier Claims Desk",
    }


# ---------------------------------------------------------------------------
# Single tick — happy path
# ---------------------------------------------------------------------------


class TestSingleTickHappyPath:
    def test_empty_claim_proposes_and_drafts(self):
        """A fresh claim with no docs and no outbounds. One tick
        should: skip ingest (no replies), propose N outbounds, draft
        every one of them."""
        cs = _caseload()
        new_cs, report = advance_correspondence(
            cs,
            "CLM-007",
            recipient_directory=_directory(),
            now=_NOW,
            openai_client=_StubOAIClient(_PASSING_BODY),  # type: ignore[arg-type]
        )

        assert report.ingest_outcomes == []
        assert report.info_gap_outcome is not None
        assert report.info_gap_outcome.proposals
        # Every proposal got drafted.
        assert len(report.draft_outcomes) == len(report.info_gap_outcome.proposals)
        # Every drafted outcome is the happy path.
        for o in report.draft_outcomes:
            assert o.outcome == "drafted"
            assert o.updated_outbound is not None
            assert o.updated_outbound.status == "drafted"
            assert o.updated_outbound.draft_body == _PASSING_BODY

        # Caseload now carries N outbounds, all in `drafted` state.
        on_claim = [
            o for o in new_cs.outbound_requests if o.claim_id == "CLM-007"
        ]
        assert len(on_claim) == len(report.info_gap_outcome.proposals)
        assert all(o.status == "drafted" for o in on_claim)

    def test_input_caseload_not_mutated(self):
        cs = _caseload()
        new_cs, _ = advance_correspondence(
            cs,
            "CLM-007",
            recipient_directory=_directory(),
            now=_NOW,
            openai_client=_StubOAIClient(_PASSING_BODY),  # type: ignore[arg-type]
        )
        assert new_cs is not cs
        assert cs.outbound_requests == []  # original still empty

    def test_report_summary_renders(self):
        cs = _caseload()
        _, report = advance_correspondence(
            cs,
            "CLM-007",
            recipient_directory=_directory(),
            now=_NOW,
            openai_client=_StubOAIClient(_PASSING_BODY),  # type: ignore[arg-type]
        )
        line = report.summary()
        assert "CLM-007" in line
        assert "ingested=0" in line
        assert "proposed=" in line
        assert "drafted=" in line


# ---------------------------------------------------------------------------
# Ingest-then-propose ordering (loop closure inside one tick)
# ---------------------------------------------------------------------------


class TestIngestRunsBeforePropose:
    def test_inbound_doc_satisfies_question_before_infogap_evaluates(self):
        """A police_report arrives as an inbound. The tick should
        ingest it FIRST, so InfoGap evaluates the open-question set
        AFTER the doc is in caseload.documents — meaning Q-LIA-001
        is no longer in the proposal set."""
        # Prior outbound asking Q-LIA-001 — gives the parser a
        # candidate to match the inbound to.
        prior = OutboundRequest(
            request_id="OBR-001",
            claim_id="CLM-007",
            recipient_party="police_records_office",
            recipient_name="FL Highway Patrol Records",
            letter_purpose="Request crash report.",
            question_ids_asked=["Q-LIA-001"],
            status="sent",
            sent_at=_NOW,
            drafted_at=_NOW,
            channel="mail",
            draft_body="Please send report.",
        )
        cs = _caseload(outbounds=[prior])

        inbound = Document(
            document_id="DOC-PR-1",
            claim_id="CLM-007",
            document_type="police_report",
            received_date=date(2026, 5, 30),
            source="FHP",
            body_text="Officer arrived 14:12; complete crash narrative.",
        )

        # Anthropic stub: parser returns a confident match on OBR-001.
        anthro = _StubAnthroClient([{
            "matched_outbound_id": "OBR-001",
            "answered_question_ids": ["Q-LIA-001"],
            "unanswered_question_ids": [],
            "partial": False,
            "confidence": 0.95,
            "text_excerpt": "Officer arrived 14:12",
            "reason": "Crash report contains scene-level facts.",
        }])

        new_cs, report = advance_correspondence(
            cs,
            "CLM-007",
            recipient_directory=_directory(),
            now=_LATER,
            inbound_replies=[inbound],
            openai_client=_StubOAIClient(_PASSING_BODY),  # type: ignore[arg-type]
            anthropic_client=anthro,  # type: ignore[arg-type]
        )

        # Step 1 verified: one ingest outcome, matched.
        assert len(report.ingest_outcomes) == 1
        assert report.ingest_outcomes[0].outcome == "matched"

        # Step 2 verified: InfoGap evaluated AFTER ingest, so
        # Q-LIA-001 (and the other police_report-satisfied Qs) are
        # NOT in the proposal set.
        assert report.info_gap_outcome is not None
        proposed_qs = {
            qid
            for o in report.info_gap_outcome.proposals
            for qid in o.question_ids_asked
        }
        assert "Q-LIA-001" not in proposed_qs

        # And OBR-001 is now replied + the inbound doc is in the caseload.
        ob1 = next(o for o in new_cs.outbound_requests if o.request_id == "OBR-001")
        assert ob1.status == "replied"
        assert any(d.document_id == "DOC-PR-1" for d in new_cs.documents)

    def test_inbound_for_different_claim_ignored(self):
        cs = _caseload()
        inbound_other = Document(
            document_id="DOC-OTHER",
            claim_id="CLM-OTHER",
            document_type="medical_records",
            received_date=date(2026, 5, 30),
            source="x",
            body_text="Records for the other claim.",
        )
        _, report = advance_correspondence(
            cs,
            "CLM-007",
            recipient_directory=_directory(),
            now=_NOW,
            inbound_replies=[inbound_other],
            openai_client=_StubOAIClient(_PASSING_BODY),  # type: ignore[arg-type]
        )
        # The off-claim inbound did NOT get ingested for this claim.
        assert report.ingest_outcomes == []


# ---------------------------------------------------------------------------
# Multi-tick convergence
# ---------------------------------------------------------------------------


class TestMultiTickConvergence:
    def test_second_tick_after_ingest_proposes_less(self):
        """Tick 1 against empty claim → N proposals drafted. Then
        manually inject an answering doc and tick again — the second
        tick should produce strictly fewer proposals."""
        cs = _caseload()

        # Tick 1: empty claim → drafts.
        cs1, report1 = advance_correspondence(
            cs,
            "CLM-007",
            recipient_directory=_directory(),
            now=_NOW,
            openai_client=_StubOAIClient(_PASSING_BODY),  # type: ignore[arg-type]
        )
        tick1_qs = {
            qid for o in report1.info_gap_outcome.proposals
            for qid in o.question_ids_asked
        }

        # Inject a police_report → Q-LIA-001..007 answered for next pass.
        police_report = Document(
            document_id="DOC-PR-1",
            claim_id="CLM-007",
            document_type="police_report",
            received_date=date(2026, 5, 30),
            source="FHP",
            body_text="Crash report.",
        )
        cs1_with_doc = cs1.model_copy(update={"documents": [police_report]})

        # Tick 2: no inbound (already ingested manually) → InfoGap +
        # drafter. The previously-proposed outbounds are still in
        # `drafted` from tick 1, so InfoGap will see them as
        # in-flight and won't re-propose those questions either.
        _, report2 = advance_correspondence(
            cs1_with_doc,
            "CLM-007",
            recipient_directory=_directory(),
            now=_LATER,
            openai_client=_StubOAIClient(_PASSING_BODY),  # type: ignore[arg-type]
        )
        tick2_qs = {
            qid for o in report2.info_gap_outcome.proposals
            for qid in o.question_ids_asked
        }

        # The police_report-satisfied questions should NOT be in tick 2.
        assert "Q-LIA-001" not in tick2_qs
        # Most things from tick 1 are now in-flight or answered.
        assert tick1_qs.isdisjoint(tick2_qs), (
            "Tick 2 should not re-propose anything from tick 1 — those "
            "outbounds are now drafted (in-flight) or answered."
        )


# ---------------------------------------------------------------------------
# ID seeding
# ---------------------------------------------------------------------------


class TestIdSeeding:
    def test_new_ids_dont_collide_with_existing(self):
        """A claim that already has OBR-005 should get OBR-006 onward
        for new proposals."""
        existing = OutboundRequest(
            request_id="OBR-005",
            claim_id="CLM-007",
            recipient_party="medical_provider",
            recipient_name="St. Anthony's Medical Records",
            letter_purpose="Earlier outbound.",
            question_ids_asked=["Q-DAM-001"],
            status="sent",
            sent_at=_NOW,
            drafted_at=_NOW,
            channel="mail",
            draft_body="prior body",
        )
        cs = _caseload(outbounds=[existing])
        new_cs, report = advance_correspondence(
            cs,
            "CLM-007",
            recipient_directory=_directory(),
            now=_NOW,
            openai_client=_StubOAIClient(_PASSING_BODY),  # type: ignore[arg-type]
        )
        proposal_ids = [o.request_id for o in report.info_gap_outcome.proposals]
        # First new id is 006, not 001.
        assert proposal_ids[0] == "OBR-006"
        # No id collides with the existing 005.
        assert "OBR-005" not in proposal_ids


# ---------------------------------------------------------------------------
# Empty pending_draft case
# ---------------------------------------------------------------------------


class TestEmptyPendingDraftCase:
    def test_no_proposals_means_no_drafter_calls(self):
        """If the directory is empty so InfoGap can't propose anything,
        the drafter step is a no-op (no LLM calls)."""
        cs = _caseload()
        stub_oai = _StubOAIClient(_PASSING_BODY)
        _, report = advance_correspondence(
            cs,
            "CLM-007",
            recipient_directory={},  # nothing routable
            now=_NOW,
            openai_client=stub_oai,  # type: ignore[arg-type]
        )
        assert report.info_gap_outcome.proposals == []
        assert report.draft_outcomes == []
        # And the drafter LLM was never called.
        assert stub_oai.chat.completions.calls == []


# ---------------------------------------------------------------------------
# Report typing
# ---------------------------------------------------------------------------


class TestReportShape:
    def test_report_is_correctly_typed(self):
        cs = _caseload()
        _, report = advance_correspondence(
            cs,
            "CLM-007",
            recipient_directory=_directory(),
            now=_NOW,
            openai_client=_StubOAIClient(_PASSING_BODY),  # type: ignore[arg-type]
        )
        assert isinstance(report, CorrespondenceAdvanceReport)
        assert report.claim_id == "CLM-007"
