"""End-to-end orchestrator demo: Reader → dispatcher → queue → runner.

Walks the full pipeline on the extended N=20 fixture:

  1. Build extended caseload (with realistic doc bodies).
  2. Run the Document Reader on every unread doc (9 calls).
  3. Dispatch jobs from each relevant Reader call.
  4. Drain the queue with the WorkflowRunner.
  5. Show end state: jobs (status, summary), result files persisted.

For the only fully-built specialist (Coverage), this produces a real
CoverageReport on REQ-015 (the claim with a coverage-posture-changing
unread doc). For Reserve and Liability, the runner uses stubs that
record the work request — those specialists' runtimes don't exist yet.

Cost: ~9 Reader calls + 1 Coverage call ≈ $0.20.

Run:
    .venv/bin/python scripts/run_orchestrator_demo.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPO_ROOT / ".env")

from argos.ontology.caseload_with_realistic_docs import (  # noqa: E402
    build_caseload_with_realistic_docs,
)
from argos.services.orchestrator.dispatcher import dispatch  # noqa: E402
from argos.services.orchestrator.job import JobStatus  # noqa: E402
from argos.services.orchestrator.queue import JobQueue  # noqa: E402
from argos.services.orchestrator.runner import WorkflowRunner  # noqa: E402
from argos.services.triage.reader_integration import screen_caseload  # noqa: E402


DEMO_ROOT = REPO_ROOT / "data" / "orchestrator-demo"
QUEUE_PATH = DEMO_ROOT / "queue.json"
RESULTS_ROOT = DEMO_ROOT / "workflow-results"
RUN_LOG_PATH = DEMO_ROOT / "demo_run.json"


def main() -> int:
    DEMO_ROOT.mkdir(parents=True, exist_ok=True)
    # Fresh queue per run for the demo. Production wouldn't blow this
    # away; it'd let the queue accumulate across reader passes.
    if QUEUE_PATH.exists():
        QUEUE_PATH.unlink()

    print("=" * 76)
    print("ORCHESTRATOR DEMO — Reader → dispatcher → queue → runner")
    print("=" * 76)
    print()

    # --- Step 1: build the extended fixture ---
    caseload = build_caseload_with_realistic_docs()
    print(f"Fixture: {len(caseload.claims)} claims, {len(caseload.documents)} documents")
    print()

    # --- Step 2: run Reader on every unread doc ---
    print("Step 1: Running Document Reader on every unread doc...")
    print("-" * 76)
    screening = screen_caseload(caseload)
    print(f"  docs screened: {screening.docs_screened}")
    print(f"  relevant-doc counts: {screening.relevant_doc_counts}")
    print()

    # --- Step 3: dispatch jobs from each relevant Reader call ---
    print("Step 2: Dispatching jobs from each relevant Reader call...")
    print("-" * 76)
    queue = JobQueue(QUEUE_PATH)
    enqueued_audit = []
    for record in screening.call_records:
        jobs_for_call = dispatch(record.call, claim_id=record.claim_id)
        for job in jobs_for_call:
            stored = queue.enqueue(job)
            is_new = stored is job
            enqueued_audit.append({
                "from_doc": record.document_id,
                "claim_id": record.claim_id,
                "workflow": job.workflow,
                "posture_changed": job.posture_changed,
                "job_id": stored.job_id,
                "newly_enqueued": is_new,
            })
            mark = "+" if is_new else "="
            print(
                f"  {mark} {record.document_id} → enqueue {job.workflow:<10} "
                f"on {record.claim_id} (job_id={stored.job_id})"
            )
        if not jobs_for_call:
            print(f"    {record.document_id} → no dispatch (relevant={record.call.relevant})")
    print()
    print(f"  total jobs enqueued: {len(queue.pending())}")
    print()

    # --- Step 4: drain the queue ---
    print("Step 3: Running queue with WorkflowRunner...")
    print("-" * 76)
    runner = WorkflowRunner(queue=queue, caseload=caseload, results_root=RESULTS_ROOT)
    processed = runner.process_all()
    for job in processed:
        mark = "✓" if job.status == JobStatus.DONE else "✗"
        print(
            f"  {mark} {job.job_id} | {job.workflow:<10} on {job.claim_id}: "
            f"{job.status.value} — {job.result_summary or job.error}"
        )
    print()

    # --- Step 5: show end state ---
    print("Step 4: End state — persisted specialist results")
    print("-" * 76)
    if not RESULTS_ROOT.exists():
        print("  (no results directory)")
    else:
        result_files = sorted(RESULTS_ROOT.rglob("*.json"))
        for f in result_files:
            rel = f.relative_to(REPO_ROOT)
            size = f.stat().st_size
            print(f"  {rel}  ({size:,} bytes)")
    print()

    # --- Composite summary + persist ---
    n_done = sum(1 for j in processed if j.status == JobStatus.DONE)
    n_failed = sum(1 for j in processed if j.status == JobStatus.FAILED)
    print("=" * 76)
    print(
        f"SUMMARY: {screening.docs_screened} docs screened, "
        f"{len(queue.all_jobs())} jobs enqueued, "
        f"{n_done} done, {n_failed} failed"
    )
    print("=" * 76)

    # Audit log
    RUN_LOG_PATH.write_text(json.dumps({
        "run_timestamp": datetime.now(timezone.utc).isoformat(),
        "docs_screened": screening.docs_screened,
        "relevant_doc_counts": screening.relevant_doc_counts,
        "enqueued": enqueued_audit,
        "processed": [
            {
                "job_id": j.job_id,
                "workflow": j.workflow,
                "claim_id": j.claim_id,
                "triggered_by_doc_id": j.triggered_by_doc_id,
                "posture_changed": j.posture_changed,
                "status": j.status.value,
                "result_path": j.result_path,
                "result_summary": j.result_summary,
                "error": j.error,
            }
            for j in processed
        ],
    }, indent=2))
    print(f"wrote {RUN_LOG_PATH.relative_to(REPO_ROOT)}")

    return 0 if n_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
