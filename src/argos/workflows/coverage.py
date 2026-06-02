"""Coverage specialist runtime.

Reads a SyntheticClaim (or the same-shape Foundry-backed claim once that's
wired) and emits a schema-conforming `CoverageReport`. The model is forced
to JSON via Anthropic's tool_use; on any Pydantic-validation failure the
runtime feeds the error back and retries once.

See AGENT_ARCHITECTURE.md §7.4 for the role; see
docs/evals/coverage-anchor-pair-thresholds.md for what counts as a passing
output on the anchor pair.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from anthropic import Anthropic
from pydantic import ValidationError

from argos.ontology.types import SyntheticClaim
from argos.schemas.workflows.coverage import CoverageReport


DEFAULT_MODEL = "claude-sonnet-4-6"
TOOL_NAME = "emit_coverage_analysis"


SYSTEM_PROMPT = """\
You are the Coverage specialist for Argos, an AI-native claims operations \
layer for specialty property and casualty TPAs.

Your role is narrow and specific:

1. Read the policy, the coverage request, and every document provided.
2. Surface the evidence you find — every claim you make about the file must \
cite a document by document_id with a verbatim text_excerpt from that \
document's body.
3. Quantify your uncertainty over coverage outcomes. Emit per-question \
probabilities (`assessments`) and a synthesis over outcome paths \
(`{clean_coverage, ROR, denial}`) that sums to 1.0.
4. Draft the coverage analysis memo. Draft the ROR letter if and only if the \
ROR outcome carries non-trivial probability (> 0.05). Draft the denial \
letter if and only if denial carries non-trivial probability (> 0.05).

What you DO NOT do:

- You do NOT recommend a path. Recommend nothing. No "we recommend ROR," no \
"the carrier should issue a denial," no "our position is X." The adjuster \
picks the path with your distribution and evidence in front of them. Your \
drafts describe analysis; they do not advocate.
- You do NOT cite anything you cannot find verbatim in the documents. Every \
`text_excerpt` must be a quote (or near-quote) from the document body. If \
you cannot find the support in a document, do not assert the claim.
- You do NOT invent facts. Every factual statement in your `reasoning` must \
map to a document you cite. If the documents do not say it, do not say it.

Output via the `emit_coverage_analysis` tool. The tool's input_schema is the \
contract — outputs that violate it are rejected upstream.
"""


def _render_claim(claim: SyntheticClaim) -> str:
    """Render the SyntheticClaim into the user-message body the specialist reads."""
    lines: list[str] = []

    p = claim.policy
    lines += [
        "=== POLICY ===",
        f"policy_id: {p.policy_id}",
        f"policy_number: {p.policy_number}",
        f"named_insured_party_id: {p.named_insured_party_id}",
        f"policy_form: {p.policy_form}",
        f"jurisdiction_state: {p.jurisdiction_state}",
        f"client_program_id: {p.client_program_id}",
        "",
    ]

    pp = claim.policy_period
    lines += [
        "=== POLICY PERIOD ===",
        f"policy_period_id: {pp.policy_period_id}",
        f"effective_from: {pp.effective_from.isoformat()}",
        f"effective_to: {pp.effective_to.isoformat()}",
        f"status: {pp.status}",
        "",
    ]

    lines.append("=== POLICY COVERAGES ===")
    for c in claim.coverages:
        lines += [
            f"- coverage_id: {c.coverage_id}",
            f"    coverage_type: {c.coverage_type}",
            f"    limit_per_occurrence: {c.limit_per_occurrence:,.2f}",
            f"    limit_per_person: {c.limit_per_person}",
            f"    limit_aggregate: {c.limit_aggregate}",
            f"    deductible: {c.deductible:,.2f}",
            f"    SIR: {c.SIR}",
        ]
    lines.append("")

    r = claim.request
    lines += [
        "=== COVERAGE REQUEST (under review) ===",
        f"request_id: {r.request_id}",
        f"claim_id: {r.claim_id}",
        f"coverage_id (targeted): {r.coverage_id}",
        f"claimant_party_id: {r.claimant_party_id}",
        f"current coverage_status: {r.coverage_status}",
        "",
        f"=== LOSS DATE === {claim.loss_date.isoformat()}",
        "",
        "=== LOSS FACTS (intake summary) ===",
        claim.loss_facts,
        "",
    ]

    lines.append("=== DOCUMENTS ===")
    lines.append(
        f"({len(claim.documents)} documents. Cite by document_id. "
        f"text_excerpt must be a verbatim quote from the document body.)"
    )
    lines.append("")
    for d in claim.documents:
        lines += [
            f"--- {d.document_id} ({d.document_type}) ---",
            f"source: {d.source}",
            f"received_date: {d.received_date.isoformat()}",
            "body_text:",
            d.body_text,
            "",
        ]

    return "\n".join(lines)


def _coverage_tool_schema() -> dict[str, Any]:
    """The JSON schema Anthropic uses to force CoverageReport-shaped output."""
    return {
        "name": TOOL_NAME,
        "description": (
            "Emit the Coverage specialist's analysis for this coverage request. "
            "All probabilities must be in [0,1]; the synthesis outcomes "
            "must sum to 1.0; every Assessment requires at least one "
            "EvidenceCitation whose text_excerpt is a verbatim quote from "
            "the cited document."
        ),
        "input_schema": CoverageReport.model_json_schema(),
    }


@dataclass
class CoverageRunResult:
    """What `run_coverage` returns: the validated analysis plus run metadata."""

    analysis: CoverageReport
    model: str
    attempts: int
    raw_tool_input: dict[str, Any]


def run_coverage(
    claim: SyntheticClaim,
    *,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 16_000,
    max_retries: int = 1,
) -> CoverageRunResult:
    """Run the Coverage specialist over a claim; return a validated analysis.

    On Pydantic validation failure, retries up to `max_retries` additional
    times with the error fed back to the model as a corrective system note.
    """
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    tool = _coverage_tool_schema()
    user_body = _render_claim(claim)
    system_prompt = SYSTEM_PROMPT

    last_error: str | None = None

    for attempt in range(max_retries + 1):
        system_text = system_prompt
        if last_error is not None:
            system_text = (
                system_prompt
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
            analysis = CoverageReport.model_validate(tool_input)
        except ValidationError as e:
            last_error = str(e)
            continue

        return CoverageRunResult(
            analysis=analysis,
            model=resp.model,
            attempts=attempt + 1,
            raw_tool_input=tool_input,
        )

    raise RuntimeError(
        f"Coverage specialist failed validation after {max_retries + 1} attempts. "
        f"Last error:\n{last_error}"
    )
