"""Tests for the triage ranker (S1 linear weighted sum).

Concerns:
 - score() math on hand-crafted normalized vectors.
 - rank() returns a total order over the caseload — no missing or duplicate
   request_ids, ties broken deterministically.
 - Monotonicity: holding everything else equal, increasing an urgency
   feature does not decrease the score; doubling a weight on an active
   feature does not decrease the score.
 - Determinism: same caseload + same weights → same ordering.
"""
from __future__ import annotations

import pytest

from argos.ontology.synthetic_caseload import build_caseload, corner_labels
from argos.services.triage.features import extract_features
from argos.services.triage.ranker import (
    DEFAULT_WEIGHTS,
    RankedItem,
    Weights,
    rank,
    score,
)


def _zero_vec() -> dict[str, float]:
    return {
        "hours_until_sla_breach": 0.0,
        "days_until_statute": 0.0,
        "hours_since_last_touch": 0.0,
        "open_diary_count": 0.0,
        "severity_tier_score": 0.0,
        "incurred_amount": 0.0,
        "reserve_adequacy_gap": 0.0,
        "days_since_claimant_contact": 0.0,
        "unread_document_count": 0.0,
        "litigation_flag": 0.0,
        "rep_flag": 0.0,
        "complaint_flag": 0.0,
    }


def _rid_for(label: str) -> str:
    return next(rid for rid, lab in corner_labels().items() if lab == label)


class TestScore:
    """Unit-level score() math."""

    def test_all_zero_vector_scores_zero(self):
        assert score(_zero_vec()) == 0.0

    def test_single_feature_at_one_default_weights_scores_one(self):
        v = _zero_vec()
        v["hours_until_sla_breach"] = 1.0
        assert score(v) == 1.0

    def test_all_features_at_one_default_weights_scores_twelve(self):
        v = {k: 1.0 for k in _zero_vec()}
        assert score(v) == 12.0

    def test_weights_multiply_features(self):
        v = _zero_vec()
        v["severity_tier_score"] = 0.5
        w = Weights(w_sev=4.0)
        assert score(v, w) == pytest.approx(2.0)

    def test_each_feature_is_weighted_by_its_dedicated_weight(self):
        # one feature on, one weight non-default, verify pairing
        cases = [
            ("hours_until_sla_breach", "w_sla"),
            ("days_until_statute", "w_stat"),
            ("hours_since_last_touch", "w_aged"),
            ("open_diary_count", "w_diary"),
            ("severity_tier_score", "w_sev"),
            ("incurred_amount", "w_amt"),
            ("reserve_adequacy_gap", "w_reserve"),
            ("days_since_claimant_contact", "w_contact"),
            ("unread_document_count", "w_unread"),
            ("litigation_flag", "w_lit"),
            ("rep_flag", "w_rep"),
            ("complaint_flag", "w_compl"),
        ]
        for feature, weight_attr in cases:
            v = _zero_vec()
            v[feature] = 1.0
            w_kwargs = {wa: 0.0 for _, wa in cases}
            w_kwargs[weight_attr] = 3.0
            assert score(v, Weights(**w_kwargs)) == pytest.approx(3.0), (
                f"{feature} should be weighted by {weight_attr}"
            )


class TestRankShape:
    """Output is a total order over the caseload."""

    @pytest.fixture
    def ranked(self):
        return rank(build_caseload())

    def test_one_row_per_request(self, ranked):
        cs = build_caseload()
        assert len(ranked) == len(cs.requests)
        assert {r.request_id for r in ranked} == {r.request_id for r in cs.requests}

    def test_ranks_are_1_to_n_unique(self, ranked):
        ranks = [r.rank for r in ranked]
        assert ranks == list(range(1, len(ranked) + 1))

    def test_returned_rows_sorted_by_score_desc(self, ranked):
        scores = [r.score for r in ranked]
        assert scores == sorted(scores, reverse=True)

    def test_tied_scores_break_on_request_id_ascending(self):
        # Build a synthetic flat-features case where everyone gets the same
        # normalized score, then check ordering falls back to request_id.
        # Easiest path: zero-weights ranker over the real caseload → every
        # score is 0, so tiebreak governs.
        ranked = rank(build_caseload(), Weights(**{f.name: 0.0 for f in Weights.__dataclass_fields__.values()}))
        request_ids = [r.request_id for r in ranked]
        assert request_ids == sorted(request_ids)


class TestRankMonotonicity:
    """Holding all-else equal, urgency-positive features increase rank order."""

    def test_doubling_sla_weight_does_not_demote_sla_corner(self):
        cs = build_caseload()
        base = rank(cs, DEFAULT_WEIGHTS)
        boosted = rank(cs, Weights(w_sla=4.0))

        rid = _rid_for("sla-1h")
        base_rank = next(r.rank for r in base if r.request_id == rid)
        boosted_rank = next(r.rank for r in boosted if r.request_id == rid)
        assert boosted_rank <= base_rank, (
            f"Boosting SLA weight moved sla-1h from rank {base_rank} "
            f"to {boosted_rank} (should improve or stay put)"
        )

    def test_doubling_severity_weight_does_not_demote_catastrophic_corner(self):
        cs = build_caseload()
        base = rank(cs, DEFAULT_WEIGHTS)
        boosted = rank(cs, Weights(w_sev=4.0))

        rid = _rid_for("hi-cat")
        base_rank = next(r.rank for r in base if r.request_id == rid)
        boosted_rank = next(r.rank for r in boosted if r.request_id == rid)
        assert boosted_rank <= base_rank

    def test_zeroing_all_weights_collapses_to_tiebreak_order(self):
        zero = Weights(**{f.name: 0.0 for f in Weights.__dataclass_fields__.values()})
        ranked = rank(build_caseload(), zero)
        for r in ranked:
            assert r.score == 0.0

    def test_score_monotonic_in_active_feature(self):
        # Synthetic 2-vector check, independent of caseload state.
        v_low = _zero_vec()
        v_low["incurred_amount"] = 0.2
        v_high = _zero_vec()
        v_high["incurred_amount"] = 0.9
        assert score(v_high) > score(v_low)


class TestDeterminism:
    """Same caseload + same weights → same ranking."""

    def test_two_runs_identical(self):
        a = rank(build_caseload())
        b = rank(build_caseload())
        assert a == b

    def test_two_runs_identical_with_custom_weights(self):
        w = Weights(w_sla=2.0, w_lit=0.5, w_compl=0.1)
        a = rank(build_caseload(), w)
        b = rank(build_caseload(), w)
        assert a == b


class TestRankedItemSurface:
    """RankedItem is the documented public surface — keep its shape stable."""

    def test_ranked_item_fields(self):
        item = RankedItem(rank=1, request_id="REQ-001", score=3.14)
        assert item.rank == 1
        assert item.request_id == "REQ-001"
        assert item.score == 3.14
