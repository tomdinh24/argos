"""Brief specialist output schema.

Source of truth: AGENT_ARCHITECTURE.md §7.6.

Brief is the only specialist whose output isn't a probabilistic recommendation
— it's a structured view that anchors the cockpit. But the citation discipline
still applies: every diff item, every "what's missing" entry, every
pending-correspondence line carries its source.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from argos.schemas.contract import EvidenceCitation


CoverageStatus = Literal[
    "pending", "accepted", "denied", "reservation_of_rights"
]
HandlingStatus = Literal[
    "open_investigation", "in_negotiation", "settled", "withdrawn", "closed"
]
SettlementStatus = Literal[
    "not_applicable", "in_progress", "executed_release", "paid_in_full"
]
RepresentationStatus = Literal["unrepresented", "represented"]
LitigationStatus = Literal[
    "none", "suit_filed", "in_discovery", "in_mediation", "in_trial", "resolved", "dismissed"
]
RecoveryStatus = Literal[
    "not_screened", "no_potential", "potential", "pursuing", "settled", "abandoned", "closed"
]
FinancialStatus = Literal[
    "no_payment_due", "reserves_outstanding", "partially_paid", "paid", "reconciled"
]
WorkflowName = Literal["coverage", "liability", "reserve", "recovery", "closure"]
CorrespondenceStatus = Literal[
    "auto_sent", "awaiting_human_approval", "sent_to_human_drafted", "not_yet_drafted"
]


class DiffItem(BaseModel):
    change_text: str
    occurred_at: datetime
    evidence_citations: list[EvidenceCitation] = Field(min_length=1)


class StatusSnapshot(BaseModel):
    coverage_status: CoverageStatus
    handling_status: HandlingStatus
    settlement_status: SettlementStatus
    representation_status: RepresentationStatus
    litigation_status: LitigationStatus
    recovery_status: RecoveryStatus
    financial_status: FinancialStatus


class FinancialSnapshot(BaseModel):
    """Per-component snapshot returned by `get_financials_as_of`."""

    as_of_effective: datetime
    as_of_recorded: datetime
    outstanding_indemnity: float
    paid_indemnity: float
    outstanding_alae: float
    paid_alae: float
    recovered: float


class SinceLastTouch(BaseModel):
    last_touch_at: datetime | None
    diff_items: list[DiffItem] = Field(default_factory=list)


class WorkflowRecommendationHeadline(BaseModel):
    workflow: WorkflowName
    agent_action_id: str
    headline: str
    awaiting_approval: bool


class MissingInfoItem(BaseModel):
    item: str
    requested_from: str
    requested_at: datetime | None = None
    response_due: datetime | None = None
    correspondence_status: CorrespondenceStatus
    evidence_citations: list[EvidenceCitation] = Field(
        min_length=1,
        description="What makes the AI conclude this info is missing",
    )


class PendingCommunication(BaseModel):
    direction: Literal["outbound", "awaiting_response"]
    recipient_party_id: str
    message_type: str
    drafted_or_sent_at: datetime
    correspondence_id: str


class ClaimBrief(BaseModel):
    request_id: str | None = Field(
        default=None,
        description="None when the brief is claim-scoped rather than exposure-scoped",
    )
    claim_id: str
    generated_at: datetime

    story_paragraph: str
    story_citations: list[EvidenceCitation] = Field(min_length=1)

    since_last_touch: SinceLastTouch
    current_status_snapshot: StatusSnapshot
    financial_snapshot: FinancialSnapshot

    workflow_recommendations_summary: list[WorkflowRecommendationHeadline] = Field(
        default_factory=list
    )
    missing_info: list[MissingInfoItem] = Field(default_factory=list)
    pending_communications: list[PendingCommunication] = Field(default_factory=list)
