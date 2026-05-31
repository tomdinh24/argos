"""Tune the triage ranker weights against gold.csv via random search.

Procedure is locked in `docs/evals/triage-ranker-tuning-procedure.md`.
Any deviation from that doc (seed, sample size, bounds, objective)
invalidates the eval.

Run:
    .venv/bin/python scripts/tune_triage_weights.py

Output:
    data/eval-runs/triage-ranker/tuned_weights.json   — best weight vector
    stdout: best score + top-5 runners-up + closest-to-uniform tiebreak
"""
from __future__ import annotations

import csv
import json
import random
import sys
from dataclasses import asdict, fields
from pathlib import Path

from argos.ontology.synthetic_caseload import build_caseload
from argos.services.triage.ranker import Weights, rank


REPO_ROOT = Path(__file__).resolve().parents[1]
GOLD_CSV = REPO_ROOT / "data" / "eval-runs" / "triage-ranker" / "gold.csv"
OUT_JSON = REPO_ROOT / "data" / "eval-runs" / "triage-ranker" / "tuned_weights.json"

# Locked search parameters — DO NOT CHANGE without revising the procedure doc.
SEED = 42
N_RANDOM_SAMPLES = 5000
WEIGHT_LOW = 0.0
WEIGHT_HIGH = 8.0

WEIGHT_NAMES = [f.name for f in fields(Weights)]

# Anchor vectors — included in the search alongside random draws.
ANCHOR_UNIFORM = {name: 1.0 for name in WEIGHT_NAMES}
ANCHOR_CLOCK_BIASED = {
    "w_sla": 4.0, "w_stat": 4.0, "w_lit": 2.0, "w_compl": 2.0,
    "w_aged": 1.0, "w_diary": 1.0, "w_sev": 1.0, "w_amt": 1.0,
    "w_reserve": 1.0, "w_contact": 1.0, "w_unread": 1.0, "w_rep": 1.0,
}


def load_gold() -> list[str]:
    with GOLD_CSV.open() as f:
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


def l2_from_uniform(w: dict[str, float]) -> float:
    return sum((w[name] - 1.0) ** 2 for name in WEIGHT_NAMES) ** 0.5


def evaluate(weights_dict: dict[str, float], caseload, gold: list[str]):
    """Return (top7, tau, l2_from_uniform) for one weight vector."""
    w = Weights(**weights_dict)
    pred = [r.request_id for r in rank(caseload, w)]
    return top7_jaccard(gold, pred), kendall_tau(gold, pred), l2_from_uniform(weights_dict)


def main() -> int:
    gold = load_gold()
    caseload = build_caseload()
    rng = random.Random(SEED)

    print(f"loaded gold ranking: {len(gold)} requests")
    print(f"search: {N_RANDOM_SAMPLES} random + 2 anchors = "
          f"{N_RANDOM_SAMPLES + 2} evaluations")
    print(f"weight bounds: [{WEIGHT_LOW}, {WEIGHT_HIGH}], seed={SEED}")
    print()

    # candidate generator: anchors first, then random draws (so anchor
    # indices are stable across runs at seed 42)
    candidates: list[dict[str, float]] = [
        dict(ANCHOR_UNIFORM),
        dict(ANCHOR_CLOCK_BIASED),
    ]
    for _ in range(N_RANDOM_SAMPLES):
        candidates.append({
            name: rng.uniform(WEIGHT_LOW, WEIGHT_HIGH) for name in WEIGHT_NAMES
        })

    # evaluate every candidate; keep (top7, tau, -l2, idx, weights)
    # sort key is (-top7, -tau, l2) ascending so the winner is at index 0
    scored = []
    for idx, w in enumerate(candidates):
        top7, tau, l2 = evaluate(w, caseload, gold)
        # use idx as final deterministic tiebreak (anchors get idx 0/1 → win
        # any genuine tie with a random draw)
        scored.append((top7, tau, l2, idx, w))

    scored.sort(key=lambda t: (-t[0], -t[1], t[2], t[3]))

    print("RESULTS")
    print("=" * 72)
    print(f"{'rank':<6}{'top7':<8}{'tau':<8}{'l2':<8}{'origin':<14}")
    for i, (top7, tau, l2, idx, w) in enumerate(scored[:6], start=1):
        origin = (
            "uniform" if idx == 0
            else "clock-biased" if idx == 1
            else f"random#{idx - 1}"
        )
        print(f"{i:<6}{top7:<8.3f}{tau:<+8.3f}{l2:<8.2f}{origin:<14}")
    print()

    best_top7, best_tau, best_l2, best_idx, best_w = scored[0]
    print(f"WINNER (origin: index {best_idx}):")
    for name in WEIGHT_NAMES:
        print(f"  {name:<12} = {best_w[name]:.3f}")
    print()
    print(f"  top-7 Jaccard = {best_top7:.3f}")
    print(f"  Kendall tau   = {best_tau:+.3f}")
    print(f"  L2 from uniform = {best_l2:.2f}")
    print()

    OUT_JSON.write_text(json.dumps({
        "seed": SEED,
        "n_random_samples": N_RANDOM_SAMPLES,
        "weight_bounds": [WEIGHT_LOW, WEIGHT_HIGH],
        "winner_origin_idx": best_idx,
        "winner": {name: round(best_w[name], 6) for name in WEIGHT_NAMES},
        "winner_metrics": {
            "top7_jaccard": round(best_top7, 6),
            "kendall_tau": round(best_tau, 6),
            "l2_from_uniform": round(best_l2, 6),
        },
        "anchors_evaluated": [
            {"name": "uniform-1.0", "top7": evaluate(ANCHOR_UNIFORM, caseload, gold)[0]},
            {"name": "clock-biased", "top7": evaluate(ANCHOR_CLOCK_BIASED, caseload, gold)[0]},
        ],
    }, indent=2))
    print(f"wrote {OUT_JSON.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
