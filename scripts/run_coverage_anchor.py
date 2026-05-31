"""Run the Coverage specialist against both anchor-pair variants and report.

Outputs (per variant):
- Schema-validated CoverageReport
- Citation verifier result
- Recommendation-prose regex result
- (Optional) premise-grounding judge result

Then prints the paired-delta evaluation against the pre-written thresholds
in docs/evals/coverage-anchor-pair-thresholds.md.

Usage:
    .venv/bin/python scripts/run_coverage_anchor.py
    .venv/bin/python scripts/run_coverage_anchor.py --skip-judge   # faster
    .venv/bin/python scripts/run_coverage_anchor.py --variant clean
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

from argos.ontology.synthetic import build_anchor_variant  # noqa: E402
from argos.ontology.types import SyntheticClaim  # noqa: E402
from argos.schemas.specialists.coverage import CoverageReport  # noqa: E402
from argos.specialists.checks import (  # noqa: E402
    check_premise_grounding,
    check_recommendation_prose,
    verify_citations,
)
from argos.specialists.coverage import DEFAULT_MODEL, run_coverage  # noqa: E402


VariantName = Literal["clean", "with_flag"]


_OUTCOME_LABEL_SPLIT = re.compile(r"[—:\-(]")


def _classify_outcome(claim_text: str) -> str:
    """Classify a synthesis outcome by its *label prefix*, not by substring.

    Models often write a label-then-explanation form: "Clean coverage: ... with no
    reservation needed." Substring matching for "reservation" then misclassifies
    that as ROR. The fix is to look only at the label prefix (text before the
    first colon / em-dash / parenthesis), then check denial -> ROR -> clean in
    that order so that "denial" wins over a stray "covered" in the same prefix.
    """
    prefix = _OUTCOME_LABEL_SPLIT.split(claim_text, maxsplit=1)[0].strip().lower()
    if "denial" in prefix or "denied" in prefix:
        return "denial"
    if "reservation" in prefix or "ror" in prefix:
        return "ROR"
    if "clean" in prefix or "covered" in prefix or "coverage" in prefix:
        return "clean"
    return "?"


def _outcome_mass(analysis: CoverageReport, kind: str) -> float | None:
    """Return the probability mass for the outcome of the given kind (clean/ROR/denial)."""
    for o in analysis.synthesis.outcomes:
        if _classify_outcome(o.claim_text) == kind:
            return o.probability
    return None


_SCOPE_CONTEXT_WORDS = (
    "course", "employment", "business", "operation", "work", "duty",
    "on-duty", "authorized", "permissive", "permission", "in-scope",
    "in scope", "out of scope", "out-of-scope", "use",
)


def _find_course_and_scope_assessment(
    analysis: CoverageReport,
) -> tuple[float, str] | None:
    """Return (probability, claim_text) for the course-and-scope Assessment, if present.

    The legal concept is "course and scope of employment / business use." Models
    paraphrase ("within the scope of authorized use", "in furtherance of
    business operations"). Match on "scope" + any operational context word.
    """
    for a in analysis.assessments:
        t = a.claim_text.lower()
        if "scope" in t and any(w in t for w in _SCOPE_CONTEXT_WORDS):
            return a.probability, a.claim_text
        if "course" in t and ("employment" in t or "business" in t):
            return a.probability, a.claim_text
    return None


def _has_home_quote_citation(analysis: CoverageReport) -> bool:
    """True if any citation in the analysis references the 'home' quote text."""
    needle = "on my way home"
    # Check evidence_found
    for c in analysis.evidence_found:
        if needle in c.text_excerpt.lower():
            return True
    for a in analysis.assessments:
        for c in a.evidence_citations:
            if needle in c.text_excerpt.lower():
                return True
    for o in analysis.synthesis.outcomes:
        for c in o.evidence_citations:
            if needle in c.text_excerpt.lower():
                return True
    return False


def _print_analysis_summary(name: str, analysis: CoverageReport) -> None:
    print(f"\n=== {name.upper()} — Coverage analysis ===")
    print(f"  request_id: {analysis.request_id}")
    print(f"  reviewed_as_of: {analysis.reviewed_as_of}")
    print(f"  evidence_found: {len(analysis.evidence_found)} citations")
    print(f"  assessments: {len(analysis.assessments)}")
    for i, a in enumerate(analysis.assessments):
        cits = ", ".join(
            (c.document_id or c.sourced_rule_id or c.ledger_entry_id or "?")
            for c in a.evidence_citations
        )
        print(f"    [{i}] p={a.probability:.3f}  {a.claim_text}")
        print(f"         cites: {cits}")
    print(f"  synthesis.outcomes ({len(analysis.synthesis.outcomes)}, sum to 1.0):")
    for o in analysis.synthesis.outcomes:
        print(f"    p={o.probability:.3f}  {o.claim_text}")
    print(f"  coverage_analysis_memo: {len(analysis.coverage_analysis_memo.body)} chars")
    print(f"  ror_letter: {'drafted' if analysis.ror_letter else 'not drafted'}")
    print(f"  denial_letter: {'drafted' if analysis.denial_letter else 'not drafted'}")


def _print_check(name: str, result: object) -> None:
    summary = getattr(result, "summary", str(result))
    print(f"  {name}: {summary}")


def _run_one(
    *,
    name: VariantName,
    claim: SyntheticClaim,
    skip_judge: bool,
    output_dir: Path,
    model: str,
) -> tuple[CoverageReport, dict[str, object]]:
    print(f"\n{'='*70}\nRunning Coverage on variant: {name}  (model={model})\n{'='*70}")
    result = run_coverage(claim, model=model)
    print(f"  → model: {result.model}, attempts: {result.attempts}")

    _print_analysis_summary(name, result.analysis)

    print(f"\n--- Post-runtime checks ({name}) ---")
    citation_result = verify_citations(result.analysis, claim)
    _print_check("citation verifier", citation_result)
    if not citation_result.passed:
        for v in citation_result.violations:
            print(f"      ✗ {v.where}: {v.reason}")
            print(f"        excerpt: {v.text_excerpt[:120]!r}")

    rec_result = check_recommendation_prose(result.analysis)
    _print_check("recommendation regex", rec_result)
    if not rec_result.passed:
        for hit in rec_result.hits:
            print(f"      ✗ {hit.where}: matched {hit.pattern_label!r}")
            print(f"        context: {hit.surrounding}")

    judge_result = None
    if skip_judge:
        print("  premise grounding: SKIPPED (--skip-judge)")
    else:
        judge_result = check_premise_grounding(result.analysis, claim)
        _print_check("premise grounding", judge_result)
        if not judge_result.passed:
            for u in judge_result.ungrounded:
                print(f"      ✗ [assessment {u.assessment_index}] {u.flagged_claim}")
                print(f"        judge: {u.judge_reasoning}")

    # Persist outputs for review
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{name}.json"
    payload = {
        "variant": name,
        "model": result.model,
        "attempts": result.attempts,
        "analysis": result.raw_tool_input,
        "checks": {
            "citation_verifier": {
                "passed": citation_result.passed,
                "total_checked": citation_result.total_checked,
                "violations": [asdict(v) for v in citation_result.violations],
            },
            "recommendation_regex": {
                "passed": rec_result.passed,
                "drafts_checked": rec_result.drafts_checked,
                "hits": [asdict(h) for h in rec_result.hits],
            },
            "premise_grounding": (
                None
                if judge_result is None
                else {
                    "passed": judge_result.passed,
                    "judge_model": judge_result.judge_model,
                    "assessments_checked": judge_result.assessments_checked,
                    "total_claims_extracted": judge_result.total_claims_extracted,
                    "ungrounded": [asdict(u) for u in judge_result.ungrounded],
                }
            ),
        },
    }
    out_path.write_text(json.dumps(payload, indent=2, default=str))
    try:
        display_path = out_path.relative_to(PROJECT_ROOT)
    except ValueError:
        display_path = out_path
    print(f"\n  → output written to {display_path}")

    checks = {
        "citation": citation_result,
        "recommendation": rec_result,
        "premise_grounding": judge_result,
    }
    return result.analysis, checks


def _paired_delta_report(
    clean: CoverageReport, flagged: CoverageReport
) -> tuple[list[tuple[str, bool, str]], bool]:
    """Compute the four paired-delta criteria; return (per-check rows, overall pass)."""
    rows: list[tuple[str, bool, str]] = []

    a_ror = _outcome_mass(clean, "ROR")
    b_ror = _outcome_mass(flagged, "ROR")
    if a_ror is None or b_ror is None:
        rows.append(("ROR delta ≥ 0.05", False, "could not locate ROR outcome in one or both variants"))
    else:
        delta = b_ror - a_ror
        rows.append((
            "ROR delta ≥ 0.05",
            delta >= 0.05,
            f"clean={a_ror:.3f}, flagged={b_ror:.3f}, delta={delta:+.3f}",
        ))

    a_clean = _outcome_mass(clean, "clean")
    b_clean = _outcome_mass(flagged, "clean")
    if a_clean is None or b_clean is None:
        rows.append(("Clean delta ≥ 0.05", False, "could not locate clean-coverage outcome in one or both variants"))
    else:
        delta = a_clean - b_clean
        rows.append((
            "Clean delta ≥ 0.05",
            delta >= 0.05,
            f"clean={a_clean:.3f}, flagged={b_clean:.3f}, delta={delta:+.3f}",
        ))

    a_cs = _find_course_and_scope_assessment(clean)
    b_cs = _find_course_and_scope_assessment(flagged)
    if a_cs is None or b_cs is None:
        rows.append((
            "Course-and-scope assessment delta ≥ 0.05",
            False,
            f"missing assessment: clean={a_cs is not None}, flagged={b_cs is not None}",
        ))
    else:
        delta = a_cs[0] - b_cs[0]
        rows.append((
            "Course-and-scope assessment delta ≥ 0.05",
            delta >= 0.05,
            f"clean={a_cs[0]:.3f}, flagged={b_cs[0]:.3f}, delta={delta:+.3f}",
        ))

    a_quote = _has_home_quote_citation(clean)
    b_quote = _has_home_quote_citation(flagged)
    rows.append((
        "Citation directionality (flagged cites home-quote, clean does not)",
        (b_quote and not a_quote),
        f"clean_has_quote={a_quote}, flagged_has_quote={b_quote}",
    ))

    overall = all(passed for _, passed, _ in rows)
    return rows, overall


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--variant",
        choices=["clean", "with_flag", "both"],
        default="both",
        help="Which variant to run (default: both)",
    )
    parser.add_argument(
        "--skip-judge",
        action="store_true",
        help="Skip the premise-grounding judge (saves an Anthropic call per assessment).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "data" / "eval-runs" / "coverage-anchor-pair",
        help="Where to write per-variant JSON outputs",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Anthropic model ID (default: {DEFAULT_MODEL}).",
    )
    args = parser.parse_args()

    variants: list[VariantName] = (
        ["clean", "with_flag"] if args.variant == "both" else [args.variant]
    )

    analyses: dict[str, CoverageReport] = {}
    all_checks: dict[str, dict[str, object]] = {}
    for v in variants:
        claim = build_anchor_variant(v)
        analysis, checks = _run_one(
            name=v,
            claim=claim,
            skip_judge=args.skip_judge,
            output_dir=args.output_dir,
            model=args.model,
        )
        analyses[v] = analysis
        all_checks[v] = checks

    if "clean" in analyses and "with_flag" in analyses:
        print(f"\n{'='*70}\nPAIRED-DELTA EVAL (against locked thresholds)\n{'='*70}")
        rows, overall = _paired_delta_report(analyses["clean"], analyses["with_flag"])
        for label, passed, detail in rows:
            mark = "✓" if passed else "✗"
            print(f"  {mark}  {label}")
            print(f"      {detail}")
        print()
        print(f"OVERALL: {'PASS' if overall else 'FAIL'}")

        # Per-variant check rollup
        print()
        print("POST-RUNTIME CHECK ROLLUP:")
        for v in ["clean", "with_flag"]:
            cit = all_checks[v]["citation"]
            rec = all_checks[v]["recommendation"]
            pg = all_checks[v]["premise_grounding"]
            print(f"  {v}: citation={getattr(cit,'passed',None)} recommendation={getattr(rec,'passed',None)} premise_grounding={getattr(pg,'passed',None) if pg is not None else 'skipped'}")

        return 0 if overall else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
