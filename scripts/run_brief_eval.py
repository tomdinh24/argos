"""Brief specialist locked-threshold eval.

Pinned by `docs/evals/brief-locked-thresholds.md`. Runs the Brief on
three pre-registered claims (CLM-007, CLM-013, CLM-015) and checks
the four criteria.

Criterion 1 (narrative hallucination check) is gated behind the
`--judge` flag because it requires another LLM call. Without
`--judge`, criterion 1 is reported as `MANUAL` and the composite
verdict abstains. Criteria 2-4 are deterministic.

Usage:
    .venv/bin/python scripts/run_brief_eval.py [--judge]
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPO_ROOT / ".env")

from argos.ontology.caseload_with_realistic_docs import (  # noqa: E402
    build_caseload_with_realistic_docs,
)
from argos.workflows.brief.assembler import assemble  # noqa: E402
from argos.workflows.brief.brief import run_brief  # noqa: E402


RESULTS_ROOT = REPO_ROOT / "data" / "orchestrator-demo" / "workflow-results"
EVAL_OUTPUT_ROOT = REPO_ROOT / "data" / "brief-eval"

# Pre-registered claims, locked in brief-locked-thresholds.md
EVAL_CLAIMS = ["CLM-007", "CLM-013", "CLM-015"]


@dataclass
class CriterionResult:
    name: str
    claim_id: str
    passed: bool | None  # None = MANUAL/abstain
    detail: str


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--judge", action="store_true",
        help="Run the LLM-judge for criterion 1 (narrative hallucinations)."
    )
    args = parser.parse_args()

    caseload = build_caseload_with_realistic_docs()
    EVAL_OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    briefs: dict[str, dict] = {}
    print("=" * 76)
    print("BRIEF EVAL — running on 3 pinned claims")
    print("=" * 76)
    for claim_id in EVAL_CLAIMS:
        print(f"\nRunning brief on {claim_id}...")
        result = run_brief(caseload, claim_id, results_root=RESULTS_ROOT)
        briefs[claim_id] = {
            "brief": result.brief.model_dump(mode="json"),
            "narrative_attempts": result.narrative_attempts,
            "gaps_attempts": result.gaps_attempts,
        }
        out_path = EVAL_OUTPUT_ROOT / f"{claim_id}-brief.json"
        out_path.write_text(
            json.dumps(briefs[claim_id], indent=2, default=str)
        )
        print(f"  → {out_path.relative_to(REPO_ROOT)}")
    print()

    # ---- Criterion 1: narrative factual accuracy (LLM judge or MANUAL) ----
    print("-" * 76)
    print("CRITERION 1 — narrative factual accuracy (no hallucinations)")
    print("-" * 76)
    c1_results: list[CriterionResult] = []
    if args.judge:
        # r2: judge runs N=3 per brief; verdict uses the median count
        # to suppress single-run LLM-judge non-determinism.
        from anthropic import Anthropic
        import os
        from statistics import median
        client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        n_runs = 3
        for claim_id in EVAL_CLAIMS:
            brief_data = briefs[claim_id]["brief"]
            draft = assemble(caseload, claim_id, results_root=RESULTS_ROOT)
            cited_doc_ids = {c["document_id"] for c in brief_data["story_citations"]}
            cited_bodies = [
                f"--- {d.document_id} ---\n{d.body_text}"
                for d in draft.documents if d.document_id in cited_doc_ids
            ]
            judge_prompt = (
                "Below is a one-paragraph claim brief, the loss-facts context "
                "the writer was given, and the cited documents. List every "
                "concrete fact in the brief (dollar amounts, dates, names, "
                "severities, postures, coverage types). For each, mark "
                "SUPPORTED if it appears in loss_facts_hint OR one of the "
                "cited documents, else UNSUPPORTED.\n\n"
                "AUTHORITY RULES:\n"
                "- The loss_facts_hint structured flags (represented, "
                "litigation_flag, complaint_flag, coverage_status, severity) "
                "are AUTHORITATIVE. If the brief states 'unrepresented' "
                "consistent with `represented: False`, mark SUPPORTED even "
                "if cited documents contain attorney correspondence — the "
                "attorney may be writing on someone else's behalf, or the "
                "flag may lag. Same for litigation and coverage_status.\n"
                "- Meta-commentary ('loss details not yet documented on file', "
                "'further information awaited') is NOT a concrete fact. Do "
                "not list it. Do not flag it as UNSUPPORTED.\n"
                "- Soft hedges ('reportedly', 'appears to') do not change a "
                "fact's verdict — judge the underlying claim.\n\n"
                "End with a single line, plain text, NO markdown emphasis: "
                "HALLUCINATIONS: <count>\n\n"
                f"=== BRIEF ===\n{brief_data['story_paragraph']}\n\n"
                f"=== LOSS FACTS HINT ===\n{draft.loss_facts_hint}\n\n"
                f"=== CITED DOCUMENTS ===\n" + "\n\n".join(cited_bodies)
            )

            counts: list[int] = []
            for _ in range(n_runs):
                resp = client.messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=1500,
                    messages=[{"role": "user", "content": judge_prompt}],
                )
                text = "".join(b.text for b in resp.content if b.type == "text")
                counts.append(_parse_hallucinations(text))

            median_count = int(median(counts))
            passed = (median_count == 0)
            c1_results.append(CriterionResult(
                name="narrative_factual_accuracy",
                claim_id=claim_id,
                passed=passed,
                detail=f"median={median_count} (N={n_runs}, counts={counts})",
            ))
            mark = "✓" if passed else "✗"
            print(f"  {mark} {claim_id}: median={median_count} (N={n_runs}, counts={counts})")
    else:
        for claim_id in EVAL_CLAIMS:
            c1_results.append(CriterionResult(
                name="narrative_factual_accuracy",
                claim_id=claim_id,
                passed=None,
                detail="judge not run (--judge omitted)",
            ))
            print(f"  ? {claim_id}: MANUAL (re-run with --judge)")

    # ---- Criterion 2: coverage_status correctness ----
    print()
    print("-" * 76)
    print("CRITERION 2 — coverage_status correctness")
    print("-" * 76)
    expected_status = {"CLM-007": "pending", "CLM-013": "pending", "CLM-015": "pending"}
    c2_results: list[CriterionResult] = []
    for claim_id in EVAL_CLAIMS:
        got = briefs[claim_id]["brief"]["current_status_snapshot"]["coverage_status"]
        want = expected_status[claim_id]
        passed = got == want
        c2_results.append(CriterionResult(
            name="coverage_status",
            claim_id=claim_id,
            passed=passed,
            detail=f"got={got!r} want={want!r}",
        ))
        mark = "✓" if passed else "✗"
        print(f"  {mark} {claim_id}: got={got!r} want={want!r}")

    # ---- Criterion 3: workflow_recommendations completeness ----
    print()
    print("-" * 76)
    print("CRITERION 3 — workflow_recommendations completeness")
    print("-" * 76)
    # Locked expectations (r1, see docs/evals/brief-locked-thresholds.md).
    # Reflects what scripts/run_orchestrator_demo.py persists for each claim.
    expected_recs = {
        "CLM-007": {"reserve"},
        "CLM-013": set(),
        "CLM-015": {"coverage"},
    }
    c3_results: list[CriterionResult] = []
    for claim_id in EVAL_CLAIMS:
        got = {
            r["workflow"]
            for r in briefs[claim_id]["brief"]["workflow_recommendations_summary"]
        }
        want = expected_recs[claim_id]
        passed = got == want
        c3_results.append(CriterionResult(
            name="workflow_recommendations",
            claim_id=claim_id,
            passed=passed,
            detail=f"got={sorted(got)} want={sorted(want)}",
        ))
        mark = "✓" if passed else "✗"
        print(f"  {mark} {claim_id}: got={sorted(got)} want={sorted(want)}")

    # ---- Criterion 4: gap detection recall ----
    print()
    print("-" * 76)
    print("CRITERION 4 — gap detection recall (LLM must not drop rule-detected gaps)")
    print("-" * 76)
    c4_results: list[CriterionResult] = []
    for claim_id in EVAL_CLAIMS:
        # Recompute the expected variables from the rule layer
        draft = assemble(caseload, claim_id, results_root=RESULTS_ROOT)
        expected_variables = {g.variable for g in draft.raw_gaps}
        got_items = {m["item"] for m in briefs[claim_id]["brief"]["missing_info"]}

        # r1: token-substring match. Each variable splits on '_' into tokens;
        # every token must appear as a case-insensitive substring in some item.
        uncovered = [
            v for v in expected_variables
            if not _variable_covered(v, got_items)
        ]
        passed = not uncovered
        c4_results.append(CriterionResult(
            name="gap_recall",
            claim_id=claim_id,
            passed=passed,
            detail=(
                f"variables={sorted(expected_variables)} "
                f"items={sorted(got_items)} "
                f"uncovered={uncovered}"
            ),
        ))
        mark = "✓" if passed else "✗"
        print(f"  {mark} {claim_id}: variables={sorted(expected_variables)}")
        print(f"      items={sorted(got_items)}")
        if uncovered:
            print(f"      UNCOVERED: {uncovered}")

    # ---- Composite verdict ----
    print()
    print("=" * 76)
    all_results = c1_results + c2_results + c3_results + c4_results
    deterministic = [r for r in all_results if r.passed is not None]
    abstained = [r for r in all_results if r.passed is None]
    all_passed = all(r.passed for r in deterministic)

    if abstained:
        verdict = "ABSTAIN" if all_passed else "FAIL"
        print(f"VERDICT: {verdict} (deterministic criteria: "
              f"{sum(1 for r in deterministic if r.passed)}/{len(deterministic)} passed; "
              f"{len(abstained)} criterion-claim entries deferred to manual judge)")
    else:
        verdict = "PASS" if all_passed else "FAIL"
        print(f"VERDICT: {verdict} ({sum(1 for r in deterministic if r.passed)}/{len(deterministic)} criterion-claim entries passed)")
    print("=" * 76)

    # Persist verdict
    verdict_path = EVAL_OUTPUT_ROOT / "last-run.json"
    verdict_path.write_text(json.dumps({
        "ts": datetime.now(timezone.utc).isoformat(),
        "judge_run": args.judge,
        "verdict": verdict,
        "results": [
            {
                "criterion": r.name,
                "claim_id": r.claim_id,
                "passed": r.passed,
                "detail": r.detail,
            }
            for r in all_results
        ],
    }, indent=2, default=str))
    print(f"\nwrote {verdict_path.relative_to(REPO_ROOT)}")

    if verdict == "FAIL":
        return 1
    return 0


def _variable_covered(variable: str, items: set[str]) -> bool:
    """C4 r1 predicate: variable's underscore-split tokens must ALL appear
    as case-insensitive substrings in some item."""
    tokens = [t.lower() for t in variable.split("_") if t]
    lowered_items = [i.lower() for i in items]
    return any(
        all(tok in item for tok in tokens)
        for item in lowered_items
    )


def _parse_hallucinations(text: str) -> int:
    """Pull the trailing HALLUCINATIONS: <N> line from judge output.

    Strips markdown emphasis (`**`, `*`, backticks) — the judge often
    bolds the verdict line, and the unstripped prefix used to break
    parsing silently (sentinel -1).
    """
    for line in reversed(text.splitlines()):
        stripped = line.strip().strip("*").strip("`").strip()
        if stripped.startswith("HALLUCINATIONS:"):
            try:
                return int(stripped.split(":", 1)[1].strip().strip("*").strip("`").strip())
            except (ValueError, IndexError):
                return -1
    return -1


if __name__ == "__main__":
    sys.exit(main())
