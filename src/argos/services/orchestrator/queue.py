"""JSON-backed in-memory job queue.

Single-process. Not thread-safe. Sufficient for the orchestrator demo
and for the per-adjuster runtime — each adjuster's caseload is small
enough that one queue per adjuster handles it. Multi-process / multi-
machine queueing is a v2 concern (Redis, SQS, etc.).

The queue persists to a JSON file on every mutating call so a crash
or restart doesn't lose pending work. Reads are from the in-memory
list. The persistence path is set at construction; pass `None` for a
purely in-memory queue (useful for tests).

Idempotency: `enqueue()` checks for an existing PENDING or RUNNING job
with the same `(specialist, claim_id, triggered_by_doc_id)` triple
before adding a new one. Done/failed jobs do not block new enqueues
on the same triple (a doc reprocessed after a failure can re-enqueue).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from argos.services.orchestrator.job import Job, JobStatus


class JobQueue:
    def __init__(self, persistence_path: Path | None = None):
        self.persistence_path = persistence_path
        self._jobs: list[Job] = []
        if persistence_path is not None and persistence_path.exists():
            self._load()

    # --- introspection ---

    def all_jobs(self) -> list[Job]:
        return list(self._jobs)

    def pending(self) -> list[Job]:
        return [j for j in self._jobs if j.status == JobStatus.PENDING]

    def by_status(self, status: JobStatus) -> list[Job]:
        return [j for j in self._jobs if j.status == status]

    def find_active(
        self, specialist: str, claim_id: str, triggered_by_doc_id: str
    ) -> Job | None:
        """Return an existing PENDING or RUNNING job with this triple,
        if one exists. Used by the dispatcher to enforce idempotency."""
        for j in self._jobs:
            if j.status not in (JobStatus.PENDING, JobStatus.RUNNING):
                continue
            if (
                j.specialist == specialist
                and j.claim_id == claim_id
                and j.triggered_by_doc_id == triggered_by_doc_id
            ):
                return j
        return None

    # --- mutation ---

    def enqueue(self, job: Job) -> Job:
        """Add `job` to the queue iff there's no active job with the same
        idempotency key. Returns the existing job if a duplicate is found,
        otherwise the newly-enqueued job."""
        existing = self.find_active(
            job.specialist, job.claim_id, job.triggered_by_doc_id
        )
        if existing is not None:
            return existing
        self._jobs.append(job)
        self._persist()
        return job

    def next_pending(self) -> Job | None:
        """FIFO. Returns the oldest PENDING job, or None if none."""
        for j in self._jobs:
            if j.status == JobStatus.PENDING:
                return j
        return None

    def mark_running(self, job_id: str) -> Job:
        job = self._get(job_id)
        job.status = JobStatus.RUNNING
        job.started_at = datetime.now(timezone.utc)
        self._persist()
        return job

    def mark_done(
        self,
        job_id: str,
        *,
        result_path: str | None = None,
        result_summary: str | None = None,
    ) -> Job:
        job = self._get(job_id)
        job.status = JobStatus.DONE
        job.completed_at = datetime.now(timezone.utc)
        job.result_path = result_path
        job.result_summary = result_summary
        self._persist()
        return job

    def mark_failed(self, job_id: str, error: str) -> Job:
        job = self._get(job_id)
        job.status = JobStatus.FAILED
        job.completed_at = datetime.now(timezone.utc)
        job.error = error
        self._persist()
        return job

    # --- internals ---

    def _get(self, job_id: str) -> Job:
        for j in self._jobs:
            if j.job_id == job_id:
                return j
        raise KeyError(f"No job with id {job_id!r}")

    def _persist(self) -> None:
        if self.persistence_path is None:
            return
        self.persistence_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"jobs": [j.to_dict() for j in self._jobs]}
        self.persistence_path.write_text(json.dumps(payload, indent=2))

    def _load(self) -> None:
        assert self.persistence_path is not None
        payload = json.loads(self.persistence_path.read_text())
        self._jobs = [Job.from_dict(d) for d in payload.get("jobs", [])]
