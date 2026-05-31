"""Tests for triage hybrid v2 — schema validation + splice correctness.

The judge call is stubbed via monkeypatch; no live API calls in pytest.
The live benchmark lives in `scripts/run_triage_hybrid_benchmark.py`.
"""
from __future__ import annotations

import pytest

from argos.ontology.synthetic_caseload import build_caseload
from argos.services.triage import hybrid
from argos.services.triage.hybrid import (
    HybridResult,
    TOP_N,
    _parse_judge_csv,
    re_rank,
)
from argos.services.triage.ranker import DEFAULT_WEIGHTS, Weights, rank


# ---------------------------------------------------------------------------
# Schema-validator unit tests
# ---------------------------------------------------------------------------


class TestParseJudgeCsv:

    def _wrap(self, body: str) -> str:
        return f"some preamble\n```csv\n{body}\n```\nsome trailing prose"

    def test_well_formed_response_parses(self):
        body = (
            "rank,request_id,reason_short\n"
            "1,REQ-001,first\n"
            "2,REQ-002,second\n"
            "3,REQ-003,third\n"
        )
        ids, err = _parse_judge_csv(
            self._wrap(body),
            expected_n=3,
            allowed_ids={"REQ-001", "REQ-002", "REQ-003"},
        )
        assert err is None
        assert ids == ["REQ-001", "REQ-002", "REQ-003"]

    def test_reorder_by_rank_not_by_row_position(self):
        body = (
            "rank,request_id,reason_short\n"
            "3,REQ-003,third\n"
            "1,REQ-001,first\n"
            "2,REQ-002,second\n"
        )
        ids, err = _parse_judge_csv(
            self._wrap(body),
            expected_n=3,
            allowed_ids={"REQ-001", "REQ-002", "REQ-003"},
        )
        assert err is None
        assert ids == ["REQ-001", "REQ-002", "REQ-003"]

    def test_missing_csv_block_fails(self):
        ids, err = _parse_judge_csv(
            "1,REQ-001,first\n2,REQ-002,second",
            expected_n=2,
            allowed_ids={"REQ-001", "REQ-002"},
        )
        assert ids == []
        assert err and "fenced" in err

    def test_wrong_row_count_fails(self):
        body = "rank,request_id,reason_short\n1,REQ-001,only"
        _, err = _parse_judge_csv(
            self._wrap(body),
            expected_n=2,
            allowed_ids={"REQ-001", "REQ-002"},
        )
        assert err and "expected 2 rows" in err

    def test_duplicate_id_fails(self):
        body = (
            "rank,request_id,reason_short\n"
            "1,REQ-001,first\n"
            "2,REQ-001,dup\n"
        )
        _, err = _parse_judge_csv(
            self._wrap(body),
            expected_n=2,
            allowed_ids={"REQ-001", "REQ-002"},
        )
        assert err and "duplicate" in err

    def test_id_outside_slice_fails(self):
        body = (
            "rank,request_id,reason_short\n"
            "1,REQ-999,not in slice\n"
            "2,REQ-001,ok\n"
        )
        _, err = _parse_judge_csv(
            self._wrap(body),
            expected_n=2,
            allowed_ids={"REQ-001", "REQ-002"},
        )
        assert err and "not in input slice" in err

    def test_rank_gap_fails(self):
        body = (
            "rank,request_id,reason_short\n"
            "1,REQ-001,first\n"
            "3,REQ-002,gap\n"
        )
        _, err = _parse_judge_csv(
            self._wrap(body),
            expected_n=2,
            allowed_ids={"REQ-001", "REQ-002"},
        )
        assert err and "1..2 with no gaps" in err

    def test_missing_required_columns_fails(self):
        body = "rank,request_id\n1,REQ-001\n2,REQ-002\n"
        _, err = _parse_judge_csv(
            self._wrap(body),
            expected_n=2,
            allowed_ids={"REQ-001", "REQ-002"},
        )
        assert err and "missing columns" in err

    def test_non_integer_rank_fails(self):
        body = (
            "rank,request_id,reason_short\n"
            "one,REQ-001,first\n"
            "2,REQ-002,second\n"
        )
        _, err = _parse_judge_csv(
            self._wrap(body),
            expected_n=2,
            allowed_ids={"REQ-001", "REQ-002"},
        )
        assert err and "non-integer rank" in err


# ---------------------------------------------------------------------------
# Splice tests — judge is stubbed; verifies hybrid only touches top-N slice
# ---------------------------------------------------------------------------


def _stub_judge_that_reverses_slice(monkeypatch):
    """Stub the judge to return the top-N slice in reverse order.
    Lets us verify the splice without a live API."""

    def fake_call_judge(prompt, *, model):
        # Extract the request_ids appearing in the prompt's `### REQ-...`
        # markers, then return them in reverse order.
        import re
        ids = re.findall(r"###\s+(REQ-\d+)", prompt)
        rows = "\n".join(
            f"{i + 1},{rid},reversed" for i, rid in enumerate(reversed(ids))
        )
        return f"```csv\nrank,request_id,reason_short\n{rows}\n```"

    monkeypatch.setattr(hybrid, "_call_judge", fake_call_judge)


class TestReRankSplice:

    def test_re_rank_returns_full_n_items(self, monkeypatch):
        _stub_judge_that_reverses_slice(monkeypatch)
        cs = build_caseload()
        result = re_rank(cs, DEFAULT_WEIGHTS)
        assert result.schema_valid
        assert len(result.items) == len(cs.requests)

    def test_re_rank_preserves_tail_ordering(self, monkeypatch):
        _stub_judge_that_reverses_slice(monkeypatch)
        cs = build_caseload()
        s1 = rank(cs, DEFAULT_WEIGHTS)
        result = re_rank(cs, DEFAULT_WEIGHTS)
        # ranks (TOP_N + 1) .. 20 must be identical to S1's tail
        s1_tail_ids = [item.request_id for item in s1[TOP_N:]]
        v2_tail_ids = [item.request_id for item in result.items[TOP_N:]]
        assert v2_tail_ids == s1_tail_ids

    def test_re_rank_reorders_only_the_top_slice(self, monkeypatch):
        _stub_judge_that_reverses_slice(monkeypatch)
        cs = build_caseload()
        s1 = rank(cs, DEFAULT_WEIGHTS)
        result = re_rank(cs, DEFAULT_WEIGHTS)
        s1_top_ids = [item.request_id for item in s1[:TOP_N]]
        v2_top_ids = [item.request_id for item in result.items[:TOP_N]]
        # Set should be unchanged; ordering should differ (we stubbed
        # the judge to reverse, so the order should be exactly reversed)
        assert set(v2_top_ids) == set(s1_top_ids)
        assert v2_top_ids == list(reversed(s1_top_ids))

    def test_re_rank_assigns_ranks_1_to_n(self, monkeypatch):
        _stub_judge_that_reverses_slice(monkeypatch)
        cs = build_caseload()
        result = re_rank(cs, DEFAULT_WEIGHTS)
        ranks = [item.rank for item in result.items]
        assert ranks == list(range(1, len(result.items) + 1))

    def test_re_rank_carries_s1_scores_into_top_slice(self, monkeypatch):
        _stub_judge_that_reverses_slice(monkeypatch)
        cs = build_caseload()
        s1 = rank(cs, DEFAULT_WEIGHTS)
        s1_score_by_id = {item.request_id: item.score for item in s1[:TOP_N]}
        result = re_rank(cs, DEFAULT_WEIGHTS)
        for item in result.items[:TOP_N]:
            assert item.score == s1_score_by_id[item.request_id]


class TestReRankSchemaFailureFallback:

    def test_invalid_judge_response_falls_back_to_s1(self, monkeypatch):
        def bad_judge(prompt, *, model):
            return "I refuse to comply with the CSV format demand."

        monkeypatch.setattr(hybrid, "_call_judge", bad_judge)
        cs = build_caseload()
        s1 = rank(cs, DEFAULT_WEIGHTS)
        result = re_rank(cs, DEFAULT_WEIGHTS)
        assert not result.schema_valid
        assert result.failure_reason is not None
        # Fallback: items should equal S1's full ordering
        assert [r.request_id for r in result.items] == [
            r.request_id for r in s1
        ]


# ---------------------------------------------------------------------------
# Sanity checks
# ---------------------------------------------------------------------------


class TestReRankValidation:

    def test_top_n_larger_than_caseload_raises(self, monkeypatch):
        _stub_judge_that_reverses_slice(monkeypatch)
        cs = build_caseload()
        with pytest.raises(ValueError, match="cannot re-rank top"):
            re_rank(cs, DEFAULT_WEIGHTS, top_n=len(cs.requests) + 1)

    def test_default_top_n_is_locked_at_10(self):
        # Spec-lock: changing TOP_N invalidates the v2 eval. This test
        # makes that change loud.
        assert TOP_N == 10
