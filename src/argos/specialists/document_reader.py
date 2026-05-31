"""Document Reader specialist runtime.

Reads one document (body + metadata) and minimal claim context, returns
a validated `MaterialityCall`. Forces JSON output via Anthropic
tool_use; on Pydantic validation failure retries once with the error
fed back.

Spec: docs/specs/document-reader.md
Thresholds: docs/evals/document-reader-anchor-pairs-thresholds.md
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from anthropic import Anthropic
from pydantic import ValidationError

from argos.schemas.specialists.document_reader import MaterialityCall


DEFAULT_MODEL = "claude-sonnet-4-6"
TOOL_NAME = "emit_materiality_call"


SYSTEM_PROMPT = """\
You are the Document Reader for Argos. You read ONE document at a time \
on a claim and classify its materiality.

A document is MATERIAL if a competent adjuster's next required action \
on the claim would change after reading it.

A document is NOT MATERIAL if it is routine — status updates, calendar \
reminders, form acknowledgments, courteous correspondence with no new \
posture-changing content.

Output exactly one of these `posture_changed` values when material:
- "reserve" — new information that should change the reserve amount \
(new diagnosis, surgical recommendation, cost estimate, extended treatment)
- "liability" — new fault determination, citation, witness statement, \
admission, police finding
- "coverage" — new tender denial, coverage dispute, reservation of rights \
notice from another carrier, exclusion fact
- "damages" — new demand number, settlement offer with figure, judgment, \
verdict, lien notice

Set `posture_changed = null` when material is false.

EXEMPLARS (use these to anchor the decision boundary):

NOT MATERIAL — example 1:
Document body: "Hi adjuster, following up on our call last Thursday. \
The claimant has asked when she can expect a status update. Please advise \
when convenient. Best regards, John Smith, Esq."
Call: material=false, posture_changed=null, text_excerpt="", \
reason="Routine status-update inquiry from claimant counsel; no new \
posture-changing content."

NOT MATERIAL — example 2:
Document body: "Acknowledgment: we have received your correspondence \
dated 4/12/2026. A representative will respond within 10 business days."
Call: material=false, posture_changed=null, text_excerpt="", \
reason="Form acknowledgment of receipt; no substantive content."

MATERIAL — liability example:
Document body: "...Officer Jones responded to the scene at 14:32. \
Driver of V-1 was issued citation under FSS 316.123(2) for failure to \
yield at uncontrolled intersection..."
Call: material=true, posture_changed="liability", \
text_excerpt="Driver of V-1 was issued citation under FSS 316.123(2) \
for failure to yield at uncontrolled intersection", \
reason="Police citation issued to insured driver for traffic violation; \
fault posture changes."

MATERIAL — damages example:
Document body: "...Accordingly, our client hereby demands the policy \
limits of $300,000.00 to fully resolve all claims..."
Call: material=true, posture_changed="damages", \
text_excerpt="our client hereby demands the policy limits of \
$300,000.00 to fully resolve all claims", \
reason="Pre-suit policy-limits demand with specific number; damages \
posture changes."

MATERIAL — coverage example:
Document body: "...After review, Acme Mutual declines your tender of \
defense and indemnity..."
Call: material=true, posture_changed="coverage", \
text_excerpt="Acme Mutual declines your tender of defense and indemnity", \
reason="Co-defendant carrier denial of tender; coverage posture changes \
(no co-defense contribution)."

MATERIAL — reserve example:
Document body: "...MRI dated 2026-05-15 reveals C5-C6 disc herniation \
with nerve root impingement; surgical intervention may be indicated... \
Estimated cost of cervical discectomy and fusion: $85,000–$120,000."
Call: material=true, posture_changed="reserve", \
text_excerpt="Estimated cost of cervical discectomy and fusion: \
$85,000–$120,000", \
reason="New surgical recommendation with cost estimate; reserve posture \
changes."

RULES:
- `text_excerpt` MUST be a verbatim quote (or near-verbatim, ≥80% \
character overlap) from the input document body. Do not paraphrase. \
Do not invent text.
- `text_excerpt` MUST be empty when material is false.
- `posture_changed` MUST be null when material is false.
- One document in, one call out. Do not synthesize across documents.

Output via the `emit_materiality_call` tool. The tool's input_schema is \
the contract — outputs that violate it are rejected upstream.
"""


@dataclass
class ClaimContext:
    """Minimal claim context the Reader sees alongside the document.

    Not the full claim — just enough to make a competent materiality
    call. Cross-document synthesis lives in the per-claim specialists,
    not here.
    """

    claim_id: str
    severity_tier: str
    current_reserve_amount: float
    paid_to_date: float
    litigation_flag: bool
    rep_flag: bool
    complaint_flag: bool
    open_coverage_status: str  # "pending" | "clean" | "ROR" | "denial"
    loss_facts: str            # one-paragraph intake summary


@dataclass
class DocumentInput:
    """The single document the Reader is classifying."""

    document_id: str
    document_type: str
    source: str
    received_date: str  # ISO-format
    body_text: str


@dataclass
class MaterialityCallResult:
    """What `run_document_reader` returns: validated call plus run metadata."""

    call: MaterialityCall
    model: str
    attempts: int
    raw_tool_input: dict[str, Any]


def _render_user_body(doc: DocumentInput, ctx: ClaimContext) -> str:
    """Render the user-message body the Reader reads."""
    return "\n".join([
        "=== CLAIM CONTEXT ===",
        f"claim_id: {ctx.claim_id}",
        f"severity_tier: {ctx.severity_tier}",
        f"current_reserve_amount: ${ctx.current_reserve_amount:,.2f}",
        f"paid_to_date: ${ctx.paid_to_date:,.2f}",
        f"litigation_flag: {ctx.litigation_flag}",
        f"rep_flag: {ctx.rep_flag}",
        f"complaint_flag: {ctx.complaint_flag}",
        f"open_coverage_status: {ctx.open_coverage_status}",
        "",
        "loss_facts:",
        ctx.loss_facts,
        "",
        "=== DOCUMENT ===",
        f"document_id: {doc.document_id}",
        f"document_type: {doc.document_type}",
        f"source: {doc.source}",
        f"received_date: {doc.received_date}",
        "",
        "body_text:",
        doc.body_text,
    ])


def _tool_schema() -> dict[str, Any]:
    return {
        "name": TOOL_NAME,
        "description": (
            "Emit the Document Reader's materiality call for this one document. "
            "When material=true, text_excerpt must be a verbatim quote from "
            "the input document body and posture_changed must be populated. "
            "When material=false, text_excerpt must be empty and posture_changed "
            "must be null."
        ),
        "input_schema": MaterialityCall.model_json_schema(),
    }


def run_document_reader(
    doc: DocumentInput,
    ctx: ClaimContext,
    *,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 2_000,
    max_retries: int = 1,
) -> MaterialityCallResult:
    """Run the Document Reader on one document; return a validated call.

    On Pydantic validation failure, retries up to `max_retries` additional
    times with the error fed back as a corrective system note.
    """
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    tool = _tool_schema()
    user_body = _render_user_body(doc, ctx)

    last_error: str | None = None

    for attempt in range(max_retries + 1):
        system_text = SYSTEM_PROMPT
        if last_error is not None:
            system_text = (
                SYSTEM_PROMPT
                + "\n\n--- PRIOR ATTEMPT REJECTED ---\n"
                + "Your previous output failed schema validation with this "
                + "error. Re-emit the tool call with the issue fixed.\n\n"
                + last_error
            )

        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system_text,
            tools=[tool],
            tool_choice={"type": "tool", "name": TOOL_NAME},
            messages=[{"role": "user", "content": user_body}],
        )

        tool_blocks = [b for b in resp.content if b.type == "tool_use"]
        if not tool_blocks:
            last_error = "Model did not emit a tool_use block. Emit the tool."
            continue

        tool_input = tool_blocks[0].input
        # Force document_id to match the input — the model can drift on this
        # and the schema doesn't enforce identity-with-input.
        if isinstance(tool_input, dict):
            tool_input.setdefault("document_id", doc.document_id)

        try:
            call = MaterialityCall.model_validate(tool_input)
        except ValidationError as e:
            last_error = str(e)
            continue

        return MaterialityCallResult(
            call=call,
            model=resp.model,
            attempts=attempt + 1,
            raw_tool_input=tool_input,
        )

    raise RuntimeError(
        f"Document Reader failed validation after {max_retries + 1} attempts. "
        f"Last error:\n{last_error}"
    )
