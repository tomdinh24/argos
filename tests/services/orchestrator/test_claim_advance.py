"""Tests for the cross-stream scheduler — `advance_claim`.

Covers:
- Reply-vs-disclosure classification heuristic
- Disclosures are added directly to caseload.documents
- Reply candidates are NOT added directly — they pass through
  correspondence ingest
- Off-claim docs are ignored
- Both streams compose correctly: a disclosure plus an empty
  correspondence cycle still surface a coherent report
- Input caseload is not mutated

Decision context: docs/DECISIONS.md →
  "Cross-stream scheduler shipped (advance_claim)"
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
from argos.schemas.workflows.document_reader import RelevanceCall
from argos.services.orchestrator.claim_advance import (
    ClaimAdvanceReport,
    advance_claim,
)
from argos.services.orchestrator.queue import JobQueue
from argos.workflows.document_reader import (
    ClaimContext,
    DocumentInput,
    RelevanceCallResult,
)


_NOW = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
_LATER = datetime(2026, 6, 2, 9, 30, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Stub OpenAI client (drafter)
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

    def create(self, **kwargs):
        return _StubOAIResponse(
            choices=[_StubOAIChoice(message=_StubOAIMessage(content=self.body))]
        )


class _StubOAIChat:
    def __init__(self, completions: _StubOAICompletions):
        self.completions = completions


class _StubOAIClient:
    def __init__(self, body: str):
        self.chat = _StubOAIChat(_StubOAICompletions(body))


# ---------------------------------------------------------------------------
# Stub Anthropic client (reply parser)
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

    def create(self, **kwargs):
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


def _doc(doc_id: str, *, claim_id: str = "CLM-007", **overrides) -> Document:
    defaults = dict(
        document_id=doc_id,
        claim_id=claim_id,
        document_type="police_report",
        received_date=date(2026, 5, 30),
        source="upload",
        body_text="Document content.",
    )
    defaults.update(overrides)
    return Document(**defaults)


def _sent_outbound(
    *,
    request_id: str = "OBR-001",
    recipient_party: str = "claimant_counsel",
    recipient_name: str = "Marisol Trent, Esq.",
    question_ids: list[str] | None = None,
) -> OutboundRequest:
    return OutboundRequest(
        request_id=request_id,
        claim_id="CLM-007",
        recipient_party=recipient_party,
        recipient_name=recipient_name,
        letter_purpose="Request initial case evaluation.",
        question_ids_asked=question_ids or ["Q-LIA-001"],
        status="sent",
        drafted_at=_NOW,
        draft_body="Prior letter body.",
        sent_at=_NOW,
        channel="email",
    )


# ---------------------------------------------------------------------------
# Classification — disclosure path
# ---------------------------------------------------------------------------


class TestDisclosureClassification:
    """No open outbounds on the claim → every inbound doc is a
    fresh disclosure. Disclosures land in caseload.documents
    directly so the analysis pipeline + is_answered() see them."""

    def test_no_open_outbounds_doc_is_disclosure(self):
        cs = _caseload()
        new_doc = _doc("DOC-NEW-1")

        new_cs, report = advance_claim(
            cs,
            "CLM-007",
            new_inbound_docs=[new_doc],
            recipient_directory=_directory(),
            now=_NOW,
            openai_client=_StubOAIClient(_PASSING_BODY),  # type: ignore[arg-type]
        )

        assert len(report.classified_docs) == 1
        assert report.classified_docs[0].classification == "disclosure"
        assert report.disclosures_added == 1
        # Disclosure lives in caseload.documents now.
        assert any(d.document_id == "DOC-NEW-1" for d in new_cs.documents)

    def test_disclosure_does_not_pass_through_ingest(self):
        """A disclosure is not handed to the correspondence ingest
        step — it shows up in `disclosures_added`, NOT in
        `correspondence.ingest_outcomes`."""
        cs = _caseload()
        new_doc = _doc("DOC-DIS-1")

        _, report = advance_claim(
            cs,
            "CLM-007",
            new_inbound_docs=[new_doc],
            recipient_directory=_directory(),
            now=_NOW,
            openai_client=_StubOAIClient(_PASSING_BODY),  # type: ignore[arg-type]
        )

        assert report.correspondence is not None
        assert report.correspondence.ingest_outcomes == []

    def test_disclosure_dedupe_against_existing_documents(self):
        """A disclosure with a document_id already in caseload.documents
        does NOT double-add. Re-firing advance with the same doc is
        idempotent."""
        existing = _doc("DOC-EXISTING")
        cs = _caseload(documents=[existing])

        new_cs, report = advance_claim(
            cs,
            "CLM-007",
            new_inbound_docs=[existing],
            recipient_directory=_directory(),
            now=_NOW,
            openai_client=_StubOAIClient(_PASSING_BODY),  # type: ignore[arg-type]
        )

        assert report.classified_docs[0].classification == "disclosure"
        assert report.disclosures_added == 0
        assert len(new_cs.documents) == 1


# ---------------------------------------------------------------------------
# Classification — reply candidate path
# ---------------------------------------------------------------------------


class TestReplyCandidateClassification:
    """Any open outbound on the claim → inbound doc is a reply
    candidate. It goes through the correspondence ingest step
    (not directly into caseload.documents)."""

    def test_open_outbound_makes_doc_reply_candidate(self):
        sent = _sent_outbound()
        cs = _caseload(outbounds=[sent])
        new_doc = _doc(
            "DOC-REPLY-1",
            document_type="claimant_counsel_letter",
            received_at=_LATER,
        )

        oa_client = _StubOAIClient(_PASSING_BODY)
        ant_client = _StubAnthroClient([{
            "matched_outbound_id": "OBR-001",
            "answered_question_ids": ["Q-LIA-001"],
            "unanswered_question_ids": [],
            "partial": False,
            "confidence": 0.95,
            "text_excerpt": "Counsel responds with initial liability assessment.",
            "reason": "Reply directly addresses Q-LIA-001.",
        }])

        _, report = advance_claim(
            cs,
            "CLM-007",
            new_inbound_docs=[new_doc],
            recipient_directory=_directory(),
            now=_LATER,
            openai_client=oa_client,  # type: ignore[arg-type]
            anthropic_client=ant_client,  # type: ignore[arg-type]
        )

        assert len(report.classified_docs) == 1
        assert report.classified_docs[0].classification == "reply_candidate"
        # Disclosure path did NOT fire.
        assert report.disclosures_added == 0
        # Ingest path DID fire.
        assert report.correspondence is not None
        assert len(report.correspondence.ingest_outcomes) == 1
        assert report.correspondence.ingest_outcomes[0].outcome == "matched"

    def test_reply_candidate_doc_added_via_correspondence_not_disclosure_path(self):
        """When the parser matches, the doc lands in caseload.documents
        — but it got there via `IngestReply.apply_outcome`, not via
        the disclosure-direct-add. The audit trail differs."""
        sent = _sent_outbound()
        cs = _caseload(outbounds=[sent])
        new_doc = _doc(
            "DOC-REPLY-2",
            document_type="claimant_counsel_letter",
            received_at=_LATER,
        )

        oa_client = _StubOAIClient(_PASSING_BODY)
        ant_client = _StubAnthroClient([{
            "matched_outbound_id": "OBR-001",
            "answered_question_ids": ["Q-LIA-001"],
            "unanswered_question_ids": [],
            "partial": False,
            "confidence": 0.95,
            "text_excerpt": "Counsel responds with initial liability assessment.",
            "reason": "Reply directly addresses Q-LIA-001.",
        }])

        new_cs, report = advance_claim(
            cs,
            "CLM-007",
            new_inbound_docs=[new_doc],
            recipient_directory=_directory(),
            now=_LATER,
            openai_client=oa_client,  # type: ignore[arg-type]
            anthropic_client=ant_client,  # type: ignore[arg-type]
        )

        # Doc IS in caseload.documents — but disclosures_added counter
        # says it didn't come from the disclosure path.
        assert any(d.document_id == "DOC-REPLY-2" for d in new_cs.documents)
        assert report.disclosures_added == 0


# ---------------------------------------------------------------------------
# Cross-claim safety
# ---------------------------------------------------------------------------


class TestOffClaimSafety:
    def test_off_claim_doc_ignored(self):
        """A doc whose claim_id differs from the advance's claim_id is
        not classified, not ingested, not added. Stays out of both
        streams."""
        cs = _caseload()
        wrong_claim_doc = _doc("DOC-OTHER-1", claim_id="CLM-999")

        new_cs, report = advance_claim(
            cs,
            "CLM-007",
            new_inbound_docs=[wrong_claim_doc],
            recipient_directory=_directory(),
            now=_NOW,
            openai_client=_StubOAIClient(_PASSING_BODY),  # type: ignore[arg-type]
        )

        assert report.classified_docs == []
        assert report.disclosures_added == 0
        assert all(d.document_id != "DOC-OTHER-1" for d in new_cs.documents)


# ---------------------------------------------------------------------------
# Composition — both streams fire in one advance
# ---------------------------------------------------------------------------


class TestComposition:
    def test_no_docs_still_runs_correspondence(self):
        """advance_claim with no inbound docs still calls the
        correspondence advance. On an empty claim, InfoGap proposes
        and Drafter drafts."""
        cs = _caseload()

        _, report = advance_claim(
            cs,
            "CLM-007",
            recipient_directory=_directory(),
            now=_NOW,
            openai_client=_StubOAIClient(_PASSING_BODY),  # type: ignore[arg-type]
        )

        assert report.classified_docs == []
        assert report.correspondence is not None
        assert report.correspondence.info_gap_outcome is not None
        assert report.correspondence.info_gap_outcome.proposals
        assert report.correspondence.draft_outcomes

    def test_disclosure_plus_correspondence_in_one_advance(self):
        """A fresh disclosure lands AND correspondence proposes more
        outbounds on the same advance call. One report carries both."""
        cs = _caseload()
        disclosure = _doc("DOC-FRESH-1")

        new_cs, report = advance_claim(
            cs,
            "CLM-007",
            new_inbound_docs=[disclosure],
            recipient_directory=_directory(),
            now=_NOW,
            openai_client=_StubOAIClient(_PASSING_BODY),  # type: ignore[arg-type]
        )

        # Disclosure landed.
        assert report.disclosures_added == 1
        assert any(d.document_id == "DOC-FRESH-1" for d in new_cs.documents)
        # Correspondence still fired.
        assert report.correspondence is not None
        assert report.correspondence.info_gap_outcome is not None

    def test_input_caseload_not_mutated(self):
        cs = _caseload()
        original_doc_count = len(cs.documents)
        original_ob_count = len(cs.outbound_requests)

        advance_claim(
            cs,
            "CLM-007",
            new_inbound_docs=[_doc("DOC-MUT-1")],
            recipient_directory=_directory(),
            now=_NOW,
            openai_client=_StubOAIClient(_PASSING_BODY),  # type: ignore[arg-type]
        )

        assert len(cs.documents) == original_doc_count
        assert len(cs.outbound_requests) == original_ob_count


# ---------------------------------------------------------------------------
# Report shape
# ---------------------------------------------------------------------------


class TestReportShape:
    def test_summary_includes_both_streams(self):
        cs = _caseload()
        _, report = advance_claim(
            cs,
            "CLM-007",
            new_inbound_docs=[_doc("DOC-SUM-1")],
            recipient_directory=_directory(),
            now=_NOW,
            openai_client=_StubOAIClient(_PASSING_BODY),  # type: ignore[arg-type]
        )

        s = report.summary()
        assert "Advance(CLM-007)" in s
        assert "disclosures" in s
        assert "Correspondence" in s

    def test_returns_claim_advance_report_instance(self):
        cs = _caseload()
        _, report = advance_claim(
            cs,
            "CLM-007",
            recipient_directory=_directory(),
            now=_NOW,
            openai_client=_StubOAIClient(_PASSING_BODY),  # type: ignore[arg-type]
        )
        assert isinstance(report, ClaimAdvanceReport)


# ---------------------------------------------------------------------------
# Analysis re-trigger on new docs — Reader + dispatcher + JobQueue
# ---------------------------------------------------------------------------


def _make_stub_reader(per_doc: dict[str, RelevanceCall]):
    """Build a stub reader_fn that returns the queued call for each doc_id.

    Any doc_id without a queued call gets a default `relevant=False`
    call (treated as routine; no analysis Jobs enqueued)."""
    def stub(doc_input: DocumentInput, ctx: ClaimContext) -> RelevanceCallResult:
        call = per_doc.get(
            doc_input.document_id,
            RelevanceCall(
                document_id=doc_input.document_id,
                relevant=False,
                posture_changed=None,
                reason="routine — no posture shift.",
                text_excerpt="",
            ),
        )
        return RelevanceCallResult(
            call=call,
            model="claude-sonnet-4-6-stub",
            attempts=1,
            raw_tool_input={},
        )
    return stub


class TestAnalysisReTriggerOptIn:
    """When `job_queue` is None, the re-trigger is skipped entirely."""

    def test_no_queue_means_no_retrigger(self):
        cs = _caseload()
        disclosure = _doc("DOC-RT-1")

        _, report = advance_claim(
            cs,
            "CLM-007",
            new_inbound_docs=[disclosure],
            recipient_directory=_directory(),
            now=_NOW,
            openai_client=_StubOAIClient(_PASSING_BODY),  # type: ignore[arg-type]
        )

        # Disclosure landed, but no Jobs were enqueued (no queue supplied).
        assert report.disclosures_added == 1
        assert report.analysis_jobs_enqueued == []


class TestAnalysisReTriggerOnDisclosures:
    """When a queue is supplied AND new disclosures land, the Reader
    runs on each, dispatcher converts the calls into Jobs, queue
    enqueues them."""

    def test_disclosure_marked_relevant_enqueues_jobs(self):
        cs = _caseload()
        disclosure = _doc(
            "DOC-RT-2",
            document_type="police_report",
            received_date=date(2026, 5, 28),
        )
        queue = JobQueue()

        reader = _make_stub_reader({
            "DOC-RT-2": RelevanceCall(
                document_id="DOC-RT-2",
                relevant=True,
                posture_changed="liability",
                reason="Police report establishes liability posture.",
                text_excerpt="Officer arrived 14:12; driver A failed to yield.",
            ),
        })

        _, report = advance_claim(
            cs,
            "CLM-007",
            new_inbound_docs=[disclosure],
            recipient_directory=_directory(),
            now=_NOW,
            openai_client=_StubOAIClient(_PASSING_BODY),  # type: ignore[arg-type]
            job_queue=queue,
            reader_fn=reader,
        )

        # Liability posture → one Liability Job per the dispatcher table.
        assert len(report.analysis_jobs_enqueued) == 1
        job = report.analysis_jobs_enqueued[0]
        assert job.workflow == "liability"
        assert job.claim_id == "CLM-007"
        assert job.triggered_by_doc_id == "DOC-RT-2"
        # Queue actually has the job.
        assert any(j.job_id == job.job_id for j in queue.all_jobs())

    def test_disclosure_marked_not_relevant_enqueues_nothing(self):
        cs = _caseload()
        disclosure = _doc("DOC-RT-3", document_type="acknowledgment_letter")
        queue = JobQueue()
        reader = _make_stub_reader({})  # default = not relevant

        _, report = advance_claim(
            cs,
            "CLM-007",
            new_inbound_docs=[disclosure],
            recipient_directory=_directory(),
            now=_NOW,
            openai_client=_StubOAIClient(_PASSING_BODY),  # type: ignore[arg-type]
            job_queue=queue,
            reader_fn=reader,
        )

        assert report.analysis_jobs_enqueued == []
        assert queue.all_jobs() == []

    def test_damages_posture_enqueues_both_reserve_and_liability(self):
        """`damages` posture → POSTURE_TO_WORKFLOWS returns [reserve,
        liability]; both Jobs land in the queue."""
        cs = _caseload()
        disclosure = _doc(
            "DOC-RT-4", document_type="medical_provider_summary",
        )
        queue = JobQueue()

        reader = _make_stub_reader({
            "DOC-RT-4": RelevanceCall(
                document_id="DOC-RT-4",
                relevant=True,
                posture_changed="damages",
                reason="Medical records establish severity and exposure.",
                text_excerpt="Patient discharged 2026-05-20; ongoing PT.",
            ),
        })

        _, report = advance_claim(
            cs,
            "CLM-007",
            new_inbound_docs=[disclosure],
            recipient_directory=_directory(),
            now=_NOW,
            openai_client=_StubOAIClient(_PASSING_BODY),  # type: ignore[arg-type]
            job_queue=queue,
            reader_fn=reader,
        )

        workflows = sorted(j.workflow for j in report.analysis_jobs_enqueued)
        assert workflows == ["liability", "reserve"]


class TestAnalysisReTriggerOnReplyBorneDocs:
    """Docs that land via `IngestReply.apply_outcome` are also new in
    `caseload.documents` this round → they too go through the Reader.
    The classification (disclosure vs reply candidate) is about
    correspondence routing, not analysis materiality."""

    def test_reply_borne_doc_gets_reader_pass(self):
        sent = _sent_outbound()
        cs = _caseload(outbounds=[sent])
        reply_doc = _doc(
            "DOC-RT-REPLY-1",
            document_type="claimant_counsel_letter",
            received_date=date(2026, 5, 30),
        )
        queue = JobQueue()

        oa_client = _StubOAIClient(_PASSING_BODY)
        ant_client = _StubAnthroClient([{
            "matched_outbound_id": "OBR-001",
            "answered_question_ids": ["Q-LIA-001"],
            "unanswered_question_ids": [],
            "partial": False,
            "confidence": 0.95,
            "text_excerpt": "Counsel responds with initial liability assessment.",
            "reason": "Reply directly addresses Q-LIA-001.",
        }])

        reader = _make_stub_reader({
            "DOC-RT-REPLY-1": RelevanceCall(
                document_id="DOC-RT-REPLY-1",
                relevant=True,
                posture_changed="liability",
                reason="Counsel's evaluation reshapes liability posture.",
                text_excerpt="Counsel notes plaintiff likely to seek limits.",
            ),
        })

        _, report = advance_claim(
            cs,
            "CLM-007",
            new_inbound_docs=[reply_doc],
            recipient_directory=_directory(),
            now=_LATER,
            openai_client=oa_client,  # type: ignore[arg-type]
            anthropic_client=ant_client,  # type: ignore[arg-type]
            job_queue=queue,
            reader_fn=reader,
        )

        # Reply was matched (correspondence side).
        assert report.correspondence is not None
        assert report.correspondence.ingest_outcomes[0].outcome == "matched"
        # Analysis re-trigger ALSO fired on the same doc.
        assert len(report.analysis_jobs_enqueued) == 1
        assert report.analysis_jobs_enqueued[0].workflow == "liability"
        assert report.analysis_jobs_enqueued[0].triggered_by_doc_id == "DOC-RT-REPLY-1"


class TestAnalysisReTriggerIdempotence:
    """Calling advance_claim twice with the same doc → second call's
    Reader pass on the same doc returns a Job that the queue rejects
    as a duplicate via the (workflow, claim_id, triggered_by_doc_id)
    idempotency key. The second call's `analysis_jobs_enqueued` is
    empty even though Reader was invoked."""

    def test_second_call_does_not_re_enqueue(self):
        cs = _caseload()
        disclosure = _doc("DOC-RT-IDEM", document_type="police_report")
        queue = JobQueue()

        reader = _make_stub_reader({
            "DOC-RT-IDEM": RelevanceCall(
                document_id="DOC-RT-IDEM",
                relevant=True,
                posture_changed="liability",
                reason="Establishes liability posture.",
                text_excerpt="Officer report attached.",
            ),
        })

        # First call: disclosure lands, Job enqueued.
        cs2, report1 = advance_claim(
            cs,
            "CLM-007",
            new_inbound_docs=[disclosure],
            recipient_directory=_directory(),
            now=_NOW,
            openai_client=_StubOAIClient(_PASSING_BODY),  # type: ignore[arg-type]
            job_queue=queue,
            reader_fn=reader,
        )
        assert len(report1.analysis_jobs_enqueued) == 1
        initial_job_count = len(queue.all_jobs())

        # Second call with the same doc — already in caseload.documents,
        # so it's NOT classified as new in Step 1, and the Reader does
        # not re-run on it. Result: zero fresh enqueues.
        _, report2 = advance_claim(
            cs2,
            "CLM-007",
            new_inbound_docs=[disclosure],
            recipient_directory=_directory(),
            now=_NOW,
            openai_client=_StubOAIClient(_PASSING_BODY),  # type: ignore[arg-type]
            job_queue=queue,
            reader_fn=reader,
        )
        assert report2.analysis_jobs_enqueued == []
        assert len(queue.all_jobs()) == initial_job_count
