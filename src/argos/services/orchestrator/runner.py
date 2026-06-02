"""Workflow runner: consumes Jobs from a JobQueue, calls the right
workflow, persists the result.

Single-threaded. `process_one()` pulls the next pending job and runs
it inline. `process_all()` drains the queue. There's no background
daemon — orchestrator invocations are explicit.

Workflows are looked up by name via the `WORKFLOW_REGISTRY`. Each
entry is a callable with signature
`(Caseload, claim_id) -> tuple[str, dict]` returning
`(result_summary, serialized_result)`. The runner persists the
serialized_result to `data/workflow-results/{claim_id}/{workflow}.json`.

Workflows not yet implemented (Reserve, Liability) are registered as
no-op stubs that mark the job done with a summary noting the missing
implementation. This keeps the dispatcher honest — it can enqueue
jobs for postures whose workflows don't yet exist, and the runner
records that fact instead of silently swallowing the work.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from argos.ontology.types import Caseload
from argos.services.orchestrator.adapter import caseload_to_synthetic_claim
from argos.services.orchestrator.job import Job
from argos.services.orchestrator.queue import JobQueue
from argos.workflows.brief.brief import run_brief
from argos.workflows.coverage import run_coverage
from argos.schemas.workflows.recovery import (
    RecoveryUpstreamContext,
    UpstreamCoverageSnapshot,
    UpstreamLiabilitySnapshot,
    UpstreamReserveSnapshot,
)
from argos.workflows.liability import run_liability
from argos.workflows.recovery import run_recovery
from argos.workflows.reserve import run_reserve


WorkflowResult = tuple[str, dict]
"""(result_summary, serialized_result_dict)"""

WorkflowFn = Callable[[Caseload, str], WorkflowResult]


# ---------------------------------------------------------------------------
# Registered workflows
# ---------------------------------------------------------------------------


def _run_coverage_via_adapter(caseload: Caseload, claim_id: str) -> WorkflowResult:
    """Real Coverage call through the Caseload→SyntheticClaim adapter."""
    synth = caseload_to_synthetic_claim(caseload, claim_id)
    result = run_coverage(synth)
    summary = (
        f"Coverage analysis for {claim_id}: "
        f"clean={result.analysis.synthesis.outcomes[0].probability:.2f}, "
        f"attempts={result.attempts}"
    )
    return summary, result.analysis.model_dump(mode="json")


def _run_reserve_via_adapter(caseload: Caseload, claim_id: str) -> WorkflowResult:
    """Real Reserve call: extractor → calculator → templated rationale."""
    synth = caseload_to_synthetic_claim(caseload, claim_id)
    claim_meta = next(
        (c for c in caseload.claims if c.claim_id == claim_id), None,
    )
    result = run_reserve(synth, claim_meta=claim_meta)
    indem_central = next(
        (c.recommended_outstanding_band.p50 for c in result.analysis.per_component
         if c.component == "indemnity"),
        0.0,
    )
    notice_count = len(result.analysis.notice_obligations_triggered)
    summary = (
        f"Reserve for {claim_id}: indemnity p50=${indem_central:,.0f}, "
        f"authority={result.analysis.authority_required_level}, "
        f"notices={notice_count}, "
        f"no_change={result.analysis.no_change_warranted}, "
        f"extractor_attempts={result.extractor_attempts}"
    )
    return summary, result.analysis.model_dump(mode="json")


def _run_liability_via_adapter(caseload: Caseload, claim_id: str) -> WorkflowResult:
    """Real Liability call: extractor → policy engine → calculator → ledger →
    templated rationale."""
    synth = caseload_to_synthetic_claim(caseload, claim_id)
    claim_meta = next(
        (c for c in caseload.claims if c.claim_id == claim_id), None,
    )
    result = run_liability(synth, claim_meta=claim_meta)
    insured_id = next(
        (
            pid
            for pid, ap in result.assessment.apportionment.items()
            if pid.startswith("P-insured") or "insured" in pid.lower()
        ),
        next(iter(result.assessment.apportionment), None),
    )
    insured_pct = (
        result.assessment.apportionment[insured_id].fault_pct
        if insured_id is not None else "n/a"
    )
    summary = (
        f"Liability for {claim_id}: insured_fault={insured_pct}%, "
        f"regime={result.assessment.applicable_regime.statute}, "
        f"bar_basis={result.assessment.applicable_regime.bar_basis}, "
        f"variance_flags={len(result.assessment.variance_flags)}, "
        f"authority={result.assessment.authority_tier_required.required_tier}, "
        f"extractor_attempts={result.extractor_attempts}"
    )
    return summary, result.assessment.model_dump(mode="json")


def _load_recovery_upstream(
    results_root: Path, claim_id: str,
) -> RecoveryUpstreamContext:
    """Load Liability/Reserve/Coverage results from prior runs into the
    small typed snapshots Recovery consumes. Each snapshot is optional —
    missing prior runs degrade gracefully (the policy engine and
    calculator treat None as "no upstream signal")."""
    liability_snap: UpstreamLiabilitySnapshot | None = None
    reserve_snap: UpstreamReserveSnapshot | None = None
    coverage_snap: UpstreamCoverageSnapshot | None = None

    claim_dir = results_root / claim_id

    lia_path = claim_dir / "liability.json"
    if lia_path.exists():
        try:
            data = json.loads(lia_path.read_text())
            apport = data.get("apportionment", {}) or {}
            apport_pct = {
                pid: a.get("fault_pct", 0) for pid, a in apport.items()
            }
            regime = data.get("applicable_regime", {}) or {}
            liability_snap = UpstreamLiabilitySnapshot(
                apportionment_by_party_id=apport_pct,
                regime_statute=regime.get("statute", "unknown"),
                recovery_bar_triggered=bool(regime.get("bar_basis")),
                bar_basis=regime.get("bar_basis", "none"),
            )
        except (json.JSONDecodeError, KeyError, TypeError):
            pass

    res_path = claim_dir / "reserve.json"
    if res_path.exists():
        try:
            data = json.loads(res_path.read_text())
            paid = {}
            outstanding = {}
            for c in data.get("per_component", []) or []:
                paid[c["component"]] = c.get("paid_to_date", 0)
                outstanding[c["component"]] = (
                    c.get("recommended_outstanding_band", {}).get("p50", 0)
                )
            reserve_snap = UpstreamReserveSnapshot(
                paid_indemnity_by_component=paid,
                outstanding_indemnity_by_component=outstanding,
            )
        except (json.JSONDecodeError, KeyError, TypeError):
            pass

    cov_path = claim_dir / "coverage.json"
    if cov_path.exists():
        try:
            data = json.loads(cov_path.read_text())
            outcomes = data.get("synthesis", {}).get("outcomes", []) or []
            clean_prob = outcomes[0].get("probability", 1.0) if outcomes else 1.0
            status = "granted" if clean_prob >= 0.5 else "under_investigation"
            coverage_snap = UpstreamCoverageSnapshot(status=status)
        except (json.JSONDecodeError, KeyError, TypeError, IndexError):
            pass

    return RecoveryUpstreamContext(
        liability=liability_snap,
        reserve=reserve_snap,
        coverage=coverage_snap,
    )


def _make_recovery_runner(results_root: Path) -> WorkflowFn:
    """Build a Recovery workflow closure that knows where to read upstream
    Liability/Reserve/Coverage results from. Recovery depends on the
    upstream snapshots for layered targets and bar evaluation; missing
    snapshots degrade to a conservative recommendation."""
    def run(caseload: Caseload, claim_id: str) -> WorkflowResult:
        synth = caseload_to_synthetic_claim(caseload, claim_id)
        claim_meta = next(
            (c for c in caseload.claims if c.claim_id == claim_id), None,
        )
        upstream = _load_recovery_upstream(results_root, claim_id)
        result = run_recovery(synth, upstream=upstream, claim_meta=claim_meta)
        summary = (
            f"Recovery for {claim_id}: recommendation={result.assessment.recommendation}, "
            f"lane={result.assessment.subrogation_lane.lane_id}, "
            f"forum={result.assessment.forum_routing.recommendation}, "
            f"net=${result.assessment.net_economics.net_total:,.0f}, "
            f"variance_flags={len(result.assessment.variance_flags)}, "
            f"authority={result.assessment.authority_tier_required.required_tier}, "
            f"extractor_attempts={result.extractor_attempts}"
        )
        return summary, result.assessment.model_dump(mode="json")
    return run


def _make_brief_runner(results_root: Path) -> WorkflowFn:
    """Build a Brief workflow closure that knows where to read other
    workflows' results from. Brief is a read-only assembler, so it
    needs the results_root to find Coverage/Liability/Reserve output
    if they've been written for this claim.
    """
    def run(caseload: Caseload, claim_id: str) -> WorkflowResult:
        result = run_brief(caseload, claim_id, results_root=results_root)
        summary = (
            f"Brief assembled for {claim_id}: "
            f"{len(result.brief.story_paragraph.split())}-word narrative, "
            f"{len(result.brief.missing_info)} open gaps, "
            f"{len(result.brief.workflow_recommendations_summary)} workflow results consumed"
        )
        return summary, result.brief.model_dump(mode="json")
    return run


def _stub_workflow(name: str) -> WorkflowFn:
    """Build a stub for a workflow whose runtime doesn't exist yet.

    The stub records the work request but does not perform analysis.
    Returning success here is honest: the dispatcher correctly enqueued
    a job; the gap is the missing workflow implementation, captured in
    the result_summary.
    """
    def stub(caseload: Caseload, claim_id: str) -> WorkflowResult:
        summary = (
            f"[stub] {name} workflow not yet implemented; "
            f"job recorded for {claim_id}"
        )
        return summary, {
            "workflow": name,
            "claim_id": claim_id,
            "status": "not_implemented",
        }
    return stub


WORKFLOW_REGISTRY: dict[str, WorkflowFn] = {
    "coverage": _run_coverage_via_adapter,
    "reserve": _run_reserve_via_adapter,
    "liability": _run_liability_via_adapter,
}


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


class WorkflowRunner:
    def __init__(
        self,
        queue: JobQueue,
        caseload: Caseload,
        results_root: Path,
        registry: dict[str, WorkflowFn] | None = None,
    ):
        self.queue = queue
        self.caseload = caseload
        self.results_root = results_root
        if registry is None:
            # Brief needs the results_root bound in; build a per-instance
            # registry on top of the static default.
            registry = {
                **WORKFLOW_REGISTRY,
                "recovery": _make_recovery_runner(results_root),
                "brief": _make_brief_runner(results_root),
            }
        self.registry = registry

    def process_one(self) -> Job | None:
        """Process the next pending job, if any. Returns the job
        (whatever its final state). Returns None when the queue is
        drained."""
        job = self.queue.next_pending()
        if job is None:
            return None

        self.queue.mark_running(job.job_id)

        fn = self.registry.get(job.workflow)
        if fn is None:
            self.queue.mark_failed(
                job.job_id,
                f"No workflow registered under name {job.workflow!r}",
            )
            return self.queue.next_pending() and job or job  # return updated job

        try:
            summary, result_dict = fn(self.caseload, job.claim_id)
        except Exception as e:  # noqa: BLE001  — surface any workflow failure
            self.queue.mark_failed(job.job_id, f"{type(e).__name__}: {e}")
            return job

        # Persist result
        result_path = (
            self.results_root / job.claim_id / f"{job.workflow}.json"
        )
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(json.dumps(result_dict, indent=2, default=str))

        self.queue.mark_done(
            job.job_id,
            result_path=str(result_path),
            result_summary=summary,
        )
        return job

    def process_all(self) -> list[Job]:
        """Drain the queue. Returns the list of processed jobs (in order
        processed)."""
        processed: list[Job] = []
        while True:
            job = self.process_one()
            if job is None:
                break
            processed.append(job)
        return processed
