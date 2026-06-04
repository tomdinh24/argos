"""Coverage workflow's Foundry writeback bridge.

Wraps the OSDK call to Foundry's `apply_coverage_decision` Action Type
so `services/orchestrator/coverage_actions.py` doesn't need to know
about OSDK internals. Single responsibility: take a (claim_id, posture)
pair and ensure the Foundry-side ClaimsV1 object reflects it.

This is the canonical bridge pattern. The other four writeback
workflows (Reserve, Liability, Recovery, Closure) will follow the same
shape:
  - one module per workflow in `services/foundry/<workflow>_bridge.py`
  - one `propagate_<workflow>_decision_to_foundry(...)` function
  - same exception ladder: NotConfigured / Disabled / OSDK-level errors
  - same observability hook (operation_id returned for audit)

See `docs/architecture/foundry-bridge-pattern.md` for the contract
the other workflows must conform to.
"""
from __future__ import annotations

import logging
from typing import Literal

from argos.services.foundry.client import (
    bridge_is_enabled,
    get_foundry_client,
    raise_if_action_invalid,
)

logger = logging.getLogger(__name__)


CoveragePosture = Literal[
    "under_investigation", "ROR_issued", "denied", "accepted"
]


class CoverageBridgeError(RuntimeError):
    """The Foundry-side write failed.

    Includes the OSDK-level cause as `__cause__` so the orchestrator
    can decide whether to retry, queue, or surface to the operator.
    """


def propagate_coverage_decision_to_foundry(
    claim_id: str,
    new_posture: CoveragePosture,
) -> str | None:
    """Mirror Argos's Pydantic-side coverage decision into Foundry.

    Calls Foundry's `apply_coverage_decision` Action Type via OSDK,
    flipping `ClaimsV1.coverage_posture` on the targeted Claim.

    Args:
        claim_id: the Foundry-side primary key of the Claim (matches
            Argos's `Claim.claim_id`).
        new_posture: one of the four allowed posture literals. Caller
            (`services/orchestrator/coverage_actions.py`) has already
            validated this against Argos's transition rules; the bridge
            performs no additional posture-graph checks.

    Returns:
        Foundry's `operation_id` (string RID) on success, suitable for
        logging into Argos's AgentAction audit substrate so we can
        cross-reference Pydantic-side and Foundry-side writes.

        Returns `None` when the bridge feature flag is off — caller
        should treat as "Pydantic-side write committed, Foundry-side
        write skipped by design".

    Raises:
        CoverageBridgeError — the OSDK call failed (Foundry returned
            non-VALID validation, network/auth failure, etc.). Caller
            decides whether to retry, queue, or surface.
        FoundryBridgeNotConfigured — env vars missing; flag is on but
            we can't reach Foundry. Propagates unchanged from
            `client.get_foundry_client()`.
        ImportError — argos_live_sdk not installed; same propagation.

    Design notes:
      - We do NOT swallow OSDK errors. A bridge that says "I tried" but
        leaves the substrates out of sync is the worst failure mode.
        Better to raise and let the caller log + queue.
      - We do NOT verify the read-back state here. The smoke test
        (scripts/foundry_smoke_test.py) does that. Production bridges
        should be invocation-only; verification is a separate concern.
    """
    if not bridge_is_enabled():
        logger.debug(
            "coverage bridge: ARGOS_FOUNDRY_BRIDGE_ENABLED not set; "
            "skipping Foundry write for claim_id=%s new_posture=%s",
            claim_id,
            new_posture,
        )
        return None

    client = get_foundry_client()

    try:
        result = client.ontology.actions.apply_coverage_decision_v2(
            claim=claim_id,
            new_posture=new_posture,
        )
    except Exception as e:
        # Catch the broad Exception is deliberate: OSDK raises a wide
        # exception family (auth, validation, network) we re-wrap into
        # a single bridge-level error so callers have one type to
        # catch. The original cause is preserved via __cause__.
        raise CoverageBridgeError(
            f"Foundry apply_coverage_decision failed for claim_id={claim_id!r} "
            f"new_posture={new_posture!r}: {e}"
        ) from e

    raise_if_action_invalid(
        result, CoverageBridgeError, "apply_coverage_decision_v2",
        claim_id=claim_id, new_posture=new_posture,
    )
    operation_id = getattr(result, "operation_id", None)
    logger.info(
        "coverage bridge: Foundry write committed claim_id=%s new_posture=%s "
        "operation_id=%s",
        claim_id,
        new_posture,
        operation_id,
    )
    return operation_id


__all__ = [
    "CoverageBridgeError",
    "CoveragePosture",
    "propagate_coverage_decision_to_foundry",
]
