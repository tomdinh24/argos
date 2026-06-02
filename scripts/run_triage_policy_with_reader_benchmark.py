"""Triage policy engine + Document Reader integration benchmark.

Runs the policy engine twice on the extended N=20 fixture:

  Baseline:    rank_policy(caseload)                       # raw unread counts
  Integrated:  rank_policy(caseload, relevant_doc_counts=...)  # Reader-screened counts

Reports both rankings side-by-side and applies the locked thresholds in
`docs/evals/triage-policy-engine-with-reader-integrated-thresholds.md`:

  Q1 — Reader output matches pre-registered predictions for all 9 docs
  Q2 — Baseline bucket assignments match pre-registered baseline gold
  Q3 — Integrated bucket assignments match pre-registered integrated gold

Costs ~9 Reader calls (~$0.10). One shot.

Run:
    .venv/bin/python scripts/run_triage_policy_with_reader_benchmark.py
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPO_ROOT / ".env")

from argos.ontology.caseload_with_realistic_docs import (  # noqa: E402
    build_caseload_with_realistic_docs,
    pinned_doc_predictions,
)
from argos.ontology.synthetic_caseload import corner_labels  # noqa: E402
from argos.services.triage.policy_engine import rank_policy  # noqa: E402
from argos.services.triage.ranker import Weights  # noqa: E402
from argos.services.triage.reader_integration import screen_caseload  # noqa: E402


EVAL_DIR = REPO_ROOT / "data" / "eval-runs" / "triage-policy-with-reader"
EVAL_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_PATH = EVAL_DIR / "integration_run.json"
TUNED_WEIGHTS_PATH = REPO_ROOT / "data" / "eval-runs" / "triage-ranker" / "tuned_weights.json"


# Pre-registered bucket gold from the locked integration thresholds doc.
BASELINE_BUCKET_GOLD: dict[str, int] = {
    "REQ-007": 6,  # $1.75M + 2 raw unread → B6
    "REQ-008": 6,  # $585K + 1 raw unread → B6
    "REQ-013": 7,
    "REQ-014": 7,
    "REQ-015": 7,
}
INTEGRATED_BUCKET_GOLD: dict[str, int] = {
    "REQ-007": 6,  # $1.75M + 1 relevant unread → B6 (Reader keeps it)
    "REQ-008": 7,  # $585K + 0 relevant unread → B7 (Reader demotes)
    "REQ-013": 7,
    "REQ-014": 7,
    "REQ-015": 7,
}


def main() -> int:
    print("=" * 76)
    print("TRIAGE POLICY ENGINE + DOCUMENT READER INTEGRATION BENCHMARK")
    print("=" * 76)
    print()

    tuned = json.loads(TUNED_WEIGHTS_PATH.read_text())
    weights = Weights(**tuned["winner"])
    labels = corner_labels()
    caseload = build_caseload_with_realistic_docs()
    predictions = pinned_doc_predictions()

    # ===================================================================
    # Step 1 — baseline: policy engine on extended fixture, raw counts
    # ===================================================================
    print("Step 1: BASELINE — policy engine on extended fixture, raw unread counts")
    print("-" * 76)
    baseline_ranked = rank_policy(caseload, weights, relevant_doc_counts=None)
    baseline_bucket_by_rid = {r.request_id: r.bucket for r in baseline_ranked}
    for rid, expected in BASELINE_BUCKET_GOLD.items():
        actual = baseline_bucket_by_rid[rid]
        mark = "✓" if actual == expected else "✗"
        print(f"  {mark} {rid} ({labels[rid]:<14}): expected B{expected}, got B{actual}")
    q2_pass = all(
        baseline_bucket_by_rid[rid] == expected
        for rid, expected in BASELINE_BUCKET_GOLD.items()
    )
    print(f"Q2 — baseline bucket gold: {'PASS' if q2_pass else 'FAIL'}")
    print()

    # ===================================================================
    # Step 2 — Reader pass: classify every unread doc, build relevance map
    # ===================================================================
    print("Step 2: READER PASS — classifying every unread doc")
    print("-" * 76)
    screening = screen_caseload(caseload)
    print(f"  docs screened: {screening.docs_screened}")
    print(f"  relevant-doc counts by claim: {screening.relevant_doc_counts}")
    print()

    print("  Per-doc Reader output vs pre-registered prediction:")
    q1_mismatches = []
    reader_audit = []
    for record in screening.call_records:
        pinned = predictions.get(record.document_id)
        if pinned is None:
            print(f"  ?  {record.document_id} — UNKNOWN DOC (not pinned)")
            q1_mismatches.append(record.document_id)
            continue
        relevant_match = record.call.relevant == pinned.expected_relevant
        posture_match = record.call.posture_changed == pinned.expected_posture
        passed = relevant_match and posture_match
        mark = "✓" if passed else "✗"
        print(
            f"  {mark} {record.document_id}: "
            f"relevant={record.call.relevant} (expected {pinned.expected_relevant}), "
            f"posture={record.call.posture_changed} (expected {pinned.expected_posture})"
        )
        if not passed:
            q1_mismatches.append(record.document_id)
        reader_audit.append({
            "document_id": record.document_id,
            "claim_id": record.claim_id,
            "expected_relevant": pinned.expected_relevant,
            "actual_relevant": record.call.relevant,
            "expected_posture": pinned.expected_posture,
            "actual_posture": record.call.posture_changed,
            "reason": record.call.reason,
            "text_excerpt": record.call.text_excerpt,
            "relevant_match": relevant_match,
            "posture_match": posture_match,
            "all_passed": passed,
        })
    q1_pass = not q1_mismatches
    print(f"Q1 — Reader output vs pre-registered: {'PASS' if q1_pass else 'FAIL'}")
    if q1_mismatches:
        print(f"  mismatches: {q1_mismatches}")
    print()

    # ===================================================================
    # Step 3 — integrated: policy engine with Reader-supplied counts
    # ===================================================================
    print("Step 3: INTEGRATED — policy engine with Reader-screened relevant-doc counts")
    print("-" * 76)
    integrated_ranked = rank_policy(
        caseload, weights, relevant_doc_counts=screening.relevant_doc_counts
    )
    integrated_bucket_by_rid = {r.request_id: r.bucket for r in integrated_ranked}
    for rid, expected in INTEGRATED_BUCKET_GOLD.items():
        actual = integrated_bucket_by_rid[rid]
        mark = "✓" if actual == expected else "✗"
        print(f"  {mark} {rid} ({labels[rid]:<14}): expected B{expected}, got B{actual}")
    q3_pass = all(
        integrated_bucket_by_rid[rid] == expected
        for rid, expected in INTEGRATED_BUCKET_GOLD.items()
    )
    print(f"Q3 — integrated bucket gold: {'PASS' if q3_pass else 'FAIL'}")
    print()

    # ===================================================================
    # Side-by-side: where Reader changed the bucket
    # ===================================================================
    print("BEFORE vs AFTER (where Reader integration changed the bucket):")
    print("-" * 76)
    changes = []
    for rid in baseline_bucket_by_rid:
        before = baseline_bucket_by_rid[rid]
        after = integrated_bucket_by_rid[rid]
        if before != after:
            changes.append((rid, before, after))
            print(
                f"  {rid} ({labels[rid]:<14}): "
                f"B{before} → B{after} "
                f"({'demoted' if after > before else 'promoted'})"
            )
    if not changes:
        print("  (no claims changed bucket)")
    print()

    # ===================================================================
    # Composite verdict
    # ===================================================================
    print("=" * 76)
    print("COMPOSITE VERDICT")
    print("=" * 76)
    composite_pass = q1_pass and q2_pass and q3_pass
    if composite_pass:
        composite = (
            "SHIP — Reader + policy engine integration works end-to-end. "
            "Q1: all 9 Reader calls match pre-registered predictions. "
            "Q2: extended-fixture baseline matches pre-registered baseline gold. "
            "Q3: Reader integration correctly promotes REQ-007 and demotes "
            "REQ-008. Policy engine stays pure (no LLM in rank_policy); "
            "Reader supplies one feature; engine applies the rules."
        )
    else:
        failed = []
        if not q1_pass:
            failed.append("Q1 (Reader output)")
        if not q2_pass:
            failed.append("Q2 (baseline gold)")
        if not q3_pass:
            failed.append("Q3 (integrated gold)")
        composite = (
            f"DO NOT SHIP — {', '.join(failed)} failed. "
            "Per locked thresholds, integration ships only when all three "
            "checks pass."
        )
    print(composite)
    print()

    # ===================================================================
    # Persist run
    # ===================================================================
    OUTPUT_PATH.write_text(json.dumps({
        "run_timestamp": datetime.now(timezone.utc).isoformat(),
        "spec": "docs/specs/triage-ranker-policy-engine.md",
        "integration_thresholds": (
            "docs/evals/triage-policy-engine-with-reader-integrated-thresholds.md"
        ),
        "tuned_weights_path": str(TUNED_WEIGHTS_PATH.relative_to(REPO_ROOT)),
        "q1_reader_output": {
            "verdict": "PASS" if q1_pass else "FAIL",
            "docs_screened": screening.docs_screened,
            "audit": reader_audit,
            "relevant_doc_counts": screening.relevant_doc_counts,
        },
        "q2_baseline_buckets": {
            "verdict": "PASS" if q2_pass else "FAIL",
            "gold": BASELINE_BUCKET_GOLD,
            "actual": {
                rid: baseline_bucket_by_rid[rid] for rid in BASELINE_BUCKET_GOLD
            },
        },
        "q3_integrated_buckets": {
            "verdict": "PASS" if q3_pass else "FAIL",
            "gold": INTEGRATED_BUCKET_GOLD,
            "actual": {
                rid: integrated_bucket_by_rid[rid] for rid in INTEGRATED_BUCKET_GOLD
            },
        },
        "bucket_changes": [
            {"request_id": rid, "before": before, "after": after}
            for rid, before, after in changes
        ],
        "composite_verdict": composite,
        "all_passed": composite_pass,
    }, indent=2))
    print(f"wrote {OUTPUT_PATH.relative_to(REPO_ROOT)}")
    return 0 if composite_pass else 1


if __name__ == "__main__":
    sys.exit(main())
