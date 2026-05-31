"""Triage ranker — policy-engine architecture.

Three-layer design (see `docs/specs/triage-ranker-policy-engine.md`):

1. **Policy engine (this module).** Deterministic gates on absolute
   raw-feature thresholds sort every claim into one of seven buckets.
   Buckets are ordered by precedence: bucket 1 always beats bucket 2.

2. **Within-bucket scorer (also this module).** Inside each bucket, a
   small bucket-specific sort key orders claims. Tiebreak is always
   `request_id` ascending.

3. **LLM specialists (out of scope here).** Document materiality,
   next-required-action, escalation-language detection — feed bucket
   triggers but live in their own modules.

The contract for this module is "given a Caseload, return a total
order over CoverageRequests with bucket + why_today annotations." No
LLM calls. No randomness. No wall-clock reads.

Triggers and within-bucket sort keys are pinned by
`docs/evals/triage-ranker-policy-engine-thresholds.md` (locked
2026-05-30).
"""
from __future__ import annotations

from dataclasses import dataclass

from argos.ontology.types import Caseload
from argos.services.triage.features import (
    RawFeatures,
    extract_features,
    extract_raw,
)
from argos.services.triage.ranker import DEFAULT_WEIGHTS, Weights, score


# --- Locked policy thresholds (from thresholds doc) ------------------------

SLA_SAME_DAY_HOURS: float = 24.0           # bucket 1
STAT_IMMINENT_DAYS: float = 7.0            # bucket 2
LIT_CLOCK_STAT_DAYS: float = 60.0          # bucket 3 — statute window
STAT_APPROACHING_MAX_DAYS: float = 30.0    # bucket 5 (upper)
HIGH_EXPOSURE_INCURRED: float = 250_000.0  # bucket 6

# Bucket precedence is the order of evaluation. First match wins.
BUCKET_NAMES: dict[int, str] = {
    1: "same-day mandatory",
    2: "statute imminent",
    3: "litigation + clock",
    4: "regulatory escalation",
    5: "statute approaching",
    6: "high exposure + action trigger",
    7: "routine work",
}


# --- Public output ---------------------------------------------------------


@dataclass(frozen=True)
class PolicyRankedItem:
    """One row of policy-engine output.

    `bucket` is 1..7; `within_bucket_rank` is 1-based inside the bucket;
    `rank` is the 1-based global rank after concatenating buckets in
    precedence order.
    """

    rank: int
    bucket: int
    bucket_name: str
    within_bucket_rank: int
    request_id: str
    why_today: str
    within_bucket_score: float


# --- Bucket assignment -----------------------------------------------------


def assign_bucket(raw: RawFeatures) -> tuple[int, str]:
    """Apply locked policy triggers to one raw-feature row. Returns
    `(bucket_number, why_today)`. First trigger that matches wins."""

    # 1 — same-day mandatory: SLA fires today
    if raw.hours_until_sla_breach < SLA_SAME_DAY_HOURS:
        return 1, f"SLA breach in {raw.hours_until_sla_breach:.1f}h"

    # 2 — statute imminent
    if raw.days_until_statute <= STAT_IMMINENT_DAYS:
        return 2, f"statute {int(raw.days_until_statute)}d"

    # 3 — litigation active with clock pressure
    if raw.litigation_flag == 1.0 and (
        raw.days_until_statute <= LIT_CLOCK_STAT_DAYS
        or raw.open_diary_count >= 1
    ):
        clock = (
            f"statute {int(raw.days_until_statute)}d"
            if raw.days_until_statute <= LIT_CLOCK_STAT_DAYS
            else f"{int(raw.open_diary_count)} overdue diary"
        )
        return 3, f"litigation + {clock}"

    # 4 — regulatory escalation (any complaint flag)
    if raw.complaint_flag == 1.0:
        return 4, "complaint flag"

    # 5 — statute approaching (8-30 day window)
    if STAT_IMMINENT_DAYS < raw.days_until_statute <= STAT_APPROACHING_MAX_DAYS:
        return 5, f"statute {int(raw.days_until_statute)}d (approaching)"

    # 6 — high exposure with action trigger
    if raw.incurred_amount >= HIGH_EXPOSURE_INCURRED and (
        raw.unread_document_count >= 1 or raw.open_diary_count >= 1
    ):
        trigger = (
            f"{int(raw.unread_document_count)} unread docs"
            if raw.unread_document_count >= 1
            else f"{int(raw.open_diary_count)} overdue diary"
        )
        return 6, f"incurred ${raw.incurred_amount:,.0f} + {trigger}"

    # 7 — routine work
    return 7, "no policy gate fired"


# --- Within-bucket sort keys ----------------------------------------------
#
# Every sort key returns a tuple that, when sorted ascending, yields the
# desired within-bucket order. Final tiebreak is request_id ascending
# (appended by `rank_policy`, not by these functions).


def _key_b1(raw: RawFeatures) -> tuple[float, ...]:
    # SLA asc → severity desc → incurred desc
    return (raw.hours_until_sla_breach, -raw.severity_tier_score, -raw.incurred_amount)


def _key_b2(raw: RawFeatures) -> tuple[float, ...]:
    return (raw.days_until_statute, -raw.severity_tier_score, -raw.incurred_amount)


def _key_b3(raw: RawFeatures) -> tuple[float, ...]:
    # Effective clock: 0 if overdue diary fires, else days_until_statute.
    # min(stat, 0 if diary>=1 else 999) per the locked thresholds doc.
    effective = min(
        raw.days_until_statute,
        0.0 if raw.open_diary_count >= 1 else 999.0,
    )
    return (effective, -raw.severity_tier_score, -raw.incurred_amount)


def _key_b4(raw: RawFeatures) -> tuple[float, ...]:
    # days_since_claimant_contact desc → severity desc → incurred desc
    return (-raw.days_since_claimant_contact, -raw.severity_tier_score, -raw.incurred_amount)


def _key_b5(raw: RawFeatures) -> tuple[float, ...]:
    return (raw.days_until_statute, -raw.severity_tier_score, -raw.incurred_amount)


def _key_b6(raw: RawFeatures) -> tuple[float, ...]:
    return (
        -raw.incurred_amount,
        -(raw.unread_document_count + raw.open_diary_count),
        -raw.severity_tier_score,
    )


def _key_b7(
    raw: RawFeatures,
    normalized: dict[str, float],
    weights: Weights,
) -> tuple[float, ...]:
    # Routine work: re-use S1 weighted sum on normalized features.
    # Sort by -score so larger-score sorts first. reserve_adequacy_gap is
    # inert by design (always 0 — see features.py:158), so its weight has
    # no effect; we leave it in for shape consistency with v1.
    return (-score(normalized, weights),)


_BUCKET_KEY_FNS = {1: _key_b1, 2: _key_b2, 3: _key_b3, 4: _key_b4, 5: _key_b5, 6: _key_b6}


# --- Main entry point -----------------------------------------------------


def rank_policy(
    caseload: Caseload,
    s1_weights: Weights = DEFAULT_WEIGHTS,
) -> list[PolicyRankedItem]:
    """Rank every CoverageRequest in the caseload via the policy engine.

    Buckets are evaluated in precedence order (1..7); within each bucket,
    the locked sort key applies; final tiebreak is request_id ascending.
    The S1 weights are used only inside bucket 7 (routine work).
    """
    raw_by_rid: dict[str, RawFeatures] = extract_raw(caseload)
    normalized_by_rid: dict[str, dict[str, float]] = extract_features(caseload)

    # Bucket each request.
    by_bucket: dict[int, list[str]] = {b: [] for b in BUCKET_NAMES}
    bucket_and_why: dict[str, tuple[int, str]] = {}
    for rid, raw in raw_by_rid.items():
        bucket, why = assign_bucket(raw)
        bucket_and_why[rid] = (bucket, why)
        by_bucket[bucket].append(rid)

    # Sort within each bucket; emit globally.
    output: list[PolicyRankedItem] = []
    global_rank = 0
    for bucket in sorted(BUCKET_NAMES):  # 1, 2, ..., 7
        rids = by_bucket[bucket]
        if not rids:
            continue

        if bucket == 7:
            # Routine work: sort key needs normalized + weights.
            def key_fn(rid: str, b: int = bucket) -> tuple:
                return (*_key_b7(raw_by_rid[rid], normalized_by_rid[rid], s1_weights), rid)
        else:
            key_fn_b = _BUCKET_KEY_FNS[bucket]
            def key_fn(rid: str, fn=key_fn_b) -> tuple:
                return (*fn(raw_by_rid[rid]), rid)

        sorted_rids = sorted(rids, key=key_fn)
        for within_rank, rid in enumerate(sorted_rids, start=1):
            global_rank += 1
            _, why = bucket_and_why[rid]
            # within-bucket score: first element of the sort key (negated
            # for the desc-sorted buckets so the reported number is
            # interpretable). For buckets that sort ascending on a positive
            # quantity (B1, B2, B3 effective clock, B5), the raw key value
            # is what we report. For B4/B6/B7 we negate to get a positive
            # urgency-direction score.
            wb_score = float(key_fn(rid)[0])
            if bucket in (4, 6, 7):
                wb_score = -wb_score
            output.append(
                PolicyRankedItem(
                    rank=global_rank,
                    bucket=bucket,
                    bucket_name=BUCKET_NAMES[bucket],
                    within_bucket_rank=within_rank,
                    request_id=rid,
                    why_today=why,
                    within_bucket_score=wb_score,
                )
            )

    return output
