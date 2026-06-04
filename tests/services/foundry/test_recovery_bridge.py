"""Integration tests for the Recovery → Foundry bridge.

Mirrors `test_coverage_bridge.py`. See that file for layer explanation.
"""
from __future__ import annotations

import os

import pytest
from dotenv import load_dotenv

load_dotenv()

from argos.services.foundry.client import (  # noqa: E402
    FoundryBridgeNotConfigured,
    bridge_is_enabled,
    reset_client_cache,
)
from argos.services.foundry.recovery_bridge import (  # noqa: E402
    propagate_recovery_decision_to_foundry,
)


def test_bridge_is_a_noop_when_flag_unset(monkeypatch):
    monkeypatch.delenv("ARGOS_FOUNDRY_BRIDGE_ENABLED", raising=False)
    assert bridge_is_enabled() is False
    assert (
        propagate_recovery_decision_to_foundry(
            claim_id="CLM-NONEXISTENT", decision="pursue"
        )
        is None
    )


def test_bridge_raises_when_flag_set_but_env_missing(monkeypatch):
    monkeypatch.setenv("ARGOS_FOUNDRY_BRIDGE_ENABLED", "1")
    monkeypatch.setenv("FOUNDRY_HOSTNAME", "")
    monkeypatch.setenv("FOUNDRY_TOKEN", "")
    reset_client_cache()
    with pytest.raises(FoundryBridgeNotConfigured):
        propagate_recovery_decision_to_foundry(
            claim_id="CLM-001", decision="pursue"
        )


def test_source_assessment_id_is_optional(monkeypatch):
    monkeypatch.delenv("ARGOS_FOUNDRY_BRIDGE_ENABLED", raising=False)
    assert (
        propagate_recovery_decision_to_foundry(
            claim_id="CLM-001", decision="abstain"
        )
        is None
    )


@pytest.mark.foundry_integration
@pytest.mark.skipif(
    not os.environ.get("FOUNDRY_TOKEN"),
    reason="FOUNDRY_TOKEN not set; integration test skipped",
)
def test_bridge_round_trip_records_operation_id(monkeypatch):
    """Live OSDK call. Requires OSDK regen against poc-2b's
    apply-recovery-decision and a Claim row in the new ontology."""
    monkeypatch.setenv("ARGOS_FOUNDRY_BRIDGE_ENABLED", "1")
    reset_client_cache()

    op_id = propagate_recovery_decision_to_foundry(
        claim_id="CLM-001",
        decision="pursue",
        source_assessment_id="assess-canary",
    )
    assert op_id is not None
    assert isinstance(op_id, str)
    assert op_id.startswith("ri.actions.")
