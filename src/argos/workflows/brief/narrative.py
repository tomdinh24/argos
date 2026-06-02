"""Narrative LLM call for the Brief specialist.

Reads the `BriefDraft` (loss_facts_hint + documents) and emits the
`story_paragraph` + `story_citations`. Same tool_use + retry pattern
as the Document Reader.

The LLM produces {document_id, text_excerpt} per citation; the
runtime converts each to a full `EvidenceCitation`. This mirrors the
Document Reader's pattern of forcing the structural fields post-hoc
rather than relying on the LLM to fill schema-required metadata it
cannot meaningfully choose.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from anthropic import Anthropic
from pydantic import BaseModel, Field, ValidationError

from argos.schemas.contract import EvidenceCitation
from argos.workflows.brief.assembler import BriefDraft


DEFAULT_MODEL = "claude-sonnet-4-6"
TOOL_NAME = "emit_brief_narrative"


SYSTEM_PROMPT = """\
You are the Brief specialist for Argos. Your job is to write a ONE \
PARAGRAPH orientation for an adjuster who just opened a claim.

The paragraph must answer, in plain English: what line of business is \
this, what was the loss event, who is the named insured, who is the \
claimant (if known), what severity tier, and what is the current \
posture (litigation, representation).

LENGTH: 2 to 4 sentences. No bullet lists. No headings.

GROUNDING:
- Every concrete fact in the paragraph must trace to either the loss \
facts hint or a document on file.
- Do not invent dollar amounts, dates, parties, or coverages. If a \
fact is unknown, omit it — do not paraphrase "unknown".
- Do NOT editorialize about absence: do not write "loss details not \
yet documented", "named insured not on file", "FNOL pending", or \
similar meta-commentary. Just omit. The reader knows what's missing \
from the gap list elsewhere in the Brief.
- You may use the loss facts hint as background context; you do not \
need to cite it.
- For every document you do reference, cite it with the document_id \
and a verbatim text_excerpt from that document's body.

STRUCTURED FLAGS ARE AUTHORITATIVE:
- Use the `represented:`, `litigation_flag:`, and `complaint_flag:` \
values from the loss facts hint verbatim. Do NOT describe the \
claimant as "represented by counsel" or the matter as "in litigation" \
based on attorney correspondence in documents alone. An attorney \
letter on file does not by itself mean represented=true — the \
authoritative flag is in the loss facts hint. (If the hint says \
represented: False, write the matter as unrepresented even when \
attorney correspondence appears on file.)
- Use the `coverage_status` value from the loss facts hint verbatim. \
Do NOT paraphrase "pending" as "ROR" or "under reservation of \
rights"; do NOT paraphrase "denied" as "tender refused". If the hint \
says "pending", write "coverage pending" or "coverage determination \
pending" — nothing stronger.

CITATIONS:
- Cite at least one document. If no documents are on file, cite the \
first available document_id in the input with text_excerpt="" and the \
narrative should rely on the loss facts hint only — but the citation \
must still be emitted, because the schema requires min_length=1.

STYLE:
- Adjuster-readable. Industry shorthand is fine (FNOL, ROR, BI, PD, \
SOL). No marketing language.
- Past-tense for the loss event; present-tense for current posture.

Output via the `emit_brief_narrative` tool.
"""


# ---------------------------------------------------------------------------
# LLM output schema (intermediate — runtime converts to EvidenceCitation)
# ---------------------------------------------------------------------------


class _CitationCandidate(BaseModel):
    document_id: str
    text_excerpt: str = Field(
        description=(
            "Verbatim quote (or near-verbatim, >=80% character overlap) "
            "from this document's body that supports the narrative. "
            "Empty string permitted only if no documents are on file."
        )
    )


class _NarrativeOutput(BaseModel):
    story_paragraph: str = Field(min_length=1)
    citations: list[_CitationCandidate] = Field(min_length=1)


@dataclass
class NarrativeResult:
    story_paragraph: str
    story_citations: list[EvidenceCitation]
    model: str
    attempts: int
    raw_tool_input: dict[str, Any]


# ---------------------------------------------------------------------------
# Prompt rendering
# ---------------------------------------------------------------------------


def _render_user_body(draft: BriefDraft) -> str:
    lines = [
        "=== LOSS FACTS HINT ===",
        draft.loss_facts_hint,
        "",
        "=== DOCUMENTS ON FILE ===",
    ]
    if not draft.documents:
        lines.append("(none)")
    for d in draft.documents:
        lines.append(
            f"\n--- document_id: {d.document_id} "
            f"(type={d.document_type}, source={d.source}, "
            f"received={d.received_date.isoformat()}) ---"
        )
        lines.append(d.body_text)
    return "\n".join(lines)


def _tool_schema() -> dict[str, Any]:
    return {
        "name": TOOL_NAME,
        "description": (
            "Emit the Brief narrative paragraph plus the documents it cites. "
            "Every cited document_id must appear in the input documents list. "
            "text_excerpt must be a verbatim quote from that document's body."
        ),
        "input_schema": _NarrativeOutput.model_json_schema(),
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run_narrative(
    draft: BriefDraft,
    *,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 1_500,
    max_retries: int = 1,
    _client: Anthropic | None = None,
) -> NarrativeResult:
    """Run the narrative LLM call; return story_paragraph + citations.

    On Pydantic validation failure or unknown-doc-id citation, retries up
    to `max_retries` additional times with the error fed back.

    `_client` is an injection point for tests.
    """
    client = _client or Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    tool = _tool_schema()
    user_body = _render_user_body(draft)
    valid_doc_ids = {d.document_id for d in draft.documents}

    last_error: str | None = None

    for attempt in range(max_retries + 1):
        system_text = SYSTEM_PROMPT
        if last_error is not None:
            system_text = (
                SYSTEM_PROMPT
                + "\n\n--- PRIOR ATTEMPT REJECTED ---\n"
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
            parsed = _NarrativeOutput.model_validate(tool_input)
        except ValidationError as e:
            last_error = str(e)
            continue

        # Validate every cited document_id exists in the input
        bad = [c.document_id for c in parsed.citations if c.document_id not in valid_doc_ids]
        if bad and valid_doc_ids:
            last_error = (
                f"Citations reference unknown document_id(s): {bad}. "
                f"Valid document_ids: {sorted(valid_doc_ids)}"
            )
            continue

        citations = [
            EvidenceCitation(
                document_id=c.document_id,
                locator="body",
                text_excerpt=c.text_excerpt,
                relation="supports",
            )
            for c in parsed.citations
        ]

        return NarrativeResult(
            story_paragraph=parsed.story_paragraph,
            story_citations=citations,
            model=resp.model,
            attempts=attempt + 1,
            raw_tool_input=tool_input if isinstance(tool_input, dict) else {},
        )

    raise RuntimeError(
        f"Brief narrative failed after {max_retries + 1} attempts. "
        f"Last error:\n{last_error}"
    )
