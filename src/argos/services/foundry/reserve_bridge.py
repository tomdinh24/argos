"""Reserve workflow's Foundry writeback bridge.

Mirrors `coverage_bridge.py` per the contract in
[`docs/architecture/foundry-bridge-pattern.md`](../../../docs/architecture/foundry-bridge-pattern.md).

Wraps the OSDK call to Foundry's `apply-reserve-decision` Action Type
so `services/orchestrator/reserve_actions.py` doesn't need to know
about OSDK internals. Single responsibility: take a (claim_id, accept)
pair and ensure the Foundry-side Claim object reflects the decision.
"""
from __future__ import annotations

import logging

from argos.services.foundry.client import (
    bridge_is_enabled,
    get_foundry_client,
    raise_if_action_invalid,
)

logger = logging.getLogger(__name__)


class ReserveBridgeError(RuntimeError):
    """The Foundry-side reserve write failed.

    Includes the OSDK-level cause as `__cause__` so the orchestrator
    can decide whether to retry, queue, or surface to the operator.
    """


def propagate_reserve_decision_to_foundry(
    claim_id: str,
    *,
    accept: bool,
    source_assessment_id: str | None = None,
) -> str | None:
    """Mirror Argos's Pydantic-side reserve decision into Foundry.

    Calls Foundry's `apply-reserve-decision` Action Type via OSDK.
    `source_assessment_id` is forwarded for audit cross-reference;
    the Foundry-side action validator does not consume it today
    (placeholder write-back logic per AI FDE), but the parameter is
    accepted so callers don't need a signature change when
    function-backed actions land.

    Args:
        claim_id: Foundry-side primary key of the Claim.
        accept: True to accept the specialist's reserve recommendation;
            False to reject. Caller has already applied the Pydantic-side
            mutation; the bridge does no additional validation.
        source_assessment_id: optional AgentAction RID that produced the
            recommendation. Forwarded to OSDK for future audit binding.

    Returns:
        Foundry's `operation_id` (RID string) on success.
        Returns `None` when `ARGOS_FOUNDRY_BRIDGE_ENABLED` is off —
        callers should treat as "Pydantic-side committed, Foundry-side
        write skipped by design."

    Raises:
        ReserveBridgeError — OSDK call failed (Foundry rejected the
            action, network/auth failure, etc.).
        FoundryBridgeNotConfigured — env vars missing; propagates from
            `client.get_foundry_client()`.
        ImportError — argos_live_sdk not installed; same propagation.
    """
    if not bridge_is_enabled():
        logger.debug(
            "reserve bridge: ARGOS_FOUNDRY_BRIDGE_ENABLED not set; "
            "skipping Foundry write for claim_id=%s accept=%s",
            claim_id,
            accept,
        )
        return None

    client = get_foundry_client()

    try:
        result = client.ontology.actions.apply_reserve_decision(
            claim=claim_id,
            accept=accept,
            source_assessment_id=source_assessment_id,
        )
    except Exception as e:
        raise ReserveBridgeError(
            f"Foundry apply_reserve_decision failed for claim_id={claim_id!r} "
            f"accept={accept!r}: {e}"
        ) from e

    raise_if_action_invalid(
        result, ReserveBridgeError, "apply_reserve_decision",
        claim_id=claim_id, accept=accept,
    )
    operation_id = getattr(result, "operation_id", None)
    logger.info(
        "reserve bridge: Foundry write committed claim_id=%s accept=%s "
        "operation_id=%s source_assessment_id=%s",
        claim_id,
        accept,
        operation_id,
        source_assessment_id,
    )
    return operation_id


__all__ = [
    "ReserveBridgeError",
    "propagate_reserve_decision_to_foundry",
]
