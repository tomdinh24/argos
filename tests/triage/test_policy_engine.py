"""Tests for the policy-engine triage ranker.

Concerns:
 - assign_bucket() returns the locked bucket for each fixture claim
   (the bucket gold in `docs/evals/triage-ranker-policy-engine-thresholds.md`).
 - Bucket precedence is respected: every claim in bucket N outranks
   every claim in bucket N+1, regardless of within-bucket score.
 - Within-bucket sort is deterministic across runs.
 - Output is a total order over the caseload (no missing or duplicate
   request_ids; ranks 1..N).
 - The locked top-7 prediction holds.
"""
from __future__ import annotations

from argos.ontology.synthetic_caseload import build_caseload, corner_labels
from argos.services.triage.features import extract_raw
from argos.services.triage.policy_engine import (
    BUCKET_NAMES,
    PolicyRankedItem,
    assign_bucket,
    rank_policy,
)


# --- Locked bucket gold from the thresholds doc ---------------------------

LOCKED_BUCKET_GOLD: dict[str, int] = {
    "sla-1h": 1,
    "sla-4h": 1,
    "sla-6h": 1,
    "stat-3d": 2,
    "stat-7d": 2,
    "stat-14d": 5,
    "hi-cat": 7,
    "hi-serious-1": 7,
    "hi-serious-2": 7,
    "aged-15d": 7,
    "aged-21d": 7,
    "aged-30d": 7,
    "unread-1": 7,
    "unread-2": 7,
    "unread-3": 7,
    "lit-rep-1": 3,
    "lit-rep-2": 3,
    "complaint-doi": 4,
    "bb-minor-1": 7,
    "bb-minor-2": 7,
}


# Locked top-7 prediction (request_ids derived from corner labels).
LOCKED_TOP7_LABELS = [
    "sla-1h", "sla-4h", "sla-6h",   # B1
    "stat-3d", "stat-7d",            # B2
    "lit-rep-1", "lit-rep-2",        # B3 (016 before 017 — overdue diary = 0d effective clock)
]


def _label_for(rid: str) -> str:
    return corner_labels()[rid]


def _rid_for(label: str) -> str:
    return next(rid for rid, lab in corner_labels().items() if lab == label)


class TestAssignBucket:
    """assign_bucket() places each fixture claim in its locked bucket."""

    def test_every_fixture_claim_lands_in_locked_bucket(self):
        caseload = build_caseload()
        raw = extract_raw(caseload)
        mismatches = []
        for rid, rfeat in raw.items():
            actual_bucket, why = assign_bucket(rfeat)
            label = _label_for(rid)
            expected_bucket = LOCKED_BUCKET_GOLD[label]
            if actual_bucket != expected_bucket:
                mismatches.append(
                    f"{rid} ({label}): expected B{expected_bucket}, got "
                    f"B{actual_bucket} ({why})"
                )
        assert not mismatches, "\n".join(mismatches)


class TestRankShape:
    """rank_policy() returns a well-formed total order."""

    def test_one_row_per_request(self):
        cs = build_caseload()
        ranked = rank_policy(cs)
        assert len(ranked) == len(cs.requests)
        assert {r.request_id for r in ranked} == {r.request_id for r in cs.requests}

    def test_ranks_are_1_to_n_unique(self):
        ranked = rank_policy(build_caseload())
        assert [r.rank for r in ranked] == list(range(1, len(ranked) + 1))

    def test_returned_items_are_policy_ranked_items(self):
        ranked = rank_policy(build_caseload())
        assert all(isinstance(r, PolicyRankedItem) for r in ranked)


class TestBucketPrecedence:
    """Every claim in bucket N outranks every claim in bucket N+1."""

    def test_buckets_appear_in_precedence_order(self):
        ranked = rank_policy(build_caseload())
        seen_buckets = [r.bucket for r in ranked]
        # ranked is the global order; bucket numbers must be non-decreasing
        assert seen_buckets == sorted(seen_buckets)

    def test_bucket_names_consistent_with_numbers(self):
        ranked = rank_policy(build_caseload())
        for r in ranked:
            assert r.bucket_name == BUCKET_NAMES[r.bucket]


class TestWithinBucketOrdering:
    """Within-bucket sort follows the locked sort keys."""

    def test_b1_sorted_by_sla_hours_ascending(self):
        ranked = rank_policy(build_caseload())
        b1_rids = [r.request_id for r in ranked if r.bucket == 1]
        # locked: sla-1h, sla-4h, sla-6h
        assert b1_rids == [_rid_for("sla-1h"), _rid_for("sla-4h"), _rid_for("sla-6h")]

    def test_b2_sorted_by_statute_days_ascending(self):
        ranked = rank_policy(build_caseload())
        b2_rids = [r.request_id for r in ranked if r.bucket == 2]
        assert b2_rids == [_rid_for("stat-3d"), _rid_for("stat-7d")]

    def test_b3_overdue_diary_outranks_only_statute(self):
        # lit-rep-1 has overdue_task_count=1 → effective clock = 0
        # lit-rep-2 has statute_days_out=45, no overdue diary → effective clock = 45
        ranked = rank_policy(build_caseload())
        b3_rids = [r.request_id for r in ranked if r.bucket == 3]
        assert b3_rids == [_rid_for("lit-rep-1"), _rid_for("lit-rep-2")]


class TestLockedTop7Prediction:
    """The locked top-7 from the thresholds doc must hold."""

    def test_top_7_matches_locked_prediction(self):
        ranked = rank_policy(build_caseload())
        top7_labels = [_label_for(r.request_id) for r in ranked[:7]]
        assert top7_labels == LOCKED_TOP7_LABELS


class TestDeterminism:
    """Same caseload → same policy ranking, every time."""

    def test_two_runs_identical(self):
        a = rank_policy(build_caseload())
        b = rank_policy(build_caseload())
        assert a == b
