"""Recovery specialist output schema.

Source of truth: AGENT_ARCHITECTURE.md §2.1.

Surfaces an opportunity probability with cited evidence, the recoverable
amount band, SOL status (only for sourced legal rules — otherwise the
specialist surfaces "SOL unknown, please review"), evidence-preservation
alerts, and a draft demand. Pursuit / referral is always human-approved.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from argos.schemas.legally_bearing import EvidenceCitation, ProbabilisticClaim


RecoveryType = Literal[
    "subrogation",
    "salvage",
    "contribution",
    "deductible_recovery",
    "restitution",
    "reinsurance_reimbursement",
]


class RecoveryAmountBand(BaseModel):
    gross_low: float = Field(ge=0)
    gross_median: float = Field(ge=0)
    gross_high: float = Field(ge=0)


class SOLStatus(BaseModel):
    """SOL is surfaced only with grounded confidence.

    If `sourced_rule_applied` is None, the specialist is admitting it does not
    have a sourced jurisdictional rule to apply, and `deadline_date` /
    `days_remaining` must be None as well. The cockpit surfaces "SOL unknown,
    please review" in that case rather than asserting a deadline.
    """

    sourced_rule_applied: EvidenceCitation | None = None
    deadline_date: datetime | None = None
    days_remaining: int | None = None
    unknown_note: str | None = Field(
        default=None,
        description="Populated when no sourced rule applies; null otherwise",
    )


class EvidencePreservationAlert(BaseModel):
    """Operational, not probabilistic. Surfaces vehicle holds, document
    preservation requirements, etc. tied to active recovery."""

    alert_text: str
    evidence_citations: list[EvidenceCitation] = Field(min_length=1)


class RecoveryDemandDraft(BaseModel):
    body: str
    recipient_party_id: str
    citations: list[EvidenceCitation] = Field(min_length=1)


class RecoveryAnalysis(BaseModel):
    exposure_id: str
    reviewed_as_of: datetime

    opportunity: ProbabilisticClaim = Field(
        description="P(a recovery opportunity exists) with reasoning + citations"
    )
    recovery_type: RecoveryType

    adverse_party_id: str | None = None
    adverse_carrier_party_id: str | None = None

    amount_band: RecoveryAmountBand
    sol_status: SOLStatus

    evidence_preservation_alerts: list[EvidencePreservationAlert] = Field(
        default_factory=list
    )

    draft_demand: RecoveryDemandDraft | None = Field(
        default=None,
        description="None when opportunity probability is below the demand-draft threshold",
    )
