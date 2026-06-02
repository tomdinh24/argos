"""Ontology types — Python shapes that mirror the Foundry object types.

Minimal subset, expanded as specialists need more. The eventual Foundry-backed
implementation reads OSDK-typed objects and adapts them to these shapes; the
synthetic fixtures construct them directly. Specialists code against these
types, not against the OSDK or the fixture layer.

Source of truth for the full set: foundry/ontology/object-types.yaml.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


CoverageType = Literal[
    "auto_BI", "auto_PD", "auto_UM_UIM", "auto_collision",
    "auto_comprehensive", "auto_medpay", "auto_rental",
    "flood_building", "flood_contents", "flood_ICC",
]

CoverageStatus = Literal[
    "pending", "accepted", "denied", "reservation_of_rights"
]

SeverityTier = Literal["catastrophic", "serious", "standard", "minor"]

ClaimStatus = Literal["open", "closed", "reopened", "suspended"]


class Policy(BaseModel):
    policy_id: str
    client_program_id: str
    policy_number: str
    named_insured_party_id: str
    policy_form: str  # e.g., "CA00" commercial auto, "PAP" personal auto
    jurisdiction_state: str


class PolicyPeriod(BaseModel):
    policy_period_id: str
    policy_id: str
    effective_from: date
    effective_to: date
    status: Literal["in_force", "expired", "cancelled", "non_renewed"]


class PolicyCoverage(BaseModel):
    coverage_id: str
    policy_period_id: str
    coverage_type: CoverageType
    limit_per_occurrence: float
    limit_per_person: float | None = None
    limit_aggregate: float | None = None
    deductible: float
    SIR: float | None = None
    sublimits_json: str | None = None
    exclusions_json: str | None = None


class CoverageRequest(BaseModel):
    request_id: str
    claim_id: str
    coverage_id: str
    claimant_party_id: str | None = None
    coverage_status: CoverageStatus = "pending"
    severity_tier: SeverityTier = "standard"


class Document(BaseModel):
    document_id: str
    claim_id: str
    document_type: str
    received_date: date
    source: str
    body_text: str = Field(
        description="Plaintext content the specialist reads. In production this "
        "is post-extraction; here it's authored directly for the fixture.",
    )


class SyntheticClaim(BaseModel):
    """A populated in-memory claim, sufficient input for one specialist run.

    The fields included are the minimum a Coverage specialist needs to read.
    Other specialists will read additional state from the same fixture; we'll
    extend this type as they come online.
    """

    policy: Policy
    policy_period: PolicyPeriod
    coverages: list[PolicyCoverage]
    request: CoverageRequest
    documents: list[Document]
    loss_date: date
    loss_facts: str

    def coverage_for_request(self) -> PolicyCoverage:
        for c in self.coverages:
            if c.coverage_id == self.request.coverage_id:
                return c
        raise ValueError(
            f"CoverageRequest {self.request.request_id} references "
            f"coverage_id={self.request.coverage_id!r} which is not "
            f"in the fixture"
        )


# =============================================================================
# Cross-claim entities — added for the Triage ranker (first cross-claim service)
# =============================================================================


class Claim(BaseModel):
    """The unit of adjuster work. Aggregates one or more CoverageRequests."""

    claim_id: str
    policy_period_id: str
    opened_date: date
    status: ClaimStatus = "open"
    severity_tier_summary: SeverityTier = "standard"
    litigation_flag: bool = False
    rep_flag: bool = False
    complaint_flag: bool = False
    claimant_name: str | None = Field(
        default=None,
        description=(
            "Display name of the claimant party. Optional because the "
            "name may be unknown at FNOL — intake_reader fills it in "
            "when extracted from documents. Workflows that need to "
            "render a letter (Outreach Drafter) require this; they "
            "raise if it's null."
        ),
    )
    insured_name: str | None = Field(
        default=None,
        description=(
            "Display name of the insured. Same null-at-FNOL semantics "
            "as claimant_name."
        ),
    )
    coverage_posture: Literal[
        "under_investigation", "ROR_issued", "denied", "accepted"
    ] = Field(
        default="under_investigation",
        description=(
            "The carrier's current coverage stance. Drives correspondence "
            "framing — once ROR_issued, every outbound to the "
            "claimant/insured/counsel must carry the reservation-of-rights "
            "caveat so subsequent communication doesn't waive the position. "
            "Defaults to under_investigation (no special framing). Today "
            "this field is hand-flipped (or set by the demo); future work "
            "wires the Coverage specialist's recommendation back onto the "
            "claim so the posture transition is automatic."
        ),
    )


class AgentAction(BaseModel):
    """Audit trail of one system (AI-agent or validator) action on a claim."""

    action_id: str
    claim_id: str
    timestamp: datetime
    workflow: str  # e.g., "coverage", "liability", "reserve", "triage"
    action_type: Literal[
        "specialist_invoked",
        "analysis_emitted",
        "validator_pass",
        "validator_fail",
        "draft_created",
        "ranker_update",
    ]
    summary: str
    success: bool = True


class WorkItem(BaseModel):
    """One recorded human touch on a claim by an adjuster."""

    work_item_id: str
    claim_id: str
    timestamp: datetime
    adjuster_id: str
    action: str  # free-form: "note_added", "status_changed", "payment_authorized", ...
    note: str | None = None


class ServiceDeadline(BaseModel):
    """Carrier-/TPA-committed deadline (e.g., 24-hour contact, 30-day decision).

    `request_id` is optional — some deadlines bind to the whole claim
    (24h-contact), others to a specific coverage request (30-day-decision).
    """

    deadline_id: str
    claim_id: str
    request_id: str | None = None
    name: str  # e.g., "24h-contact", "30-day-decision", "client-monthly-report"
    deadline: datetime
    met: bool = False
    met_at: datetime | None = None


class ScheduledTask(BaseModel):
    """A scheduled follow-up task on a claim (diary item in industry parlance)."""

    task_id: str
    claim_id: str
    fire_date: datetime
    description: str
    cleared: bool = False
    cleared_at: datetime | None = None


class LedgerEntry(BaseModel):
    """One paid or reserved dollar event on a specific coverage request."""

    entry_id: str
    request_id: str
    timestamp: datetime
    entry_type: Literal["payment", "reserve_set", "reserve_adjusted", "reserve_release"]
    amount: float  # signed: positive for payments and reserve increases, negative for releases
    payee_party_id: str | None = None
    note: str | None = None


class Communication(BaseModel):
    """One recorded interaction with a party (inbound or outbound)."""

    communication_id: str
    claim_id: str
    timestamp: datetime
    direction: Literal["inbound", "outbound"]
    channel: Literal["phone", "email", "letter", "portal", "in_person", "sms"]
    party_id: str
    party_role: Literal[
        "claimant", "insured", "counsel", "vendor",
        "witness", "broker", "carrier_internal",
    ]
    summary: str


class LegalDeadline(BaseModel):
    """A legally-imposed deadline on a coverage request (statute of limitations,
    coverage notice deadline, etc.). Date-granularity is enough — these are
    set by statute or contract on a calendar day."""

    deadline_id: str
    request_id: str
    name: str  # e.g., "subro_SOL_FL_auto", "coverage_notice_30day"
    deadline_date: date
    expired: bool = False


OutboundChannel = Literal[
    "email", "phone", "portal", "fax", "mail", "in_person",
    "subpoena", "court_record",
]
"""How an outbound request was (or will be) delivered. Mirrors the
`Channel` literal in `services/info_map/types.py` minus the
internal-only channels (`internal_lookup`, `api`) — those don't
generate an `OutboundRequest`."""


OutboundStatus = Literal[
    "pending_draft",  # created, awaiting LLM drafter
    "drafted",        # LLM produced body; adjuster hasn't sent
    "sent",           # adjuster sent; awaiting reply
    "replied",        # Reply Parser linked an inbound document
    "overdue",        # follow_up_due_at passed without reply
    "cancelled",      # adjuster cancelled before send
]


class OutboundRequest(BaseModel):
    """One outbound information request the adjuster (with help from
    the system) sends to an external party to close one or more open
    questions.

    Lifecycle: `pending_draft` → `drafted` → `sent` → `replied`. The
    `overdue` and `cancelled` branches break from `sent` and any
    pre-send state respectively.

    Created by `RecordOutboundRequest` Action Type (Foundry mapping).
    Mutated by `SendOutbound`, `MarkOverdue`, `MarkReplied` Action
    Types. The LLM-produced body is filled in by the `DraftOutreach`
    Action Type when the Outreach Drafter specialist ships (step 3b).
    """

    request_id: str = Field(
        description="Stable identifier (e.g., 'OBR-001234')."
    )
    claim_id: str
    recipient_party: str = Field(
        description=(
            "Free-form party identifier matching info-map source.party "
            "values: 'claimant_counsel', 'body_shop', 'medical_provider', "
            "'iso_claim_search', etc."
        )
    )
    recipient_name: str = Field(
        min_length=1,
        description=(
            "Display name of the specific recipient ('Marisol Trent, "
            "Esq.', 'St. Anthony's Medical Records Desk'). Part of "
            "the thread key with (claim_id, recipient_party) — "
            "different recipients at the same party reset the thread."
        ),
    )
    letter_purpose: str = Field(
        min_length=1,
        description=(
            "Free-form one-line purpose the info-gap detector "
            "captures at creation time ('Follow up with defense "
            "counsel; initial case eval not received after 22 "
            "days'). The drafter reads this to choose tone/framing "
            "without re-deriving intent."
        ),
    )
    question_ids_asked: list[str] = Field(
        min_length=1,
        description=(
            "Info-map question IDs this outbound asks about. Used by "
            "Reply Parser to scope the candidate set when matching a "
            "reply to questions."
        ),
    )
    status: OutboundStatus = "pending_draft"

    # Draft phase (filled by Outreach Drafter — step 3b)
    drafted_at: datetime | None = None
    draft_body: str | None = Field(
        default=None,
        description=(
            "LLM-produced outreach text. Null until the Outreach "
            "Drafter ships."
        ),
    )

    # Send phase (filled when adjuster acts on the draft)
    sent_at: datetime | None = None
    channel: OutboundChannel | None = None
    follow_up_due_at: datetime | None = Field(
        default=None,
        description=(
            "When a follow-up reminder fires if no reply has arrived. "
            "Set at send time based on the question's expected "
            "cycle_time."
        ),
    )

    # Reply phase (filled by Reply Parser — step 4)
    replied_at: datetime | None = None
    reply_doc_id: str | None = Field(
        default=None,
        description=(
            "Document ID of the inbound document Reply Parser matched "
            "to this outbound."
        ),
    )

    @model_validator(mode="after")
    def status_field_consistency(self) -> OutboundRequest:
        """Each status implies which fields must be populated; enforced
        here so downstream code can rely on the invariant."""
        if self.status in ("sent", "replied", "overdue") and self.sent_at is None:
            raise ValueError(
                f"OutboundRequest {self.request_id}: status={self.status!r} "
                f"requires sent_at to be set."
            )
        if self.status == "replied":
            if self.reply_doc_id is None:
                raise ValueError(
                    f"OutboundRequest {self.request_id}: status='replied' "
                    f"requires reply_doc_id."
                )
            if self.replied_at is None:
                raise ValueError(
                    f"OutboundRequest {self.request_id}: status='replied' "
                    f"requires replied_at."
                )
        return self


class Caseload(BaseModel):
    """The complete cross-claim state for a triage run.

    Bundles every Claim + CoverageRequest the adjuster has open, plus the
    cross-claim state (deadlines, tasks, ledger, communications, audit trail)
    that the ranker scores. `as_of` is the "now" reference — features that
    depend on time (hours_until_sla_breach, days_since_claimant_contact) are
    computed against this timestamp, not the wall clock, so ranks are
    reproducible.
    """

    as_of: datetime

    claims: list[Claim]
    requests: list[CoverageRequest]
    documents: list[Document] = Field(default_factory=list)

    service_deadlines: list[ServiceDeadline] = Field(default_factory=list)
    legal_deadlines: list[LegalDeadline] = Field(default_factory=list)
    scheduled_tasks: list[ScheduledTask] = Field(default_factory=list)
    ledger_entries: list[LedgerEntry] = Field(default_factory=list)
    communications: list[Communication] = Field(default_factory=list)
    agent_actions: list[AgentAction] = Field(default_factory=list)
    work_items: list[WorkItem] = Field(default_factory=list)
    outbound_requests: list[OutboundRequest] = Field(default_factory=list)

    # ----- derivation helpers (kept small; features.py builds on these) -----

    def claim_for(self, request: CoverageRequest) -> Claim:
        for c in self.claims:
            if c.claim_id == request.claim_id:
                return c
        raise ValueError(
            f"CoverageRequest {request.request_id} references "
            f"claim_id={request.claim_id!r} which is not in the caseload"
        )

    def outbounds_for_claim(self, claim_id: str) -> list[OutboundRequest]:
        """All outbound requests bound to this claim, in insertion
        order. Used by Brief to render outreach state in the
        open-questions panel and by Reply Parser to scope the
        candidate set when an inbound document arrives."""
        return [o for o in self.outbound_requests if o.claim_id == claim_id]

    def open_outbounds_for_claim(self, claim_id: str) -> list[OutboundRequest]:
        """Outbounds that are still awaiting a reply (sent but not
        replied/cancelled). Reply Parser scopes its candidate set to
        these on inbound."""
        return [
            o for o in self.outbounds_for_claim(claim_id)
            if o.status in ("sent", "overdue")
        ]

    def paid_to_date(self, request_id: str) -> float:
        """Sum of all payment LedgerEntries on this coverage request."""
        return sum(
            e.amount for e in self.ledger_entries
            if e.request_id == request_id and e.entry_type == "payment"
        )

    def reserve_current(self, request_id: str) -> float:
        """Sum of reserve-shaped LedgerEntries (set + adjusted + release) on this
        coverage request. Returns 0.0 if no reserve has been set yet."""
        return sum(
            e.amount for e in self.ledger_entries
            if e.request_id == request_id and e.entry_type in (
                "reserve_set", "reserve_adjusted", "reserve_release",
            )
        )
