"""Cockpit-facing FastAPI surface.

Thin wrappers around the existing orchestrator + workflow runner. State
lives in-process: a Caseload loaded once at startup, workflow results
written to `data/workflow-results/{claim_id}/{workflow}.json`, and an
audit log under `data/agent-actions/`.

This is the demo-friendly path. Production deployment will replace the
in-process Caseload with the Foundry projection (per
SYSTEM_ARCHITECTURE §2) — the wire shapes in `schemas.py` are the
contract that survives that swap.

Auth: bearer token via `ARGOS_DEMO_TOKEN` env var. If unset, no auth is
enforced (local dev). CORS allows `NEXT_PUBLIC_API_BASE` consumers.
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from pathlib import Path
from typing import Annotated

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

# Load .env early so ANTHROPIC_API_KEY + ARGOS_* are visible to workflows.
load_dotenv()

from argos.api.mappers import (
    WORKFLOW_CHAIN,
    _pending_rec_from_result,
    iter_open_claims,
    to_claim_detail,
    to_claim_summary,
    to_dashboard_metrics,
)
from argos.api.schemas import (
    ClaimDetail,
    ClaimSummary,
    DashboardMetrics,
    DecisionRequest,
    DecisionResponse,
    ExampleClaim,
    PendingRecommendation,
    SeedClaimRequest,
    WorkflowName,
)
from argos.ontology.cockpit_caseload import build_cockpit_caseload
from argos.ontology.types import Caseload
from argos.services.orchestrator.audit_log import (
    VALIDATOR_FAIL,
    VALIDATOR_PASS,
    append_agent_action,
    build_agent_action,
)
from argos.services.orchestrator.coverage_actions import apply_coverage_decision
from argos.services.orchestrator.reserve_actions import apply_reserve_decision
from argos.services.orchestrator.liability_actions import apply_liability_decision
from argos.services.orchestrator.recovery_actions import apply_recovery_decision
from argos.services.orchestrator.closure_actions import (
    apply_closure_decision,
    apply_reopen_decision,
)
from argos.services.orchestrator.job import Job, JobStatus
from argos.services.orchestrator.queue import JobQueue
from argos.services.orchestrator.runner import WorkflowRunner

log = logging.getLogger(__name__)

app = FastAPI(title="Argos API", version="0.1.0")

# Cockpit local dev (Next defaults to 3000; this repo's dev server runs on
# 3007) + the Vercel-hosted cockpit. Public demo URL is argos-claims.vercel.app;
# web-beryl-one-98 is Vercel's auto-assigned alias for the same project (kept as
# a fallback). Add more origins per environment via ARGOS_CORS_EXTRA.
_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:3007",
    "https://argos-claims.vercel.app",
    "https://web-beryl-one-98.vercel.app",
]
_extra = os.environ.get("ARGOS_CORS_EXTRA", "").split(",")
_ALLOWED_ORIGINS.extend(o.strip() for o in _extra if o.strip())

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


# --- shared state -----------------------------------------------------------

DATA_ROOT = Path(os.environ.get("ARGOS_DATA_ROOT", "data"))
RESULTS_ROOT = DATA_ROOT / "workflow-results"
AUDIT_LOG_ROOT = DATA_ROOT / "agent-actions"
RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
AUDIT_LOG_ROOT.mkdir(parents=True, exist_ok=True)


def _build_state() -> dict:
    caseload = build_cockpit_caseload()
    queue = JobQueue()
    runner = WorkflowRunner(
        queue=queue,
        caseload=caseload,
        results_root=RESULTS_ROOT,
        audit_log_root=AUDIT_LOG_ROOT,
    )
    return {"caseload": caseload, "queue": queue, "runner": runner}


_STATE = _build_state()


def get_caseload() -> Caseload:
    return _STATE["caseload"]


def get_runner() -> WorkflowRunner:
    return _STATE["runner"]


def get_queue() -> JobQueue:
    return _STATE["queue"]


def _set_caseload(caseload: Caseload) -> None:
    """Persist a post-decision caseload back into shared state. The
    `apply_*_decision` handlers return a NEW immutable Caseload, so the
    in-process state (and the runner's view of it) must be replaced or the
    commit would be invisible to the next GET."""
    _STATE["caseload"] = caseload
    _STATE["runner"].caseload = caseload


# --- decision routing -------------------------------------------------------

_REOPEN_REASONS = {
    "post_close_demand",
    "post_close_lien_surfaced",
    "post_close_cms_final_demand",
    "post_close_litigation_filed",
    "material_new_information",
}


def _result_field(workflow: str, claim_id: str, field: str) -> str | None:
    """Pull a top-level field from a persisted workflow result, or None."""
    p = RESULTS_ROOT / claim_id / f"{workflow}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text()).get(field)
    except (json.JSONDecodeError, OSError):
        return None


def _coverage_posture_from_result(claim_id: str) -> str | None:
    """Map the coverage workflow's top verdict to a CoveragePosture literal."""
    p = RESULTS_ROOT / claim_id / "coverage.json"
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    outcomes = data.get("synthesis", {}).get("outcomes", []) or []
    if not outcomes:
        return None
    top = max(outcomes, key=lambda o: o.get("probability", 0))
    label = (top.get("claim_text", "") or "").lower()
    if "denial" in label or "deny" in label:
        return "denied"
    if "reservation" in label or "ror" in label:
        return "ROR_issued"
    if "clean" in label or "accept" in label:
        return "accepted"
    return None


def _commit_via_handler(caseload: Caseload, claim_id: str, req: DecisionRequest) -> Caseload:
    """Route an approved/modified decision to the matching orchestrator
    action handler. The handler commits the Pydantic-side mutation AND fires
    the workflow's Foundry bridge (gated by ARGOS_FOUNDRY_BRIDGE_ENABLED).

    We deliberately pass NO `audit_log_root` — the human-decision audit row is
    written once by `record_decision` (which also mirrors an AgentAction to
    Foundry). v1 commits the recommended value from the persisted result;
    `outcome="modified"` is treated as a soft-approve of that value.

    A handler that rejects the commit (bad transition, blocked closure, a
    routing-only recovery flag) raises ValueError — caught here so the decision
    is still logged and the chain still advances; the commit just no-ops."""
    wf = req.workflow
    rid = req.recommendation_id
    try:
        if wf == "coverage":
            posture = _coverage_posture_from_result(claim_id)
            if posture is None:
                log.warning("coverage commit skipped: no posture from result (%s)", claim_id)
                return caseload
            return apply_coverage_decision(
                caseload, claim_id, new_posture=posture, source_recommendation_id=rid,  # type: ignore[arg-type]
            )
        if wf == "reserve":
            return apply_reserve_decision(caseload, claim_id, accept=True, source_assessment_id=rid)
        if wf == "liability":
            return apply_liability_decision(caseload, claim_id, accept=True, source_assessment_id=rid)
        if wf == "recovery":
            decision = _result_field("recovery", claim_id, "recommendation")
            if not decision or decision == "senior_review_required":
                log.warning("recovery commit skipped: decision=%r (%s)", decision, claim_id)
                return caseload
            return apply_recovery_decision(
                caseload, claim_id, decision=decision, source_assessment_id=rid,  # type: ignore[arg-type]
            )
        if wf == "closure":
            rec = _result_field("closure", claim_id, "recommendation")
            if not rec:
                log.warning("closure commit skipped: no recommendation (%s)", claim_id)
                return caseload
            return apply_closure_decision(
                caseload, claim_id, recommendation=rec, source_assessment_id=rid,  # type: ignore[arg-type]
            )
        if wf == "reopen":
            reason = req.reason if req.reason in _REOPEN_REASONS else "material_new_information"
            return apply_reopen_decision(
                caseload, claim_id, reopen_reason=reason, source_assessment_id=rid,  # type: ignore[arg-type]
            )
    except ValueError as exc:
        log.warning("decision handler rejected commit (%s/%s): %s", wf, claim_id, exc)
    return caseload


# --- auth -------------------------------------------------------------------

def require_token(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> None:
    """Bearer token check. Skipped entirely when ARGOS_DEMO_TOKEN is unset
    (local dev). On Railway/Vercel, set ARGOS_DEMO_TOKEN and the cockpit's
    NEXT_PUBLIC_DEMO_TOKEN to the same value."""
    expected = os.environ.get("ARGOS_DEMO_TOKEN")
    if not expected:
        return
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    if authorization.removeprefix("Bearer ").strip() != expected:
        raise HTTPException(status_code=401, detail="Invalid bearer token")


# --- endpoints --------------------------------------------------------------

@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/claims", response_model=list[ClaimSummary])
def list_claims(
    _auth: None = Depends(require_token),
    caseload: Caseload = Depends(get_caseload),
) -> list[ClaimSummary]:
    """All open claims, sorted by triage band (red → amber → green)."""
    rows = [to_claim_summary(c, caseload, RESULTS_ROOT, AUDIT_LOG_ROOT) for c in iter_open_claims(caseload)]
    band_order = {"red": 0, "amber": 1, "green": 2}
    rows.sort(key=lambda r: (band_order[r.triage_band], r.reported_at), reverse=False)
    return rows[:10]  # cockpit shows top N


@app.get("/api/claims/{claim_id}", response_model=ClaimDetail)
def get_claim(
    claim_id: str,
    _auth: None = Depends(require_token),
    caseload: Caseload = Depends(get_caseload),
) -> ClaimDetail:
    claim = next((c for c in caseload.claims if c.claim_id == claim_id), None)
    if claim is None:
        raise HTTPException(status_code=404, detail=f"Claim {claim_id} not found")
    return to_claim_detail(claim, caseload, RESULTS_ROOT, AUDIT_LOG_ROOT)


@app.post("/api/claims/{claim_id}/run/{workflow}", response_model=PendingRecommendation | None)
def run_workflow(
    claim_id: str,
    workflow: WorkflowName,
    _auth: None = Depends(require_token),
    caseload: Caseload = Depends(get_caseload),
    runner: WorkflowRunner = Depends(get_runner),
    queue: JobQueue = Depends(get_queue),
) -> PendingRecommendation | None:
    """Run a single workflow against a claim, synchronously. Returns the
    fresh pending recommendation derived from the persisted result.

    This is the hot path for the cockpit — clicking into a claim with no
    cached result for the active stage fires this to materialize one.
    Latency = the workflow's LLM round-trips (typically a few seconds)."""
    if workflow not in WORKFLOW_CHAIN and workflow != "brief":
        raise HTTPException(status_code=400, detail=f"Unknown workflow {workflow}")
    claim = next((c for c in caseload.claims if c.claim_id == claim_id), None)
    if claim is None:
        raise HTTPException(status_code=404, detail=f"Claim {claim_id} not found")

    job = queue.enqueue(Job(
        workflow=workflow,
        claim_id=claim_id,
        triggered_by_doc_id="cockpit",
        posture_changed="manual_run",
    ))
    runner.process_one()  # drains exactly this job (queue is single-threaded)
    final = next((j for j in queue.all_jobs() if j.job_id == job.job_id), None)
    if final is None or final.status != JobStatus.DONE:
        raise HTTPException(
            status_code=500,
            detail=f"Workflow {workflow} failed: {final.error if final else 'no result'}",
        )

    # Surface the rec for the workflow we just ran (not next_workflow, which
    # has already advanced now that {workflow}.json exists on disk).
    return _pending_rec_from_result(
        workflow, RESULTS_ROOT / claim_id / f"{workflow}.json",
    )


@app.post("/api/claims/{claim_id}/decisions", response_model=DecisionResponse)
def record_decision(
    claim_id: str,
    req: DecisionRequest,
    _auth: None = Depends(require_token),
    caseload: Caseload = Depends(get_caseload),
) -> DecisionResponse:
    """Log a human decision (approve/modify/reject) on a pending recommendation.

    Approving advances the chain (the next workflow becomes the cockpit's
    active stage). Rejecting holds the stage open. Modify is treated as a
    soft-approve — the final_title carries the modified text/amount."""
    claim = next((c for c in caseload.claims if c.claim_id == claim_id), None)
    if claim is None:
        raise HTTPException(status_code=404, detail=f"Claim {claim_id} not found")

    decision_id = f"DEC-{uuid.uuid4().hex[:10]}"
    # Canonical human-decision audit row. append_agent_action writes the local
    # JSONL AND (when the bridge flag is on) mirrors an AgentAction into the
    # Foundry ontology — this is the row that proves "a human decided".
    append_agent_action(
        build_agent_action(
            claim_id=claim_id,
            workflow=req.workflow,
            action_type=VALIDATOR_PASS if req.outcome != "rejected" else VALIDATOR_FAIL,
            summary=(
                f"{req.outcome}: {req.final_title}"
                + (f" (reason: {req.reason})" if req.reason else "")
            ),
            success=req.outcome != "rejected",
        ),
        log_root=AUDIT_LOG_ROOT,
    )

    # On approve/modify, commit the decision through the orchestrator action
    # handler (mutates the claim + fires the workflow's Foundry bridge), then
    # persist the new caseload so the next read reflects it. Rejection holds
    # the stage open and commits nothing.
    next_wf: WorkflowName | None = None
    if req.outcome in {"approved", "modified"}:
        new_caseload = _commit_via_handler(caseload, claim_id, req)
        if new_caseload is not caseload:
            _set_caseload(new_caseload)
        idx = WORKFLOW_CHAIN.index(req.workflow) if req.workflow in WORKFLOW_CHAIN else -1
        if 0 <= idx < len(WORKFLOW_CHAIN) - 1:
            next_wf = WORKFLOW_CHAIN[idx + 1]

    return DecisionResponse(ok=True, decision_id=decision_id, next_workflow=next_wf)


@app.get("/api/metrics", response_model=DashboardMetrics)
def get_metrics(
    _auth: None = Depends(require_token),
    caseload: Caseload = Depends(get_caseload),
) -> DashboardMetrics:
    return to_dashboard_metrics(caseload, RESULTS_ROOT, AUDIT_LOG_ROOT)


@app.get("/api/demo/examples", response_model=list[ExampleClaim])
def list_examples(
    _auth: None = Depends(require_token),
    caseload: Caseload = Depends(get_caseload),
) -> list[ExampleClaim]:
    """Pull a small set of fixture claims that haven't been seeded yet, so
    the cockpit's "Add example claim" sheet shows real options from the
    synthetic caseload."""
    seen = {p.name for p in RESULTS_ROOT.glob("*") if p.is_dir()}
    examples: list[ExampleClaim] = []
    for claim in iter_open_claims(caseload):
        if claim.claim_id in seen:
            continue
        summary = to_claim_summary(claim, caseload, RESULTS_ROOT)
        examples.append(ExampleClaim(
            example_id=claim.claim_id,
            label=summary.insured_name,
            loss_type=summary.loss_type,
            triage_band=summary.triage_band,
            description=summary.rationale,
        ))
        if len(examples) >= 6:
            break
    return examples


@app.post("/api/demo/seed-claim", response_model=ClaimSummary)
def seed_claim(
    req: SeedClaimRequest,
    _auth: None = Depends(require_token),
    caseload: Caseload = Depends(get_caseload),
    runner: WorkflowRunner = Depends(get_runner),
    queue: JobQueue = Depends(get_queue),
) -> ClaimSummary:
    """Pick a synthetic claim, run its first workflow (coverage) so the
    cockpit sees a fresh draft, return the now-live summary."""
    claim = next((c for c in caseload.claims if c.claim_id == req.example_id), None)
    if claim is None:
        raise HTTPException(status_code=404, detail=f"No example {req.example_id}")
    # Run coverage to materialize the first draft on disk.
    job = queue.enqueue(Job(
        workflow="coverage",
        claim_id=claim.claim_id,
        triggered_by_doc_id="seed",
        posture_changed="manual_seed",
    ))
    runner.process_one()
    final = next((j for j in queue.all_jobs() if j.job_id == job.job_id), None)
    if final is None or final.status != JobStatus.DONE:
        log.warning("seed_claim coverage failed for %s: %s",
                    claim.claim_id, final.error if final else "no result")
    return to_claim_summary(claim, caseload, RESULTS_ROOT)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    response = await call_next(request)
    log.info("%s %s → %d", request.method, request.url.path, response.status_code)
    return response
