"""Liability specialist output schema.

Source of truth: AGENT_ARCHITECTURE.md §7.5.

Surfaces evidence, applies the jurisdictional comparative-fault rule, and
emits a distribution over fault-allocation buckets. The adjuster picks the
bucket. No recommendation field.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from argos.schemas.contract import Assessment, EvidenceCitation


ComparativeFaultRule = Literal["pure", "modified_50", "modified_51", "contributory"]


class FaultAllocationBucket(BaseModel):
    """One bucket in the fault-allocation synthesis.

    `other_party_fault_pct` is populated for multi-party (3+ vehicle) crashes
    and left None for two-party cases.
    """

    insured_fault_pct: float = Field(ge=0.0, le=100.0)
    claimant_fault_pct: float = Field(ge=0.0, le=100.0)
    other_party_fault_pct: float | None = Field(default=None, ge=0.0, le=100.0)
    probability: float = Field(ge=0.0, le=1.0)
    reasoning: str
    evidence_citations: list[EvidenceCitation] = Field(min_length=1)

    @model_validator(mode="after")
    def percentages_sum_to_100(self) -> FaultAllocationBucket:
        total = self.insured_fault_pct + self.claimant_fault_pct
        if self.other_party_fault_pct is not None:
            total += self.other_party_fault_pct
        if not (99.0 <= total <= 101.0):
            raise ValueError(
                f"Fault percentages must sum to 100 (±1); got {total:.2f}"
            )
        return self


class FaultAllocationSynthesis(BaseModel):
    buckets: list[FaultAllocationBucket] = Field(min_length=2)
    would_shift_distribution: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def probabilities_sum_to_one(self) -> FaultAllocationSynthesis:
        total = sum(b.probability for b in self.buckets)
        if not (0.99 <= total <= 1.01):
            raise ValueError(
                f"Fault-allocation probabilities must sum to 1.0 (±0.01); got {total:.4f}"
            )
        return self


class LiabilityDraft(BaseModel):
    body: str
    citations: list[EvidenceCitation] = Field(min_length=1)


class LiabilityAnalysis(BaseModel):
    exposure_id: str
    reviewed_as_of: datetime

    jurisdiction: str = Field(description="State or jurisdiction code, e.g. 'FL'")
    comparative_fault_rule: ComparativeFaultRule
    comparative_fault_rule_citation: EvidenceCitation = Field(
        description="Must point at a sourced legal rule, not an unvalidated config entry"
    )

    evidence_found: list[EvidenceCitation] = Field(min_length=1)

    assessments: list[Assessment] = Field(min_length=1)

    fault_allocation_synthesis: FaultAllocationSynthesis

    recovery_barred_probability: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Derived: sum of bucket probabilities where claimant fault pct exceeds "
            "the jurisdictional bar (e.g., >50% under modified_51)"
        ),
    )

    draft_analysis: LiabilityDraft

    @model_validator(mode="after")
    def rule_citation_is_sourced(self) -> LiabilityAnalysis:
        if self.comparative_fault_rule_citation.sourced_rule_id is None:
            raise ValueError(
                "comparative_fault_rule_citation must point at a sourced legal rule "
                "(sourced_rule_id required, document_id and ledger_entry_id are not "
                "acceptable substrates for the rule that governs the analysis)"
            )
        return self
