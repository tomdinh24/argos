"""Intake Reader specialist runtime.

Reads one FNOL bundle (free-text narrative + any attached documents)
and emits a validated `IntakeExtraction`. Forces JSON output via
Anthropic tool_use; on Pydantic validation failure, retries once with
the error fed back.

This is the entry-point layer: claims start as unstructured input,
and this is what turns them into the structured `Claim` /
`CoverageRequest` records the triage policy engine reads.

Decision context: docs/DECISIONS.md →
  "Intake reader is a distinct, unbuilt layer" (decision)
  "Build order locked" step 2 (sequencing)
  "System flow target (canonical, full loop)" (where this fits)
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from anthropic import Anthropic
from pydantic import ValidationError

from argos.schemas.workflows.intake_reader import IntakeExtraction


DEFAULT_MODEL = "claude-sonnet-4-6"
TOOL_NAME = "emit_intake_extraction"


SYSTEM_PROMPT = """\
You are the Intake Reader for Argos. You read ONE FNOL (First Notice \
of Loss) bundle — a free-text narrative plus any attached documents \
(police reports, photos, witness statements) — and extract the \
structured fields the rest of the claim system needs.

Your output drives downstream triage. Get the severity tier and the \
three flags right; everything else is supporting context.

SEVERITY TIER assignment (default to the LOWER tier when uncertain):

- catastrophic: fatality, paralysis, traumatic brain injury, organ \
loss, or other life-altering injury. "Pronounced dead at the scene" \
→ catastrophic. "Paraplegic from C5 injury" → catastrophic.
- serious: hospitalization required, surgery required, broken bones \
beyond a single extremity. "Admitted for surgery on femoral fracture" \
→ serious. "Concussion with overnight observation" → serious.
- standard: medical treatment required but no major surgery, no \
hospitalization beyond ER visit. "Soft tissue injury, prescribed PT" \
→ standard. "Whiplash, treated at urgent care" → standard.
- minor: no injury, or cosmetic damage only. "Property damage only, \
no occupants" → minor. "Sore neck the next day, no treatment" → minor.

FLAG DEFINITIONS (precise — false flagging is more costly than \
under-flagging):

- litigation_flag: TRUE only if a LAWSUIT has been filed OR explicitly \
threatened ("we will sue", "complaint filed", "served papers"). \
Attorney representation alone is NOT litigation_flag.
- rep_flag: TRUE if the claimant is REPRESENTED BY COUNSEL. A letter \
of representation, a lawyer's name on file, or "my attorney" in the \
FNOL all qualify. A lawsuit implies rep_flag too.
- complaint_flag: TRUE if a regulatory complaint (state DOI, AG, BBB) \
about this claim is mentioned. Not the same as a court complaint.

EVIDENCE RULES (load-bearing):

- `severity_evidence` MUST be a verbatim quote from the FNOL bundle \
that supports your tier assignment. Required for every extraction.
- For each flag, the corresponding `*_evidence` field MUST be a \
verbatim quote when the flag is TRUE. MUST be empty when the flag \
is FALSE.
- Do not invent quotes. If you can't find evidence in the bundle, \
the flag is False.

PARTIES + IDENTITY (best-effort):

- `policy_number`: extract if stated; null if not.
- `insured_name`, `claimant_name`: extract if named.

LOSS FACTS:

- `loss_date`: ISO YYYY-MM-DD. If the bundle gives a range, pick the \
earliest plausible date.
- `loss_location`: free-text, as specific as the bundle allows.
- `loss_summary`: 1-3 neutral sentences. Adjuster-readable. No \
editorializing on fault — that's the Liability specialist's job.

EXAMPLES:

FNOL narrative: "Caller reports rear-end collision at I-95 mile 41 \
on 2026-04-12. Their wife was driving their 2022 Camry. Other driver \
ran into them at full speed. Wife pronounced dead at the scene. \
They've already retained Morgan & Morgan and are filing suit."

Extraction:
- severity_tier=catastrophic, severity_evidence="Wife pronounced \
dead at the scene"
- litigation_flag=true, litigation_evidence="filing suit"
- rep_flag=true, rep_evidence="retained Morgan & Morgan"
- complaint_flag=false, complaint_evidence=""
- loss_date=2026-04-12, loss_location="I-95 mile 41"
- loss_summary="Rear-end collision on I-95 resulted in fatality of \
the insured's wife, who was driving."

Output via the `emit_intake_extraction` tool. Outputs that violate \
the schema are rejected upstream.
"""


@dataclass
class IntakeReaderResult:
    """What `run_intake_reader` returns: validated extraction plus
    run metadata."""

    extraction: IntakeExtraction
    model: str
    attempts: int
    raw_tool_input: dict[str, Any]


def _render_user_body(fnol_bundle: str) -> str:
    """Render the user-message body the Intake Reader reads.

    For v1, the FNOL bundle is a single multi-section string. Real
    production bundles are messier (recorded calls, photo OCR,
    multi-document PDFs); the schema accepts whatever the caller
    has assembled into the bundle text.
    """
    return "\n".join([
        "=== FNOL BUNDLE ===",
        fnol_bundle,
    ])


def _tool_schema() -> dict[str, Any]:
    return {
        "name": TOOL_NAME,
        "description": (
            "Emit the Intake Reader's structured extraction for this "
            "FNOL bundle. All evidence fields must be verbatim quotes "
            "from the bundle. Flag-evidence pairs must agree: True "
            "flag → non-empty evidence; False flag → empty evidence."
        ),
        "input_schema": IntakeExtraction.model_json_schema(),
    }


def run_intake_reader(
    fnol_bundle: str,
    *,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 4_000,
    max_retries: int = 1,
    _client: Anthropic | None = None,
) -> IntakeReaderResult:
    """Run the Intake Reader on one FNOL bundle; return a validated
    extraction.

    On Pydantic validation failure, retries up to `max_retries`
    additional times with the error fed back as a corrective system
    note. Caller-injected `_client` is for tests; production uses a
    fresh Anthropic client per call.
    """
    client = _client or Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    tool = _tool_schema()
    user_body = _render_user_body(fnol_bundle)

    last_error: str | None = None

    for attempt in range(max_retries + 1):
        system_text = SYSTEM_PROMPT
        if last_error is not None:
            system_text = (
                SYSTEM_PROMPT
                + "\n\n--- PRIOR ATTEMPT REJECTED ---\n"
                + "Your previous output failed schema validation with "
                + "this error. Re-emit the tool call with the issue "
                + "fixed.\n\n"
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
            extraction = IntakeExtraction.model_validate(tool_input)
        except ValidationError as e:
            last_error = str(e)
            continue

        return IntakeReaderResult(
            extraction=extraction,
            model=resp.model,
            attempts=attempt + 1,
            raw_tool_input=tool_input if isinstance(tool_input, dict) else {},
        )

    raise RuntimeError(
        f"Intake Reader failed schema validation after "
        f"{max_retries + 1} attempts. Last error:\n{last_error}"
    )


__all__ = [
    "DEFAULT_MODEL",
    "IntakeReaderResult",
    "TOOL_NAME",
    "run_intake_reader",
]
