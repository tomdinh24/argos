"""Reserve specialist output schema.

Source of truth: AGENT_ARCHITECTURE.md §7.3.

Emits a band (p10/p50/p90) per component, not a point. The adjuster picks the
point. Every triggers_fired entry carries its own evidence; every notice
obligation carries its own evidence. Authority routing is part of the output —
the cockpit auto-applies below handler authority and creates an
AuthorityRequest above it.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from argos.schemas.contract import EvidenceCitation


ReserveComponent = Literal[
    "indemnity", "ALAE", "ULAE", "ALE", "expert_fees", "defense", "mitigation"
]

NoticeType = Literal[
    "excess_carrier", "reinsurer", "client", "DOI", "Medicare_Section_111"
]

AuthorityLevel = Literal["handler", "supervisor", "manager", "client"]


class ReserveBand(BaseModel):
    p10: float = Field(ge=0)
    p50: float = Field(ge=0)
    p90: float = Field(ge=0)

    @model_validator(mode="after")
    def ordered(self) -> ReserveBand:
        if not (self.p10 <= self.p50 <= self.p90):
            raise ValueError(f"Band must be ordered p10 ≤ p50 ≤ p90; got {self}")
        return self


class TriggerFired(BaseModel):
    """A material event from SpecialistConfig that fired on this exposure."""

    trigger_id: str = Field(
        description="Reference to material_event_definitions in SpecialistConfig"
    )
    evidence_citations: list[EvidenceCitation] = Field(min_length=1)


class ReserveComponentAnalysis(BaseModel):
    component: ReserveComponent
    current_outstanding: float = Field(ge=0)
    recommended_outstanding_band: ReserveBand
    rationale: str
    triggers_fired: list[TriggerFired] = Field(default_factory=list)
    evidence_citations: list[EvidenceCitation] = Field(
        min_length=1,
        description="Supports the band itself, distinct from triggers",
    )


class NoticeObligationTriggered(BaseModel):
    notice_type: NoticeType
    probability: float = Field(ge=0.0, le=1.0)
    reasoning: str
    required_by_date: datetime
    evidence_citations: list[EvidenceCitation] = Field(min_length=1)


class ReserveAnalysis(BaseModel):
    exposure_id: str
    reviewed_as_of: datetime

    per_component: list[ReserveComponentAnalysis] = Field(min_length=1)
    notice_obligations_triggered: list[NoticeObligationTriggered] = Field(
        default_factory=list
    )

    authority_required_level: AuthorityLevel
    no_change_warranted: bool = False
