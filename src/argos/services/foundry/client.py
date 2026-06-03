"""Foundry OSDK client builder — single source of truth for the FoundryClient.

Every workflow bridge (coverage, reserve, liability, recovery, closure)
calls `get_foundry_client()` rather than constructing its own client.
Reasons:
  - One place to swap UserTokenAuth -> ConfidentialClientAuth when the
    tier bump unlocks Application permissions (one-line diff here).
  - One place to add scopes, retries, telemetry, or error mappers.
  - Singleton-ish behavior: the FoundryClient is cheap to build but
    holding many connections per-process is wasteful; the cached
    accessor avoids it without forcing global state on callers.

The client is OPT-IN. Argos's analytical workflows do not talk to
Foundry; only the writeback layer (`services/orchestrator/*_actions.py`
-> `services/foundry/*_bridge.py`) does. Per-bridge config:
  - `ARGOS_FOUNDRY_BRIDGE_ENABLED=1` to actually propagate writes.
    When unset/empty, bridges no-op (so unit/integration tests stay
    hermetic by default).
  - `FOUNDRY_HOSTNAME`, `FOUNDRY_TOKEN` in `.env` (or shell env) for
    auth. Bridges raise `FoundryBridgeNotConfigured` if either is
    missing AND the bridge was asked to propagate.

This module does NOT import the OSDK at module load. Reason: the OSDK
package (`argos_osdk_sdk`) is a private Foundry-pypi install and may
not be present in every environment (CI without secrets, contributor
machines). The import is deferred to the call site so absence is a
runtime error only when the bridge is actually invoked.
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import TYPE_CHECKING

from dotenv import load_dotenv

if TYPE_CHECKING:
    from argos_osdk_sdk import FoundryClient


# Lazy import sentinel — see module docstring.
_OSDK_IMPORT_ERROR_HINT = (
    "argos_osdk_sdk is not installed. Install per "
    "`docs/foundry-osdk-install.md` (private Foundry pypi)."
)


class FoundryBridgeNotConfigured(RuntimeError):
    """Raised when a bridge is asked to propagate but env is unset."""


class FoundryBridgeDisabled(RuntimeError):
    """Raised when a bridge is invoked without the feature flag.

    Bridges should catch this and no-op silently — it's expected
    behavior outside production. Surfaced as an exception (not a
    boolean return) so the call-site is forced to handle it explicitly,
    not silently swallow Foundry-side failures.
    """


def bridge_is_enabled() -> bool:
    """Return True if the bridge feature flag is on.

    Decoupled from `get_foundry_client()` so that callers can short-circuit
    BEFORE building a client (which would touch the OSDK import path).
    """
    load_dotenv()
    return bool(os.environ.get("ARGOS_FOUNDRY_BRIDGE_ENABLED", "").strip())


@lru_cache(maxsize=1)
def get_foundry_client() -> "FoundryClient":
    """Build (and cache) the FoundryClient from env.

    Lazy-imports argos_osdk_sdk so the rest of Argos imports cleanly
    in envs without the private OSDK installed.

    Raises:
        FoundryBridgeNotConfigured — env vars missing.
        ImportError — argos_osdk_sdk not installed (with install hint).

    TODO(post tier-bump): swap UserTokenAuth for ConfidentialClientAuth
    using FOUNDRY_CLIENT_ID + FOUNDRY_CLIENT_SECRET (already in .env);
    auto-refresh on token expiry, no manual rotation.
    """
    load_dotenv()

    hostname = os.environ.get("FOUNDRY_HOSTNAME")
    token = os.environ.get("FOUNDRY_TOKEN")
    if not hostname or not token:
        missing = [
            name
            for name, val in [("FOUNDRY_HOSTNAME", hostname), ("FOUNDRY_TOKEN", token)]
            if not val
        ]
        raise FoundryBridgeNotConfigured(
            f"FoundryClient cannot be built: missing env var(s) {missing}. "
            "Set them in .env or shell, then retry."
        )

    try:
        from argos_osdk_sdk import FoundryClient, UserTokenAuth
    except ImportError as e:
        raise ImportError(_OSDK_IMPORT_ERROR_HINT) from e

    return FoundryClient(auth=UserTokenAuth(token=token), hostname=hostname)


def reset_client_cache() -> None:
    """Drop the cached client.

    Useful in tests that need to re-init after mutating env vars, and
    in production if we ever wire a rotation hook on token expiry.
    """
    get_foundry_client.cache_clear()


__all__ = [
    "FoundryBridgeDisabled",
    "FoundryBridgeNotConfigured",
    "bridge_is_enabled",
    "get_foundry_client",
    "reset_client_cache",
]
