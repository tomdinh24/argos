"""Reply Parser workflow runtime.

Single-shot LLM workflow (not an agent — see DECISIONS.md
"Terminology: what we call 'specialists' are AI workflows"). Takes
one inbound document plus the open outbounds on the claim and
emits a validated `ReplyParseResult` saying which outbound this
reply answers and which of that outbound's asked questions are
actually answered.

Decision context: docs/DECISIONS.md →
  "Inbound Reply Handler / Reply Parser" (decision)
  "Build order locked" step 4 (sequencing)
  "System flow target (canonical, full loop)" (where this fits)
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from anthropic import Anthropic
from pydantic import ValidationError

from argos.ontology.types import Document, OutboundRequest
from argos.schemas.workflows.reply_parser import ReplyParseResult


DEFAULT_MODEL = "claude-sonnet-4-6"
TOOL_NAME = "emit_reply_parse_result"


SYSTEM_PROMPT = """\
You are the Reply Parser for Argos. You read ONE inbound document \
(a reply from an external party — counsel, body shop, medical \
provider, etc.) plus a list of OPEN OUTBOUND REQUESTS on the \
claim. You decide:

1. Which outbound (OBR-XXX) this reply is answering.
2. Which of that outbound's asked questions are answered by the \
reply content.
3. Which remain unanswered (so the adjuster knows what to chase next).

MATCHING THE OUTBOUND:

- The reply will usually reference the outbound explicitly (subject \
line, RE: thread, claim number, prior message). When it does, match \
on that.
- When the reply doesn't explicitly reference the outbound, match \
on content: which outbound's question_ids_asked are answered by \
the body of the reply?
- If two outbounds share question subject matter (e.g., two separate \
medical-records requests to different providers), match on the \
specific provider / recipient identifier in the reply.
- You MUST pick one of the supplied outbound IDs. Do not invent a \
new one.

DECIDING WHICH QUESTIONS ARE ANSWERED:

- A question is answered when the reply body contains the actual \
information requested. A reply saying "we received your request and \
will respond within 30 days" answers NOTHING — that's \
acknowledgement-only.
- A reply containing the specific information (e.g., "the policy \
declarations page is attached" with the attached content) answers \
the underlying question.
- Partial replies are common. "Here are the medical records through \
2026-03; surgical records still being compiled" answers \
Q-DAM-001/002 partially. Mark `partial=true` and put the answered \
subset in `answered_question_ids`.
- For acknowledgement-only replies, set `answered_question_ids=[]`, \
`unanswered_question_ids` = the full asked set, `partial=true`, \
and explain in `reason`.

PARTITION INVARIANT:

- `answered_question_ids` and `unanswered_question_ids` MUST \
together equal the matched outbound's full `question_ids_asked` set.
- No overlap. No invented question IDs.

EVIDENCE:

- `text_excerpt` MUST be a verbatim quote from the inbound document \
body that establishes the answer. Required when any question is \
answered. May be empty for acknowledgement-only replies.

CONFIDENCE:

- 0.9+ when the reply explicitly references the outbound and \
contains the asked information.
- 0.7-0.9 when matching is content-based and the answer is clear.
- 0.5-0.7 when matching is ambiguous or the answer is partial / \
indirect.
- Below 0.5 means escalate — you're guessing. Pick the best match \
but flag it with low confidence so the orchestrator routes to a \
human.

Output via the `emit_reply_parse_result` tool. The tool's \
input_schema is the contract — outputs that violate it are rejected \
upstream.
"""


@dataclass
class ReplyParserResult:
    """What `run_reply_parser` returns: validated parse result plus
    run metadata."""

    result: ReplyParseResult
    model: str
    attempts: int
    raw_tool_input: dict[str, Any]


def _render_outbound_summary(o: OutboundRequest) -> str:
    """One-block summary of an outbound for the prompt."""
    return "\n".join([
        f"OUTBOUND_ID: {o.request_id}",
        f"  recipient: {o.recipient_party}",
        f"  sent_at: {o.sent_at.isoformat() if o.sent_at else 'unknown'}",
        f"  channel: {o.channel or 'unknown'}",
        f"  questions_asked: {', '.join(o.question_ids_asked)}",
        f"  draft_body_excerpt: "
        + (
            (o.draft_body[:200] + ("..." if len(o.draft_body) > 200 else ""))
            if o.draft_body else "(none)"
        ),
    ])


def _render_user_body(
    inbound_doc: Document,
    open_outbounds: list[OutboundRequest],
) -> str:
    """Render the user-message body the Reply Parser reads."""
    lines = [
        "=== INBOUND DOCUMENT ===",
        f"document_id: {inbound_doc.document_id}",
        f"document_type: {inbound_doc.document_type}",
        f"source: {inbound_doc.source}",
        f"received_date: {inbound_doc.received_date.isoformat()}",
        "",
        "body_text:",
        inbound_doc.body_text,
        "",
        "=== OPEN OUTBOUND REQUESTS ON THIS CLAIM ===",
    ]
    if not open_outbounds:
        lines.append("(none — escalate; reply cannot be matched)")
    else:
        for o in open_outbounds:
            lines.append(_render_outbound_summary(o))
            lines.append("")
    return "\n".join(lines)


def _tool_schema() -> dict[str, Any]:
    return {
        "name": TOOL_NAME,
        "description": (
            "Emit the Reply Parser's mapping for this inbound document. "
            "matched_outbound_id must be one of the supplied open "
            "outbounds; answered + unanswered partition must equal "
            "that outbound's full question_ids_asked set."
        ),
        "input_schema": ReplyParseResult.model_json_schema(),
    }


def run_reply_parser(
    inbound_doc: Document,
    open_outbounds: list[OutboundRequest],
    *,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 2_000,
    max_retries: int = 1,
    _client: Anthropic | None = None,
) -> ReplyParserResult:
    """Run the Reply Parser on one inbound document.

    Validates that the model's `matched_outbound_id` is one of the
    supplied outbounds, and that the answered+unanswered partition
    equals that outbound's `question_ids_asked` exactly. Retries
    once on validation failure (Pydantic OR runtime invariants) with
    the error fed back as a corrective system note.

    Raises `ValueError` if `open_outbounds` is empty — that's a
    caller-side bug; the parser has nothing to match against.
    """
    if not open_outbounds:
        raise ValueError(
            "run_reply_parser: open_outbounds is empty. Reply Parser "
            "needs at least one candidate outbound to match against. "
            "Caller should escalate to human triage instead of "
            "invoking the parser."
        )

    client = _client or Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    tool = _tool_schema()
    user_body = _render_user_body(inbound_doc, open_outbounds)
    candidate_ids = {o.request_id for o in open_outbounds}
    asked_by_outbound = {
        o.request_id: set(o.question_ids_asked) for o in open_outbounds
    }

    last_error: str | None = None

    for attempt in range(max_retries + 1):
        system_text = SYSTEM_PROMPT
        if last_error is not None:
            system_text = (
                SYSTEM_PROMPT
                + "\n\n--- PRIOR ATTEMPT REJECTED ---\n"
                + "Your previous output failed validation with this "
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

        try:
            result = ReplyParseResult.model_validate(tool_input)
        except ValidationError as e:
            last_error = str(e)
            continue

        # Runtime invariant 1: matched_outbound_id is a real candidate.
        if result.matched_outbound_id not in candidate_ids:
            last_error = (
                f"matched_outbound_id={result.matched_outbound_id!r} is "
                f"not in the supplied open outbounds. Valid IDs: "
                f"{sorted(candidate_ids)}."
            )
            continue

        # Runtime invariant 2: answered + unanswered partition the
        # matched outbound's full asked set.
        asked = asked_by_outbound[result.matched_outbound_id]
        emitted = set(result.answered_question_ids) | set(
            result.unanswered_question_ids
        )
        if emitted != asked:
            missing = asked - emitted
            extra = emitted - asked
            last_error = (
                f"answered + unanswered must equal "
                f"matched_outbound's question_ids_asked exactly. "
                f"Missing from your output: {sorted(missing)}. "
                f"Extra (not in asked set): {sorted(extra)}."
            )
            continue

        return ReplyParserResult(
            result=result,
            model=resp.model,
            attempts=attempt + 1,
            raw_tool_input=tool_input if isinstance(tool_input, dict) else {},
        )

    raise RuntimeError(
        f"Reply Parser failed validation after {max_retries + 1} "
        f"attempts. Last error:\n{last_error}"
    )


__all__ = [
    "DEFAULT_MODEL",
    "ReplyParserResult",
    "TOOL_NAME",
    "run_reply_parser",
]
