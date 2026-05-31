"""Run the policy-engine triage ranker and apply locked thresholds.

Spec: docs/specs/triage-ranker-policy-engine.md
Thresholds: docs/evals/triage-ranker-policy-engine-thresholds.md

Three orthogonal metrics:

  Q1 — Bucket-assignment accuracy (primary). 20/20 or bust.
  Q2 — Top-7 k vs each independent LLM gold (gpt5, gpt55pro).
       v1 baseline: k=6 on both. Pre-registered prediction: same.
  Q3 — Kendall tau on full N=20 vs each independent gold.
       v1 tau baselines: gpt5=0.811, gpt55pro=0.747. Allow ±0.1 drift.

No network calls. No randomness. One run, locked verdict.

Run:
    .venv/bin/python scripts/run_triage_policy_benchmark.py
"""
from __future__ import annotations

import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from argos.ontology.synthetic_caseload import build_caseload, corner_labels
from argos.services.triage.policy_engine import (
    BUCKET_NAMES,
    PolicyRankedItem,
    rank_policy,
)
from argos.services.triage.ranker import Weights, rank


REPO_ROOT = Path(__file__).resolve().parents[1]
EVAL_DIR = REPO_ROOT / "data" / "eval-runs" / "triage-ranker"
GOLD_GPT5 = EVAL_DIR / "gold_gpt5.csv"
GOLD_GPT55PRO = EVAL_DIR / "gold_gpt55pro.csv"
TUNED_WEIGHTS_PATH = EVAL_DIR / "tuned_weights.json"
POLICY_OUTPUT_PATH = EVAL_DIR / "policy_engine_run.json"

# Locked from triage-ranker-policy-engine-thresholds.md (Q3 baselines)
V1_TAU_GPT5 = 0.811
V1_TAU_GPT55PRO = 0.747
TAU_DRIFT_TOLERANCE = 0.10  # per locked thresholds Q3

# Locked bucket gold (per claim label) from thresholds doc Q1
LOCKED_BUCKET_GOLD: dict[str, int] = {
    "sla-1h": 1, "sla-4h": 1, "sla-6h": 1,
    "stat-3d": 2, "stat-7d": 2,
    "stat-14d": 5,
    "hi-cat": 7, "hi-serious-1": 7, "hi-serious-2": 7,
    "aged-15d": 7, "aged-21d": 7, "aged-30d": 7,
    "unread-1": 7, "unread-2": 7, "unread-3": 7,
    "lit-rep-1": 3, "lit-rep-2": 3,
    "complaint-doi": 4,
    "bb-minor-1": 7, "bb-minor-2": 7,
}


def load_gold(path: Path) -> list[str]:
    with path.open() as f:
        rows = sorted(csv.DictReader(f), key=lambda r: int(r["rank"]))
    return [r["request_id"] for r in rows]


def top7_jaccard(gold: list[str], pred: list[str]) -> float:
    a, b = set(gold[:7]), set(pred[:7])
    return len(a & b) / len(a | b)


def kendall_tau(gold: list[str], pred: list[str]) -> float:
    gold_rank = {rid: i for i, rid in enumerate(gold)}
    pred_rank = {rid: i for i, rid in enumerate(pred)}
    ids = list(gold)
    n = len(ids)
    c = d = 0
    for i in range(n):
        for j in range(i + 1, n):
            a, b = ids[i], ids[j]
            sg = gold_rank[a] - gold_rank[b]
            sp = pred_rank[a] - pred_rank[b]
            if sg * sp > 0:
                c += 1
            else:
                d += 1
    return (c - d) / (n * (n - 1) // 2)


def jaccard_to_k(j: float) -> int:
    """Discrete top-7 Jaccard bucket → k (0..7)."""
    for k in range(8):
        denom = 14 - k
        target = (k / denom) if denom > 0 else 1.0
        if abs(j - target) < 1e-6:
            return k
    return -1


def main() -> int:
    print("=" * 72)
    print("POLICY-ENGINE TRIAGE BENCHMARK")
    print("=" * 72)
    print()

    # Setup
    tuned = json.loads(TUNED_WEIGHTS_PATH.read_text())
    weights = Weights(**tuned["winner"])
    caseload = build_caseload()
    labels = corner_labels()

    # --- Run S1 v1 (for comparison) ---
    s1_full = rank(caseload, weights)
    s1_ids = [item.request_id for item in s1_full]

    # --- Run policy engine ---
    policy_full: list[PolicyRankedItem] = rank_policy(caseload, weights)
    policy_ids = [item.request_id for item in policy_full]

    # ===================================================================
    # Q1 — Bucket-assignment accuracy
    # ===================================================================
    print("Q1 — BUCKET-ASSIGNMENT ACCURACY")
    print("-" * 72)
    bucket_mismatches: list[str] = []
    bucket_assignments: dict[str, dict] = {}
    for item in policy_full:
        label = labels[item.request_id]
        expected = LOCKED_BUCKET_GOLD[label]
        match = item.bucket == expected
        bucket_assignments[item.request_id] = {
            "label": label,
            "expected_bucket": expected,
            "actual_bucket": item.bucket,
            "bucket_name": item.bucket_name,
            "why_today": item.why_today,
            "rank": item.rank,
            "match": match,
        }
        if not match:
            bucket_mismatches.append(
                f"  {item.request_id} ({label}): expected B{expected}, "
                f"got B{item.bucket} ({item.why_today})"
            )

    q1_pass = not bucket_mismatches
    print(f"Bucket matches: {len(policy_full) - len(bucket_mismatches)}/{len(policy_full)}")
    if bucket_mismatches:
        print("Mismatches:")
        for m in bucket_mismatches:
            print(m)
        print()
        print("Q1 VERDICT: FAIL — policy engine does not implement the locked policy.")
        print("Fix the engine and re-run. This is the only legitimate re-run.")
        return 1
    print("Q1 VERDICT: PASS — engine matches locked bucket gold (20/20).")
    print()

    # ===================================================================
    # Q2 — Top-7 k vs both independent golds
    # ===================================================================
    print("Q2 — TOP-7 OVERLAP vs INDEPENDENT LLM GOLDS")
    print("-" * 72)
    q2_rows = []
    for gold_label, gold_path in [("gpt5", GOLD_GPT5), ("gpt55pro", GOLD_GPT55PRO)]:
        gold = load_gold(gold_path)
        s1_j = top7_jaccard(gold, s1_ids)
        pe_j = top7_jaccard(gold, policy_ids)
        q2_rows.append({
            "gold": gold_label,
            "s1_top7_jaccard": s1_j,
            "s1_k": jaccard_to_k(s1_j),
            "policy_top7_jaccard": pe_j,
            "policy_k": jaccard_to_k(pe_j),
            "k_delta": jaccard_to_k(pe_j) - jaccard_to_k(s1_j),
        })

    print(f"{'gold':<12}{'s1 k':<8}{'policy k':<11}{'Δk':<6}")
    for r in q2_rows:
        print(
            f"{r['gold']:<12}"
            f"{r['s1_k']:<8}"
            f"{r['policy_k']:<11}"
            f"{r['k_delta']:+d}"
        )
    print()

    policy_ks = tuple(r["policy_k"] for r in q2_rows)
    # Locked rule mapping
    if policy_ks == (7, 7):
        q2_verdict = "extraordinary — investigate gold contamination before celebrating"
    elif policy_ks == (6, 6):
        q2_verdict = "equivalent to v1 on set metric — ship; operational shape is the win"
    elif set(policy_ks) == {6, 7}:
        q2_verdict = "mixed lift — strictly ≥ v1 on both, > v1 on one; ship"
    elif 5 in policy_ks:
        q2_verdict = "regression on set metric — investigate before shipping"
    elif min(policy_ks) <= 4:
        q2_verdict = "hard fail — bucket triggers do not match adjuster judgment; back to spec"
    else:
        q2_verdict = "unclassified — manual read required"
    print(f"Q2 VERDICT: {q2_verdict}")
    print()

    # ===================================================================
    # Q3 — Kendall tau on full N=20
    # ===================================================================
    print("Q3 — KENDALL TAU vs INDEPENDENT LLM GOLDS")
    print("-" * 72)
    q3_rows = []
    for gold_label, gold_path, v1_tau in [
        ("gpt5", GOLD_GPT5, V1_TAU_GPT5),
        ("gpt55pro", GOLD_GPT55PRO, V1_TAU_GPT55PRO),
    ]:
        gold = load_gold(gold_path)
        s1_t = kendall_tau(gold, s1_ids)
        pe_t = kendall_tau(gold, policy_ids)
        drift = pe_t - v1_tau
        in_tol = abs(drift) <= TAU_DRIFT_TOLERANCE
        q3_rows.append({
            "gold": gold_label,
            "s1_tau": s1_t,
            "policy_tau": pe_t,
            "v1_tau_locked": v1_tau,
            "drift_vs_v1": drift,
            "in_tolerance": in_tol,
        })

    print(f"{'gold':<12}{'s1 tau':<10}{'policy tau':<13}{'Δ vs v1':<10}{'in ±0.10':<10}")
    for r in q3_rows:
        print(
            f"{r['gold']:<12}"
            f"{r['s1_tau']:<+10.3f}"
            f"{r['policy_tau']:<+13.3f}"
            f"{r['drift_vs_v1']:<+10.3f}"
            f"{'yes' if r['in_tolerance'] else 'NO':<10}"
        )
    print()

    drifts = [abs(r["drift_vs_v1"]) for r in q3_rows]
    if all(d <= 0.10 for d in drifts):
        q3_verdict = "ordering preserved at locked tolerance; pass"
    elif max(drifts) > 0.20:
        q3_verdict = "hard tau regression — bucket precedence loses ordering v1 had"
    else:
        q3_verdict = "tau drift > 0.10 on at least one gold — flag for read"
    print(f"Q3 VERDICT: {q3_verdict}")
    print()

    # ===================================================================
    # Composite verdict
    # ===================================================================
    print("=" * 72)
    print("COMPOSITE VERDICT")
    print("=" * 72)
    if q1_pass and policy_ks == (6, 6) and all(d <= 0.10 for d in drifts):
        composite = (
            "SHIP — policy engine implements locked policy (Q1 pass), "
            "matches v1 on top-7 set (k=6 on both golds, Q2), preserves "
            "ordering within tolerance (Q3). Structural win: 7th-claim "
            "disagreement is now a visible policy call, not an implicit "
            "weight imbalance."
        )
    elif q1_pass and 7 in policy_ks and 5 not in policy_ks and all(d <= 0.10 for d in drifts):
        composite = (
            "SHIP+ — policy engine lifts at least one gold above v1 baseline."
        )
    elif q1_pass and 5 in policy_ks:
        composite = (
            "INVESTIGATE — Q1 pass but Q2 regressed below v1 on at least "
            "one gold. The structural argument may justify shipping but "
            "write the analysis first."
        )
    elif q1_pass:
        composite = "MIXED — Q1 passes; Q2/Q3 mixed. Read manually."
    else:
        composite = "Q1 FAIL — see above."
    print(composite)
    print()

    # ===================================================================
    # Top-10 side-by-side
    # ===================================================================
    print("Top-10 ordering: S1 → policy engine")
    print("-" * 72)
    for i in range(10):
        s1_rid = s1_ids[i]
        pe_item = policy_full[i]
        same = " " if s1_rid == pe_item.request_id else "*"
        print(
            f"  rank {i + 1:>2}: "
            f"{s1_rid:<10} ({labels[s1_rid]:<14}) "
            f"→ {pe_item.request_id:<10} "
            f"[B{pe_item.bucket} {pe_item.bucket_name}: {pe_item.why_today}] {same}"
        )
    print()

    # Full policy output
    print("Full policy ranking:")
    print("-" * 72)
    for r in policy_full:
        print(
            f"  {r.rank:>2}. {r.request_id:<10} "
            f"B{r.bucket}#{r.within_bucket_rank} "
            f"{labels[r.request_id]:<14} "
            f"score={r.within_bucket_score:>10.3f}  "
            f"{r.why_today}"
        )
    print()

    # ===================================================================
    # Persist run
    # ===================================================================
    POLICY_OUTPUT_PATH.write_text(json.dumps({
        "run_timestamp": datetime.now(timezone.utc).isoformat(),
        "spec": "docs/specs/triage-ranker-policy-engine.md",
        "thresholds": "docs/evals/triage-ranker-policy-engine-thresholds.md",
        "tuned_weights_path": str(TUNED_WEIGHTS_PATH.relative_to(REPO_ROOT)),
        "q1_bucket_accuracy": {
            "matches": len(policy_full) - len(bucket_mismatches),
            "total": len(policy_full),
            "verdict": "PASS" if q1_pass else "FAIL",
            "assignments": bucket_assignments,
        },
        "q2_top7_overlap": {
            "rows": q2_rows,
            "verdict": q2_verdict,
        },
        "q3_kendall_tau": {
            "rows": q3_rows,
            "verdict": q3_verdict,
        },
        "composite_verdict": composite,
        "policy_top_n_ordering": [
            {
                "rank": r.rank,
                "request_id": r.request_id,
                "label": labels[r.request_id],
                "bucket": r.bucket,
                "bucket_name": r.bucket_name,
                "why_today": r.why_today,
                "within_bucket_score": r.within_bucket_score,
            }
            for r in policy_full
        ],
        "s1_top_n_ordering": s1_ids,
    }, indent=2))
    print(f"wrote {POLICY_OUTPUT_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
