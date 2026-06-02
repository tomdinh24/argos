"""Synthetic caseload builder for the Triage ranker benchmark.

Generates an N=20 corner-covering caseload as a `Caseload` object — every
Claim, CoverageRequest, and supporting cross-claim state (ServiceDeadlines,
LegalDeadlines, ScheduledTasks, LedgerEntries, Communications, AgentActions,
WorkItems) the ranker needs to compute features.

Corner mix (spec docs/specs/triage-ranker.md "Fixture" section):

  3 SLA-imminent       (ServiceDeadline 1h / 4h / 6h out)
  3 statute-approaching (LegalDeadline 3d / 7d / 14d out)
  3 high incurred / high severity
  3 aged / silent      (no system or human touch in 14+ days)
  3 with recent unread evidence (1 / 2 / 3 new docs since last AgentAction)
  2 with litigation + rep flags
  1 with complaint flag
  2 obvious backburner (minor severity, no clocks, recent touch)
  = 20 total

Each corner anchors one or two features at the extreme; everything else
on that claim is set to baseline values so the targeted feature carries
the signal. The hand-ranking gold is built against this mix.

Reproducibility: the caseload is deterministic given `as_of`. Same `as_of`
in → identical Caseload out. No randomness, no wall-clock reads.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from argos.ontology.types import (
    AgentAction,
    Caseload,
    Claim,
    Communication,
    CoverageRequest,
    Document,
    LedgerEntry,
    LegalDeadline,
    ScheduledTask,
    ServiceDeadline,
    SeverityTier,
    WorkItem,
)


# A fixed, realistic "now" for the synthetic caseload. Friday morning, 09:00 ET.
DEFAULT_AS_OF = datetime(2026, 5, 29, 13, 0, tzinfo=timezone.utc)  # 09:00 EDT


# Placeholder coverage_id strings — the triage ranker doesn't read policy
# structure, so these are just labels. (Coverage specialist reads PolicyCoverage
# objects directly via SyntheticClaim.)
_COVERAGE_BI = "CP-AUTO-BI-STANDARD"
_COVERAGE_PD = "CP-AUTO-PD-STANDARD"
_COVERAGE_PROP = "CP-PROP-BUILDING"


# Each corner case is specified declaratively with this struct. The builder
# converts it into Claim + CoverageRequest + supporting state.
@dataclass
class _ExposureSpec:
    """Declarative spec for one fixture exposure. The builder fills the rest."""

    label: str  # short human label, used in IDs and CSVs
    opened_days_ago: int = 45
    severity: SeverityTier = "standard"
    coverage_id: str = _COVERAGE_BI

    # Time-since-touch
    last_action_hours_ago: float = 24.0  # most recent AgentAction
    last_work_hours_ago: float = 36.0    # most recent WorkItem

    # Deadlines
    sla_hours_out: float | None = None       # None = no SLA deadline firing
    statute_days_out: int | None = None       # None = no statute deadline

    # Tasks (diary)
    open_task_count: int = 0
    overdue_task_count: int = 0  # subset of open, already past fire_date

    # Ledger
    reserve_amount: float = 5_000.0
    paid_amount: float = 0.0

    # Communications
    days_since_claimant_contact: int = 7

    # Documents
    unread_doc_count: int = 0  # documents received after last AgentAction

    # Flags
    litigation: bool = False
    rep: bool = False
    complaint: bool = False


@dataclass
class _ExposureBundle:
    """All entities produced for one fixture exposure."""

    claim: Claim
    request: CoverageRequest
    documents: list[Document] = field(default_factory=list)
    service_deadlines: list[ServiceDeadline] = field(default_factory=list)
    legal_deadlines: list[LegalDeadline] = field(default_factory=list)
    scheduled_tasks: list[ScheduledTask] = field(default_factory=list)
    ledger_entries: list[LedgerEntry] = field(default_factory=list)
    communications: list[Communication] = field(default_factory=list)
    agent_actions: list[AgentAction] = field(default_factory=list)
    work_items: list[WorkItem] = field(default_factory=list)


# ---------------------------------------------------------------------------
# The 20 corner cases — one _ExposureSpec each, ordered by category
# ---------------------------------------------------------------------------


def _spec_list() -> list[_ExposureSpec]:
    return [
        # --- 3 SLA-imminent ---------------------------------------------------
        _ExposureSpec("sla-1h", sla_hours_out=1.0, severity="serious", reserve_amount=80_000),
        _ExposureSpec("sla-4h", sla_hours_out=4.0, severity="standard", reserve_amount=25_000),
        _ExposureSpec("sla-6h", sla_hours_out=6.0, severity="standard", reserve_amount=15_000),

        # --- 3 statute-approaching --------------------------------------------
        _ExposureSpec("stat-3d", statute_days_out=3, severity="serious", reserve_amount=120_000),
        _ExposureSpec("stat-7d", statute_days_out=7, severity="standard", reserve_amount=40_000),
        _ExposureSpec("stat-14d", statute_days_out=14, severity="standard", reserve_amount=30_000),

        # --- 3 high incurred / high severity ----------------------------------
        _ExposureSpec(
            "hi-cat", severity="catastrophic",
            reserve_amount=1_500_000, paid_amount=250_000,
            coverage_id=_COVERAGE_BI, opened_days_ago=120,
        ),
        _ExposureSpec(
            "hi-serious-1", severity="serious",
            reserve_amount=500_000, paid_amount=85_000,
        ),
        _ExposureSpec(
            "hi-serious-2", severity="serious",
            reserve_amount=750_000, paid_amount=125_000,
            coverage_id=_COVERAGE_PROP,
        ),

        # --- 3 aged / silent (no touch in 14+ days) ---------------------------
        _ExposureSpec(
            "aged-15d", last_action_hours_ago=15 * 24, last_work_hours_ago=15 * 24,
            severity="standard", reserve_amount=20_000, days_since_claimant_contact=20,
        ),
        _ExposureSpec(
            "aged-21d", last_action_hours_ago=21 * 24, last_work_hours_ago=21 * 24,
            severity="standard", reserve_amount=35_000, days_since_claimant_contact=25,
        ),
        _ExposureSpec(
            "aged-30d", last_action_hours_ago=30 * 24, last_work_hours_ago=30 * 24,
            severity="serious", reserve_amount=60_000, days_since_claimant_contact=30,
        ),

        # --- 3 with recent unread evidence ------------------------------------
        _ExposureSpec(
            "unread-1", unread_doc_count=1, severity="standard",
            reserve_amount=18_000, last_action_hours_ago=72,
        ),
        _ExposureSpec(
            "unread-2", unread_doc_count=2, severity="serious",
            reserve_amount=55_000, last_action_hours_ago=96,
        ),
        _ExposureSpec(
            "unread-3", unread_doc_count=3, severity="serious",
            reserve_amount=90_000, last_action_hours_ago=120,
        ),

        # --- 2 with litigation + rep flags ------------------------------------
        _ExposureSpec(
            "lit-rep-1", litigation=True, rep=True,
            severity="serious", reserve_amount=200_000,
            open_task_count=2, overdue_task_count=1,
        ),
        _ExposureSpec(
            "lit-rep-2", litigation=True, rep=True,
            severity="serious", reserve_amount=350_000,
            statute_days_out=45,
        ),

        # --- 1 with complaint flag --------------------------------------------
        _ExposureSpec(
            "complaint-doi", complaint=True, rep=True,
            severity="standard", reserve_amount=15_000,
            days_since_claimant_contact=2, open_task_count=1,
        ),

        # --- 2 obvious backburner ---------------------------------------------
        _ExposureSpec(
            "bb-minor-1", severity="minor", reserve_amount=2_000, paid_amount=1_500,
            last_action_hours_ago=12, last_work_hours_ago=18,
            days_since_claimant_contact=2,
        ),
        _ExposureSpec(
            "bb-minor-2", severity="minor", reserve_amount=750, paid_amount=500,
            last_action_hours_ago=8, last_work_hours_ago=10,
            days_since_claimant_contact=1,
        ),
    ]


# ---------------------------------------------------------------------------
# Builder — converts a spec into entities, keyed by sequential ID
# ---------------------------------------------------------------------------


def _hours_ago(as_of: datetime, hours: float) -> datetime:
    return as_of - timedelta(hours=hours)


def _build_one(spec: _ExposureSpec, idx: int, as_of: datetime) -> _ExposureBundle:
    """Materialize one spec into an _ExposureBundle. `idx` is 1-based."""
    n = f"{idx:03d}"
    claim_id = f"CLM-{n}"
    request_id = f"REQ-{n}"
    claimant_id = f"PTY-CLM-{n}"

    opened = (as_of - timedelta(days=spec.opened_days_ago)).date()

    # Claim
    claim = Claim(
        claim_id=claim_id,
        policy_period_id="PP-FIXTURE-2026",
        opened_date=opened,
        status="open",
        severity_tier_summary=spec.severity,
        litigation_flag=spec.litigation,
        rep_flag=spec.rep,
        complaint_flag=spec.complaint,
    )

    # CoverageRequest
    request = CoverageRequest(
        request_id=request_id,
        claim_id=claim_id,
        coverage_id=spec.coverage_id,
        claimant_party_id=claimant_id,
        coverage_status="pending",
        severity_tier=spec.severity,
    )

    bundle = _ExposureBundle(claim=claim, request=request)

    # Most recent AgentAction — drives "hours_since_last_touch" and the
    # unread-doc cutoff (documents received_date > last AgentAction.timestamp).
    last_action_ts = _hours_ago(as_of, spec.last_action_hours_ago)
    bundle.agent_actions.append(AgentAction(
        action_id=f"AA-{n}-001",
        claim_id=claim_id,
        timestamp=last_action_ts,
        workflow="coverage",
        action_type="analysis_emitted",
        summary="initial coverage analysis",
        success=True,
    ))

    # Most recent WorkItem (human touch)
    last_work_ts = _hours_ago(as_of, spec.last_work_hours_ago)
    bundle.work_items.append(WorkItem(
        work_item_id=f"WI-{n}-001",
        claim_id=claim_id,
        timestamp=last_work_ts,
        adjuster_id="ADJ-001",
        action="note_added",
        note="reviewed",
    ))

    # SLA deadline (optional)
    if spec.sla_hours_out is not None:
        bundle.service_deadlines.append(ServiceDeadline(
            deadline_id=f"SD-{n}-001",
            claim_id=claim_id,
            request_id=None,
            name="30-day-decision",
            deadline=as_of + timedelta(hours=spec.sla_hours_out),
            met=False,
        ))

    # Statute deadline (optional)
    if spec.statute_days_out is not None:
        bundle.legal_deadlines.append(LegalDeadline(
            deadline_id=f"LD-{n}-001",
            request_id=request_id,
            name="subro_SOL",
            deadline_date=as_of.date() + timedelta(days=spec.statute_days_out),
            expired=False,
        ))

    # Open / overdue scheduled tasks
    for t in range(spec.open_task_count):
        is_overdue = t < spec.overdue_task_count
        # overdue tasks fire 1+ days before as_of; non-overdue fire 2+ days ahead
        fire = as_of - timedelta(days=t + 1) if is_overdue else as_of + timedelta(days=2 + t)
        bundle.scheduled_tasks.append(ScheduledTask(
            task_id=f"ST-{n}-{t+1:02d}",
            claim_id=claim_id,
            fire_date=fire,
            description="diary follow-up",
            cleared=False,
        ))

    # Reserve ledger entry (single "reserve_set" event)
    if spec.reserve_amount > 0:
        bundle.ledger_entries.append(LedgerEntry(
            entry_id=f"LE-{n}-RES",
            request_id=request_id,
            timestamp=last_action_ts,  # set when initial analysis ran
            entry_type="reserve_set",
            amount=spec.reserve_amount,
        ))

    # Payments to date
    if spec.paid_amount > 0:
        bundle.ledger_entries.append(LedgerEntry(
            entry_id=f"LE-{n}-PAY",
            request_id=request_id,
            timestamp=last_action_ts + timedelta(hours=1),
            entry_type="payment",
            amount=spec.paid_amount,
            payee_party_id=claimant_id,
        ))

    # Most recent claimant communication
    bundle.communications.append(Communication(
        communication_id=f"CO-{n}-001",
        claim_id=claim_id,
        timestamp=as_of - timedelta(days=spec.days_since_claimant_contact),
        direction="outbound",
        channel="phone",
        party_id=claimant_id,
        party_role="claimant",
        summary="status update call",
    ))

    # Unread documents — received after the last AgentAction so they count
    # as "unread by the system"
    for d in range(spec.unread_doc_count):
        # received between last_action_ts and now, spaced evenly
        offset = timedelta(hours=(d + 1) * (spec.last_action_hours_ago / (spec.unread_doc_count + 1)))
        received_dt = last_action_ts + offset
        bundle.documents.append(Document(
            document_id=f"DOC-{n}-{d+1:02d}",
            claim_id=claim_id,
            document_type="correspondence",
            received_date=received_dt.date(),
            source="claimant_email",
            body_text="(synthetic placeholder body)",
        ))

    return bundle


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def build_caseload(as_of: datetime = DEFAULT_AS_OF) -> Caseload:
    """Build the deterministic N=20 corner-covering triage caseload.

    Given the same `as_of`, returns an identical Caseload — no randomness, no
    wall-clock reads. Used by the triage benchmark and by `synthetic_caseload`
    consumers that want a stable cross-claim fixture.
    """
    specs = _spec_list()
    if len(specs) != 20:  # defensive — keep the corner mix locked at 20
        raise ValueError(
            f"Expected 20 exposure specs (corner mix), got {len(specs)}"
        )

    bundles = [_build_one(spec, idx=i + 1, as_of=as_of) for i, spec in enumerate(specs)]

    return Caseload(
        as_of=as_of,
        claims=[b.claim for b in bundles],
        requests=[b.request for b in bundles],
        documents=[d for b in bundles for d in b.documents],
        service_deadlines=[sd for b in bundles for sd in b.service_deadlines],
        legal_deadlines=[ld for b in bundles for ld in b.legal_deadlines],
        scheduled_tasks=[st for b in bundles for st in b.scheduled_tasks],
        ledger_entries=[le for b in bundles for le in b.ledger_entries],
        communications=[co for b in bundles for co in b.communications],
        agent_actions=[aa for b in bundles for aa in b.agent_actions],
        work_items=[wi for b in bundles for wi in b.work_items],
    )


# Mapping of request_id → corner-case label, for downstream CSV / gold-ranking
# bookkeeping. Stable as long as `_spec_list()` order is stable.
def corner_labels() -> dict[str, str]:
    return {f"REQ-{i+1:03d}": spec.label for i, spec in enumerate(_spec_list())}
