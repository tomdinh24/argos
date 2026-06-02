"""Glue between the Document Reader and the triage policy engine.

Given a `Caseload`, runs the Reader on every unread document and
returns a `{claim_id: relevant_unread_count}` map ready to pass into
`rank_policy(..., relevant_doc_counts=...)`.

"Unread" matches the same definition the triage features use: a
document whose `received_date` is strictly after the most recent
`AgentAction.timestamp` for that claim (or all docs on the claim if
no AgentAction exists).

No business logic lives here — just orchestration over the Reader.
The policy engine stays pure (no LLM calls inside `rank_policy()`);
this module is what supplies it Reader-screened counts.

Spec: `docs/specs/triage-ranker-policy-engine.md` Layer 3.
Integration thresholds: `docs/evals/triage-policy-engine-with-reader-integrated-thresholds.md`.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Callable

from argos.ontology.types import Caseload, Document
from argos.services.orchestrator.dispatcher import dispatch
from argos.services.orchestrator.job import Job
from argos.services.orchestrator.queue import JobQueue
from argos.workflows.document_reader import (
    ClaimContext,
    DocumentInput,
    RelevanceCall,
    RelevanceCallResult,
    run_document_reader,
)


ReaderFn = Callable[[DocumentInput, ClaimContext], RelevanceCallResult]
"""Signature of `run_document_reader`. Tests can pass a stub; production
callers leave it None and the real Reader is used."""


@dataclass(frozen=True)
class ReaderCallRecord:
    """Audit record for one Reader call: input doc + output call."""

    document_id: str
    claim_id: str
    call: RelevanceCall
    model: str
    attempts: int


def _unread_docs_by_claim(caseload: Caseload) -> dict[str, list[Document]]:
    """Match the unread definition in `features.py:extract_raw`:
    received_date > last AgentAction timestamp on the claim. If no
    AgentAction exists, every doc on the claim counts as unread."""
    out: dict[str, list[Document]] = defaultdict(list)
    last_action_by_claim: dict[str, object] = {}
    for a in caseload.agent_actions:
        prev = last_action_by_claim.get(a.claim_id)
        if prev is None or a.timestamp > prev:  # type: ignore[operator]
            last_action_by_claim[a.claim_id] = a.timestamp
    for d in caseload.documents:
        last = last_action_by_claim.get(d.claim_id)
        if last is None:
            out[d.claim_id].append(d)
        else:
            if d.received_date > last.date():  # type: ignore[union-attr]
                out[d.claim_id].append(d)
    return out


def _build_claim_context(caseload: Caseload, claim_id: str) -> ClaimContext:
    """Render the minimal ClaimContext the Reader needs for one claim.

    Pulls severity, reserves, flags, coverage status, and a one-line
    loss_facts summary from the Caseload entities. Mirrors what the
    Reader's anchor-pair fixtures supply.
    """
    claim = next(c for c in caseload.claims if c.claim_id == claim_id)
    request = next(r for r in caseload.requests if r.claim_id == claim_id)

    current_reserve = caseload.reserve_current(request.request_id)
    paid = caseload.paid_to_date(request.request_id)

    # Minimal loss-facts placeholder — the synthetic fixture doesn't carry
    # a loss_facts field on Claim, so we synthesize one from severity +
    # type. Real production would pull from the underlying intake record.
    loss_facts = (
        f"Auto bodily injury claim, severity tier '{claim.severity_tier_summary}', "
        f"opened {claim.opened_date.isoformat()}."
    )

    return ClaimContext(
        claim_id=claim_id,
        severity_tier=claim.severity_tier_summary,
        current_reserve_amount=current_reserve,
        paid_to_date=paid,
        litigation_flag=claim.litigation_flag,
        rep_flag=claim.rep_flag,
        complaint_flag=claim.complaint_flag,
        open_coverage_status=request.coverage_status,
        loss_facts=loss_facts,
    )


@dataclass
class ReaderScreeningResult:
    """Output of `screen_caseload`: per-claim relevant-doc counts +
    audit trail of every Reader call made."""

    relevant_doc_counts: dict[str, int]
    call_records: list[ReaderCallRecord]
    docs_screened: int


def screen_caseload(caseload: Caseload) -> ReaderScreeningResult:
    """Run the Document Reader on every unread doc in the caseload.

    Returns `{claim_id: material_count}` ready to pass into
    `rank_policy(..., relevant_doc_counts=...)`, plus an audit list of
    every Reader call (for benchmark verification against pre-registered
    Reader output predictions).
    """
    unread = _unread_docs_by_claim(caseload)
    relevant_doc_counts: dict[str, int] = defaultdict(int)
    call_records: list[ReaderCallRecord] = []
    docs_screened = 0

    for claim_id, docs in unread.items():
        ctx = _build_claim_context(caseload, claim_id)
        for doc in docs:
            docs_screened += 1
            doc_input = DocumentInput(
                document_id=doc.document_id,
                document_type=doc.document_type,
                source=doc.source,
                received_date=doc.received_date.isoformat(),
                body_text=doc.body_text,
            )
            result: RelevanceCallResult = run_document_reader(doc_input, ctx)
            call_records.append(
                ReaderCallRecord(
                    document_id=doc.document_id,
                    claim_id=claim_id,
                    call=result.call,
                    model=result.model,
                    attempts=result.attempts,
                )
            )
            if result.call.relevant:
                relevant_doc_counts[claim_id] += 1

    # Convert to plain dict (defaultdict shouldn't leak into callers).
    return ReaderScreeningResult(
        relevant_doc_counts=dict(relevant_doc_counts),
        call_records=call_records,
        docs_screened=docs_screened,
    )


def dispatch_screening_results(
    screening: ReaderScreeningResult,
    queue: JobQueue,
) -> list[Job]:
    """Auto-dispatch specialist jobs from a screening pass.

    For every Reader call where `relevant == True`, runs the pure
    `orchestrator.dispatcher.dispatch()` function to map the posture
    to one or more specialist jobs, then enqueues each via
    `JobQueue.enqueue()` (which is idempotent on
    `(specialist, claim_id, triggered_by_doc_id)`).

    Returns the list of Job objects that were actually enqueued
    (after idempotency filtering by the queue). Empty when no call
    was relevant or when every implied job was already pending /
    running.

    This is the wire that turns "Reader said this doc matters" into
    "Coverage / Reserve / Liability runs in the background" without
    a caller manually walking the screening output. See decision
    `docs/DECISIONS.md` — "Auto-dispatch from Reader → Orchestrator".
    """
    enqueued: list[Job] = []
    for record in screening.call_records:
        for job in dispatch(record.call, record.claim_id):
            persisted = queue.enqueue(job)
            # JobQueue.enqueue returns the existing job on idempotency
            # collision and the new job on a fresh enqueue. Only
            # count fresh enqueues here so callers can see what
            # actually changed.
            if persisted is job:
                enqueued.append(job)
    return enqueued


def retrigger_analysis_for_docs(
    docs: list[Document],
    claim_id: str,
    *,
    caseload: Caseload,
    queue: JobQueue,
    reader_fn: ReaderFn | None = None,
) -> list[Job]:
    """Run Reader on each doc, dispatch the resulting calls, enqueue.

    The cross-stream entry point (`advance_claim`) calls this after
    new disclosures land in `caseload.documents`, so the analysis
    pipeline (Coverage / Reserve / Liability) re-fires on fresh
    evidence. Without this, disclosures would sit in the file
    unread until the next manual screening pass.

    Reader runs inline here (one LLM call per doc) — that's cheap,
    and the routing decision needs to happen before any analysis
    Job can be enqueued. The heavy analytical workflows still drain
    on the runner's cadence, NOT inline. Same separation of "fast
    routing decisions" vs. "expensive specialist runs" the rest of
    the orchestrator uses.

    Returns the list of Jobs that were newly enqueued (idempotency
    filter applied — if a Coverage job for (claim, doc) already
    exists in the queue, this call returns it but doesn't duplicate).

    `reader_fn` is a callable injection point for tests. Production
    callers leave it None and the real `run_document_reader` is
    invoked.
    """
    if not docs:
        return []
    ctx = _build_claim_context(caseload, claim_id)
    fn = reader_fn or run_document_reader
    enqueued: list[Job] = []
    for doc in docs:
        doc_input = DocumentInput(
            document_id=doc.document_id,
            document_type=doc.document_type,
            source=doc.source,
            received_date=doc.received_date.isoformat(),
            body_text=doc.body_text,
        )
        result = fn(doc_input, ctx)
        for job in dispatch(result.call, claim_id):
            persisted = queue.enqueue(job)
            if persisted is job:
                enqueued.append(job)
    return enqueued
