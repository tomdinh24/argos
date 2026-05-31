"""Glue between the Document Reader and the triage policy engine.

Given a `Caseload`, runs the Reader on every unread document and
returns a `{claim_id: material_unread_count}` map ready to pass into
`rank_policy(..., material_counts=...)`.

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

from argos.ontology.types import Caseload, Document
from argos.specialists.document_reader import (
    ClaimContext,
    DocumentInput,
    MaterialityCall,
    MaterialityCallResult,
    run_document_reader,
)


@dataclass(frozen=True)
class ReaderCallRecord:
    """Audit record for one Reader call: input doc + output call."""

    document_id: str
    claim_id: str
    call: MaterialityCall
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
    """Output of `screen_caseload`: per-claim material counts + audit
    trail of every Reader call made."""

    material_counts: dict[str, int]
    call_records: list[ReaderCallRecord]
    docs_screened: int


def screen_caseload(caseload: Caseload) -> ReaderScreeningResult:
    """Run the Document Reader on every unread doc in the caseload.

    Returns `{claim_id: material_count}` ready to pass into
    `rank_policy(..., material_counts=...)`, plus an audit list of
    every Reader call (for benchmark verification against pre-registered
    Reader output predictions).
    """
    unread = _unread_docs_by_claim(caseload)
    material_counts: dict[str, int] = defaultdict(int)
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
            result: MaterialityCallResult = run_document_reader(doc_input, ctx)
            call_records.append(
                ReaderCallRecord(
                    document_id=doc.document_id,
                    claim_id=claim_id,
                    call=result.call,
                    model=result.model,
                    attempts=result.attempts,
                )
            )
            if result.call.material:
                material_counts[claim_id] += 1

    # Convert to plain dict (defaultdict shouldn't leak into callers).
    return ReaderScreeningResult(
        material_counts=dict(material_counts),
        call_records=call_records,
        docs_screened=docs_screened,
    )
