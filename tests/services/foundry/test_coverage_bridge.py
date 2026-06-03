"""Integration tests for the Coverage → Foundry bridge.

Two layers:

1. UNIT (always runs): bridge no-ops when feature flag is off, raises
   FoundryBridgeNotConfigured when flag is on but env is missing.
   Hermetic — no Foundry calls, no OSDK import side-effects.

2. INTEGRATION (`-m foundry_integration`): live OSDK call against
   the tenant. Gated on FOUNDRY_TOKEN presence AND opt-in marker so
   the default test run never spends API quota or mutates Foundry data.

Run integration tests explicitly:
    uv run pytest tests/services/foundry/ -m foundry_integration -q
"""
from __future__ import annotations

import os

import pytest
from dotenv import load_dotenv

# Load .env at module-import time so the skipif on the integration test
# sees FOUNDRY_TOKEN if it's only set in .env (not the shell).
load_dotenv()

from argos.services.foundry.client import (  # noqa: E402 — must follow load_dotenv
    FoundryBridgeNotConfigured,
    bridge_is_enabled,
    reset_client_cache,
)
from argos.services.foundry.coverage_bridge import (
    propagate_coverage_decision_to_foundry,
)


# ---------------------------------------------------------------------------
# Unit tests — feature-flag + env-var contracts
# ---------------------------------------------------------------------------


def test_bridge_is_a_noop_when_flag_unset(monkeypatch):
    """When ARGOS_FOUNDRY_BRIDGE_ENABLED is unset, the bridge returns
    None without touching Foundry. This is the default for tests."""
    monkeypatch.delenv("ARGOS_FOUNDRY_BRIDGE_ENABLED", raising=False)
    assert bridge_is_enabled() is False
    assert (
        propagate_coverage_decision_to_foundry(
            claim_id="CLM-NONEXISTENT", new_posture="ROR_issued"
        )
        is None
    )


def test_bridge_raises_when_flag_set_but_env_missing(monkeypatch):
    """When the flag is on but FOUNDRY_HOSTNAME/FOUNDRY_TOKEN are
    missing, fail loudly so misconfig surfaces immediately.

    Set to empty string (not delenv) because the bridge calls
    load_dotenv() which would otherwise reload .env and reinstate
    values that the developer's local environment happens to have set.
    """
    monkeypatch.setenv("ARGOS_FOUNDRY_BRIDGE_ENABLED", "1")
    monkeypatch.setenv("FOUNDRY_HOSTNAME", "")
    monkeypatch.setenv("FOUNDRY_TOKEN", "")
    reset_client_cache()
    with pytest.raises(FoundryBridgeNotConfigured):
        propagate_coverage_decision_to_foundry(
            claim_id="CLM-001", new_posture="ROR_issued"
        )


def test_bridge_is_enabled_treats_empty_string_as_off(monkeypatch):
    """Empty string is off (not truthy)."""
    monkeypatch.setenv("ARGOS_FOUNDRY_BRIDGE_ENABLED", "")
    assert bridge_is_enabled() is False


# ---------------------------------------------------------------------------
# Integration test — live Foundry round-trip
# ---------------------------------------------------------------------------


@pytest.mark.foundry_integration
@pytest.mark.skipif(
    not os.environ.get("FOUNDRY_TOKEN"),
    reason="FOUNDRY_TOKEN not set; integration test skipped",
)
def test_bridge_round_trip_flips_claim_posture(monkeypatch):
    """Live OSDK call: flip CLM-001 to under_investigation (the
    baseline value) and read it back.

    Uses CLM-001 as the canary because the smoke test already flipped
    it earlier; the deterministic test target lets us re-run this
    suite without polluting other claims. Final state after this test
    is always `under_investigation`.
    """
    from argos_osdk_sdk import FoundryClient, UserTokenAuth

    monkeypatch.setenv("ARGOS_FOUNDRY_BRIDGE_ENABLED", "1")
    reset_client_cache()

    op_id = propagate_coverage_decision_to_foundry(
        claim_id="CLM-001",
        new_posture="under_investigation",
    )
    assert op_id is not None
    assert isinstance(op_id, str)
    assert op_id.startswith("ri.actions.")

    # Independent read-back (don't trust the cached client; build a
    # fresh one to verify state landed in Foundry-truth, not local cache).
    client = FoundryClient(
        auth=UserTokenAuth(token=os.environ["FOUNDRY_TOKEN"]),
        hostname=os.environ["FOUNDRY_HOSTNAME"],
    )
    claim = client.ontology.objects.ClaimsV1.get("CLM-001")
    assert claim.coverage_posture == "under_investigation"
