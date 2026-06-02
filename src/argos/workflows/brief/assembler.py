"""Read-only assembler for the Brief specialist.

Pulls everything Brief needs from Caseload and the persisted
workflow-results directory. No LLM calls here. Produces a
`BriefDraft` — every `ClaimBrief` field except the two LLM-generated
ones (`story_paragraph` + `story_citations`, and the per-gap
rationale lines inside `missing_info`).

The narrative module fills the story; the gaps module turns the
detected raw gaps into final `MissingInfoItem` entries with LLM-
generated rationale + citations. `brief.py` glues them together.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from argos.ontology.types import Caseload, Claim, CoverageRequest, Document
from argos.schemas.workflows.brief import (
    CoverageStatus,
    FinancialSnapshot,
    HandlingStatus,
    LitigationStatus,
    RecoveryStatus,
    RepresentationStatus,
    SettlementStatus,
    SinceLastTouch,
    WorkflowName,
    WorkflowRecommendationHeadline,
    StatusSnapshot,
)
from argos.workflows.brief.answer_detector import detect_open_questions


# ---------------------------------------------------------------------------
# Raw gap shape (rule layer output, pre-LLM)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RawGap:
    """One detected gap before the LLM has written its rationale.

    `variable` is the missing thing (e.g., "policy_declarations").
    `requested_from` is the party who'd be asked for it. `citations`
    are the evidence the rule used to conclude it's missing —
    usually document_ids that exist (proving what we do have) or
    the absence of expected document types.
    """

    variable: str
    requested_from: str
    citation_doc_ids: tuple[str, ...]  # docs that prove the gap (often "what we have without it")


# ---------------------------------------------------------------------------
# Draft shape returned by the assembler
# ---------------------------------------------------------------------------


@dataclass
class BriefDraft:
    """Everything the assembler can produce without an LLM call.

    `brief.py` consumes this, makes the narrative + gap-rationale LLM
    calls, then assembles the final `ClaimBrief`.
    """

    claim_id: str
    request_id: str | None
    generated_at: datetime

    # Data needed by the narrative LLM call
    claim: Claim
    request: CoverageRequest | None
    documents: list[Document]
    loss_facts_hint: str  # one-paragraph context for the LLM, deterministic

    # Pre-built schema slices
    status_snapshot: StatusSnapshot
    financial_snapshot: FinancialSnapshot
    since_last_touch: SinceLastTouch
    workflow_recommendations: list[WorkflowRecommendationHeadline]

    # Raw gaps to be rationalized by the LLM gap call
    raw_gaps: list[RawGap] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Assembler entry-point
# ---------------------------------------------------------------------------


def assemble(
    caseload: Caseload,
    claim_id: str,
    results_root: Path | None = None,
) -> BriefDraft:
    """Build a `BriefDraft` for `claim_id` from `caseload` state.

    If `results_root` is provided, the assembler will read persisted
    specialist results from `{results_root}/{claim_id}/{specialist}.json`
    to populate `status_snapshot.coverage_status` and the
    `workflow_recommendations` list. When a specialist hasn't run, the
    corresponding field stays at its "not yet analyzed" default.
    """
    claim = _find_claim(caseload, claim_id)
    requests = [r for r in caseload.requests if r.claim_id == claim_id]
    request = requests[0] if requests else None
    documents = [d for d in caseload.documents if d.claim_id == claim_id]

    coverage_status, coverage_result = _read_coverage_result(
        results_root, claim_id, request
    )

    status_snapshot = StatusSnapshot(
        coverage_status=coverage_status,
        handling_status=_derive_handling_status(claim),
        settlement_status=_derive_settlement_status(),
        representation_status="represented" if claim.rep_flag else "unrepresented",
        litigation_status=_derive_litigation_status(claim),
        recovery_status="not_screened",
        financial_status=_derive_financial_status(caseload, requests),
    )

    financial_snapshot = _build_financial_snapshot(caseload, requests)

    workflow_recommendations = _build_workflow_recommendations(
        results_root, claim_id, coverage_result
    )

    raw_gaps = _detect_gaps(claim, documents, coverage_result, caseload.as_of)

    return BriefDraft(
        claim_id=claim_id,
        request_id=request.request_id if request else None,
        generated_at=_now(),
        claim=claim,
        request=request,
        documents=documents,
        loss_facts_hint=_loss_facts_hint(claim, request, documents),
        status_snapshot=status_snapshot,
        financial_snapshot=financial_snapshot,
        since_last_touch=SinceLastTouch(last_touch_at=None, diff_items=[]),
        workflow_recommendations=workflow_recommendations,
        raw_gaps=raw_gaps,
    )


# ---------------------------------------------------------------------------
# Pull-from-caseload helpers
# ---------------------------------------------------------------------------


def _find_claim(caseload: Caseload, claim_id: str) -> Claim:
    for c in caseload.claims:
        if c.claim_id == claim_id:
            return c
    raise ValueError(f"Claim {claim_id!r} not in caseload")


def _derive_handling_status(claim: Claim) -> HandlingStatus:
    if claim.status == "closed":
        return "closed"
    if claim.litigation_flag:
        return "in_negotiation"
    return "open_investigation"


def _derive_settlement_status() -> SettlementStatus:
    # No settlement tracking in the current Caseload shape. Defaults to
    # not_applicable until the Settlement/Closure specialists feed us data.
    return "not_applicable"


def _derive_litigation_status(claim: Claim) -> LitigationStatus:
    return "suit_filed" if claim.litigation_flag else "none"


def _derive_financial_status(caseload: Caseload, requests: list[CoverageRequest]):
    if not requests:
        return "no_payment_due"
    total_paid = sum(caseload.paid_to_date(r.request_id) for r in requests)
    total_reserved = sum(caseload.reserve_current(r.request_id) for r in requests)
    if total_paid == 0 and total_reserved == 0:
        return "no_payment_due"
    if total_paid == 0:
        return "reserves_outstanding"
    if total_paid > 0 and total_reserved > 0:
        return "partially_paid"
    return "paid"


def _build_financial_snapshot(
    caseload: Caseload, requests: list[CoverageRequest]
) -> FinancialSnapshot:
    paid = sum(caseload.paid_to_date(r.request_id) for r in requests)
    reserved = sum(caseload.reserve_current(r.request_id) for r in requests)
    now = _now()
    return FinancialSnapshot(
        as_of_effective=now,
        as_of_recorded=now,
        outstanding_indemnity=max(reserved - paid, 0.0),
        paid_indemnity=paid,
        outstanding_alae=0.0,
        paid_alae=0.0,
        recovered=0.0,
    )


# ---------------------------------------------------------------------------
# Specialist-results helpers
# ---------------------------------------------------------------------------


def _read_coverage_result(
    results_root: Path | None,
    claim_id: str,
    request: CoverageRequest | None,
) -> tuple[CoverageStatus, dict | None]:
    """Return (status, raw_result_dict_or_None).

    Status falls back to the CoverageRequest's own `coverage_status` when
    no specialist result is available. The request defaults to "pending".
    """
    default_status: CoverageStatus = (
        request.coverage_status if request else "pending"
    )
    if results_root is None:
        return default_status, None

    path = results_root / claim_id / "coverage.json"
    if not path.exists():
        return default_status, None

    result = json.loads(path.read_text())
    # Coverage analysis emits a `synthesis.outcomes` list; the top outcome
    # is the "clean coverage" probability. We only surface the request's
    # own status here — the headline goes into workflow_recommendations.
    return default_status, result


def _build_workflow_recommendations(
    results_root: Path | None,
    claim_id: str,
    coverage_result: dict | None,
) -> list[WorkflowRecommendationHeadline]:
    if results_root is None:
        return []

    headlines: list[WorkflowRecommendationHeadline] = []
    for name, result in _iter_specialist_results(results_root, claim_id, coverage_result):
        headline = _headline_for(name, result)
        if headline is not None:
            headlines.append(headline)
    return headlines


def _iter_specialist_results(
    results_root: Path, claim_id: str, coverage_result: dict | None
):
    claim_dir = results_root / claim_id
    if not claim_dir.exists():
        return
    for path in sorted(claim_dir.glob("*.json")):
        name = path.stem
        if name == "coverage" and coverage_result is not None:
            yield name, coverage_result
        else:
            try:
                yield name, json.loads(path.read_text())
            except json.JSONDecodeError:
                continue


def _headline_for(name: str, result: dict) -> WorkflowRecommendationHeadline | None:
    """One-line summary from a specialist's persisted result.

    Conservative: if the result shape doesn't match anything we know,
    drop it rather than fabricate a headline.
    """
    if name not in ("coverage", "liability", "reserve", "recovery", "closure"):
        return None

    workflow: WorkflowName = name  # type: ignore[assignment]
    if name == "coverage":
        try:
            outcomes = result["synthesis"]["outcomes"]
            top = outcomes[0]
            headline = (
                f"Coverage clean probability {top['probability']:.0%} — "
                f"{top.get('outcome', 'see report')}"
            )
        except (KeyError, IndexError, TypeError):
            headline = "Coverage analysis available; details in result file"
    else:
        # Stub specialists or future shapes — short generic line.
        headline = result.get("status", f"{name} result available")

    return WorkflowRecommendationHeadline(
        workflow=workflow,
        agent_action_id=f"AA-{name}-{result.get('claim_id', 'unknown')}",
        headline=headline,
        awaiting_approval=False,
    )


# ---------------------------------------------------------------------------
# Gap detection — deterministic rules
# ---------------------------------------------------------------------------


def _detect_gaps(
    claim: Claim,
    documents: list[Document],
    coverage_result: dict | None,
    as_of: datetime,
) -> list[RawGap]:
    """Detect open questions for the claim by consulting the info map.

    Variable names are info-map question IDs (e.g., "Q-COV-001"). The
    requested_from party comes from the question's highest-fidelity
    source. Order is critical-path: perishable first, then longest
    cycle descending.

    `coverage_result` and `as_of` are accepted but unused — they were
    needed by the pre-info-map rule layer to surface a "coverage
    analysis stale" gap, which is an orchestrator concern, not an
    adjuster open question. Kept in the signature for callers that
    still pass them.
    """
    del coverage_result, as_of  # retained for caller compatibility
    citation_pool = tuple(d.document_id for d in documents)
    return [
        RawGap(
            variable=q.id,
            requested_from=q.sources[0].party,
            citation_doc_ids=citation_pool,
        )
        for q in detect_open_questions(claim, documents)
    ]


# ---------------------------------------------------------------------------
# Misc helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _loss_facts_hint(
    claim: Claim,
    request: CoverageRequest | None,
    documents: list[Document],
) -> str:
    """A deterministic context blob the narrative LLM call uses as input.

    Not a finished narrative — just structured facts the LLM stitches
    into prose. Keeps the LLM honest by giving it the source facts
    explicitly.
    """
    parts = [
        f"Claim {claim.claim_id} opened {claim.opened_date.isoformat()}.",
        f"Severity tier: {claim.severity_tier_summary}.",
        f"Status: {claim.status}.",
        f"Litigation flag: {claim.litigation_flag}; "
        f"represented: {claim.rep_flag}; "
        f"complaint flag: {claim.complaint_flag}.",
    ]
    if request:
        parts.append(
            f"Coverage request {request.request_id} on coverage_id "
            f"{request.coverage_id} (status: {request.coverage_status})."
        )
    if documents:
        doc_summary = ", ".join(
            f"{d.document_id} ({d.document_type})" for d in documents[:6]
        )
        parts.append(f"Documents on file: {doc_summary}.")
    else:
        parts.append("No documents on file yet.")
    return " ".join(parts)
