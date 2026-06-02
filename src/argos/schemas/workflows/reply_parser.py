"""Reply Parser workflow output schema.

The Reply Parser is a single-shot LLM workflow that takes one
inbound document plus the open outbound requests on a claim and
emits which outbound this reply answers + which of that outbound's
asked questions are actually answered by the reply content.

This closes the outreach loop: outbound goes out → reply comes
back → Reply Parser maps reply → questions flip to `answered` →
triage may re-bucket → brief flagged stale.

Spec: docs/specs/reply-parser.md (to be written)
Decision: docs/DECISIONS.md → "Inbound Reply Handler / Reply Parser"
                            → "Step 4: Reply Parser" (when shipped)
"""
from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class ReplyParseResult(BaseModel):
    """Single per-reply mapping: which outbound this reply answers
    and which of that outbound's asked questions are answered by it.

    Schema invariants enforced here (pure-schema layer):
      - At least one question is answered OR partial=True with reason
      - text_excerpt non-empty when any question is answered
      - confidence in [0, 1]
      - matched_outbound_id format validated (OBR-XXX prefix)

    The "answered_question_ids ⊆ matched outbound's question_ids_asked"
    invariant is checked at the runtime layer because it needs the
    candidate outbound set, not just the model's output.
    """

    matched_outbound_id: str = Field(
        description=(
            "The OBR-XXX identifier of the outbound this reply answers. "
            "Must be one of the open outbounds passed to the parser; "
            "the runtime rejects mismatches."
        )
    )
    answered_question_ids: list[str] = Field(
        description=(
            "Subset of matched outbound's `question_ids_asked` that "
            "this reply actually answers (verbatim content supplies "
            "the answer). Empty list is allowed when the reply is "
            "acknowledgement-only — set `partial=True` and explain "
            "in `reason`."
        ),
    )
    unanswered_question_ids: list[str] = Field(
        description=(
            "Subset of matched outbound's `question_ids_asked` that "
            "this reply does NOT answer. Together with "
            "answered_question_ids must equal the full asked set; the "
            "runtime enforces the partition."
        ),
    )
    partial: bool = Field(
        description=(
            "True when the reply answers some but not all of the "
            "outbound's asked questions, OR when the reply is an "
            "acknowledgement / non-substantive (no questions answered)."
        )
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Calibrated 0-1 confidence in matched_outbound_id and the "
            "partition of asked questions. Below 0.5 should escalate "
            "to human review at the orchestrator layer."
        ),
    )
    text_excerpt: str = Field(
        default="",
        description=(
            "Verbatim quote from the inbound document body that "
            "establishes the match. Required (non-empty) when any "
            "question is answered. May be empty for acknowledgement-"
            "only replies."
        ),
    )
    reason: str = Field(
        max_length=300,
        description=(
            "One-line plain-English explanation of the match decision. "
            "Always populated."
        ),
    )

    @model_validator(mode="after")
    def matched_outbound_id_well_formed(self) -> ReplyParseResult:
        if not self.matched_outbound_id.startswith("OBR-"):
            raise ValueError(
                f"matched_outbound_id={self.matched_outbound_id!r} must "
                f"start with 'OBR-' (outbound identifier prefix)."
            )
        return self

    @model_validator(mode="after")
    def excerpt_when_answering(self) -> ReplyParseResult:
        if self.answered_question_ids and not self.text_excerpt.strip():
            raise ValueError(
                "ReplyParseResult.text_excerpt must be non-empty when "
                "any question is marked answered (verbatim quote "
                "supporting the answer)."
            )
        return self

    @model_validator(mode="after")
    def partial_consistent_with_answer_state(self) -> ReplyParseResult:
        if not self.partial and not self.answered_question_ids:
            raise ValueError(
                "partial=False requires at least one answered question. "
                "Set partial=True for acknowledgement-only or no-answer "
                "replies."
            )
        if (
            not self.partial
            and self.unanswered_question_ids
        ):
            raise ValueError(
                "partial=False requires unanswered_question_ids to be "
                "empty (fully-answered reply). Use partial=True when "
                "any question remains unanswered."
            )
        return self

    @model_validator(mode="after")
    def question_id_partition_no_overlap(self) -> ReplyParseResult:
        overlap = set(self.answered_question_ids) & set(self.unanswered_question_ids)
        if overlap:
            raise ValueError(
                f"Question IDs cannot be in both answered and "
                f"unanswered sets: {sorted(overlap)}."
            )
        return self
