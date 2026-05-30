"""The output contract every legally-bearing specialist obeys.

Source of truth: AGENT_ARCHITECTURE.md §3.

Every probabilistic claim an AI specialist emits must (a) be a number in [0, 1],
(b) carry its own reasoning, and (c) cite at least one source — a Document, a
sourced legal rule, or a ledger entry. Outputs missing these are rejected at
this schema layer, before the specialist's proposal reaches Foundry as an
AgentAction. There is no recommendation field on any output type; specialists
surface evidence and probability, humans pick the path.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class EvidenceCitation(BaseModel):
    """A pointer from a probabilistic claim to its supporting source.

    Exactly one of `document_id`, `sourced_rule_id`, or `ledger_entry_id`
    must be populated. The `text_excerpt` records what the cited source
    actually says, so a verifier can later confirm the citation isn't
    hallucinated — see `verification_status` on the persisted Foundry
    object (ontology/object-types.yaml :: EvidenceCitation).
    """

    document_id: str | None = None
    sourced_rule_id: str | None = None
    ledger_entry_id: str | None = None
    locator: str = Field(
        description="Page, paragraph, section, field, or row identifier within the cited source"
    )
    text_excerpt: str = Field(description="What the cited source actually says")
    relation: Literal["supports", "refutes", "contextual"]

    @model_validator(mode="after")
    def exactly_one_source(self) -> EvidenceCitation:
        sources = [self.document_id, self.sourced_rule_id, self.ledger_entry_id]
        populated = [s for s in sources if s is not None]
        if len(populated) != 1:
            raise ValueError(
                "EvidenceCitation must point at exactly one of: document_id, "
                "sourced_rule_id, ledger_entry_id "
                f"(got {len(populated)} populated)"
            )
        return self


class ProbabilisticClaim(BaseModel):
    """A single quantified assertion with backing.

    Used as a building block in every legally-bearing specialist's output.
    `evidence_citations` is required and must be non-empty — the schema
    rejects bare probabilities. This is the contract that makes hallucinated
    confidence visible at the validator layer rather than at deployment.
    """

    claim_text: str
    probability: float = Field(ge=0.0, le=1.0)
    reasoning: str
    evidence_citations: list[EvidenceCitation] = Field(min_length=1)


class OutcomePathDistribution(BaseModel):
    """A distribution over mutually exclusive outcome paths.

    Coverage uses this over {clean coverage, ROR, denial}. Liability uses it
    over fault-allocation buckets. Reserve and Recovery use it for outcome
    paths where applicable. Every path is a `ProbabilisticClaim` (so every
    path carries its own evidence). Probabilities must sum to 1.0 within
    floating-point tolerance.
    """

    paths: list[ProbabilisticClaim] = Field(min_length=2)
    would_shift_distribution: list[str] = Field(
        default_factory=list,
        description="What evidence, if present or absent, would move the mass",
    )

    @model_validator(mode="after")
    def probabilities_sum_to_one(self) -> OutcomePathDistribution:
        total = sum(p.probability for p in self.paths)
        if not (0.99 <= total <= 1.01):
            raise ValueError(
                f"Outcome path probabilities must sum to 1.0 (±0.01); got {total:.4f}. "
                f"Paths: {[(p.claim_text, p.probability) for p in self.paths]}"
            )
        return self
