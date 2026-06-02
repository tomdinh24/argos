"""Outreach Drafter workflow schemas — input + output.

The Outreach Drafter is a single-shot, thread-aware LLM workflow
that writes the BODY of one outbound letter from the adjuster to an
external party. It is NOT an agent: no tools, no autonomous action.
The "memory" is the relational layer (`OutboundRequest` records +
Reply Parser results), assembled into structured input on each call.

Architectural pattern: stateless LLM, stateful caller. The drafter
receives a structured snapshot of the per-recipient thread plus the
current letter's purpose and open question IDs, and emits the body.
The persistence layer is the source of truth across calls.

Decision context: docs/DECISIONS.md →
  "Outreach Drafter consumes a per-recipient info-map slice"
  "Outreach Drafter v1" (when shipped)
  "Step 3 split: 3a (OutboundRequest data) ships now; 3b (LLM drafter) waits"
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


ThreadDirection = Literal["sent", "received"]


class OpenQuestionRef(BaseModel):
    """A reference to one info-map question the letter must address.

    Carries both the internal `id` (for traceability + lint linkage to
    `OutboundRequest.question_ids_asked`) and the human-readable
    `description` (what the model uses to write the prose).

    The model is instructed to write about the description, NOT to
    print the ID in the letter body. The ID stays in metadata.
    """

    id: str = Field(
        description=(
            "Stable info-map ID (e.g., 'Q-LIA-001'). Internal — must "
            "not appear in the letter body."
        )
    )
    description: str = Field(
        description=(
            "Plain-English description of what the recipient needs to "
            "address. The model writes prose about this; e.g., "
            "'counsel's initial liability assessment'."
        ),
        min_length=1,
    )


class OutreachThreadTurn(BaseModel):
    """One turn in the (claim_id, recipient_party, named_party) thread.

    A `sent` turn is one of our outbound letters. A `received` turn is
    an inbound reply. Together, an ordered list of turns forms the
    conversation history the drafter sees.

    The drafter uses `question_ids_asked` to know what we've already
    asked (so we don't restate), and the answered/unanswered split on
    received turns to know what is still outstanding.
    """

    direction: ThreadDirection = Field(
        description="'sent' = our outbound; 'received' = their reply."
    )
    turn_date: date = Field(
        description=(
            "Date of the turn. Used in the prompt for explicit "
            "back-references ('Following our letter of [date]...')."
        )
    )
    summary: str = Field(
        description=(
            "One- or two-sentence plain-English summary of the turn. "
            "Caller-supplied; not parsed by the model."
        ),
        min_length=1,
    )
    question_ids_asked: list[str] = Field(
        default_factory=list,
        description=(
            "Question IDs asked on this turn. Populated for 'sent' "
            "turns; empty list for 'received' turns."
        ),
    )
    question_ids_answered: list[str] = Field(
        default_factory=list,
        description=(
            "Question IDs the recipient answered on this turn. "
            "Populated for 'received' turns (from Reply Parser); empty "
            "for 'sent' turns."
        ),
    )
    question_ids_unanswered: list[str] = Field(
        default_factory=list,
        description=(
            "Question IDs that remained unanswered after this turn. "
            "Populated for 'received' turns; empty for 'sent' turns."
        ),
    )


class OutreachDrafterInput(BaseModel):
    """What the Outreach Drafter consumes for one letter.

    Everything the model needs is here — no retrieval, no tools. The
    caller assembles this from `Caseload`/`OutboundRequest` state via
    `build_drafter_input_for_outbound` (or hand-built for tests).

    Thread identity: (`claim_id`, `recipient_party`, `recipient_name`).
    Recipient substitution (counsel withdraws + new counsel appears,
    different records-desk staffer responds) resets the thread, so
    `recipient_name` is part of the key, not just party type.
    """

    # ---- Identity ----
    claim_id: str
    recipient_party: str = Field(
        description=(
            "Free-form party identifier matching info-map source.party "
            "values: 'defense_counsel', 'claimant_counsel', "
            "'medical_provider', 'body_shop', 'police_records', etc."
        )
    )
    recipient_name: str = Field(
        description=(
            "Named recipient. Part of the thread key — counsel "
            "substitution resets the thread."
        )
    )

    # ---- Claim-level facts the letter references ----
    claimant_name: str
    insured_name: str
    date_of_loss: date
    coverage_posture: Literal[
        "under_investigation", "ROR_issued", "denied", "accepted"
    ] = Field(
        default="under_investigation",
        description=(
            "Carrier's current coverage stance on this claim. Drives "
            "framing: at ROR_issued, every letter to claimant/insured/"
            "counsel MUST include the reservation-of-rights caveat "
            "paragraph so the communication doesn't waive the position. "
            "At denied, the system should not be drafting routine "
            "asks to claimant/insured — that's escalation territory. "
            "Default under_investigation = no special framing."
        ),
    )

    # ---- The current letter ----
    letter_purpose: str = Field(
        description=(
            "One-paragraph plain-English statement of why this letter "
            "is being sent. Caller-authored; shapes the model's framing."
        ),
        min_length=1,
    )
    open_questions: list[OpenQuestionRef] = Field(
        description=(
            "Info-map questions this letter is asking about, with "
            "both ID (internal traceability) and description (what "
            "the model writes prose about). The caller has already "
            "pre-filtered to questions applicable to this recipient "
            "and still open. The model is instructed to use the "
            "DESCRIPTION in the body and NEVER print the ID."
        ),
    )

    # ---- The thread (NEW vs Option A) ----
    conversation_history: list[OutreachThreadTurn] = Field(
        default_factory=list,
        description=(
            "Chronologically-ordered prior turns with this recipient "
            "on this claim. Empty list = first letter on the thread."
        ),
    )
    older_history_summary: str | None = Field(
        default=None,
        description=(
            "When the thread has more than ~5 turns, the caller may "
            "supply a one-line summary of older turns ('Prior "
            "exchanges from 2025-11-04 to 2026-02-12 resolved "
            "Q-LIA-001, Q-DAM-002.') instead of including them all "
            "in `conversation_history`. The model is instructed to "
            "treat this as context, not detail."
        ),
    )


class OutreachDrafterResult(BaseModel):
    """What `run_outreach_drafter` returns: the drafted body plus
    deterministic lint metadata and run metadata for audit.

    The drafter does NOT decide whether the letter is "good enough" to
    send — it surfaces the body and the lint metrics, and the adjuster
    (or a downstream action) decides. The `lint_passes` boolean is a
    SIGNAL, not a gate.
    """

    body_text: str = Field(
        description=(
            "The letter body, paragraphs separated by blank lines. "
            "No salutation, no header, no signature block."
        ),
        min_length=1,
    )
    lint_metrics: dict = Field(
        description=(
            "Full output of `run_anti_slop_lint(body_text)` — every "
            "deterministic check the lint runs. Surfaced to the "
            "adjuster as the signal layer."
        ),
    )
    lint_passes: bool = Field(
        description="Convenience flag: `lint_metrics['passes']`."
    )
    model: str = Field(description="Resolved model ID from the API response.")
    drafted_at: datetime = Field(
        description="When the draft completed. Caller-supplied for determinism."
    )
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)


__all__ = [
    "OpenQuestionRef",
    "OutreachDrafterInput",
    "OutreachDrafterResult",
    "OutreachThreadTurn",
    "ThreadDirection",
]
