"""Run hybrid v2 against both independent golds and apply locked thresholds.

Spec: docs/specs/triage-ranker-hybrid-v2.md
Thresholds: docs/evals/triage-ranker-hybrid-v2-thresholds.md

Calls GPT-5.5-pro twice (once per gold benchmark) — this script costs
real money. Run once, report the verdict, do not loop.

Run:
    .venv/bin/python scripts/run_triage_hybrid_benchmark.py
"""
from __future__ import annotations

import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from argos.ontology.synthetic_caseload import build_caseload
from argos.services.triage.hybrid import HybridResult, TOP_N, re_rank
from argos.services.triage.ranker import Weights, rank


REPO_ROOT = Path(__file__).resolve().parents[1]
EVAL_DIR = REPO_ROOT / "data" / "eval-runs" / "triage-ranker"
GOLD_GPT5 = EVAL_DIR / "gold_gpt5.csv"
GOLD_GPT55PRO = EVAL_DIR / "gold_gpt55pro.csv"
TUNED_WEIGHTS_PATH = EVAL_DIR / "tuned_weights.json"
HYBRID_OUTPUT_PATH = EVAL_DIR / "hybrid_v2_run.json"

# Locked thresholds from triage-ranker-hybrid-v2-thresholds.md
V1_TAU_GPT5 = 0.811
V1_TAU_GPT55PRO = 0.747
TAU_DRIFT_TOLERANCE = 0.05


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
    # discrete top-7 Jaccard bucket → k
    for k in range(8):
        if abs(j - (k / (14 - k) if k < 14 else 1.0)) < 1e-6:
            return k
    return -1  # not a valid top-7 Jaccard value


def main() -> int:
    print("=" * 72)
    print("HYBRID V2 BENCHMARK — GPT-5.5-pro re-rank on tuned-S1 top-10")
    print("=" * 72)
    print()

    # Load locked S1 weights + caseload
    tuned = json.loads(TUNED_WEIGHTS_PATH.read_text())
    weights = Weights(**tuned["winner"])
    caseload = build_caseload()
    s1_full = rank(caseload, weights)
    s1_ids = [item.request_id for item in s1_full]

    # Two judge calls — one per gold benchmark, both use the SAME hybrid run
    # output (the judge re-rank doesn't depend on which gold we score
    # against). Single re_rank call, two scorings.
    print(f"Calling judge ({TOP_N}-slice, gpt-5.5-pro)...")
    hybrid_result: HybridResult = re_rank(caseload, weights)
    if not hybrid_result.schema_valid:
        print(f"!!! JUDGE OUTPUT FAILED SCHEMA: {hybrid_result.failure_reason}")
        print("Raw response:")
        print(hybrid_result.judge_raw_response[:2000])
        return 1

    hybrid_ids = [item.request_id for item in hybrid_result.items]
    print(f"Judge returned a valid {TOP_N}-row CSV. Re-rank applied.")
    print()

    # Score against both golds
    rows = []
    for gold_label, gold_path, v1_tau in [
        ("gpt5", GOLD_GPT5, V1_TAU_GPT5),
        ("gpt55pro", GOLD_GPT55PRO, V1_TAU_GPT55PRO),
    ]:
        gold = load_gold(gold_path)
        s1_j = top7_jaccard(gold, s1_ids)
        s1_t = kendall_tau(gold, s1_ids)
        v2_j = top7_jaccard(gold, hybrid_ids)
        v2_t = kendall_tau(gold, hybrid_ids)
        rows.append({
            "gold": gold_label,
            "s1_top7": s1_j,
            "s1_k": jaccard_to_k(s1_j),
            "s1_tau": s1_t,
            "v2_top7": v2_j,
            "v2_k": jaccard_to_k(v2_j),
            "v2_tau": v2_t,
            "k_delta": jaccard_to_k(v2_j) - jaccard_to_k(s1_j),
            "tau_delta": v2_t - s1_t,
            "v1_tau_locked": v1_tau,
            "tau_in_tolerance": abs(v2_t - v1_tau) <= TAU_DRIFT_TOLERANCE,
        })

    # Report
    print("RESULTS")
    print("-" * 72)
    print(f"{'gold':<10}{'s1 k':<8}{'v2 k':<8}{'Δk':<6}{'s1 tau':<10}{'v2 tau':<10}{'Δtau':<8}{'τ OK':<6}")
    for r in rows:
        print(
            f"{r['gold']:<10}"
            f"{r['s1_k']:<8}"
            f"{r['v2_k']:<8}"
            f"{r['k_delta']:+d}{'':<3}"
            f"{r['s1_tau']:<+10.3f}"
            f"{r['v2_tau']:<+10.3f}"
            f"{r['tau_delta']:<+8.3f}"
            f"{'yes' if r['tau_in_tolerance'] else 'NO':<6}"
        )
    print()

    # Verdict per locked thresholds
    v2_ks = [r["v2_k"] for r in rows]
    tau_ok = all(r["tau_in_tolerance"] for r in rows)

    if all(k == 7 for k in v2_ks) and tau_ok:
        verdict = "SHIP V2 — LLM re-rank closes the 7th-slot gap on both independent golds."
    elif any(k == 7 for k in v2_ks) and tau_ok:
        verdict = (
            "HOLD — v2 lifts one gold to k=7 but not the other. Investigate the asymmetry "
            "(why does the LLM judge align with one gold judge and not the other?) before shipping."
        )
    elif all(k == 6 for k in v2_ks) and tau_ok:
        verdict = (
            "DEFER V2, SHIP V1 — 7th-claim disagreement is genuine adjuster ambiguity, "
            "not closeable by LLM judgment."
        )
    elif any(k <= 5 for k in v2_ks):
        verdict = "DO NOT SHIP — v2 regresses below the k=6 baseline; LLM re-rank is introducing noise."
    elif not tau_ok:
        verdict = (
            "DO NOT SHIP AS-IS — tau drift exceeds ±0.05 on at least one gold. "
            "Re-rank is scrambling the top slice in ways that hurt overall ordering."
        )
    else:
        verdict = "UNCLASSIFIED — manual read required."

    print(f"VERDICT: {verdict}")
    print()
    print("Top-10 ordering comparison (S1 → v2):")
    s1_top = [item.request_id for item in s1_full[:TOP_N]]
    v2_top = hybrid_ids[:TOP_N]
    for i in range(TOP_N):
        same = " " if s1_top[i] == v2_top[i] else "*"
        print(f"  rank {i + 1}: {s1_top[i]:<10}→ {v2_top[i]:<10}{same}")
    print()
    print("Judge's full response (audit trail):")
    print("-" * 72)
    print(hybrid_result.judge_raw_response)
    print("-" * 72)

    # Persist the run for the audit record
    HYBRID_OUTPUT_PATH.write_text(json.dumps({
        "run_timestamp": datetime.now(timezone.utc).isoformat(),
        "judge_model": "gpt-5.5-pro",
        "top_n": TOP_N,
        "schema_valid": hybrid_result.schema_valid,
        "v2_top_n_ordering": v2_top,
        "s1_top_n_ordering": s1_top,
        "results": rows,
        "verdict": verdict,
        "judge_raw_response": hybrid_result.judge_raw_response,
    }, indent=2))
    print(f"wrote {HYBRID_OUTPUT_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
