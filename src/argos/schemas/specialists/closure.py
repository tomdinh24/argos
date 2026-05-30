"""Closure specialist output schema.

Source of truth: AGENT_ARCHITECTURE.md §2.1.

Surfaces a ready-to-close probability and a list of blocking defects with
citations. The actual close write is rejected by the Action Type validator
when defects exist — the Closure specialist's output is advisory; the
substrate enforces the block. Closure execution itself is always
human-approved.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from argos.schemas.legally_bearing import EvidenceCitation, ProbabilisticClaim


DefectKind = Literal[
    "outstanding_reserve",
    "open_recovery",
    "open_lien",
    "missing_release",
    "missing_required_document",
    "pending_litigation",
    "pending_section_111",
    "pending_authority_decision",
    "client_checklist_item",
]


class ClosureDefect(BaseModel):
    kind: DefectKind
    description: str
    evidence_citations: list[EvidenceCitation] = Field(min_length=1)
    resolution_hint: str | None = Field(
        default=None,
        description="What action would resolve this defect (informational, not prescriptive)",
    )


class ClosureAnalysis(BaseModel):
    exposure_id: str
    reviewed_as_of: datetime

    ready_to_close: ProbabilisticClaim = Field(
        description="P(file is ready to close cleanly) with reasoning + citations"
    )

    blocking_defects: list[ClosureDefect] = Field(
        default_factory=list,
        description=(
            "Empty when ready_to_close.probability is near 1.0; populated otherwise. "
            "The Action Type validator independently re-checks these conditions when "
            "the close write is attempted — the specialist's advisory is not the "
            "authoritative block."
        ),
    )
