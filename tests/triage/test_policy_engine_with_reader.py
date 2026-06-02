"""Tests for the Reader↔policy-engine integration surface.

No live API calls — these tests cover:

- `relevant_doc_counts=None` reproduces v3 behavior exactly (backward compat).
- `relevant_doc_counts={}` makes B6 fire only on overdue diary, not on
  raw unread doc count.
- `relevant_doc_counts={CLM-X: 1}` correctly promotes a high-exposure
  claim into B6.
- `relevant_doc_counts={CLM-Y: 0}` correctly demotes a high-exposure
  claim with unread docs into B7.
- Extended fixture has the right doc inventory (9 pinned docs on
  the right 5 claims, no placeholder bodies remaining on those
  claims).
"""
from __future__ import annotations

from argos.ontology.caseload_with_realistic_docs import (
    PINNED_DOCS,
    build_caseload_with_realistic_docs,
    pinned_doc_predictions,
)
from argos.ontology.synthetic_caseload import build_caseload, corner_labels
from argos.services.triage.policy_engine import rank_policy


def _label_for(rid: str) -> str:
    return corner_labels()[rid]


def _rid_for(label: str) -> str:
    return next(rid for rid, lab in corner_labels().items() if lab == label)


def _bucket_of(rid: str, ranked) -> int:
    return next(r.bucket for r in ranked if r.request_id == rid)


# --- Backward-compatibility ----------------------------------------------


class TestBackwardCompat:
    def test_v3_caseload_unchanged_with_none_relevant_doc_counts(self):
        """v3 fixture + relevant_doc_counts=None → identical to v3 output."""
        baseline = rank_policy(build_caseload())
        with_none = rank_policy(build_caseload(), relevant_doc_counts=None)
        assert baseline == with_none

    def test_v3_caseload_buckets_stable_with_none(self):
        ranked = rank_policy(build_caseload(), relevant_doc_counts=None)
        # spot-check: known v3 bucket gold for a few corner cases
        assert _bucket_of(_rid_for("sla-1h"), ranked) == 1
        assert _bucket_of(_rid_for("stat-3d"), ranked) == 2
        assert _bucket_of(_rid_for("lit-rep-1"), ranked) == 3
        assert _bucket_of(_rid_for("complaint-doi"), ranked) == 4
        assert _bucket_of(_rid_for("stat-14d"), ranked) == 5
        assert _bucket_of(_rid_for("hi-cat"), ranked) == 7  # no unread in v3


# --- Extended fixture shape ----------------------------------------------


class TestExtendedFixture:
    def test_extended_caseload_has_pinned_docs(self):
        cs = build_caseload_with_realistic_docs()
        ids = {d.document_id for d in cs.documents}
        for pinned in PINNED_DOCS:
            assert pinned.document_id in ids, (
                f"pinned doc {pinned.document_id} missing from extended fixture"
            )

    def test_extended_caseload_drops_placeholder_bodies_on_target_claims(self):
        cs = build_caseload_with_realistic_docs()
        target_claims = {"CLM-013", "CLM-014", "CLM-015"}
        for d in cs.documents:
            if d.claim_id in target_claims:
                assert "(synthetic placeholder body)" not in d.body_text, (
                    f"{d.document_id} on {d.claim_id} still has placeholder body"
                )

    def test_extended_caseload_has_correct_per_claim_doc_counts(self):
        cs = build_caseload_with_realistic_docs()
        per_claim: dict[str, int] = {}
        for d in cs.documents:
            per_claim[d.claim_id] = per_claim.get(d.claim_id, 0) + 1
        assert per_claim.get("CLM-007") == 2
        assert per_claim.get("CLM-008") == 1
        assert per_claim.get("CLM-013") == 1
        assert per_claim.get("CLM-014") == 2
        assert per_claim.get("CLM-015") == 3

    def test_pinned_doc_predictions_includes_all_pinned(self):
        preds = pinned_doc_predictions()
        assert len(preds) == len(PINNED_DOCS)
        for pinned in PINNED_DOCS:
            assert preds[pinned.document_id] is pinned


# --- Material-count override behavior ------------------------------------


class TestMaterialCountsOverride:
    def test_empty_relevant_doc_counts_demotes_req_008_to_b7(self):
        """Extended fixture + empty relevant_doc_counts: B6 should NOT fire
        on REQ-008 (which has 1 raw unread doc but 0 material). Without
        the override, raw count would trigger B6."""
        cs = build_caseload_with_realistic_docs()
        ranked = rank_policy(cs, relevant_doc_counts={})
        # REQ-008 has 0 material, $585K incurred → B7
        assert _bucket_of("REQ-008", ranked) == 7
        # REQ-007 has 0 material (because we passed empty), $1.75M → B7
        assert _bucket_of("REQ-007", ranked) == 7

    def test_relevant_doc_counts_promotes_req_007_to_b6(self):
        """Reader-style override saying REQ-007 has 1 material doc:
        $1.75M incurred + 1 material → B6 fires."""
        cs = build_caseload_with_realistic_docs()
        ranked = rank_policy(cs, relevant_doc_counts={"CLM-007": 1})
        assert _bucket_of("REQ-007", ranked) == 6
        # REQ-008 still has 0 material → still B7
        assert _bucket_of("REQ-008", ranked) == 7

    def test_baseline_no_override_fires_b6_on_raw_unread_counts(self):
        """Extended fixture + relevant_doc_counts=None: B6 fires on REQ-007
        AND REQ-008 because both have raw unread docs ≥ 1 and
        incurred ≥ $250K. This is the 'before integration' baseline
        that the Reader should fix."""
        cs = build_caseload_with_realistic_docs()
        ranked = rank_policy(cs, relevant_doc_counts=None)
        assert _bucket_of("REQ-007", ranked) == 6  # 2 unread, $1.75M
        assert _bucket_of("REQ-008", ranked) == 6  # 1 unread, $585K

    def test_full_pre_registered_override_matches_integration_gold(self):
        """The full pre-registered relevant_doc_counts from the integration
        thresholds doc: REQ-007=1, REQ-008=0, REQ-013=0, REQ-014=1,
        REQ-015=1. Expected post-integration buckets: REQ-007 in B6,
        REQ-008 in B7, REQ-013/014/015 in B7."""
        cs = build_caseload_with_realistic_docs()
        relevant_doc_counts = {
            "CLM-007": 1,
            "CLM-008": 0,
            "CLM-013": 0,
            "CLM-014": 1,
            "CLM-015": 1,
        }
        ranked = rank_policy(cs, relevant_doc_counts=relevant_doc_counts)
        assert _bucket_of("REQ-007", ranked) == 6
        assert _bucket_of("REQ-008", ranked) == 7
        assert _bucket_of("REQ-013", ranked) == 7
        assert _bucket_of("REQ-014", ranked) == 7  # below $250K threshold
        assert _bucket_of("REQ-015", ranked) == 7  # below $250K threshold

    def test_missing_claim_id_in_relevant_doc_counts_treated_as_zero(self):
        """If a claim isn't in relevant_doc_counts, default to 0 — not
        a fallback to raw unread count. Otherwise the Reader integration
        would silently mix raw and Reader-screened signals."""
        cs = build_caseload_with_realistic_docs()
        # Only specify REQ-007; REQ-008 not in dict
        ranked = rank_policy(cs, relevant_doc_counts={"CLM-007": 1})
        # REQ-007 promoted to B6
        assert _bucket_of("REQ-007", ranked) == 6
        # REQ-008 has 0 material (defaulted) despite 1 raw unread doc → B7
        assert _bucket_of("REQ-008", ranked) == 7
