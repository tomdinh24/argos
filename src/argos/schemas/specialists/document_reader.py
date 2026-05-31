"""Document Reader specialist output schema.

The Document Reader reads one document at a time and classifies its
materiality: does this document change reserve, liability, coverage,
or damages posture? Output is intentionally tiny — one boolean, one
posture enum, one reason, one verbatim excerpt.

Spec: docs/specs/document-reader.md
Thresholds: docs/evals/document-reader-anchor-pairs-thresholds.md
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


PostureChanged = Literal["reserve", "liability", "coverage", "damages"]


class MaterialityCall(BaseModel):
    """Single per-document materiality classification.

    Schema invariants enforced here:
      - text_excerpt non-empty iff material == True
      - posture_changed populated iff material == True

    The "text_excerpt is verbatim from the cited document body" rule is
    checked at the runtime layer (it needs the document body to verify),
    not in this pure schema.
    """

    document_id: str = Field(description="The document this call is about")
    material: bool = Field(
        description=(
            "True if a competent adjuster's next required action on the "
            "claim would change after reading this document; False otherwise."
        )
    )
    posture_changed: PostureChanged | None = Field(
        default=None,
        description=(
            "Which posture changes: reserve, liability, coverage, or damages. "
            "Required when material == True; must be None when material == False."
        ),
    )
    reason: str = Field(
        max_length=300,
        description=(
            "One-line plain-English explanation of the materiality call. "
            "On material == True, references the specific event that changed "
            "posture. On material == False, references why the document is "
            "routine."
        ),
    )
    text_excerpt: str = Field(
        default="",
        description=(
            "Verbatim sentence(s) from the input document body that support "
            "the call. Required (non-empty) when material == True; empty "
            "when material == False."
        ),
    )

    @model_validator(mode="after")
    def excerpt_iff_material(self) -> MaterialityCall:
        if self.material and not self.text_excerpt.strip():
            raise ValueError(
                "MaterialityCall.text_excerpt must be non-empty when "
                "material == True (verbatim quote from document body)."
            )
        if not self.material and self.text_excerpt.strip():
            raise ValueError(
                "MaterialityCall.text_excerpt must be empty when "
                "material == False."
            )
        return self

    @model_validator(mode="after")
    def posture_iff_material(self) -> MaterialityCall:
        if self.material and self.posture_changed is None:
            raise ValueError(
                "MaterialityCall.posture_changed is required when "
                "material == True."
            )
        if not self.material and self.posture_changed is not None:
            raise ValueError(
                "MaterialityCall.posture_changed must be None when "
                "material == False."
            )
        return self
