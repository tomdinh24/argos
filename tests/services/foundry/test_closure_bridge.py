"""Integration tests for the Closure → Foundry bridge.

Two functions in one bridge module (closure + reopen), so this file
exercises both. Mirrors `test_coverage_bridge.py`.
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
from argos.services.foundry.closure_bridge import (  # noqa: E402
    propagate_closure_decision_to_foundry,
    propagate_reopen_decision_to_foundry,
)


# ----- closure decision -----


def test_closure_bridge_is_a_noop_when_flag_unset(monkeypatch):
    monkeypatch.delenv("ARGOS_FOUNDRY_BRIDGE_ENABLED", raising=False)
    assert bridge_is_enabled() is False
    assert (
        propagate_closure_decision_to_foundry(
            claim_id="CLM-NONEXISTENT",
            recommendation="ready_to_close_with_payment",
        )
        is None
    )


def test_closure_bridge_raises_when_flag_set_but_env_missing(monkeypatch):
    monkeypatch.setenv("ARGOS_FOUNDRY_BRIDGE_ENABLED", "1")
    monkeypatch.setenv("FOUNDRY_HOSTNAME", "")
    monkeypatch.setenv("FOUNDRY_TOKEN", "")
    reset_client_cache()
    with pytest.raises(FoundryBridgeNotConfigured):
        propagate_closure_decision_to_foundry(
            claim_id="CLM-001",
            recommendation="ready_to_close_with_payment",
        )


# ----- reopen decision (paired function in same bridge module) -----


def test_reopen_bridge_is_a_noop_when_flag_unset(monkeypatch):
    monkeypatch.delenv("ARGOS_FOUNDRY_BRIDGE_ENABLED", raising=False)
    assert (
        propagate_reopen_decision_to_foundry(
            claim_id="CLM-NONEXISTENT",
            reopen_reason="material_new_information",
        )
        is None
    )


def test_reopen_bridge_raises_when_flag_set_but_env_missing(monkeypatch):
    monkeypatch.setenv("ARGOS_FOUNDRY_BRIDGE_ENABLED", "1")
    monkeypatch.setenv("FOUNDRY_HOSTNAME", "")
    monkeypatch.setenv("FOUNDRY_TOKEN", "")
    reset_client_cache()
    with pytest.raises(FoundryBridgeNotConfigured):
        propagate_reopen_decision_to_foundry(
            claim_id="CLM-001",
            reopen_reason="post_close_demand",
        )


# ----- live integration (skipped without FOUNDRY_TOKEN) -----


@pytest.mark.foundry_integration
@pytest.mark.skipif(
    not os.environ.get("FOUNDRY_TOKEN"),
    reason="FOUNDRY_TOKEN not set; integration test skipped",
)
def test_closure_bridge_round_trip_records_operation_id(monkeypatch):
    """Live OSDK call. Requires OSDK regen + a Claim row in the new
    ontology."""
    monkeypatch.setenv("ARGOS_FOUNDRY_BRIDGE_ENABLED", "1")
    reset_client_cache()

    op_id = propagate_closure_decision_to_foundry(
        claim_id="CLM-001",
        recommendation="ready_to_close_with_payment",
        source_assessment_id="assess-canary",
    )
    assert op_id is not None
    assert isinstance(op_id, str)
    assert op_id.startswith("ri.actions.")
