"""Run the Document Reader against the locked anchor pairs and apply thresholds.

Spec: docs/specs/document-reader.md
Thresholds:
  v1 (Pairs 1-4 baseline): docs/evals/document-reader-anchor-pairs-thresholds.md
  v2 (Pairs 1-4 controls hardened): docs/evals/document-reader-anchor-pairs-v2-thresholds.md
  v3 (Pairs 5-7 subrogation): docs/evals/document-reader-anchor-pairs-v3-subrogation-thresholds.md

Calls Claude Sonnet 4.6 twice per pair (one shot per variant) — costs
real money. Per-variant + paired-delta checks per the locked thresholds;
PASS only if ALL pairs in the selected subset pass.

Run:
    .venv/bin/python scripts/run_document_reader_anchors.py                    # all 7 pairs
    .venv/bin/python scripts/run_document_reader_anchors.py --version v3       # subrogation only (5,6,7)
    .venv/bin/python scripts/run_document_reader_anchors.py --version v2       # baseline 4 only (1,2,3,4)
    .venv/bin/python scripts/run_document_reader_anchors.py --pair 1           # single pair by index
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPO_ROOT / ".env")

from argos.ontology.document_reader_anchors import AnchorPair, all_pairs  # noqa: E402
from argos.workflows.document_reader import (  # noqa: E402
    DEFAULT_MODEL,
    ClaimContext,
    DocumentInput,
    RelevanceCallResult,
    run_document_reader,
)


EVAL_DIR = REPO_ROOT / "data" / "eval-runs" / "document-reader-anchors"
EVAL_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_PATH = EVAL_DIR / "anchor_pairs_run.json"

# Substring/overlap tolerance for text_excerpt verification.
EXCERPT_OVERLAP_THRESHOLD = 0.80


def excerpt_overlaps(excerpt: str, body: str) -> tuple[bool, float]:
    """Return (passes, best_ratio). Passes if excerpt is a substring of
    body OR has ≥EXCERPT_OVERLAP_THRESHOLD ratio with some substring of
    body roughly the excerpt's length."""
    if not excerpt:
        return False, 0.0
    if excerpt in body:
        return True, 1.0
    # Fallback: sliding-window best ratio
    ex_len = len(excerpt)
    best = 0.0
    # coarse stride for speed; eval bodies are ~2KB, excerpts ~50-200 chars
    stride = max(1, ex_len // 4)
    for start in range(0, max(1, len(body) - ex_len + 1), stride):
        window = body[start : start + ex_len]
        ratio = SequenceMatcher(None, excerpt, window).ratio()
        if ratio > best:
            best = ratio
            if best >= 0.99:
                break
    return best >= EXCERPT_OVERLAP_THRESHOLD, best


def excerpt_overlaps_with(excerpt: str, target_sentence: str) -> tuple[bool, float]:
    """Specifically check whether the excerpt overlaps with the
    added_sentence (used for Variant B directionality check)."""
    if not excerpt:
        return False, 0.0
    if excerpt in target_sentence or target_sentence in excerpt:
        return True, 1.0
    ratio = SequenceMatcher(None, excerpt, target_sentence).ratio()
    return ratio >= EXCERPT_OVERLAP_THRESHOLD, ratio


def evaluate_variant(
    pair: AnchorPair,
    variant_label: str,
    doc: DocumentInput,
    expected_relevant: bool,
    expected_posture: str | None,
    ctx: ClaimContext,
    added_sentence: str,
) -> dict:
    """Run the Reader on one variant and apply the locked per-variant +
    paired-delta criteria. Returns a structured result dict."""

    print(f"  → {pair.pair_id} variant {variant_label}: calling Reader...")
    try:
        result: RelevanceCallResult = run_document_reader(doc, ctx)
    except Exception as e:
        return {
            "pair_id": pair.pair_id,
            "variant": variant_label,
            "expected_relevant": expected_relevant,
            "expected_posture": expected_posture,
            "schema_valid": False,
            "runtime_error": str(e),
            "checks": {"any_pass": False},
        }

    call = result.call
    checks: dict[str, dict] = {}

    # 1. Schema validation already passed (Pydantic in run_document_reader)
    checks["schema_valid"] = {"passed": True, "detail": "Pydantic validation passed"}

    # 2. Excerpt iff relevant (Pydantic enforces, double-check at logic level)
    excerpt_iff_relevant = (call.relevant and bool(call.text_excerpt.strip())) or (
        not call.relevant and not call.text_excerpt.strip()
    )
    checks["excerpt_iff_relevant"] = {"passed": excerpt_iff_relevant}

    # 3. Posture iff relevant (also Pydantic, double-check)
    posture_iff_relevant = (call.relevant and call.posture_changed is not None) or (
        not call.relevant and call.posture_changed is None
    )
    checks["posture_iff_relevant"] = {"passed": posture_iff_relevant}

    # 4. Excerpt verbatim in document body (when relevant)
    if call.relevant:
        in_body, body_ratio = excerpt_overlaps(call.text_excerpt, doc.body_text)
        checks["excerpt_in_body"] = {
            "passed": in_body,
            "overlap_ratio": round(body_ratio, 3),
        }
    else:
        checks["excerpt_in_body"] = {"passed": True, "detail": "n/a (relevant=False)"}

    # 5. relevance matches expected
    checks["relevant_matches"] = {
        "passed": call.relevant == expected_relevant,
        "expected": expected_relevant,
        "actual": call.relevant,
    }

    # 6. posture matches expected (when relevant)
    if expected_relevant:
        checks["posture_matches"] = {
            "passed": call.posture_changed == expected_posture,
            "expected": expected_posture,
            "actual": call.posture_changed,
        }
    else:
        checks["posture_matches"] = {"passed": True, "detail": "n/a (relevant=False)"}

    # 8 (paired-delta excerpt directionality, applies only on variant B)
    if variant_label == "B" and call.relevant:
        quotes_added, added_ratio = excerpt_overlaps_with(call.text_excerpt, added_sentence)
        checks["excerpt_directionality"] = {
            "passed": quotes_added,
            "overlap_with_added_sentence": round(added_ratio, 3),
        }
    elif variant_label == "A":
        checks["excerpt_directionality"] = {
            "passed": not call.text_excerpt.strip(),
            "detail": "Variant A excerpt must be empty",
        }
    else:
        # Variant B but relevant=False — already failed at relevant_matches.
        checks["excerpt_directionality"] = {
            "passed": False,
            "detail": "Variant B relevant=False, cannot check directionality",
        }

    all_passed = all(c["passed"] for c in checks.values())

    return {
        "pair_id": pair.pair_id,
        "posture": pair.posture,
        "variant": variant_label,
        "expected_relevant": expected_relevant,
        "expected_posture": expected_posture,
        "actual_relevant": call.relevant,
        "actual_posture": call.posture_changed,
        "actual_reason": call.reason,
        "actual_text_excerpt": call.text_excerpt,
        "model": result.model,
        "attempts": result.attempts,
        "schema_valid": True,
        "checks": {k: v for k, v in checks.items()},
        "all_per_variant_checks_passed": all_passed,
    }


def evaluate_pair(pair: AnchorPair) -> dict:
    """Run both variants of one pair and apply the paired-delta criteria."""
    print(f"\nPair: {pair.pair_id} ({pair.posture})")

    a = evaluate_variant(
        pair,
        "A",
        pair.variant_a,
        expected_relevant=False,
        expected_posture=None,
        ctx=pair.context,
        added_sentence=pair.added_sentence,
    )
    b = evaluate_variant(
        pair,
        "B",
        pair.variant_b,
        expected_relevant=True,
        expected_posture=pair.posture,
        ctx=pair.context,
        added_sentence=pair.added_sentence,
    )

    # 7. Paired-delta: relevance flip
    relevance_flip = (
        a.get("actual_relevant") is False and b.get("actual_relevant") is True
    )

    pair_passed = (
        a.get("all_per_variant_checks_passed", False)
        and b.get("all_per_variant_checks_passed", False)
        and relevance_flip
    )

    return {
        "pair_id": pair.pair_id,
        "posture": pair.posture,
        "variant_a_result": a,
        "variant_b_result": b,
        "paired_delta_relevance_flip": relevance_flip,
        "pair_passed": pair_passed,
    }


VERSION_SUBSETS = {
    "v2": [1, 2, 3, 4],  # liability, coverage, damages, reserve (baseline 4)
    "v3": [5, 6, 7],     # subrogation (3 added 2026-06-02)
    "all": [1, 2, 3, 4, 5, 6, 7],
}


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--pair",
        type=int,
        choices=[1, 2, 3, 4, 5, 6, 7],
        help=(
            "Run only one pair by 1-indexed slot "
            "(1=liability, 2=coverage, 3=damages, 4=reserve, "
            "5/6/7=subrogation)"
        ),
    )
    group.add_argument(
        "--version",
        choices=["v2", "v3", "all"],
        default="all",
        help=(
            "Run a version subset (default: all). "
            "v2 = baseline 4 (Pairs 1-4); "
            "v3 = subrogation 3 (Pairs 5-7)."
        ),
    )
    args = parser.parse_args()

    print("=" * 72)
    print("DOCUMENT READER — ANCHOR-PAIR BENCHMARK")
    print(f"Model: {DEFAULT_MODEL}")
    print(f"Subset: {'pair ' + str(args.pair) if args.pair else args.version}")
    print("=" * 72)

    pairs = all_pairs()
    if args.pair is not None:
        pairs = [pairs[args.pair - 1]]
    else:
        pairs = [pairs[i - 1] for i in VERSION_SUBSETS[args.version]]

    pair_results = [evaluate_pair(p) for p in pairs]

    # ============================================================
    # Per-pair report
    # ============================================================
    print()
    print("=" * 72)
    print("PER-PAIR RESULTS")
    print("=" * 72)
    for pr in pair_results:
        status = "PASS" if pr["pair_passed"] else "FAIL"
        print(f"\n[{status}] {pr['pair_id']} ({pr['posture']})")
        for variant_key in ("variant_a_result", "variant_b_result"):
            v = pr[variant_key]
            print(f"  Variant {v['variant']}:")
            print(
                f"    expected: relevant={v['expected_relevant']}, "
                f"posture={v['expected_posture']}"
            )
            print(
                f"    actual:   relevant={v.get('actual_relevant')}, "
                f"posture={v.get('actual_posture')}"
            )
            print(f"    reason: {v.get('actual_reason', '(error)')}")
            if v.get("actual_text_excerpt"):
                excerpt = v["actual_text_excerpt"]
                preview = excerpt[:120] + ("..." if len(excerpt) > 120 else "")
                print(f"    excerpt: \"{preview}\"")
            for ck_name, ck in v["checks"].items():
                mark = "✓" if ck["passed"] else "✗"
                extra = ""
                for k, val in ck.items():
                    if k == "passed":
                        continue
                    extra += f" {k}={val}"
                print(f"      {mark} {ck_name}{extra}")
        print(f"  paired-delta relevance_flip: {pr['paired_delta_relevance_flip']}")

    # ============================================================
    # Composite verdict (only meaningful when running the full 4)
    # ============================================================
    print()
    print("=" * 72)
    print("COMPOSITE VERDICT")
    print("=" * 72)
    all_passed = all(pr["pair_passed"] for pr in pair_results)
    n_total = len(pair_results)
    n_pass = sum(1 for p in pair_results if p["pair_passed"])
    postures = sorted({p["posture"] for p in pair_results})
    subset_label = (
        f"pair {args.pair}" if args.pair else args.version
    )
    if args.pair is not None:
        composite = (
            f"PARTIAL RUN (1 pair) — "
            f"{'PASS' if all_passed else 'FAIL'} on the subset. "
            "Composite ship/no-ship requires the full version subset run."
        )
    elif all_passed:
        composite = (
            f"SHIP ({subset_label}) — Reader classifies relevance from evidence "
            f"on {n_total} pair(s) covering posture(s): {', '.join(postures)}. "
            f"Schema valid, excerpts verbatim, paired-delta directionality holds."
        )
    else:
        composite = (
            f"DO NOT SHIP ({subset_label}) — {n_pass}/{n_total} pairs passed. "
            "Per locked thresholds, Reader ships only when all pairs in the "
            "subset pass. Failure detail above."
        )
    print(composite)

    # ============================================================
    # Persist run
    # ============================================================
    OUTPUT_PATH.write_text(json.dumps({
        "run_timestamp": datetime.now(timezone.utc).isoformat(),
        "spec": "docs/specs/document-reader.md",
        "thresholds": {
            "v2": "docs/evals/document-reader-anchor-pairs-v2-thresholds.md",
            "v3": "docs/evals/document-reader-anchor-pairs-v3-subrogation-thresholds.md",
        },
        "subset": subset_label,
        "model": DEFAULT_MODEL,
        "pairs_run": [pr["pair_id"] for pr in pair_results],
        "pair_results": pair_results,
        "composite_verdict": composite,
        "all_passed": all_passed,
    }, indent=2))
    print()
    print(f"wrote {OUTPUT_PATH.relative_to(REPO_ROOT)}")
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
