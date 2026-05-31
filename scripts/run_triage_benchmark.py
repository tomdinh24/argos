"""Run the triage ranker against the gold ranking and print the verdict.

Reads:
  - `data/eval-runs/triage-ranker/gold.csv` (rank, request_id, reason_short)
  - the deterministic N=20 caseload from `synthetic_caseload.build_caseload()`

Computes:
  - top-7 Jaccard agreement between ranker's top 7 and gold's top 7
  - Kendall's tau on the full N=20 ordering

Compares both against the locked thresholds in
`docs/evals/triage-ranker-thresholds.md` and prints a verdict.

Run:
    .venv/bin/python scripts/run_triage_benchmark.py
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from argos.ontology.synthetic_caseload import build_caseload
from argos.services.triage.ranker import DEFAULT_WEIGHTS, Weights, rank


REPO_ROOT = Path(__file__).resolve().parents[1]
GOLD_CSV = REPO_ROOT / "data" / "eval-runs" / "triage-ranker" / "gold.csv"

# Locked thresholds — must match docs/evals/triage-ranker-thresholds.md
THRESHOLD_TOP7_HIGH = 0.80
THRESHOLD_TOP7_LOW = 0.60
THRESHOLD_TAU_HIGH = 0.60
THRESHOLD_TAU_LOW = 0.40

# Noise-floor reference (analytic, from the thresholds doc)
NOISE_TOP7 = 0.21
NOISE_TAU_STDDEV = 0.16


def load_gold(path: Path) -> list[str]:
    """Return request_ids in gold-rank order (rank 1 first)."""
    with path.open() as f:
        rows = sorted(csv.DictReader(f), key=lambda r: int(r["rank"]))
    return [r["request_id"] for r in rows]


def top7_jaccard(gold: list[str], pred: list[str]) -> float:
    a, b = set(gold[:7]), set(pred[:7])
    return len(a & b) / len(a | b)


def kendall_tau(gold: list[str], pred: list[str]) -> float:
    """Kendall's tau between two total orderings of the same items.

    Implemented as O(n²) pair scan — fine for N=20. Returns
    (C - D) / (n*(n-1)/2) with no tie correction (both inputs are total
    orders by request_id, so ties are impossible).
    """
    if set(gold) != set(pred):
        raise ValueError("gold and pred must rank the same set of items")
    gold_rank = {rid: i for i, rid in enumerate(gold)}
    pred_rank = {rid: i for i, rid in enumerate(pred)}
    ids = list(gold)
    n = len(ids)
    concordant = 0
    discordant = 0
    for i in range(n):
        for j in range(i + 1, n):
            a, b = ids[i], ids[j]
            sign_gold = gold_rank[a] - gold_rank[b]
            sign_pred = pred_rank[a] - pred_rank[b]
            if sign_gold * sign_pred > 0:
                concordant += 1
            else:
                discordant += 1
    pairs = n * (n - 1) // 2
    return (concordant - discordant) / pairs


def tier_top7(j: float) -> str:
    if j >= THRESHOLD_TOP7_HIGH:
        return "high"
    if j >= THRESHOLD_TOP7_LOW:
        return "mid"
    return "low"


def tier_tau(t: float) -> str:
    if t >= THRESHOLD_TAU_HIGH:
        return "high"
    if t >= THRESHOLD_TAU_LOW:
        return "mid"
    return "low"


def verdict(top7_tier: str, tau_tier: str) -> str:
    if top7_tier == tau_tier == "high":
        return "DETERMINISTIC IS ENOUGH — defer hybrid, ship S1."
    if top7_tier == tau_tier == "mid":
        return "HYBRID LIFTS — S1 is the base; build hybrid v2 with LLM materiality layer."
    if top7_tier == tau_tier == "low":
        return "HYBRID IS STRUCTURAL — features alone do not capture priority; hybrid is required for v1."
    return (
        f"SPLIT VERDICT — top-7={top7_tier}, tau={tau_tier}. "
        "Read the per-metric tier in context: a high top-7 with low tau means "
        "the today's-work set matches but the fine ordering doesn't — points "
        "at a hybrid that re-ranks the top slice."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--weights",
        type=Path,
        default=None,
        help="Path to a tuned-weights JSON file (output of "
             "scripts/tune_triage_weights.py). If omitted, uses uniform 1.0.",
    )
    parser.add_argument(
        "--gold",
        type=Path,
        default=GOLD_CSV,
        help="Path to gold ranking CSV. Defaults to the Opus 4.8 gold "
             "(data/eval-runs/triage-ranker/gold.csv).",
    )
    args = parser.parse_args()

    gold_path = args.gold
    if not gold_path.exists():
        print(f"gold ranking not found at {gold_path}", file=sys.stderr)
        return 2

    if args.weights is not None:
        payload = json.loads(args.weights.read_text())
        weights = Weights(**payload["winner"])
        try:
            label_path = args.weights.resolve().relative_to(REPO_ROOT)
        except ValueError:
            label_path = args.weights
        weights_label = f"tuned weights ({label_path})"
    else:
        weights = DEFAULT_WEIGHTS
        weights_label = "default weights (uniform 1.0)"

    gold = load_gold(gold_path)
    caseload = build_caseload()
    ranked = rank(caseload, weights)
    pred = [r.request_id for r in ranked]

    j = top7_jaccard(gold, pred)
    t = kendall_tau(gold, pred)

    print("=" * 64)
    print(f"TRIAGE RANKER BENCHMARK — S1, {weights_label}")
    print("=" * 64)
    print()
    print(f"N = {len(gold)}, fixture = synthetic_caseload.build_caseload()")
    try:
        gold_label = gold_path.resolve().relative_to(REPO_ROOT)
    except ValueError:
        gold_label = gold_path
    print(f"gold = {gold_label}")
    print()
    print(f"top-7 Jaccard : {j:.3f}   (noise floor {NOISE_TOP7:.2f}; "
          f"{j / NOISE_TOP7:.1f}× noise)")
    print(f"Kendall tau   : {t:+.3f}   (noise stddev {NOISE_TAU_STDDEV:.2f}; "
          f"{t / NOISE_TAU_STDDEV:+.1f}σ)")
    print()
    print(f"top-7 tier    : {tier_top7(j)}   "
          f"(low <{THRESHOLD_TOP7_LOW} ≤ mid <{THRESHOLD_TOP7_HIGH} ≤ high)")
    print(f"tau tier      : {tier_tau(t)}   "
          f"(low <{THRESHOLD_TAU_LOW} ≤ mid <{THRESHOLD_TAU_HIGH} ≤ high)")
    print()
    print(f"VERDICT: {verdict(tier_top7(j), tier_tau(t))}")
    print()
    print("Per-rank comparison (rank=gold, pred_rank=ranker):")
    print(f"  {'rank':<6}{'gold_id':<10}{'pred_id':<10}{'pred_rank_of_gold':<20}")
    pred_index = {rid: i + 1 for i, rid in enumerate(pred)}
    for i, rid in enumerate(gold):
        print(f"  {i + 1:<6}{rid:<10}{pred[i]:<10}{pred_index[rid]:<20}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
