"""Run the Coverage specialist N times on the same fixture; report variance.

If run-to-run variance on identical input is on the same order as the inter-
variant delta we measured (+0.02), then that delta is statistically
indistinguishable from noise — and the bias test we ran is uninformative
regardless of which interpretation looked more convincing.

This baseline is a precondition for any future threshold-setting. Per Codex's
methodology guidance: if σ ≈ 0.02, a +0.05 threshold is meaningful; if σ
itself is ≈ 0.05, the threshold isn't testable signal.

Usage:
    .venv/bin/python scripts/variance_baseline_coverage.py
    .venv/bin/python scripts/variance_baseline_coverage.py --runs 7
    .venv/bin/python scripts/variance_baseline_coverage.py --variant with_flag
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

from argos.ontology.synthetic import build_anchor_variant  # noqa: E402
from argos.schemas.specialists.coverage import CoverageReport  # noqa: E402
from argos.specialists.coverage import run_coverage  # noqa: E402


_OUTCOME_LABEL_SPLIT = re.compile(r"[—:\-(]")


def _classify_outcome(claim_text: str) -> str:
    """Classify by *label prefix*; see run_coverage_anchor._classify_outcome."""
    prefix = _OUTCOME_LABEL_SPLIT.split(claim_text, maxsplit=1)[0].strip().lower()
    if "denial" in prefix or "denied" in prefix:
        return "denial"
    if "reservation" in prefix or "ror" in prefix:
        return "ROR"
    if "clean" in prefix or "covered" in prefix or "coverage" in prefix:
        return "clean"
    return "?"


def _outcome_mass(analysis: CoverageReport, kind: str) -> float | None:
    for o in analysis.synthesis.outcomes:
        if _classify_outcome(o.claim_text) == kind:
            return o.probability
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--runs", type=int, default=5,
        help="Number of independent runs on the same fixture (default 5).",
    )
    parser.add_argument(
        "--variant", choices=["clean", "with_flag"], default="clean",
        help="Which anchor variant to repeat (default: clean).",
    )
    parser.add_argument(
        "--output-dir", type=Path,
        default=PROJECT_ROOT / "data" / "eval-runs" / "coverage-anchor-variance",
        help="Where to write the per-run JSON outputs.",
    )
    args = parser.parse_args()

    claim = build_anchor_variant(args.variant)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, object]] = []
    print(f"Running Coverage specialist {args.runs}× on variant={args.variant}\n")

    for i in range(1, args.runs + 1):
        print(f"  run {i}/{args.runs} ... ", end="", flush=True)
        result = run_coverage(claim)
        clean = _outcome_mass(result.analysis, "clean")
        ror = _outcome_mass(result.analysis, "ROR")
        denial = _outcome_mass(result.analysis, "denial")
        n_assess = len(result.analysis.assessments)
        n_cites = len(result.analysis.evidence_found)
        def _fmt(v: float | None) -> str:
            return f"{v:.3f}" if v is not None else "—"
        print(
            f"clean={_fmt(clean)} ROR={_fmt(ror)} denial={_fmt(denial)}  "
            f"(attempts={result.attempts}, model={result.model})"
        )
        rows.append({
            "run": i,
            "clean": clean,
            "ROR": ror,
            "denial": denial,
            "n_assessments": n_assess,
            "n_evidence_citations": n_cites,
            "model": result.model,
            "attempts": result.attempts,
        })
        out_path = args.output_dir / f"{args.variant}_run{i:02d}.json"
        out_path.write_text(json.dumps(result.raw_tool_input, indent=2, default=str))

    if not rows:
        return 1

    print("\n" + "=" * 70)
    print(f"VARIANCE BASELINE — {args.variant} variant, n={args.runs}")
    print("=" * 70)
    for label in ["clean", "ROR", "denial"]:
        vals = [r[label] for r in rows if r[label] is not None]
        if len(vals) < 2:
            print(f"  {label:>10}: insufficient samples")
            continue
        mean = statistics.mean(vals)
        sd = statistics.stdev(vals)
        lo, hi = min(vals), max(vals)
        rng = hi - lo
        print(
            f"  {label:>10}: mean={mean:.3f}  σ={sd:.4f}  "
            f"range=[{lo:.3f}, {hi:.3f}] (Δ={rng:.3f})  "
            f"samples={vals}"
        )

    print()
    print("INTERPRETATION KEY:")
    print("  If σ(ROR) ≈ 0.02, the +0.02 inter-variant delta we measured is NOISE.")
    print("  If σ(ROR) ≈ 0.005, the +0.02 delta is REAL SIGNAL but smaller than threshold.")
    print("  If σ(ROR) ≈ 0.005 AND mean is near the clean baseline (0.08), the model")
    print("  is consistent on this fixture and the inter-variant delta means something.")

    # Persist aggregate
    agg = {
        "variant": args.variant,
        "runs": args.runs,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "per_run": rows,
        "stats": {
            label: (
                {
                    "mean": statistics.mean([r[label] for r in rows if r[label] is not None]),
                    "stdev": statistics.stdev([r[label] for r in rows if r[label] is not None]),
                    "min": min([r[label] for r in rows if r[label] is not None]),
                    "max": max([r[label] for r in rows if r[label] is not None]),
                }
                if sum(1 for r in rows if r[label] is not None) >= 2
                else None
            )
            for label in ["clean", "ROR", "denial"]
        },
    }
    agg_path = args.output_dir / f"summary_{args.variant}.json"
    agg_path.write_text(json.dumps(agg, indent=2, default=str))
    print(f"\n→ aggregate written to {agg_path.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
