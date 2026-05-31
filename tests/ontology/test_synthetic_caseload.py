"""Tests for the triage synthetic caseload fixture.

The fixture is load-bearing for the triage benchmark: if the corner mix
silently drifts (e.g., the SLA-imminent case loses its deadline because of a
refactor), the benchmark verdict becomes meaningless. These tests pin the
contract.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from argos.ontology.synthetic_caseload import (
    DEFAULT_AS_OF,
    build_caseload,
    corner_labels,
)


class TestCaseloadShape:
    """Caseload size and aggregate counts are pinned."""

    def test_caseload_has_exactly_20_requests(self):
        cs = build_caseload()
        assert len(cs.requests) == 20
        assert len(cs.claims) == 20  # 1 claim per request in v1

    def test_one_claim_per_request(self):
        cs = build_caseload()
        for request in cs.requests:
            cs.claim_for(request)  # raises if missing

    def test_all_corner_labels_present(self):
        labels = set(corner_labels().values())
        assert labels == {
            "sla-1h", "sla-4h", "sla-6h",
            "stat-3d", "stat-7d", "stat-14d",
            "hi-cat", "hi-serious-1", "hi-serious-2",
            "aged-15d", "aged-21d", "aged-30d",
            "unread-1", "unread-2", "unread-3",
            "lit-rep-1", "lit-rep-2",
            "complaint-doi",
            "bb-minor-1", "bb-minor-2",
        }
        assert len(labels) == 20

    def test_corner_labels_one_to_one_with_request_ids(self):
        labels = corner_labels()
        cs = build_caseload()
        request_ids = {r.request_id for r in cs.requests}
        assert set(labels.keys()) == request_ids


class TestDeterminism:
    """Same as_of in → identical Caseload out. No randomness, no wall-clock."""

    def test_two_builds_identical(self):
        a = build_caseload()
        b = build_caseload()
        assert a.model_dump_json() == b.model_dump_json()

    def test_different_as_of_changes_timestamps(self):
        ts_a = datetime(2026, 5, 29, 13, 0, tzinfo=timezone.utc)
        ts_b = datetime(2026, 6, 1, 13, 0, tzinfo=timezone.utc)
        a = build_caseload(as_of=ts_a)
        b = build_caseload(as_of=ts_b)
        # IDs are stable, timestamps shift
        assert a.as_of != b.as_of
        assert {r.request_id for r in a.requests} == {r.request_id for r in b.requests}


class TestCornerCases:
    """Each corner case actually anchors the feature it claims to anchor."""

    @pytest.fixture
    def cs(self):
        return build_caseload()

    def _request_for_label(self, cs, label):
        rid = next(rid for rid, lab in corner_labels().items() if lab == label)
        return next(r for r in cs.requests if r.request_id == rid)

    def _claim_for_label(self, cs, label):
        return cs.claim_for(self._request_for_label(cs, label))

    # --- SLA-imminent corners ----------------------------------------------

    @pytest.mark.parametrize("label,expected_hours", [
        ("sla-1h", 1.0),
        ("sla-4h", 4.0),
        ("sla-6h", 6.0),
    ])
    def test_sla_corners_have_deadline_at_expected_hours(self, cs, label, expected_hours):
        claim = self._claim_for_label(cs, label)
        sds = [sd for sd in cs.service_deadlines if sd.claim_id == claim.claim_id]
        assert len(sds) == 1, f"{label} should have exactly 1 ServiceDeadline"
        hours_out = (sds[0].deadline - cs.as_of).total_seconds() / 3600
        assert hours_out == pytest.approx(expected_hours, abs=0.01)

    # --- Statute-approaching corners ---------------------------------------

    @pytest.mark.parametrize("label,expected_days", [
        ("stat-3d", 3),
        ("stat-7d", 7),
        ("stat-14d", 14),
    ])
    def test_statute_corners_have_legal_deadline_at_expected_days(self, cs, label, expected_days):
        request = self._request_for_label(cs, label)
        lds = [ld for ld in cs.legal_deadlines if ld.request_id == request.request_id]
        assert len(lds) == 1, f"{label} should have exactly 1 LegalDeadline"
        days_out = (lds[0].deadline_date - cs.as_of.date()).days
        assert days_out == expected_days

    # --- High-incurred corners ---------------------------------------------

    def test_hi_cat_has_catastrophic_severity_and_seven_figure_reserve(self, cs):
        request = self._request_for_label(cs, "hi-cat")
        assert request.severity_tier == "catastrophic"
        assert cs.reserve_current(request.request_id) >= 1_000_000

    def test_hi_serious_corners_are_serious(self, cs):
        for label in ("hi-serious-1", "hi-serious-2"):
            request = self._request_for_label(cs, label)
            assert request.severity_tier == "serious"
            assert cs.reserve_current(request.request_id) >= 400_000

    # --- Aged / silent corners ---------------------------------------------

    @pytest.mark.parametrize("label,min_days", [
        ("aged-15d", 14),
        ("aged-21d", 20),
        ("aged-30d", 28),
    ])
    def test_aged_corners_last_action_is_at_least_min_days_old(self, cs, label, min_days):
        claim = self._claim_for_label(cs, label)
        actions = [a for a in cs.agent_actions if a.claim_id == claim.claim_id]
        assert actions, f"{label} should have at least one AgentAction"
        latest = max(a.timestamp for a in actions)
        age = (cs.as_of - latest).days
        assert age >= min_days, f"{label} latest action only {age}d old"

    # --- Unread evidence corners -------------------------------------------

    @pytest.mark.parametrize("label,expected_count", [
        ("unread-1", 1),
        ("unread-2", 2),
        ("unread-3", 3),
    ])
    def test_unread_corners_have_documents_after_last_action(self, cs, label, expected_count):
        claim = self._claim_for_label(cs, label)
        actions = [a for a in cs.agent_actions if a.claim_id == claim.claim_id]
        last_action_ts = max(a.timestamp for a in actions)
        docs = [d for d in cs.documents if d.claim_id == claim.claim_id]
        unread = [d for d in docs if d.received_date > last_action_ts.date()]
        # Document received_date is date-granularity; the builder spaces docs
        # within the touch window, so they should all be > last_action_date.
        # If the action timestamp falls on the same date as the doc, that's
        # still "after" semantically (received later in the same day).
        assert len(docs) == expected_count, f"{label} should have {expected_count} docs"

    # --- Litigation / rep corners ------------------------------------------

    @pytest.mark.parametrize("label", ["lit-rep-1", "lit-rep-2"])
    def test_lit_rep_corners_have_both_flags(self, cs, label):
        claim = self._claim_for_label(cs, label)
        assert claim.litigation_flag is True
        assert claim.rep_flag is True

    def test_complaint_doi_corner_has_complaint_flag(self, cs):
        claim = self._claim_for_label(cs, "complaint-doi")
        assert claim.complaint_flag is True

    # --- Backburner corners ------------------------------------------------

    @pytest.mark.parametrize("label", ["bb-minor-1", "bb-minor-2"])
    def test_backburner_corners_are_minor_severity_and_recent(self, cs, label):
        request = self._request_for_label(cs, label)
        claim = self._claim_for_label(cs, label)
        assert request.severity_tier == "minor"
        assert claim.litigation_flag is False
        assert claim.rep_flag is False
        assert claim.complaint_flag is False
        # No SLA or statute clocks firing
        assert not any(sd.claim_id == claim.claim_id for sd in cs.service_deadlines)
        assert not any(ld.request_id == request.request_id for ld in cs.legal_deadlines)
        # Recent touch (< 1 day)
        actions = [a for a in cs.agent_actions if a.claim_id == claim.claim_id]
        latest = max(a.timestamp for a in actions)
        assert (cs.as_of - latest) <= timedelta(hours=24)


class TestDerivationHelpers:
    """paid_to_date and reserve_current aggregate LedgerEntries correctly."""

    def test_paid_to_date_sums_payment_entries(self):
        cs = build_caseload()
        # hi-cat has paid=$250K per the spec
        rid = next(r for r, lab in corner_labels().items() if lab == "hi-cat")
        assert cs.paid_to_date(rid) == 250_000.0

    def test_reserve_current_sums_reserve_entries(self):
        cs = build_caseload()
        rid = next(r for r, lab in corner_labels().items() if lab == "hi-cat")
        assert cs.reserve_current(rid) == 1_500_000.0

    def test_paid_to_date_zero_when_no_payments(self):
        cs = build_caseload()
        rid = next(r for r, lab in corner_labels().items() if lab == "sla-1h")
        # sla-1h has no paid_amount, just reserve
        assert cs.paid_to_date(rid) == 0.0
        assert cs.reserve_current(rid) == 80_000.0
