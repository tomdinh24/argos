"""Reserve / Liability / Recovery writeback action tests.

Symmetric to test_closure_actions / test_coverage_actions. Each
writeback flips a single Claim field and (optionally) appends one
AgentAction(`validator_pass`) row to the audit log.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from argos.ontology.types import Caseload, Claim
from argos.services.orchestrator.audit_log import (
    VALIDATOR_PASS,
    load_agent_actions,
)
from argos.services.orchestrator.liability_actions import (
    apply_liability_decision,
)
from argos.services.orchestrator.recovery_actions import (
    apply_recovery_decision,
)
from argos.services.orchestrator.reserve_actions import (
    apply_reserve_decision,
)


def _caseload() -> Caseload:
    claim = Claim(
        claim_id="CLM-100",
        policy_period_id="PP-1",
        opened_date=date(2025, 6, 3),
    )
    return Caseload(
        as_of=datetime(2026, 6, 2, tzinfo=timezone.utc),
        policies=[], policy_periods=[], coverages=[], parties=[],
        claims=[claim], requests=[], documents=[],
    )


def _find(cs: Caseload, claim_id: str) -> Claim:
    return next(c for c in cs.claims if c.claim_id == claim_id)


# ---------------------------------------------------------------------------
# Reserve
# ---------------------------------------------------------------------------


class TestReserveWriteback:
    def test_accept_flips_to_committed(self):
        cs = _caseload()
        assert _find(cs, "CLM-100").reserve_decision_committed is False
        out = apply_reserve_decision(cs, "CLM-100", accept=True)
        assert _find(out, "CLM-100").reserve_decision_committed is True

    def test_defer_is_noop(self):
        cs = _caseload()
        out = apply_reserve_decision(cs, "CLM-100", accept=False)
        assert _find(out, "CLM-100").reserve_decision_committed is False
        assert out == cs

    def test_idempotent_on_already_committed(self):
        cs = _caseload()
        once = apply_reserve_decision(cs, "CLM-100", accept=True)
        twice = apply_reserve_decision(once, "CLM-100", accept=True)
        assert _find(twice, "CLM-100").reserve_decision_committed is True

    def test_unknown_claim_raises(self):
        cs = _caseload()
        with pytest.raises(ValueError, match="not present"):
            apply_reserve_decision(cs, "CLM-DOES-NOT-EXIST", accept=True)

    def test_input_caseload_not_mutated(self):
        cs = _caseload()
        _ = apply_reserve_decision(cs, "CLM-100", accept=True)
        assert _find(cs, "CLM-100").reserve_decision_committed is False

    def test_audit_row_emitted_on_accept(self, tmp_path: Path):
        cs = _caseload()
        apply_reserve_decision(
            cs, "CLM-100", accept=True,
            source_assessment_id="RES-abc",
            audit_log_root=tmp_path,
        )
        rows = load_agent_actions("CLM-100", log_root=tmp_path)
        assert len(rows) == 1
        assert rows[0].workflow == "reserve"
        assert rows[0].action_type == VALIDATOR_PASS
        assert "RES-abc" in rows[0].summary

    def test_no_audit_row_on_defer(self, tmp_path: Path):
        cs = _caseload()
        apply_reserve_decision(
            cs, "CLM-100", accept=False, audit_log_root=tmp_path,
        )
        assert load_agent_actions("CLM-100", log_root=tmp_path) == []


# ---------------------------------------------------------------------------
# Liability
# ---------------------------------------------------------------------------


class TestLiabilityWriteback:
    def test_accept_flips_to_committed(self):
        cs = _caseload()
        out = apply_liability_decision(cs, "CLM-100", accept=True)
        assert _find(out, "CLM-100").liability_apportionment_committed is True

    def test_defer_is_noop(self):
        cs = _caseload()
        out = apply_liability_decision(cs, "CLM-100", accept=False)
        assert _find(out, "CLM-100").liability_apportionment_committed is False

    def test_idempotent_on_already_committed(self):
        cs = _caseload()
        once = apply_liability_decision(cs, "CLM-100", accept=True)
        twice = apply_liability_decision(once, "CLM-100", accept=True)
        assert _find(twice, "CLM-100").liability_apportionment_committed is True

    def test_unknown_claim_raises(self):
        cs = _caseload()
        with pytest.raises(ValueError, match="not present"):
            apply_liability_decision(cs, "CLM-NONE", accept=True)

    def test_audit_row_emitted_on_accept(self, tmp_path: Path):
        cs = _caseload()
        apply_liability_decision(
            cs, "CLM-100", accept=True,
            source_assessment_id="LIA-xyz",
            audit_log_root=tmp_path,
        )
        rows = load_agent_actions("CLM-100", log_root=tmp_path)
        assert len(rows) == 1
        assert rows[0].workflow == "liability"
        assert "LIA-xyz" in rows[0].summary


# ---------------------------------------------------------------------------
# Recovery
# ---------------------------------------------------------------------------


class TestRecoveryWriteback:
    def test_accept_pursue_flips_both_fields(self):
        cs = _caseload()
        out = apply_recovery_decision(cs, "CLM-100", decision="pursue")
        claim = _find(out, "CLM-100")
        assert claim.recovery_pursuit_decision_committed is True
        assert claim.recovery_pursuit_decision == "pursue"

    def test_accept_route_to_af(self):
        cs = _caseload()
        out = apply_recovery_decision(cs, "CLM-100", decision="route_to_af")
        claim = _find(out, "CLM-100")
        assert claim.recovery_pursuit_decision == "route_to_af"

    def test_accept_abstain(self):
        cs = _caseload()
        out = apply_recovery_decision(cs, "CLM-100", decision="abstain")
        claim = _find(out, "CLM-100")
        assert claim.recovery_pursuit_decision == "abstain"

    def test_senior_review_required_rejected_as_routing_signal(self):
        cs = _caseload()
        with pytest.raises(ValueError, match="routing signal"):
            apply_recovery_decision(
                cs, "CLM-100", decision="senior_review_required",
            )

    def test_idempotent_on_same_decision(self):
        cs = _caseload()
        once = apply_recovery_decision(cs, "CLM-100", decision="pursue")
        twice = apply_recovery_decision(once, "CLM-100", decision="pursue")
        assert _find(twice, "CLM-100").recovery_pursuit_decision == "pursue"

    def test_change_decision_updates_field(self):
        cs = _caseload()
        first = apply_recovery_decision(cs, "CLM-100", decision="pursue")
        second = apply_recovery_decision(
            first, "CLM-100", decision="route_to_af",
        )
        assert _find(second, "CLM-100").recovery_pursuit_decision == "route_to_af"

    def test_unknown_claim_raises(self):
        cs = _caseload()
        with pytest.raises(ValueError, match="not present"):
            apply_recovery_decision(cs, "CLM-NONE", decision="pursue")

    def test_audit_row_carries_decision_and_assessment_id(self, tmp_path: Path):
        cs = _caseload()
        apply_recovery_decision(
            cs, "CLM-100", decision="pursue",
            source_assessment_id="REC-foo",
            audit_log_root=tmp_path,
        )
        rows = load_agent_actions("CLM-100", log_root=tmp_path)
        assert len(rows) == 1
        assert rows[0].workflow == "recovery"
        assert "pursue" in rows[0].summary
        assert "REC-foo" in rows[0].summary
