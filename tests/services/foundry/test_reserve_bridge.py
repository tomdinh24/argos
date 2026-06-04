"""Integration tests for the Reserve → Foundry bridge.

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
from argos.services.foundry.reserve_bridge import (  # noqa: E402
    propagate_reserve_decision_to_foundry,
)


def test_bridge_is_a_noop_when_flag_unset(monkeypatch):
    """When ARGOS_FOUNDRY_BRIDGE_ENABLED is unset, the bridge returns
    None without touching Foundry."""
    monkeypatch.delenv("ARGOS_FOUNDRY_BRIDGE_ENABLED", raising=False)
    assert bridge_is_enabled() is False
    assert (
        propagate_reserve_decision_to_foundry(
            claim_id="CLM-NONEXISTENT", accept=True
        )
        is None
    )


def test_bridge_raises_when_flag_set_but_env_missing(monkeypatch):
    """Flag on but FOUNDRY_HOSTNAME/FOUNDRY_TOKEN missing → fail loudly."""
    monkeypatch.setenv("ARGOS_FOUNDRY_BRIDGE_ENABLED", "1")
    monkeypatch.setenv("FOUNDRY_HOSTNAME", "")
    monkeypatch.setenv("FOUNDRY_TOKEN", "")
    reset_client_cache()
    with pytest.raises(FoundryBridgeNotConfigured):
        propagate_reserve_decision_to_foundry(claim_id="CLM-001", accept=True)


def test_source_assessment_id_is_optional(monkeypatch):
    """source_assessment_id defaults to None and the bridge still
    no-ops cleanly when the flag is off."""
    monkeypatch.delenv("ARGOS_FOUNDRY_BRIDGE_ENABLED", raising=False)
    assert (
        propagate_reserve_decision_to_foundry(claim_id="CLM-001", accept=False)
        is None
    )


@pytest.mark.foundry_integration
@pytest.mark.skipif(
    not os.environ.get("FOUNDRY_TOKEN"),
    reason="FOUNDRY_TOKEN not set; integration test skipped",
)
def test_bridge_round_trip_records_operation_id(monkeypatch):
    """Live OSDK call against the new Claim object type.

    Requires (a) the OSDK is regenerated against poc-2b's
    apply-reserve-decision action and (b) a Claim row exists in the
    new ontology for the bridge to target. Until data-plane is wired,
    this test will fail with "object not found" — that's expected
    while the integration test runs as a skeleton.
    """
    monkeypatch.setenv("ARGOS_FOUNDRY_BRIDGE_ENABLED", "1")
    reset_client_cache()

    op_id = propagate_reserve_decision_to_foundry(
        claim_id="CLM-001",
        accept=True,
        source_assessment_id="assess-canary",
    )
    assert op_id is not None
    assert isinstance(op_id, str)
    assert op_id.startswith("ri.actions.")
