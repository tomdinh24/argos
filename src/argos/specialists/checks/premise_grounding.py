"""Judge check: does every factual claim in `reasoning` map to a document?

Schema and citation-verifier together enforce that EvidenceCitations are
real. Neither catches a model that asserts an UNCITED fact inside an
Assessment's `reasoning` prose — e.g., "Marcus has fourteen years of
commercial driving experience" when no document mentions that.

This check uses Claude as a judge: given the documents the specialist had
access to and the specialist's reasoning prose, list every factual claim
and mark each as `grounded` (traceable to a document) or `ungrounded`
(invented or assumed). Any ungrounded claim fails the check.

Judgments are themselves probabilistic — the judge can be wrong. Outputs
include the judge's per-claim reasoning so a human can spot-check.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

from anthropic import Anthropic
from pydantic import BaseModel, Field, ValidationError

from argos.ontology.types import SyntheticClaim
from argos.schemas.specialists.coverage import CoverageReport


DEFAULT_JUDGE_MODEL = "claude-sonnet-4-6"
JUDGE_TOOL_NAME = "report_grounding"


class _GroundingClaim(BaseModel):
    """One factual claim the judge extracted from an Assessment's reasoning."""

    claim_text: str = Field(description="The factual assertion, in the judge's own words")
    grounded: bool = Field(
        description=(
            "True if the claim is traceable to one of the provided documents; "
            "False if the claim is invented or assumed without document support."
        )
    )
    supporting_document_id: str | None = Field(
        default=None,
        description="If grounded, the document_id that supports this claim; else null.",
    )
    judge_reasoning: str = Field(
        description="One-sentence justification for the grounded/ungrounded judgment."
    )


class _GroundingReport(BaseModel):
    """The judge's full per-assessment report."""

    claims: list[_GroundingClaim] = Field(default_factory=list)


@dataclass
class UngroundedClaim:
    """One ungrounded claim flagged by the judge."""

    assessment_index: int
    assessment_claim_text: str
    flagged_claim: str
    judge_reasoning: str


@dataclass
class PremiseGroundingResult:
    """Aggregate result across all of an analysis's assessments."""

    assessments_checked: int = 0
    total_claims_extracted: int = 0
    ungrounded: list[UngroundedClaim] = field(default_factory=list)
    judge_model: str = ""

    @property
    def passed(self) -> bool:
        return not self.ungrounded

    @property
    def summary(self) -> str:
        if self.passed:
            return (
                f"PASS — {self.total_claims_extracted} factual claim(s) across "
                f"{self.assessments_checked} assessment(s), all grounded"
            )
        return (
            f"FAIL — {len(self.ungrounded)} ungrounded claim(s) flagged across "
            f"{self.assessments_checked} assessment(s)"
        )


_JUDGE_SYSTEM = """\
You are a grounding judge. You are given a set of documents from a claim file \
and one block of reasoning prose from an AI specialist. Your job is to \
extract every factual claim the reasoning makes and decide, for each, whether \
that claim is supported by the documents.

A claim is GROUNDED if any document body contains the claim, paraphrases the \
claim, or supports the claim by direct implication (e.g., "the driver was \
authorized" is grounded if a dispatch log lists the driver as assigned).

A claim is UNGROUNDED if no document body supports it — e.g., an invented \
biographical fact, an asserted prior history not in any document, or an \
asserted state of mind nobody recorded.

Procedural language ("the policy in force test asks whether…") and analytical \
framing ("this evidence supports a finding of…") are NOT factual claims. \
Only the factual assertions count.

Emit your report via the `report_grounding` tool.
"""


def _judge_tool_schema() -> dict[str, Any]:
    return {
        "name": JUDGE_TOOL_NAME,
        "description": (
            "Report whether each factual claim in the reasoning is grounded "
            "in the documents."
        ),
        "input_schema": _GroundingReport.model_json_schema(),
    }


def _docs_block(claim: SyntheticClaim) -> str:
    parts: list[str] = []
    for d in claim.documents:
        parts.append(f"--- {d.document_id} ({d.document_type}) ---\n{d.body_text}\n")
    return "\n".join(parts)


def _judge_one(
    *,
    client: Anthropic,
    model: str,
    docs_block: str,
    reasoning_text: str,
    assessment_claim_text: str,
) -> _GroundingReport:
    user = (
        "DOCUMENTS:\n\n"
        + docs_block
        + "\n\nSPECIALIST'S ASSESSMENT CLAIM:\n"
        + assessment_claim_text
        + "\n\nSPECIALIST'S REASONING (judge this):\n"
        + reasoning_text
    )
    resp = client.messages.create(
        model=model,
        max_tokens=4_000,
        system=_JUDGE_SYSTEM,
        tools=[_judge_tool_schema()],
        tool_choice={"type": "tool", "name": JUDGE_TOOL_NAME},
        messages=[{"role": "user", "content": user}],
    )
    tool_blocks = [b for b in resp.content if b.type == "tool_use"]
    if not tool_blocks:
        raise RuntimeError("Judge did not emit a tool_use block")
    try:
        return _GroundingReport.model_validate(tool_blocks[0].input)
    except ValidationError as e:
        raise RuntimeError(f"Judge output failed validation: {e}\n{json.dumps(tool_blocks[0].input)[:500]}") from e


def check_premise_grounding(
    analysis: CoverageReport,
    claim: SyntheticClaim,
    *,
    model: str = DEFAULT_JUDGE_MODEL,
) -> PremiseGroundingResult:
    """For each Assessment, judge whether every factual claim in reasoning is grounded."""
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    docs_block = _docs_block(claim)
    result = PremiseGroundingResult(judge_model=model)

    for idx, assessment in enumerate(analysis.assessments):
        result.assessments_checked += 1
        report = _judge_one(
            client=client,
            model=model,
            docs_block=docs_block,
            reasoning_text=assessment.reasoning,
            assessment_claim_text=assessment.claim_text,
        )
        result.total_claims_extracted += len(report.claims)
        for c in report.claims:
            if not c.grounded:
                result.ungrounded.append(
                    UngroundedClaim(
                        assessment_index=idx,
                        assessment_claim_text=assessment.claim_text,
                        flagged_claim=c.claim_text,
                        judge_reasoning=c.judge_reasoning,
                    )
                )
    return result
