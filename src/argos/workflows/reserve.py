"""Reserve workflow runtime — LLM extractor + Python calculator + templated rationale.

Architecture (locked 2026-06-01, see docs/DECISIONS.md):

  1. Extractor: Anthropic tool_use forces a ReserveInputs-shaped output from
     SyntheticClaim + ClaimContext. Bounded to extraction; emits no numbers.
  2. Calculator: pure-Python compute_reserve consumes ReserveInputs +
     ProgramConfig and produces ReserveAnalysis.
  3. Rationale: render_reserve_rationale interpolates CalculationContext into
     a deterministic audit-trail string and attaches to the analysis.

Only step 1 talks to an LLM. Steps 2 and 3 are reproducible byte-for-byte.

Spec: docs/specs/reserve-workflow.md.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from anthropic import Anthropic
from pydantic import ValidationError

from argos.ontology.types import Claim, SyntheticClaim
from argos.schemas.workflows.reserve import (
    ProgramConfig,
    ReserveAnalysis,
    ReserveInputs,
)
from argos.services.reserve.calculator import compute_reserve
from argos.services.reserve.constants import DEFAULT_PROGRAM
from argos.services.reserve.rationale import render_reserve_rationale


DEFAULT_MODEL = "claude-sonnet-4-6"
TOOL_NAME = "emit_reserve_inputs"
DEFAULT_TRIGGER = "CALENDAR_DIARY_90_DAY"


SYSTEM_PROMPT = """\
You are the Reserve extractor for Argos, an AI-native claims operations \
layer for specialty property and casualty TPAs.

Your role is narrow and bounded: read the policy, the claim record, and \
every document provided, and emit a structured `ReserveInputs` payload via \
the `emit_reserve_inputs` tool.

What you DO:

1. Extract facts that exist in the documents and structured claim state. \
For temporal fields (accrual_date, fnol_date, filing_date, mmi_date, \
crn cure_deadline, etc.), use exact dates from the source.
2. Classify the injury into one of the five `injury_bucket` values based on \
the medical evidence — not on the dollar amount, not on what would be \
"safe" to reserve. Use the criteria below.
3. Surface specials line-by-line. Every MedicalBill has billed + paid + \
payer + provider. If a bill is on a Letter of Protection (LOP), set \
`lop_flag=true` and `payer="lop"`.
4. Pull representation_status from the rep letter / demand letter directly. \
If there is no rep letter in the file, `represented=false`.
5. Pull crn_status from any Civil Remedy Notice (CRN) in the file. If no \
CRN, set crn_status=null.
6. Pull permanency_status from the treating physician records. \
`opinion_present=true` only if there is a written permanency opinion in the \
medical records — not an inference from severity.

What you DO NOT do:

- You do NOT estimate dollar reserves. The calculator owns all reserve math. \
Your fields feed the calculator; you do not produce ReserveBand values or \
reserve recommendations.
- You do NOT invent facts. If a field is not in the documents and not in the \
structured claim state, use the conservative default (e.g., \
`permanency_status.opinion_present=false`, empty lists).
- You do NOT classify a soft-tissue case as `surgical_recovering` because \
the medicals are large. The bucket reflects the injury, not the bill stack.

INJURY BUCKET CRITERIA:

- `minor_soft_tissue`: strain/sprain/whiplash, conservative care only, no MRI \
findings or normal MRI, no permanency opinion, full clinical resolution.
- `moderate_ortho_non_surgical`: confirmed disc bulge/herniation, fracture \
without surgery, sustained PT >12 weeks, possible permanency at MMI.
- `surgical_recovering`: surgical fixation, fusion, ORIF; documented \
permanency rating; MMI achieved.
- `severe_permanent`: permanent significant impairment, multi-level fusion, \
RSD/CRPS, significant scarring/disfigurement.
- `catastrophic`: fatality, TBI moderate-severe, SCI, amputation, severe \
burns >20% BSA, permanent total disability. ALSO populate \
`catastrophic_indicators` with the matching tags.

FL-SPECIFIC NOTES:

- `accrual_date` is the date the cause of action accrued — usually the loss \
date / date of accident from the police report or FNOL.
- `filing_date` is null until a complaint is filed.
- `venue_county` is from the claimant's address if pre-suit, or the complaint's \
filing county if a suit is on file.
- `tortfeasor_pip_compliant` defaults to true unless the file documents \
non-compliance.
- `pip_status.cap_applicable` is 2500 without EMC determination, 10000 with EMC.
- `actual_notice_date` starts §624.155(4) 90-day clock — only populate when \
the file shows attorney correspondence or a demand letter that puts the \
carrier on actual notice of a covered loss with sufficient supporting \
evidence.

Emit via `emit_reserve_inputs`. The tool's input_schema is the contract — \
outputs that violate it are rejected upstream.
"""


def _render_for_extractor(claim: SyntheticClaim, claim_meta: Claim | None) -> str:
    """Render the SyntheticClaim and Claim meta for the extractor user-message body."""
    lines: list[str] = []

    if claim_meta is not None:
        lines += [
            "=== CLAIM RECORD ===",
            f"claim_id: {claim_meta.claim_id}",
            f"opened_date: {claim_meta.opened_date}",
            f"status: {claim_meta.status}",
            f"severity_tier_summary: {claim_meta.severity_tier_summary}",
            f"litigation_flag: {claim_meta.litigation_flag}",
            f"rep_flag: {claim_meta.rep_flag}",
            f"complaint_flag: {claim_meta.complaint_flag}",
            f"coverage_posture: {claim_meta.coverage_posture}",
            f"claimant_name: {claim_meta.claimant_name or '(not yet extracted)'}",
            f"insured_name: {claim_meta.insured_name or '(not yet extracted)'}",
            "",
        ]

    p = claim.policy
    lines += [
        "=== POLICY ===",
        f"policy_id: {p.policy_id}",
        f"policy_number: {p.policy_number}",
        f"policy_form: {p.policy_form}",
        f"jurisdiction_state: {p.jurisdiction_state}",
        "",
        "=== COVERAGES ===",
    ]
    for c in claim.coverages:
        lines += [
            f"- coverage_id: {c.coverage_id}",
            f"  type: {c.coverage_type}",
            f"  per_occurrence: ${c.limit_per_occurrence:,.0f}",
            (
                f"  per_person: ${c.limit_per_person:,.0f}"
                if c.limit_per_person is not None else "  per_person: (none)"
            ),
            f"  deductible: ${c.deductible:,.0f}",
            (
                f"  SIR: ${c.SIR:,.0f}" if c.SIR is not None else "  SIR: (none)"
            ),
        ]
    lines += ["", "=== LOSS ===", f"loss_date: {claim.loss_date}", "", "loss_facts:", claim.loss_facts, ""]

    lines += ["=== DOCUMENTS ==="]
    for d in claim.documents:
        lines += [
            f"--- document_id: {d.document_id} ---",
            f"type: {d.document_type}",
            f"received_date: {d.received_date}",
            f"source: {d.source}",
            "body:",
            d.body_text,
            "",
        ]

    return "\n".join(lines)


def _reserve_inputs_tool_schema() -> dict[str, Any]:
    """JSON schema that forces ReserveInputs-shaped tool_use output."""
    return {
        "name": TOOL_NAME,
        "description": (
            "Emit the structured ReserveInputs payload for this claim, "
            "extracted from documents and structured claim state. Do not "
            "estimate any dollar reserves; the calculator handles math. "
            "Conservative defaults when a field is not in the file."
        ),
        "input_schema": ReserveInputs.model_json_schema(),
    }


@dataclass
class ReserveRunResult:
    """What `run_reserve` returns: validated analysis + extraction metadata."""

    analysis: ReserveAnalysis
    extractor_model: str
    extractor_attempts: int
    raw_inputs: ReserveInputs


def extract_reserve_inputs(
    claim: SyntheticClaim,
    *,
    claim_meta: Claim | None = None,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 16_000,
    max_retries: int = 1,
    anthropic_client: Anthropic | None = None,
) -> tuple[ReserveInputs, str, int]:
    """LLM-extract ReserveInputs from claim documents. Returns (inputs, model, attempts)."""
    client = anthropic_client or Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    tool = _reserve_inputs_tool_schema()
    user_body = _render_for_extractor(claim, claim_meta)

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
        try:
            inputs = ReserveInputs.model_validate(tool_input)
        except ValidationError as e:
            last_error = str(e)
            continue

        return inputs, resp.model, attempt + 1

    raise RuntimeError(
        f"Reserve extractor failed validation after {max_retries + 1} attempts. "
        f"Last error:\n{last_error}"
    )


def run_reserve(
    claim: SyntheticClaim,
    *,
    claim_meta: Claim | None = None,
    program_config: ProgramConfig = DEFAULT_PROGRAM,
    request_id: str | None = None,
    reviewed_as_of: datetime | None = None,
    eval_seq: int = 1,
    trigger_name: str = DEFAULT_TRIGGER,
    trigger_event_date: datetime | None = None,
    examiner_id: str = "system",
    extractor_model: str = DEFAULT_MODEL,
    max_retries: int = 1,
    anthropic_client: Anthropic | None = None,
    inputs_override: ReserveInputs | None = None,
) -> ReserveRunResult:
    """End-to-end Reserve workflow.

    Extractor → calculator → rationale. The result has a templated audit-
    trail rationale interpolated from CalculationContext.

    `inputs_override` short-circuits the extractor — useful for tests and the
    demo runner when ReserveInputs is hand-constructed from a fixture.
    """
    rid = request_id or f"RES-{claim.request.request_id}"
    review_dt = reviewed_as_of or datetime.now(timezone.utc)
    trigger_dt = trigger_event_date or review_dt
    claim_id = claim_meta.claim_id if claim_meta is not None else claim.request.claim_id

    if inputs_override is not None:
        inputs = inputs_override
        model_used = "(override — no LLM call)"
        attempts = 0
    else:
        inputs, model_used, attempts = extract_reserve_inputs(
            claim,
            claim_meta=claim_meta,
            model=extractor_model,
            max_retries=max_retries,
            anthropic_client=anthropic_client,
        )

    analysis, ctx = compute_reserve(
        inputs, program_config,
        request_id=rid, reviewed_as_of=review_dt,
    )
    rationale = render_reserve_rationale(
        ctx,
        claim_id=claim_id,
        eval_seq=eval_seq,
        trigger_name=trigger_name,
        trigger_event_date=trigger_dt,
        examiner_id=examiner_id,
    )
    analysis = analysis.model_copy(update={"rationale": rationale})

    return ReserveRunResult(
        analysis=analysis,
        extractor_model=model_used,
        extractor_attempts=attempts,
        raw_inputs=inputs,
    )
