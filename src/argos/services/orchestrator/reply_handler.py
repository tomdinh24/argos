"""Inbound-reply orchestration wire — the IngestReply Action.

Glue between an arriving inbound `Document` and the Reply Parser
workflow. Owns the small amount of routing logic that the parser
itself doesn't:

  1. Scope the candidate set — `Caseload.open_outbounds_for_claim`.
  2. Escalate when there are no open outbounds (parser would raise).
  3. Call `run_reply_parser` over the inbound doc + candidates.
  4. Escalate when the parser's confidence is below threshold.
  5. Produce the `OutboundRequest` state transition (sent → replied)
     and surface the answered/unanswered question IDs for downstream
     consumers (Brief gap recompute, Reserve trigger, etc.).
  6. Ingest the inbound document into `Caseload.documents` so the
     next deterministic `is_answered()` pass (Outreach Drafter,
     Brief assembler) sees the new evidence — this is what closes
     the question-state loop. Doc ingestion happens for escalation
     outcomes too: the record arrived; only the outbound state
     transition is gated by a confident parser match.

This module performs NO live LLM calls itself — it delegates to
`run_reply_parser`. Its responsibility is the deterministic routing
around that single workflow call. Symmetric to
`draft_handler.handle_pending_draft` (the DraftOutreach Action) —
together they form the two mutation surfaces on `OutboundRequest`.

Decision context: docs/DECISIONS.md →
  "Inbound Reply Handler / Reply Parser" (decision)
  "Step 4: Reply Parser workflow shipped"
  "Reply Parser orchestration wire shipped" (this module)
  "IngestReply closes the question-state loop"

Palantir mapping: this module is the orchestration logic that, when
moved to Foundry, fires the `IngestReply` Action Type — which
performs two object mutations atomically: marks the matched
`OutboundRequest` as replied AND links the inbound `Document` to the
`Claim` — then emits a `ReplyIngested` event the downstream
pipelines subscribe to.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from anthropic import Anthropic

from argos.ontology.types import Caseload, Document, OutboundRequest
from argos.workflows.reply_parser import ReplyParserResult, run_reply_parser


HandlerOutcome = Literal[
    "matched",                  # parser matched + confidence OK; updated_outbound populated
    "escalate_no_candidates",   # no open outbounds on the claim
    "escalate_low_confidence",  # parser ran but confidence < threshold
]

DEFAULT_MIN_CONFIDENCE = 0.5


@dataclass
class ReplyHandlerOutcome:
    """What the wire produces from one inbound reply.

    `matched` outcomes carry `parsed`, `updated_outbound`, and the
    answered/unanswered question ID partition. Escalations carry
    `reason` and (when the parser ran) `parsed`.

    `inbound_doc` is the full inbound document (not just its id) so
    `apply_outcome` can ingest it into `Caseload.documents`. Every
    outcome — matched or escalated — carries it, because the doc
    arrived in the file regardless of whether the parser confidently
    matched it.
    """

    outcome: HandlerOutcome
    inbound_doc: Document
    claim_id: str
    parsed: ReplyParserResult | None = None
    updated_outbound: OutboundRequest | None = None
    answered_question_ids: list[str] = field(default_factory=list)
    unanswered_question_ids: list[str] = field(default_factory=list)
    reason: str = ""

    @property
    def inbound_doc_id(self) -> str:
        """Convenience for callers that only need the id."""
        return self.inbound_doc.document_id


def handle_inbound_reply(
    inbound_doc: Document,
    caseload: Caseload,
    *,
    now: datetime,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    _client: Anthropic | None = None,
) -> ReplyHandlerOutcome:
    """Route one inbound document through the Reply Parser.

    `now` is the timestamp recorded as `replied_at` on the outbound
    when the match succeeds — passed in explicitly so this function
    is deterministic and easy to test.

    Escalates without calling the parser when there are no open
    outbounds on the claim. Calls the parser otherwise; escalates
    again if the parser's confidence falls below `min_confidence`.
    """
    open_outbounds = caseload.open_outbounds_for_claim(inbound_doc.claim_id)
    if not open_outbounds:
        return ReplyHandlerOutcome(
            outcome="escalate_no_candidates",
            inbound_doc=inbound_doc,
            claim_id=inbound_doc.claim_id,
            reason=(
                f"No open outbounds on claim {inbound_doc.claim_id!r}; "
                f"reply cannot be matched and must be reviewed by a human."
            ),
        )

    parsed = run_reply_parser(
        inbound_doc,
        open_outbounds,
        _client=_client,
    )

    if parsed.result.confidence < min_confidence:
        return ReplyHandlerOutcome(
            outcome="escalate_low_confidence",
            inbound_doc=inbound_doc,
            claim_id=inbound_doc.claim_id,
            parsed=parsed,
            reason=(
                f"Reply Parser confidence {parsed.result.confidence:.2f} is "
                f"below threshold {min_confidence:.2f}; reply needs human "
                f"review before mutating outbound state."
            ),
        )

    matched = _find_outbound(open_outbounds, parsed.result.matched_outbound_id)
    updated_outbound = matched.model_copy(
        update={
            "status": "replied",
            "replied_at": now,
            "reply_doc_id": inbound_doc.document_id,
        }
    )

    return ReplyHandlerOutcome(
        outcome="matched",
        inbound_doc=inbound_doc,
        claim_id=inbound_doc.claim_id,
        parsed=parsed,
        updated_outbound=updated_outbound,
        answered_question_ids=list(parsed.result.answered_question_ids),
        unanswered_question_ids=list(parsed.result.unanswered_question_ids),
    )


def apply_outcome(caseload: Caseload, outcome: ReplyHandlerOutcome) -> Caseload:
    """Apply an IngestReply outcome to a caseload. Returns a new
    Caseload; the input is not mutated.

    Two object mutations, applied atomically:

    1. **Document ingestion** — append `outcome.inbound_doc` to
       `caseload.documents` (idempotent by `document_id`). This
       fires for every outcome (matched or escalated): the record
       arrived; the file should reflect it regardless of whether
       the parser confidently matched it to an outbound. Once
       ingested, the deterministic `is_answered()` check picks up
       the new evidence on the next pass, closing the
       question-state loop without any explicit Q-state object.

    2. **Outbound transition** — replace the matched outbound with
       its updated `replied` state. ONLY fires for `matched`
       outcomes; escalations leave outbounds untouched (the human
       queue resolves them).
    """
    new_documents = list(caseload.documents)
    if not any(d.document_id == outcome.inbound_doc.document_id for d in new_documents):
        new_documents.append(outcome.inbound_doc)

    if outcome.outcome == "matched" and outcome.updated_outbound is not None:
        updated_id = outcome.updated_outbound.request_id
        new_outbounds = [
            outcome.updated_outbound if o.request_id == updated_id else o
            for o in caseload.outbound_requests
        ]
        return caseload.model_copy(update={
            "documents": new_documents,
            "outbound_requests": new_outbounds,
        })

    return caseload.model_copy(update={"documents": new_documents})


def _find_outbound(
    outbounds: list[OutboundRequest], request_id: str
) -> OutboundRequest:
    """Lookup helper — the Reply Parser runtime already validated that
    `matched_outbound_id` is one of the candidates, so missing here
    would be a programmer error."""
    for o in outbounds:
        if o.request_id == request_id:
            return o
    raise AssertionError(
        f"_find_outbound: request_id={request_id!r} not in candidate set "
        f"despite Reply Parser runtime validation. Caller bug."
    )


__all__ = [
    "DEFAULT_MIN_CONFIDENCE",
    "HandlerOutcome",
    "ReplyHandlerOutcome",
    "apply_outcome",
    "handle_inbound_reply",
]
