"""Run the Brief specialist on one claim and print the result.

Usage:
    .venv/bin/python scripts/run_brief.py [claim_id]

Defaults to CLM-015 (the extended fixture's coverage-posture-changing
claim where Coverage has been run by the orchestrator demo). Reads
persisted specialist results from `data/orchestrator-demo/workflow-results/`
if present so the Brief consumes them.

Cost: ~2 LLM calls (narrative + gaps) ≈ $0.02.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPO_ROOT / ".env")

from argos.ontology.caseload_with_realistic_docs import (  # noqa: E402
    build_caseload_with_realistic_docs,
)
from argos.workflows.brief.brief import run_brief  # noqa: E402


DEFAULT_CLAIM_ID = "CLM-015"
RESULTS_ROOT = REPO_ROOT / "data" / "orchestrator-demo" / "workflow-results"
BRIEF_OUTPUT_ROOT = REPO_ROOT / "data" / "brief-demo"


def main() -> int:
    claim_id = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CLAIM_ID

    print(f"Running Brief on {claim_id}...")
    print(f"  results_root: {RESULTS_ROOT}")
    print()

    caseload = build_caseload_with_realistic_docs()
    result = run_brief(caseload, claim_id, results_root=RESULTS_ROOT)
    brief = result.brief

    print("=" * 76)
    print(f"BRIEF — {claim_id}")
    print("=" * 76)
    print()
    print("STORY")
    print("-" * 76)
    print(brief.story_paragraph)
    print()
    print(f"  cited {len(brief.story_citations)} document(s): "
          f"{[c.document_id for c in brief.story_citations]}")
    print()

    print("STATUS SNAPSHOT")
    print("-" * 76)
    for field, value in brief.current_status_snapshot.model_dump().items():
        print(f"  {field}: {value}")
    print()

    print("FINANCIAL SNAPSHOT")
    print("-" * 76)
    for field, value in brief.financial_snapshot.model_dump().items():
        print(f"  {field}: {value}")
    print()

    print(f"SPECIALIST RECOMMENDATIONS ({len(brief.workflow_recommendations_summary)})")
    print("-" * 76)
    for rec in brief.workflow_recommendations_summary:
        print(f"  [{rec.workflow}] {rec.headline}")
    if not brief.workflow_recommendations_summary:
        print("  (no specialist results consumed)")
    print()

    print(f"OPEN GAPS ({len(brief.missing_info)})")
    print("-" * 76)
    for item in brief.missing_info:
        print(f"  • {item.item} (request from: {item.requested_from})")
        print(f"      cites {len(item.evidence_citations)} doc(s); "
              f"status: {item.correspondence_status}")
    if not brief.missing_info:
        print("  (no gaps detected, or no docs on file to cite)")
    print()

    print("=" * 76)
    print(f"narrative attempts: {result.narrative_attempts}, "
          f"gaps attempts: {result.gaps_attempts}")
    print("=" * 76)

    # Persist
    BRIEF_OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    out_path = BRIEF_OUTPUT_ROOT / f"{claim_id}-brief.json"
    out_path.write_text(json.dumps(brief.model_dump(mode="json"), indent=2, default=str))
    print(f"\nwrote {out_path.relative_to(REPO_ROOT)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
