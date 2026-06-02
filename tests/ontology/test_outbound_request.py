"""Tests for the `OutboundRequest` ontology type.

Covers:
- Schema invariants (status-vs-field consistency, min question count)
- Caseload helpers (`outbounds_for_claim`, `open_outbounds_for_claim`)
- Status lifecycle: a typical pending_draft → drafted → sent → replied
  flow constructs cleanly at each step.

Decision context: docs/DECISIONS.md →
  "Outbound status tracking is a first-class concern" (decision)
  "Step 3 split: 3a ships now" (sequencing)
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from argos.ontology.types import (
    Caseload,
    Claim,
    CoverageRequest,
    OutboundRequest,
)


_NOW = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)


def _outbound(**overrides) -> OutboundRequest:
    """Build a minimal-valid OutboundRequest in `pending_draft`."""
    defaults = dict(
        request_id="OBR-001",
        claim_id="CLM-007",
        recipient_party="claimant_counsel",
        recipient_name="Marisol Trent, Esq.",
        letter_purpose="Request initial case evaluation.",
        question_ids_asked=["Q-DAM-013"],
    )
    return OutboundRequest(**{**defaults, **overrides})


# ---------------------------------------------------------------------------
# Schema shape + defaults
# ---------------------------------------------------------------------------


class TestOutboundRequestSchema:
    def test_minimal_constructor_defaults_to_pending_draft(self):
        ob = _outbound()
        assert ob.status == "pending_draft"
        assert ob.drafted_at is None
        assert ob.draft_body is None
        assert ob.sent_at is None
        assert ob.replied_at is None
        assert ob.reply_doc_id is None
        assert ob.follow_up_due_at is None

    def test_question_ids_must_be_non_empty(self):
        with pytest.raises(ValidationError):
            _outbound(question_ids_asked=[])

    def test_can_carry_multiple_questions(self):
        ob = _outbound(question_ids_asked=["Q-LIA-001", "Q-LIA-002", "Q-LIA-003"])
        assert len(ob.question_ids_asked) == 3

    def test_recipient_name_required_non_empty(self):
        with pytest.raises(ValidationError):
            _outbound(recipient_name="")

    def test_letter_purpose_required_non_empty(self):
        with pytest.raises(ValidationError):
            _outbound(letter_purpose="")


# ---------------------------------------------------------------------------
# Status-vs-field consistency
# ---------------------------------------------------------------------------


class TestStatusFieldConsistency:
    def test_sent_status_requires_sent_at(self):
        with pytest.raises(ValidationError, match="sent_at"):
            _outbound(status="sent", channel="email")

    def test_sent_with_sent_at_valid(self):
        ob = _outbound(
            status="sent",
            sent_at=_NOW,
            channel="email",
            drafted_at=_NOW,
            draft_body="Dear counsel, please provide ...",
        )
        assert ob.status == "sent"

    def test_replied_requires_reply_doc_id(self):
        with pytest.raises(ValidationError, match="reply_doc_id"):
            _outbound(
                status="replied",
                sent_at=_NOW,
                replied_at=_NOW,
            )

    def test_replied_requires_replied_at(self):
        with pytest.raises(ValidationError, match="replied_at"):
            _outbound(
                status="replied",
                sent_at=_NOW,
                reply_doc_id="DOC-999",
            )

    def test_replied_with_all_fields_valid(self):
        ob = _outbound(
            status="replied",
            sent_at=_NOW,
            replied_at=_NOW,
            reply_doc_id="DOC-999",
        )
        assert ob.status == "replied"
        assert ob.reply_doc_id == "DOC-999"

    def test_overdue_requires_sent_at(self):
        with pytest.raises(ValidationError, match="sent_at"):
            _outbound(status="overdue")


# ---------------------------------------------------------------------------
# Typical lifecycle constructibility
# ---------------------------------------------------------------------------


class TestLifecycle:
    def test_pending_draft_then_drafted(self):
        pending = _outbound()
        drafted = _outbound(
            status="drafted",
            drafted_at=_NOW,
            draft_body="Dear counsel ...",
        )
        assert pending.status == "pending_draft"
        assert drafted.status == "drafted"
        assert drafted.draft_body is not None

    def test_drafted_then_sent_then_replied(self):
        sent = _outbound(
            status="sent",
            drafted_at=_NOW,
            draft_body="Dear counsel ...",
            sent_at=_NOW,
            channel="email",
            follow_up_due_at=_NOW,
        )
        replied = _outbound(
            status="replied",
            drafted_at=_NOW,
            draft_body="Dear counsel ...",
            sent_at=_NOW,
            channel="email",
            replied_at=_NOW,
            reply_doc_id="DOC-INBOUND-1",
        )
        assert sent.status == "sent"
        assert replied.status == "replied"
        assert replied.reply_doc_id == "DOC-INBOUND-1"

    def test_cancelled_status_no_send_required(self):
        """A cancelled outbound has no sent_at — pre-send abort."""
        ob = _outbound(status="cancelled")
        assert ob.status == "cancelled"
        assert ob.sent_at is None


# ---------------------------------------------------------------------------
# Caseload helpers
# ---------------------------------------------------------------------------


def _bare_caseload(outbounds: list[OutboundRequest]) -> Caseload:
    """Minimal Caseload carrying just outbounds — Claim + Request stubs
    are enough to satisfy the Pydantic shape."""
    return Caseload(
        as_of=_NOW,
        claims=[Claim(claim_id="CLM-007", policy_period_id="PP-1", opened_date=_NOW.date())],
        requests=[CoverageRequest(
            request_id="REQ-007", claim_id="CLM-007", coverage_id="COV-1",
        )],
        outbound_requests=outbounds,
    )


class TestCaseloadHelpers:
    def test_outbounds_for_claim_filters(self):
        cs = _bare_caseload([
            _outbound(request_id="OBR-1", claim_id="CLM-007"),
            _outbound(request_id="OBR-2", claim_id="CLM-008"),
            _outbound(request_id="OBR-3", claim_id="CLM-007"),
        ])
        result = cs.outbounds_for_claim("CLM-007")
        assert [o.request_id for o in result] == ["OBR-1", "OBR-3"]

    def test_outbounds_for_claim_preserves_insertion_order(self):
        cs = _bare_caseload([
            _outbound(request_id="OBR-3", claim_id="CLM-007"),
            _outbound(request_id="OBR-1", claim_id="CLM-007"),
            _outbound(request_id="OBR-2", claim_id="CLM-007"),
        ])
        result = cs.outbounds_for_claim("CLM-007")
        assert [o.request_id for o in result] == ["OBR-3", "OBR-1", "OBR-2"]

    def test_outbounds_for_unknown_claim_empty(self):
        cs = _bare_caseload([_outbound(claim_id="CLM-007")])
        assert cs.outbounds_for_claim("CLM-999") == []

    def test_open_outbounds_excludes_pending_draft_and_replied(self):
        """Open = sent OR overdue. pending_draft, drafted, replied,
        cancelled are NOT open (drafted hasn't gone out yet; replied/
        cancelled are terminal)."""
        cs = _bare_caseload([
            _outbound(request_id="OBR-1", claim_id="CLM-007"),  # pending_draft
            _outbound(
                request_id="OBR-2", claim_id="CLM-007",
                status="drafted", drafted_at=_NOW, draft_body="x",
            ),
            _outbound(
                request_id="OBR-3", claim_id="CLM-007",
                status="sent", sent_at=_NOW, channel="email",
            ),
            _outbound(
                request_id="OBR-4", claim_id="CLM-007",
                status="overdue", sent_at=_NOW, channel="email",
            ),
            _outbound(
                request_id="OBR-5", claim_id="CLM-007",
                status="replied", sent_at=_NOW, replied_at=_NOW,
                reply_doc_id="DOC-1",
            ),
            _outbound(request_id="OBR-6", claim_id="CLM-007", status="cancelled"),
        ])
        open_ids = {o.request_id for o in cs.open_outbounds_for_claim("CLM-007")}
        assert open_ids == {"OBR-3", "OBR-4"}


# ---------------------------------------------------------------------------
# Claim.coverage_posture — input-driven framing signal for the Drafter
# ---------------------------------------------------------------------------


class TestClaimCoveragePosture:
    """The carrier's coverage stance. Drives Outreach Drafter framing
    via the OutreachDrafterInput plumbing chain. Today this field is
    hand-flipped; future work wires the Coverage specialist's
    recommendation back onto the claim."""

    def _claim(self, **overrides) -> Claim:
        defaults = dict(
            claim_id="CLM-007",
            policy_period_id="PP-1",
            opened_date=date(2026, 5, 10),
        )
        return Claim(**{**defaults, **overrides})

    def test_default_posture_is_under_investigation(self):
        """Backwards-compat: claims constructed without the field
        land in the most permissive posture (no special framing)."""
        c = self._claim()
        assert c.coverage_posture == "under_investigation"

    def test_accepts_all_known_postures(self):
        for posture in (
            "under_investigation", "ROR_issued", "denied", "accepted"
        ):
            c = self._claim(coverage_posture=posture)
            assert c.coverage_posture == posture

    def test_rejects_unknown_postures(self):
        with pytest.raises(ValidationError):
            self._claim(coverage_posture="reservation_issued")  # close-but-wrong

    def test_rejects_empty_posture(self):
        with pytest.raises(ValidationError):
            self._claim(coverage_posture="")
