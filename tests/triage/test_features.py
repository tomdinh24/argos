"""Tests for the triage feature extractor.

Three concerns:
 - Each raw feature reads what the spec says it reads (sanity per corner).
 - Normalization is min-max with epsilon, monotonic with raw rank, and
   inverts the inverse-direction features so "higher = more urgent."
 - Extraction is deterministic — same caseload in, same vectors out.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from argos.ontology.synthetic_caseload import (
    DEFAULT_AS_OF,
    build_caseload,
    corner_labels,
)
from argos.services.triage.features import (
    BOOLEAN_FEATURES,
    INVERSE_FEATURES,
    RawFeatures,
    extract_features,
    extract_raw,
    normalize,
)


def _rid_for(label: str) -> str:
    return next(rid for rid, lab in corner_labels().items() if lab == label)


class TestRawExtraction:
    """Raw features read the right fields off the right corner."""

    @pytest.fixture
    def cs(self):
        return build_caseload()

    @pytest.fixture
    def raw(self, cs):
        return extract_raw(cs)

    def test_one_raw_row_per_request(self, cs, raw):
        assert set(raw.keys()) == {r.request_id for r in cs.requests}

    def test_sla_corner_hours_match_fixture(self, raw):
        # sla-1h fixture sets ServiceDeadline 1.0h after as_of
        rid = _rid_for("sla-1h")
        assert raw[rid].hours_until_sla_breach == pytest.approx(1.0, abs=0.01)

    def test_no_sla_corner_uses_sentinel(self, raw):
        # backburner has no SLA — should land at the SLA sentinel (large)
        rid = _rid_for("bb-minor-1")
        assert raw[rid].hours_until_sla_breach > 24 * 7  # at least a week out

    def test_statute_corner_days_match_fixture(self, raw):
        rid = _rid_for("stat-3d")
        assert raw[rid].days_until_statute == pytest.approx(3.0, abs=0.01)

    def test_aged_corner_hours_since_touch_is_large(self, raw):
        rid = _rid_for("aged-30d")
        # 30 days * 24 hours, both action and work item set there
        assert raw[rid].hours_since_last_touch == pytest.approx(30 * 24, abs=1)

    def test_severity_score_scale(self, raw):
        assert raw[_rid_for("hi-cat")].severity_tier_score == 4.0
        assert raw[_rid_for("hi-serious-1")].severity_tier_score == 3.0
        assert raw[_rid_for("sla-4h")].severity_tier_score == 2.0
        assert raw[_rid_for("bb-minor-1")].severity_tier_score == 1.0

    def test_incurred_sums_paid_and_reserve(self, raw):
        # hi-cat: 1.5M reserve + 250K paid = 1.75M
        rid = _rid_for("hi-cat")
        assert raw[rid].incurred_amount == pytest.approx(1_750_000.0)

    def test_unread_count_matches_corner(self, raw):
        assert raw[_rid_for("unread-1")].unread_document_count == 1.0
        assert raw[_rid_for("unread-2")].unread_document_count == 2.0
        assert raw[_rid_for("unread-3")].unread_document_count == 3.0

    def test_flags_lift_for_lit_rep_corner(self, raw):
        rid = _rid_for("lit-rep-1")
        assert raw[rid].litigation_flag == 1.0
        assert raw[rid].rep_flag == 1.0
        assert raw[rid].complaint_flag == 0.0

    def test_complaint_corner_flag(self, raw):
        rid = _rid_for("complaint-doi")
        assert raw[rid].complaint_flag == 1.0

    def test_days_since_claimant_contact_matches_fixture(self, raw):
        # aged-21d has days_since_claimant_contact=25
        rid = _rid_for("aged-21d")
        assert raw[rid].days_since_claimant_contact == pytest.approx(25.0, abs=0.1)

    def test_reserve_adequacy_gap_zero_until_reserve_specialist_runs(self, raw):
        # spec: gap is 0 by default; only populated once Reserve specialist runs
        for rf in raw.values():
            assert rf.reserve_adequacy_gap == 0.0


class TestNormalization:
    """Min-max scaling, inversion, epsilon, monotonicity."""

    @pytest.fixture
    def normed(self):
        return extract_features(build_caseload())

    def test_all_values_in_unit_interval(self, normed):
        for vec in normed.values():
            for name, v in vec.items():
                assert 0.0 <= v <= 1.0, f"{name}={v} out of [0,1]"

    def test_inverse_features_invert_rank(self, normed):
        # raw smallest hours_until_sla_breach (sla-1h) should map to the
        # *largest* normalized value (most urgent)
        rid_urgent = _rid_for("sla-1h")
        max_sla = max(v["hours_until_sla_breach"] for v in normed.values())
        assert normed[rid_urgent]["hours_until_sla_breach"] == pytest.approx(max_sla)

    def test_forward_feature_monotonic_with_raw(self):
        # increasing raw `hours_since_last_touch` ⇒ non-decreasing normalized value
        cs = build_caseload()
        raw = extract_raw(cs)
        normed = normalize(raw)

        pairs = sorted(
            ((raw[rid].hours_since_last_touch, normed[rid]["hours_since_last_touch"])
             for rid in raw),
            key=lambda p: p[0],
        )
        for (_, n_lo), (_, n_hi) in zip(pairs, pairs[1:]):
            assert n_hi >= n_lo

    def test_inverse_feature_monotonic_with_inverted_raw(self):
        # increasing raw `days_until_statute` ⇒ non-increasing normalized value
        cs = build_caseload()
        raw = extract_raw(cs)
        normed = normalize(raw)

        pairs = sorted(
            ((raw[rid].days_until_statute, normed[rid]["days_until_statute"])
             for rid in raw),
            key=lambda p: p[0],
        )
        for (_, n_lo), (_, n_hi) in zip(pairs, pairs[1:]):
            assert n_hi <= n_lo

    def test_flat_feature_contributes_nothing(self):
        # If every request has the same raw value, normalized = 0 everywhere
        # (rather than 1.0 for inverse — which would be false signal).
        flat_raw = {
            "REQ-001": _zero_features(hours_until_sla_breach=10.0),
            "REQ-002": _zero_features(hours_until_sla_breach=10.0),
            "REQ-003": _zero_features(hours_until_sla_breach=10.0),
        }
        normed = normalize(flat_raw)
        for rid in flat_raw:
            assert normed[rid]["hours_until_sla_breach"] == 0.0

    def test_boolean_features_pass_through_unchanged(self, normed):
        cs = build_caseload()
        raw = extract_raw(cs)
        for rid in raw:
            for name in BOOLEAN_FEATURES:
                assert normed[rid][name] == raw[rid].as_dict()[name]

    def test_normalization_does_not_swallow_zero_spread_via_divide_by_zero(self):
        # Two-request caseload with identical raw vectors — no exception.
        flat = {
            "REQ-A": _zero_features(),
            "REQ-B": _zero_features(),
        }
        out = normalize(flat)  # would raise if epsilon weren't applied
        for vec in out.values():
            for v in vec.values():
                assert v == 0.0

    def test_empty_caseload_returns_empty_dict(self):
        assert normalize({}) == {}


class TestDeterminism:
    """Same caseload in → byte-identical raw + normalized output."""

    def test_extract_raw_is_deterministic(self):
        a = extract_raw(build_caseload())
        b = extract_raw(build_caseload())
        # RawFeatures is frozen + Pydantic-free; equality is by-value
        assert a == b

    def test_extract_features_is_deterministic(self):
        a = extract_features(build_caseload())
        b = extract_features(build_caseload())
        assert a == b


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _zero_features(**overrides) -> RawFeatures:
    base = dict(
        hours_until_sla_breach=0.0,
        days_until_statute=0.0,
        hours_since_last_touch=0.0,
        open_diary_count=0.0,
        severity_tier_score=0.0,
        incurred_amount=0.0,
        reserve_adequacy_gap=0.0,
        days_since_claimant_contact=0.0,
        unread_document_count=0.0,
        litigation_flag=0.0,
        rep_flag=0.0,
        complaint_flag=0.0,
    )
    base.update(overrides)
    return RawFeatures(**base)
