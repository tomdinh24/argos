"""Job model for the workflow orchestrator.

A `Job` is one unit of work the orchestrator routes to a workflow
runtime: "run Coverage on claim X because document Y materially changed
coverage posture." Jobs are persisted (JSON-on-disk) so a restart
doesn't lose pending work.

Status lifecycle:

    pending → running → done
                     ↓
                   failed

`triggered_by_doc_id` is the document whose Reader call surfaced the
material change. Together with `workflow + claim_id` it forms the
idempotency key — the dispatcher won't enqueue a duplicate job for
the same (workflow, claim, doc) triple.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass
class Job:
    """One workflow-run request."""

    workflow: str               # e.g., "coverage", "reserve", "liability"
    claim_id: str               # which claim this job is about
    triggered_by_doc_id: str    # which document surfaced the trigger
    posture_changed: str        # the Reader's posture call that triggered this
    job_id: str = field(default_factory=lambda: f"JOB-{uuid.uuid4().hex[:12]}")
    status: JobStatus = JobStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result_path: str | None = None       # path to persisted workflow output
    result_summary: str | None = None    # one-line summary for the audit log
    error: str | None = None             # populated on FAILED

    def idempotency_key(self) -> tuple[str, str, str]:
        return (self.workflow, self.claim_id, self.triggered_by_doc_id)

    def to_dict(self) -> dict:
        """JSON-safe dict for queue persistence."""
        return {
            "job_id": self.job_id,
            "workflow": self.workflow,
            "claim_id": self.claim_id,
            "triggered_by_doc_id": self.triggered_by_doc_id,
            "posture_changed": self.posture_changed,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "result_path": self.result_path,
            "result_summary": self.result_summary,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Job:
        return cls(
            job_id=d["job_id"],
            workflow=d["workflow"],
            claim_id=d["claim_id"],
            triggered_by_doc_id=d["triggered_by_doc_id"],
            posture_changed=d["posture_changed"],
            status=JobStatus(d["status"]),
            created_at=datetime.fromisoformat(d["created_at"]),
            started_at=datetime.fromisoformat(d["started_at"]) if d.get("started_at") else None,
            completed_at=datetime.fromisoformat(d["completed_at"]) if d.get("completed_at") else None,
            result_path=d.get("result_path"),
            result_summary=d.get("result_summary"),
            error=d.get("error"),
        )
