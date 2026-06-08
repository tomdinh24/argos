"""Pre-run the 5-stage workflow chain for cockpit demo claims.

The cockpit detail page (`to_dossier`, `src/argos/api/mappers.py`) renders
*nothing* until a claim has committed workflow results on disk — `coverage.json`
is the gate, the other four stages enrich. Only the heroes wired up by hand
(CLM-001, CLM-004) ship with full chains; every other claim opens to the empty
state.

This harness runs the *real* chain (coverage → reserve → liability → recovery →
closure) through the same `WorkflowRunner` / `WORKFLOW_REGISTRY` the live API
uses, writing each result to `data/workflow-results/<claim>/<workflow>.json` and
the matching `analysis_emitted` rows to `data/agent-actions/<claim>.jsonl`. That
is byte-for-byte the state the two existing heroes are in, so freshly pre-run
claims render identically.

It is the missing piece the orchestrator demo doesn't cover:
`run_orchestrator_demo.py` writes to a throwaway dir and stubs the non-coverage
workflows; this writes to the canonical `ARGOS_DATA_ROOT` with the real runtimes.

Caseload source is `build_cockpit_caseload()` — the eval-safe wrapper — so the
documents the workflows cite are the cockpit's enriched bundles (hero injury
docs, the new property / ambiguous-coverage bundles), not the bare triage
fixture.

Determinism: the policy engines + calculators are deterministic; only the
per-workflow LLM extractor is stochastic (1 retry). Re-running a claim wipes its
prior results + audit rows first so the on-disk state is the latest run, not an
accreting pile.

Usage (needs ANTHROPIC_API_KEY in .env — the workflows make live LLM calls):

    .venv/bin/python scripts/prerun_cockpit_chains.py                 # all targets
    .venv/bin/python scripts/prerun_cockpit_chains.py CLM-007 CLM-009 # subset
    .venv/bin/python scripts/prerun_cockpit_chains.py CLM-008 --stages coverage,reserve

Cost: each full chain ≈ 5 LLM extractor calls (~15-20s/stage observed).
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPO_ROOT / ".env")

from argos.ontology.cockpit_caseload import build_cockpit_caseload  # noqa: E402
from argos.services.orchestrator.job import Job, JobStatus  # noqa: E402
from argos.services.orchestrator.queue import JobQueue  # noqa: E402
from argos.services.orchestrator.runner import WorkflowRunner  # noqa: E402

# The cockpit reads from ARGOS_DATA_ROOT (default "data"); mirror that exactly so
# what we write is what the live API serves.
import os  # noqa: E402

DATA_ROOT = REPO_ROOT / os.environ.get("ARGOS_DATA_ROOT", "data")
RESULTS_ROOT = DATA_ROOT / "workflow-results"
AUDIT_LOG_ROOT = DATA_ROOT / "agent-actions"

# Same chain the cockpit walks (mappers.WORKFLOW_CHAIN). Brief is a separate
# read-only assembler the dossier doesn't require.
WORKFLOW_CHAIN = ["coverage", "reserve", "liability", "recovery", "closure"]

# Default target set: the three empty red-band top rows the data strategy fills.
DEFAULT_TARGETS = ["CLM-007", "CLM-008", "CLM-009"]


def _reset_claim(claim_id: str) -> None:
    """Drop any prior results + audit rows for a claim so a re-run is clean."""
    results_dir = RESULTS_ROOT / claim_id
    if results_dir.exists():
        shutil.rmtree(results_dir)
    audit_file = AUDIT_LOG_ROOT / f"{claim_id}.jsonl"
    if audit_file.exists():
        audit_file.unlink()


def prerun_claim(
    runner: WorkflowRunner, claim_id: str, stages: list[str]
) -> list[Job]:
    """Enqueue + drain the chain (in order) for one claim. Recovery/Closure read
    their upstream snapshots from disk, so order matters and each stage is
    persisted before the next runs (FIFO drain)."""
    queue = runner.queue
    for stage in stages:
        queue.enqueue(
            Job(
                workflow=stage,
                claim_id=claim_id,
                # Unique per (claim, stage) so the idempotency key never dedupes
                # a stage we intend to run.
                triggered_by_doc_id=f"prerun-{claim_id}-{stage}",
                posture_changed="prerun",
            )
        )
    return runner.process_all()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "claims", nargs="*", default=None,
        help=f"Claim ids to pre-run (default: {' '.join(DEFAULT_TARGETS)})",
    )
    parser.add_argument(
        "--stages", default=",".join(WORKFLOW_CHAIN),
        help="Comma-separated stage prefix to run (default: full chain)",
    )
    parser.add_argument(
        "--keep", action="store_true",
        help="Append to existing results instead of resetting the claim first",
    )
    args = parser.parse_args()

    targets = args.claims or DEFAULT_TARGETS
    stages = [s.strip() for s in args.stages.split(",") if s.strip()]
    bad = [s for s in stages if s not in WORKFLOW_CHAIN]
    if bad:
        print(f"Unknown stage(s): {bad}; valid: {WORKFLOW_CHAIN}", file=sys.stderr)
        return 2

    caseload = build_cockpit_caseload()
    known = {c.claim_id for c in caseload.claims}
    missing = [c for c in targets if c not in known]
    if missing:
        print(f"Unknown claim(s): {missing}", file=sys.stderr)
        return 2

    print("=" * 76)
    print(f"PRE-RUN cockpit chains → {RESULTS_ROOT.relative_to(REPO_ROOT)}")
    print(f"targets: {targets}  ·  stages: {stages}")
    print("=" * 76)

    # One fresh in-memory queue; the runner persists results + audit rows.
    runner = WorkflowRunner(
        queue=JobQueue(persistence_path=None),
        caseload=caseload,
        results_root=RESULTS_ROOT,
        audit_log_root=AUDIT_LOG_ROOT,
    )

    any_failed = False
    for claim_id in targets:
        if not args.keep:
            _reset_claim(claim_id)
        print(f"\n--- {claim_id} ---")
        processed = prerun_claim(runner, claim_id, stages)
        for job in processed:
            if job.claim_id != claim_id:
                continue
            ok = job.status == JobStatus.DONE
            any_failed = any_failed or not ok
            mark = "OK " if ok else "ERR"
            print(f"  [{mark}] {job.workflow:<9} {job.result_summary or job.error}")

    print("\n" + "=" * 76)
    print("DONE" if not any_failed else "DONE (with failures — see [ERR] rows)")
    print("=" * 76)
    return 1 if any_failed else 0


if __name__ == "__main__":
    sys.exit(main())
