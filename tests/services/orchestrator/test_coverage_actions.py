"""Tests for `apply_coverage_decision` — the Coverage → Claim
writeback action.

Covers:
- Valid transitions flip `claim.coverage_posture`
- Invalid transitions raise (terminal states don't transition, ROR
  doesn't regress to under_investigation)
- Idempotent: same posture in, no error
- Unknown claim_id raises
- Input caseload is not mutated
- Other claims in the caseload are untouched

Decision context: docs/DECISIONS.md →
  "Coverage->Claim writeback (apply_coverage_decision)"
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from argos.ontology.types import Caseload, Claim, CoverageRequest
from argos.services.orchestrator.coverage_actions import (
    apply_coverage_decision,
)


_NOW = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)


def _claim(
    claim_id: str = "CLM-007",
    *,
    coverage_posture: str = "under_investigation",
) -> Claim:
    return Claim(
        claim_id=claim_id,
        policy_period_id="PP-1",
        opened_date=date(2026, 5, 10),
        coverage_posture=coverage_posture,
    )


def _caseload(claims: list[Claim] | None = None) -> Caseload:
    cs_claims = claims or [_claim()]
    return Caseload(
        as_of=_NOW,
        claims=cs_claims,
        requests=[
            CoverageRequest(
                request_id=f"REQ-{c.claim_id}",
                claim_id=c.claim_id,
                coverage_id="COV-1",
            )
            for c in cs_claims
        ],
    )


# ---------------------------------------------------------------------------
# Valid transitions
# ---------------------------------------------------------------------------


class TestValidTransitions:
    def test_under_investigation_to_ror_issued(self):
        cs = _caseload()
        new_cs = apply_coverage_decision(
            cs, "CLM-007", new_posture="ROR_issued",
        )
        target = next(c for c in new_cs.claims if c.claim_id == "CLM-007")
        assert target.coverage_posture == "ROR_issued"

    def test_under_investigation_to_accepted(self):
        cs = _caseload()
        new_cs = apply_coverage_decision(
            cs, "CLM-007", new_posture="accepted",
        )
        target = next(c for c in new_cs.claims if c.claim_id == "CLM-007")
        assert target.coverage_posture == "accepted"

    def test_under_investigation_to_denied(self):
        cs = _caseload()
        new_cs = apply_coverage_decision(
            cs, "CLM-007", new_posture="denied",
        )
        target = next(c for c in new_cs.claims if c.claim_id == "CLM-007")
        assert target.coverage_posture == "denied"

    def test_ror_issued_resolves_to_accepted(self):
        cs = _caseload([_claim(coverage_posture="ROR_issued")])
        new_cs = apply_coverage_decision(
            cs, "CLM-007", new_posture="accepted",
        )
        target = next(c for c in new_cs.claims if c.claim_id == "CLM-007")
        assert target.coverage_posture == "accepted"

    def test_ror_issued_resolves_to_denied(self):
        cs = _caseload([_claim(coverage_posture="ROR_issued")])
        new_cs = apply_coverage_decision(
            cs, "CLM-007", new_posture="denied",
        )
        target = next(c for c in new_cs.claims if c.claim_id == "CLM-007")
        assert target.coverage_posture == "denied"

    def test_source_recommendation_id_accepted(self):
        """v1 accepts but does not persist source_recommendation_id —
        the parameter exists so future audit-log work doesn't need a
        signature change."""
        cs = _caseload()
        new_cs = apply_coverage_decision(
            cs,
            "CLM-007",
            new_posture="ROR_issued",
            source_recommendation_id="REC-COV-001",
        )
        target = next(c for c in new_cs.claims if c.claim_id == "CLM-007")
        assert target.coverage_posture == "ROR_issued"


# ---------------------------------------------------------------------------
# Invalid transitions
# ---------------------------------------------------------------------------


class TestInvalidTransitions:
    def test_accepted_is_terminal(self):
        cs = _caseload([_claim(coverage_posture="accepted")])
        with pytest.raises(ValueError, match="terminal posture"):
            apply_coverage_decision(
                cs, "CLM-007", new_posture="denied",
            )

    def test_denied_is_terminal(self):
        cs = _caseload([_claim(coverage_posture="denied")])
        with pytest.raises(ValueError, match="terminal posture"):
            apply_coverage_decision(
                cs, "CLM-007", new_posture="accepted",
            )

    def test_terminal_cannot_revert_to_under_investigation(self):
        cs = _caseload([_claim(coverage_posture="accepted")])
        with pytest.raises(ValueError, match="terminal posture"):
            apply_coverage_decision(
                cs, "CLM-007", new_posture="under_investigation",
            )

    def test_ror_cannot_regress_to_under_investigation(self):
        cs = _caseload([_claim(coverage_posture="ROR_issued")])
        with pytest.raises(ValueError, match="cannot regress"):
            apply_coverage_decision(
                cs, "CLM-007", new_posture="under_investigation",
            )


# ---------------------------------------------------------------------------
# Idempotence
# ---------------------------------------------------------------------------


class TestIdempotence:
    def test_same_posture_is_no_op(self):
        """Cockpit clicks ROR_issued twice → second call is a no-op
        (no raise, no diff). Important for an "Issue ROR" button
        that may be clicked twice."""
        cs = _caseload([_claim(coverage_posture="ROR_issued")])
        new_cs = apply_coverage_decision(
            cs, "CLM-007", new_posture="ROR_issued",
        )
        target = next(c for c in new_cs.claims if c.claim_id == "CLM-007")
        assert target.coverage_posture == "ROR_issued"

    def test_terminal_same_posture_idempotent_not_error(self):
        """Re-confirming a terminal posture (`accepted` → `accepted`)
        is the no-op path, not the "terminal cannot transition" error."""
        cs = _caseload([_claim(coverage_posture="accepted")])
        new_cs = apply_coverage_decision(
            cs, "CLM-007", new_posture="accepted",
        )
        target = next(c for c in new_cs.claims if c.claim_id == "CLM-007")
        assert target.coverage_posture == "accepted"


# ---------------------------------------------------------------------------
# Unknown claim
# ---------------------------------------------------------------------------


class TestUnknownClaim:
    def test_missing_claim_id_raises(self):
        cs = _caseload()
        with pytest.raises(ValueError, match="not present in caseload"):
            apply_coverage_decision(
                cs, "CLM-DOES-NOT-EXIST", new_posture="ROR_issued",
            )


# ---------------------------------------------------------------------------
# Immutability + isolation
# ---------------------------------------------------------------------------


class TestImmutability:
    def test_input_caseload_not_mutated(self):
        cs = _caseload()
        apply_coverage_decision(
            cs, "CLM-007", new_posture="ROR_issued",
        )
        # Original is still under_investigation.
        original = next(c for c in cs.claims if c.claim_id == "CLM-007")
        assert original.coverage_posture == "under_investigation"

    def test_other_claims_untouched(self):
        cs = _caseload([
            _claim("CLM-007"),
            _claim("CLM-008", coverage_posture="accepted"),
            _claim("CLM-009", coverage_posture="ROR_issued"),
        ])
        new_cs = apply_coverage_decision(
            cs, "CLM-007", new_posture="ROR_issued",
        )
        # CLM-008 still accepted, CLM-009 still ROR_issued.
        c8 = next(c for c in new_cs.claims if c.claim_id == "CLM-008")
        c9 = next(c for c in new_cs.claims if c.claim_id == "CLM-009")
        assert c8.coverage_posture == "accepted"
        assert c9.coverage_posture == "ROR_issued"
