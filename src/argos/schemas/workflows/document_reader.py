"""Document Reader specialist output schema.

The Document Reader reads one document at a time and classifies its
relevance: is this document relevant enough to act on, and if so does
it change reserve / liability / coverage / damages posture? Output is
intentionally tiny — one boolean, one posture enum, one reason, one
verbatim excerpt.

The JSON wire-format field is kept as `"material"` (alias) so the LLM
sees the exact same schema + tool name as the locked
document-reader-anchor-pairs eval. Python code reads the cleaner
`.relevant` attribute via the Pydantic alias mechanism.

Spec: docs/specs/document-reader.md
Thresholds: docs/evals/document-reader-anchor-pairs-thresholds.md
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


PostureChanged = Literal["reserve", "liability", "coverage", "damages", "subrogation"]


class RelevanceCall(BaseModel):
    """Single per-document relevance classification (the Document
    Reader's verdict on one doc).

    Schema invariants enforced here:
      - text_excerpt non-empty iff relevant == True
      - posture_changed populated iff relevant == True

    The "text_excerpt is verbatim from the cited document body" rule is
    checked at the runtime layer (it needs the document body to verify),
    not in this pure schema.

    The wire-format alias `material` is what the LLM emits — kept for
    eval-threshold continuity. Code should use `.relevant`.
    """

    model_config = ConfigDict(populate_by_name=True)

    document_id: str = Field(description="The document this call is about")
    relevant: bool = Field(
        alias="material",
        description=(
            "True if a competent adjuster's next required action on the "
            "claim would change after reading this document; False otherwise."
        ),
    )
    posture_changed: PostureChanged | None = Field(
        default=None,
        description=(
            "Which posture changes: reserve, liability, coverage, or damages. "
            "Required when relevant == True; must be None when relevant == False."
        ),
    )
    reason: str = Field(
        max_length=300,
        description=(
            "One-line plain-English explanation of the relevance call. "
            "On relevant == True, references the specific event that changed "
            "posture. On relevant == False, references why the document is "
            "routine."
        ),
    )
    text_excerpt: str = Field(
        default="",
        description=(
            "Verbatim sentence(s) from the input document body that support "
            "the call. Required (non-empty) when relevant == True; empty "
            "when relevant == False."
        ),
    )

    @model_validator(mode="after")
    def excerpt_iff_relevant(self) -> RelevanceCall:
        if self.relevant and not self.text_excerpt.strip():
            raise ValueError(
                "RelevanceCall.text_excerpt must be non-empty when "
                "relevant == True (verbatim quote from document body)."
            )
        if not self.relevant and self.text_excerpt.strip():
            raise ValueError(
                "RelevanceCall.text_excerpt must be empty when "
                "relevant == False."
            )
        return self

    @model_validator(mode="after")
    def posture_iff_relevant(self) -> RelevanceCall:
        if self.relevant and self.posture_changed is None:
            raise ValueError(
                "RelevanceCall.posture_changed is required when "
                "relevant == True."
            )
        if not self.relevant and self.posture_changed is not None:
            raise ValueError(
                "RelevanceCall.posture_changed must be None when "
                "relevant == False."
            )
        return self
