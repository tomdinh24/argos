"""Triage ranker — hybrid v2 (LLM materiality re-rank).

Pure orchestration: takes S1's ranking, hands the top-N slice to
GPT-5.5-pro for materiality re-ranking, splices the re-ranked slice
back in front of S1's tail.

Spec: docs/specs/triage-ranker-hybrid-v2.md
Thresholds: docs/evals/triage-ranker-hybrid-v2-thresholds.md

The judge model, slice size, prompt template, and schema validation
rules are LOCKED in the spec. Changing any of them without revising
the spec invalidates the v2 eval.
"""
from __future__ import annotations

import csv
import io
import os
import re
from dataclasses import dataclass

from argos.ontology.types import Caseload
from argos.services.triage.features import extract_raw
from argos.services.triage.ranker import RankedItem, Weights, rank


# === LOCKED CONSTANTS (changing any of these invalidates the v2 eval) =====

JUDGE_MODEL = "gpt-5.5-pro"
TOP_N = 10
JUDGE_REASONING_EFFORT = "medium"

# === Prompt template — LOCKED ============================================

_PROMPT_PREAMBLE = """\
You are an experienced claims adjuster. It is 9 AM on Friday, May 29, 2026.

A deterministic ranker has already scored your full open caseload and \
selected its top {n} claims as the "needs attention soon" band. Your job \
is to re-rank ONLY these {n} claims by what you should actually work on \
today, in light of:

- The deterministic ranker's own rank for each claim (so you know what \
the linear model thought)
- The full 12-feature signal vector
- Recent claimant communications (last two per claim)

Apply adjuster judgment the linear scorer cannot. Examples:
- Litigation + statute under 60 days = top-3 regardless of other features
- Complaint with represented claimant needs same-day acknowledgment
- A "stale" file with a settlement window approaching may outrank a \
fresher file with no clock

You may agree with the deterministic ranker (it scored these {n} \
correctly) or re-order. Do not introduce claims outside this slice. Do \
not omit any of the {n}.

Return your re-ranked list as CSV with the exact header below, {n} rows, \
no extra commentary outside the CSV block:

```csv
rank,request_id,reason_short
1,REQ-XXX,one-line reason
...
{n},REQ-XXX,one-line reason
```

Top-{n} slice (deterministic ranker's ordering shown first):
"""


# === Public surface ======================================================


@dataclass(frozen=True)
class HybridResult:
    """The output of hybrid v2. Same shape as v1's `RankedItem` list."""

    items: list[RankedItem]
    judge_raw_response: str  # full LLM output, for audit
    schema_valid: bool       # did the judge return a parseable, valid CSV?
    failure_reason: str | None = None  # set iff schema_valid is False


def re_rank(
    caseload: Caseload,
    s1_weights: Weights,
    *,
    top_n: int = TOP_N,
    judge_model: str = JUDGE_MODEL,
) -> HybridResult:
    """Run S1, hand the top-N slice to the LLM judge, splice the result.

    Determinism: S1 is deterministic; the judge call is not. Each call
    to `re_rank` may produce a different `items` ordering for the same
    inputs. The benchmark uses `temperature=0` to minimize per-call
    variance, but variance is expected.

    Raises:
        RuntimeError if the OpenAI SDK is not installed or
        `OPENAI_API_KEY` is unset. Schema-validation failures are
        captured in `HybridResult.schema_valid=False`, NOT raised.
    """
    s1_full = rank(caseload, s1_weights)
    if len(s1_full) < top_n:
        raise ValueError(
            f"Caseload has {len(s1_full)} requests, cannot re-rank top {top_n}"
        )

    slice_top = s1_full[:top_n]
    tail = s1_full[top_n:]

    prompt = _build_prompt(caseload, slice_top, s1_weights, top_n=top_n)
    judge_response = _call_judge(prompt, model=judge_model)

    reranked_ids, parse_error = _parse_judge_csv(
        judge_response,
        expected_n=top_n,
        allowed_ids={item.request_id for item in slice_top},
    )

    if parse_error is not None:
        return HybridResult(
            items=s1_full,  # fall back to S1's ordering on parse failure
            judge_raw_response=judge_response,
            schema_valid=False,
            failure_reason=parse_error,
        )

    # Rebuild RankedItem list: judge ordering for the top, S1 for the tail.
    # Scores in the top slice are not meaningful (judge didn't emit them);
    # we preserve S1's score for the same request_id for traceability.
    s1_score_by_id = {item.request_id: item.score for item in slice_top}
    new_items = [
        RankedItem(rank=i + 1, request_id=rid, score=s1_score_by_id[rid])
        for i, rid in enumerate(reranked_ids)
    ] + [
        RankedItem(rank=top_n + i + 1, request_id=item.request_id, score=item.score)
        for i, item in enumerate(tail)
    ]

    return HybridResult(
        items=new_items,
        judge_raw_response=judge_response,
        schema_valid=True,
    )


# === Internals ===========================================================


def _build_prompt(
    caseload: Caseload,
    slice_top: list[RankedItem],
    s1_weights: Weights,
    *,
    top_n: int,
) -> str:
    raw = extract_raw(caseload)
    blocks: list[str] = []
    for item in slice_top:
        rid = item.request_id
        rf = raw[rid]
        request = next(r for r in caseload.requests if r.request_id == rid)
        claim = caseload.claim_for(request)
        # Most recent 2 claimant communications
        comms = sorted(
            (c for c in caseload.communications
             if c.claim_id == claim.claim_id and c.party_role == "claimant"),
            key=lambda c: c.timestamp,
            reverse=True,
        )[:2]
        comm_lines = "\n".join(
            f"    - {c.timestamp.date().isoformat()} {c.channel} {c.direction}: {c.summary}"
            for c in comms
        ) or "    - (no claimant communications on file)"
        block = (
            f"### {rid}\n"
            f"- deterministic_rank: {item.rank} (of {top_n})\n"
            f"- deterministic_score: {item.score:.3f}\n"
            f"- severity: {request.severity_tier}\n"
            f"- opened_date: {claim.opened_date.isoformat()}\n"
            f"- service_deadline_hours: {_fmt(rf.hours_until_sla_breach, 'hours_or_none')}\n"
            f"- legal_deadline_days: {_fmt(rf.days_until_statute, 'days_or_none')}\n"
            f"- hours_since_last_activity: {rf.hours_since_last_touch:.1f}\n"
            f"- overdue_tasks: {int(rf.open_diary_count)}\n"
            f"- total_incurred: ${rf.incurred_amount:,.0f}\n"
            f"- days_since_last_claimant_contact: {rf.days_since_claimant_contact:.1f}\n"
            f"- new_documents: {int(rf.unread_document_count)}\n"
            f"- litigation: {bool(rf.litigation_flag)}\n"
            f"- claimant_represented: {bool(rf.rep_flag)}\n"
            f"- complaint: {bool(rf.complaint_flag)}\n"
            f"- recent_claimant_comms:\n{comm_lines}\n"
        )
        blocks.append(block)

    return _PROMPT_PREAMBLE.format(n=top_n) + "\n" + "\n".join(blocks)


def _fmt(v: float, kind: str) -> str:
    if kind == "hours_or_none":
        return f"{v:.1f}" if v < 24 * 14 else "none"
    if kind == "days_or_none":
        return f"{int(v)}" if v < 365 else "none"
    return str(v)


def _call_judge(prompt: str, *, model: str) -> str:
    """Call the OpenAI Responses API and return the model's output text.

    Imports openai lazily so the rest of the module is importable without
    the SDK (the tests stub `_call_judge` directly).
    """
    try:
        from openai import OpenAI
    except ImportError as e:
        raise RuntimeError(
            "openai package not installed; required for hybrid v2 judge"
        ) from e
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError(
            "OPENAI_API_KEY not set; required for hybrid v2 judge"
        )
    client = OpenAI()
    resp = client.responses.create(
        model=model,
        input=prompt,
        reasoning={"effort": JUDGE_REASONING_EFFORT},
    )
    parts: list[str] = []
    for item in resp.output:
        if getattr(item, "type", None) == "message":
            for block in item.content:
                if getattr(block, "type", None) == "output_text":
                    parts.append(block.text)
    return "\n".join(parts)


# Schema validation — strict, no auto-recovery
_CSV_BLOCK = re.compile(r"```csv\s*\n(.*?)\n```", re.DOTALL)


def _parse_judge_csv(
    response: str,
    *,
    expected_n: int,
    allowed_ids: set[str],
) -> tuple[list[str], str | None]:
    """Parse the judge's CSV block; return (ordered_ids, error_or_None).

    Strict schema rules:
      - Response must contain a ```csv ... ``` fenced block.
      - Block must have header `rank,request_id,reason_short`.
      - Exactly `expected_n` data rows.
      - Ranks must be 1..N with no gaps or duplicates.
      - request_ids must be unique and a subset of `allowed_ids`.
    """
    match = _CSV_BLOCK.search(response)
    if not match:
        return [], "no fenced ```csv ... ``` block in judge response"

    csv_text = match.group(1)
    try:
        rows = list(csv.DictReader(io.StringIO(csv_text)))
    except csv.Error as e:
        return [], f"CSV parse error: {e}"

    if not rows:
        return [], "CSV block has no data rows"

    required_cols = {"rank", "request_id", "reason_short"}
    if not required_cols.issubset(rows[0].keys()):
        return [], (
            f"CSV header missing columns. Got {list(rows[0].keys())}, "
            f"need {sorted(required_cols)}"
        )

    if len(rows) != expected_n:
        return [], f"expected {expected_n} rows, got {len(rows)}"

    try:
        ranks = [int(r["rank"]) for r in rows]
    except (ValueError, KeyError) as e:
        return [], f"non-integer rank value: {e}"

    if sorted(ranks) != list(range(1, expected_n + 1)):
        return [], f"ranks must be 1..{expected_n} with no gaps; got {sorted(ranks)}"

    ids = [r["request_id"].strip() for r in rows]
    if len(set(ids)) != len(ids):
        return [], "duplicate request_id in judge output"

    stray = set(ids) - allowed_ids
    if stray:
        return [], f"judge returned request_ids not in input slice: {sorted(stray)}"

    # Reorder by rank ascending so callers get rank-1 first.
    ordered = [r["request_id"].strip() for r in sorted(rows, key=lambda r: int(r["rank"]))]
    return ordered, None
