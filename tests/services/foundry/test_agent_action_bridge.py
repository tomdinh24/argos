"""Integration tests for the AgentAction → Foundry bridge.

Mirrors `test_coverage_bridge.py` shape. See that file for the layer
explanation.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest
from dotenv import load_dotenv

load_dotenv()

from argos.ontology.types import AgentAction  # noqa: E402
from argos.services.foundry.agent_action_bridge import (  # noqa: E402
    propagate_agent_action_to_foundry,
)
from argos.services.foundry.client import (  # noqa: E402
    FoundryBridgeNotConfigured,
    bridge_is_enabled,
    reset_client_cache,
)


def _action(action_id: str = "AA-TEST-001") -> AgentAction:
    return AgentAction(
        action_id=action_id,
        claim_id="CLM-001",
        timestamp=datetime(2026, 6, 4, 0, 0, 0, tzinfo=timezone.utc),
        workflow="coverage",
        action_type="analysis_emitted",
        summary="Coverage workflow emitted CoverageReport for CLM-001",
        success=True,
    )


def test_bridge_is_a_noop_when_flag_unset(monkeypatch):
    """When ARGOS_FOUNDRY_BRIDGE_ENABLED is unset, the bridge returns
    None without touching Foundry."""
    monkeypatch.delenv("ARGOS_FOUNDRY_BRIDGE_ENABLED", raising=False)
    assert bridge_is_enabled() is False
    assert propagate_agent_action_to_foundry(_action()) is None


def test_bridge_raises_when_flag_set_but_env_missing(monkeypatch):
    """Flag on but FOUNDRY_HOSTNAME/FOUNDRY_TOKEN missing → fail loudly."""
    monkeypatch.setenv("ARGOS_FOUNDRY_BRIDGE_ENABLED", "1")
    monkeypatch.setenv("FOUNDRY_HOSTNAME", "")
    monkeypatch.setenv("FOUNDRY_TOKEN", "")
    reset_client_cache()
    with pytest.raises(FoundryBridgeNotConfigured):
        propagate_agent_action_to_foundry(_action())


def test_citation_arrays_default_to_empty(monkeypatch):
    """No citations passed → bridge still no-ops cleanly when flag off."""
    monkeypatch.delenv("ARGOS_FOUNDRY_BRIDGE_ENABLED", raising=False)
    assert (
        propagate_agent_action_to_foundry(
            _action(),
            citation_ids=None,
            document_ids=None,
        )
        is None
    )


@pytest.mark.foundry_integration
@pytest.mark.skipif(
    not os.environ.get("FOUNDRY_TOKEN"),
    reason="FOUNDRY_TOKEN not set; integration test skipped",
)
def test_bridge_round_trip_records_operation_id(monkeypatch):
    """Live OSDK call against the live Argos ontology.

    Requires (a) OSDK regenerated with `emit_agent_action` exposed
    (argos_live_sdk v0.2.0+) and (b) CLM-001 Claim seeded.
    """
    monkeypatch.setenv("ARGOS_FOUNDRY_BRIDGE_ENABLED", "1")
    reset_client_cache()

    op_id = propagate_agent_action_to_foundry(
        _action(action_id=f"AA-LIVE-{datetime.now(timezone.utc).isoformat()}"),
    )
    assert op_id is not None
    assert isinstance(op_id, str)
    assert op_id.startswith("ri.actions.")
