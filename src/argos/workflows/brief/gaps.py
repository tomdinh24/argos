"""Gap rationale LLM call for the Brief specialist.

Takes the list of `RawGap` from the assembler and, in one batched LLM
call, turns each into a `MissingInfoItem` — humanized name, rationale
(why_it_matters), and citations.

Citation excerpts may be empty strings when the gap is about
*absence* of a document type (e.g., "policy declarations missing"
cites the docs we DO have, none of which contain policy declarations
— there is no quotable text). The schema permits this; only the list
length is constrained to >=1.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from anthropic import Anthropic
from pydantic import BaseModel, Field, ValidationError

from argos.schemas.contract import EvidenceCitation
from argos.schemas.workflows.brief import MissingInfoItem
from argos.workflows.brief.assembler import BriefDraft, RawGap


DEFAULT_MODEL = "claude-sonnet-4-6"
TOOL_NAME = "emit_brief_gaps"


SYSTEM_PROMPT = """\
You are the Brief specialist for Argos, writing the "open gaps" \
section. For each detected gap, write a humanized name and a one-line \
"why it matters" rationale an adjuster can act on.

For every gap you process:
- `item`: human-readable name for the missing thing (e.g., \
"Policy declarations page", "ISO claim search result").
- `requested_from`: party who would supply it (passed through from \
input — use the value provided).
- `why_it_matters`: ONE sentence on what is at risk if this stays \
missing. Plain English, adjuster-readable. No headings. No marketing.
- `citations`: 1 to 3 document_ids from the on-file documents. \
text_excerpt may be empty when the gap is about ABSENCE (we cite the \
docs we have to prove the missing thing is not among them). When the \
gap is about something present in the docs but flagged, quote the \
relevant text.

RULES:
- Process every input gap. Do not drop one. Do not add new ones.
- Citations must use document_ids from the input documents list.
- If no documents are on file, do not invent citations — instead, \
echo back zero gaps. (The assembler is responsible for not asking \
when there's nothing to cite.)
- One sentence per `why_it_matters`. Do not stack reasons.

Output via the `emit_brief_gaps` tool.
"""


# ---------------------------------------------------------------------------
# LLM output schema (intermediate)
# ---------------------------------------------------------------------------


class _GapCitationCandidate(BaseModel):
    document_id: str
    text_excerpt: str = Field(
        description=(
            "Verbatim quote from the cited document body, OR empty string "
            "when the gap is about absence and the citation proves what we "
            "do have."
        )
    )


class _GapOutput(BaseModel):
    variable: str = Field(description="Echo the input variable name unchanged")
    item: str
    requested_from: str
    why_it_matters: str = Field(min_length=1)
    citations: list[_GapCitationCandidate] = Field(min_length=1, max_length=3)


class _GapsBatchOutput(BaseModel):
    gaps: list[_GapOutput]


@dataclass
class GapsResult:
    missing_info: list[MissingInfoItem]
    model: str
    attempts: int
    raw_tool_input: dict[str, Any]


# ---------------------------------------------------------------------------
# Prompt rendering
# ---------------------------------------------------------------------------


def _render_user_body(draft: BriefDraft) -> str:
    lines = [
        f"=== CLAIM CONTEXT ===",
        f"claim_id: {draft.claim_id}",
        f"severity_tier: {draft.claim.severity_tier_summary}",
        f"litigation_flag: {draft.claim.litigation_flag}",
        f"rep_flag: {draft.claim.rep_flag}",
        "",
        "=== DOCUMENTS ON FILE ===",
    ]
    if not draft.documents:
        lines.append("(none)")
    for d in draft.documents:
        lines.append(
            f"--- document_id: {d.document_id} "
            f"(type={d.document_type}, source={d.source}) ---"
        )
        # Truncate doc body for the gap call — gaps don't need full body, just enough to cite
        excerpt = d.body_text[:600]
        lines.append(excerpt)
        if len(d.body_text) > 600:
            lines.append("... [truncated]")
        lines.append("")

    lines.append("=== GAPS TO RATIONALIZE ===")
    for g in draft.raw_gaps:
        lines.append(
            f"- variable: {g.variable}, requested_from: {g.requested_from}"
        )
    return "\n".join(lines)


def _tool_schema() -> dict[str, Any]:
    return {
        "name": TOOL_NAME,
        "description": (
            "Emit one rationalized entry per input gap. The variable field "
            "must echo the input variable unchanged. Process every input gap; "
            "do not drop or add."
        ),
        "input_schema": _GapsBatchOutput.model_json_schema(),
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run_gaps(
    draft: BriefDraft,
    *,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 2_000,
    max_retries: int = 1,
    _client: Anthropic | None = None,
) -> GapsResult:
    """Rationalize all raw gaps in one LLM call. Returns `MissingInfoItem`s.

    Returns an empty list (skipping the LLM call entirely) when:
    - There are no raw gaps, OR
    - There are no documents on file (citations require at least one
      document_id from the on-file set).
    """
    if not draft.raw_gaps:
        return GapsResult(
            missing_info=[], model=model, attempts=0, raw_tool_input={}
        )

    if not draft.documents:
        # Can't satisfy citation min_length=1 with documents that don't exist.
        # Honest: emit no missing_info; the gap is still visible in raw_gaps
        # for callers who want it.
        return GapsResult(
            missing_info=[], model=model, attempts=0, raw_tool_input={}
        )

    client = _client or Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    tool = _tool_schema()
    user_body = _render_user_body(draft)
    valid_doc_ids = {d.document_id for d in draft.documents}
    expected_variables = {g.variable for g in draft.raw_gaps}

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
            parsed = _GapsBatchOutput.model_validate(tool_input)
        except ValidationError as e:
            last_error = str(e)
            continue

        emitted_variables = {g.variable for g in parsed.gaps}
        if emitted_variables != expected_variables:
            last_error = (
                f"Emitted gaps must match input variables exactly. "
                f"Expected: {sorted(expected_variables)}. "
                f"Got: {sorted(emitted_variables)}."
            )
            continue

        bad_doc_ids = [
            c.document_id
            for g in parsed.gaps
            for c in g.citations
            if c.document_id not in valid_doc_ids
        ]
        if bad_doc_ids:
            last_error = (
                f"Citations reference unknown document_id(s): {bad_doc_ids}. "
                f"Valid document_ids: {sorted(valid_doc_ids)}"
            )
            continue

        missing_info = [
            MissingInfoItem(
                item=g.item,
                requested_from=g.requested_from,
                requested_at=None,
                response_due=None,
                correspondence_status="not_yet_drafted",
                evidence_citations=[
                    EvidenceCitation(
                        document_id=c.document_id,
                        locator="body",
                        text_excerpt=c.text_excerpt,
                        relation=("supports" if c.text_excerpt else "contextual"),
                    )
                    for c in g.citations
                ],
            )
            for g in parsed.gaps
        ]

        return GapsResult(
            missing_info=missing_info,
            model=resp.model,
            attempts=attempt + 1,
            raw_tool_input=tool_input if isinstance(tool_input, dict) else {},
        )

    raise RuntimeError(
        f"Brief gap rationalization failed after {max_retries + 1} attempts. "
        f"Last error:\n{last_error}"
    )


# ---------------------------------------------------------------------------
# Pure helper for callers who want to render `RawGap` deterministically
# ---------------------------------------------------------------------------


def humanize_variable(variable: str) -> str:
    """Default human-readable name for a RawGap variable.

    Used as a fallback when the LLM call is skipped (no docs on file)
    and a caller wants to surface raw_gaps as a degraded missing_info
    list.
    """
    return variable.replace("_", " ").capitalize()


__all__ = [
    "DEFAULT_MODEL",
    "GapsResult",
    "humanize_variable",
    "run_gaps",
]
