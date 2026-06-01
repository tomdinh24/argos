"""Specialist runner: consumes Jobs from a JobQueue, calls the right
specialist, persists the result.

Single-threaded. `process_one()` pulls the next pending job and runs
it inline. `process_all()` drains the queue. There's no background
daemon — orchestrator invocations are explicit.

Specialists are looked up by name via the `SPECIALIST_REGISTRY`. Each
entry is a callable with signature
`(Caseload, claim_id) -> tuple[str, dict]` returning
`(result_summary, serialized_result)`. The runner persists the
serialized_result to `data/specialist-results/{claim_id}/{specialist}.json`.

Specialists not yet implemented (Reserve, Liability) are registered as
no-op stubs that mark the job done with a summary noting the missing
implementation. This keeps the dispatcher honest — it can enqueue
jobs for postures whose specialists don't yet exist, and the runner
records that fact instead of silently swallowing the work.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Callable

from argos.ontology.types import Caseload
from argos.services.orchestrator.adapter import caseload_to_synthetic_claim
from argos.services.orchestrator.job import Job, JobStatus
from argos.services.orchestrator.queue import JobQueue
from argos.specialists.coverage import run_coverage


SpecialistResult = tuple[str, dict]
"""(result_summary, serialized_result_dict)"""

SpecialistFn = Callable[[Caseload, str], SpecialistResult]


# ---------------------------------------------------------------------------
# Registered specialists
# ---------------------------------------------------------------------------


def _run_coverage_via_adapter(caseload: Caseload, claim_id: str) -> SpecialistResult:
    """Real Coverage call through the Caseload→SyntheticClaim adapter."""
    synth = caseload_to_synthetic_claim(caseload, claim_id)
    result = run_coverage(synth)
    summary = (
        f"Coverage analysis for {claim_id}: "
        f"clean={result.analysis.synthesis.outcomes[0].probability:.2f}, "
        f"attempts={result.attempts}"
    )
    return summary, result.analysis.model_dump(mode="json")


def _stub_specialist(name: str) -> SpecialistFn:
    """Build a stub for a specialist whose runtime doesn't exist yet.

    The stub records the work request but does not perform analysis.
    Returning success here is honest: the dispatcher correctly enqueued
    a job; the gap is the missing specialist implementation, captured in
    the result_summary.
    """
    def stub(caseload: Caseload, claim_id: str) -> SpecialistResult:
        summary = (
            f"[stub] {name} specialist not yet implemented; "
            f"job recorded for {claim_id}"
        )
        return summary, {
            "specialist": name,
            "claim_id": claim_id,
            "status": "not_implemented",
        }
    return stub


SPECIALIST_REGISTRY: dict[str, SpecialistFn] = {
    "coverage": _run_coverage_via_adapter,
    "reserve": _stub_specialist("reserve"),
    "liability": _stub_specialist("liability"),
}


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


class SpecialistRunner:
    def __init__(
        self,
        queue: JobQueue,
        caseload: Caseload,
        results_root: Path,
        registry: dict[str, SpecialistFn] | None = None,
    ):
        self.queue = queue
        self.caseload = caseload
        self.results_root = results_root
        self.registry = registry or SPECIALIST_REGISTRY

    def process_one(self) -> Job | None:
        """Process the next pending job, if any. Returns the job
        (whatever its final state). Returns None when the queue is
        drained."""
        job = self.queue.next_pending()
        if job is None:
            return None

        self.queue.mark_running(job.job_id)

        fn = self.registry.get(job.specialist)
        if fn is None:
            self.queue.mark_failed(
                job.job_id,
                f"No specialist registered under name {job.specialist!r}",
            )
            return self.queue.next_pending() and job or job  # return updated job

        try:
            summary, result_dict = fn(self.caseload, job.claim_id)
        except Exception as e:  # noqa: BLE001  — surface any specialist failure
            self.queue.mark_failed(job.job_id, f"{type(e).__name__}: {e}")
            return job

        # Persist result
        result_path = (
            self.results_root / job.claim_id / f"{job.specialist}.json"
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
