"""Triage ranker — S1 (linear weighted sum on normalized features).

Given a `Caseload`, score every CoverageRequest and return a total order
(highest priority first). All scoring is deterministic: same caseload +
same weights → same ordering, every time.

The feature vectors arrive from `features.extract_features(caseload)` in
"higher = more urgent" form, so every weight is positive and the same
direction (no inversion in this module).

Tiebreaker: when two requests have identical scores, break on `request_id`
ascending. Without a deterministic tiebreak, Kendall tau and top-7
Jaccard against the gold ranking become noisy. See the thresholds doc:
`docs/evals/triage-ranker-thresholds.md`.

S1 vs S2: S2 (bucket-then-tiebreak) is closer to how adjusters describe
their own thinking, but S1's continuous score is what the benchmark
tuning loop needs. If S1 produces good agreement after weight tuning,
the bucket behavior can be reconstructed by binning the scores. See
`docs/specs/triage-ranker.md`, "Scoring function."
"""
from __future__ import annotations

from dataclasses import dataclass

from argos.ontology.types import Caseload
from argos.services.triage.features import extract_features


@dataclass(frozen=True)
class Weights:
    """One weight per feature emitted by `features.extract_features`.

    Default 1.0 across the board (uniform prior). The benchmark + tuning
    loop adjusts these against the hand-ranked gold.
    """

    w_sla: float = 1.0
    w_stat: float = 1.0
    w_aged: float = 1.0
    w_diary: float = 1.0
    w_sev: float = 1.0
    w_amt: float = 1.0
    w_reserve: float = 1.0
    w_contact: float = 1.0
    w_unread: float = 1.0
    w_lit: float = 1.0
    w_rep: float = 1.0
    w_compl: float = 1.0


DEFAULT_WEIGHTS = Weights()


@dataclass(frozen=True)
class RankedItem:
    """One row of the ranker output."""

    rank: int  # 1-based, 1 = top priority
    request_id: str
    score: float


def score(features: dict[str, float], weights: Weights = DEFAULT_WEIGHTS) -> float:
    """Linear weighted sum of normalized features.

    `features` is a dict from `features.extract_features(caseload)[rid]`.
    All values are urgency-direction (higher = more urgent), so every
    weighted term contributes positively to score."""
    return (
        weights.w_sla * features["hours_until_sla_breach"]
        + weights.w_stat * features["days_until_statute"]
        + weights.w_aged * features["hours_since_last_touch"]
        + weights.w_diary * features["open_diary_count"]
        + weights.w_sev * features["severity_tier_score"]
        + weights.w_amt * features["incurred_amount"]
        + weights.w_reserve * features["reserve_adequacy_gap"]
        + weights.w_contact * features["days_since_claimant_contact"]
        + weights.w_unread * features["unread_document_count"]
        + weights.w_lit * features["litigation_flag"]
        + weights.w_rep * features["rep_flag"]
        + weights.w_compl * features["complaint_flag"]
    )


def rank(
    caseload: Caseload,
    weights: Weights = DEFAULT_WEIGHTS,
) -> list[RankedItem]:
    """Score every CoverageRequest in the caseload and return a total order,
    highest priority first. Ties on score break on `request_id` ascending
    (deterministic)."""
    normalized = extract_features(caseload)
    # Sort by (-score, request_id): score descending, request_id ascending
    # for the tiebreak. Python's sort is stable, but the tuple sort handles
    # both keys in one pass.
    scored = sorted(
        ((rid, score(vec, weights)) for rid, vec in normalized.items()),
        key=lambda pair: (-pair[1], pair[0]),
    )
    return [
        RankedItem(rank=i + 1, request_id=rid, score=s)
        for i, (rid, s) in enumerate(scored)
    ]
