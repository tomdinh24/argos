"""Liability workflow's Foundry writeback bridge.

Mirrors `coverage_bridge.py` per the contract in
[`docs/architecture/foundry-bridge-pattern.md`](../../../docs/architecture/foundry-bridge-pattern.md).

Wraps the OSDK call to Foundry's `apply-liability-decision` Action Type
so `services/orchestrator/liability_actions.py` doesn't need to know
about OSDK internals.
"""
from __future__ import annotations

import logging

from argos.services.foundry.client import (
    bridge_is_enabled,
    get_foundry_client,
    raise_if_action_invalid,
)

logger = logging.getLogger(__name__)


class LiabilityBridgeError(RuntimeError):
    """The Foundry-side liability write failed.

    Includes the OSDK-level cause as `__cause__`.
    """


def propagate_liability_decision_to_foundry(
    claim_id: str,
    *,
    accept: bool,
    source_assessment_id: str | None = None,
) -> str | None:
    """Mirror Argos's Pydantic-side liability decision into Foundry.

    Calls Foundry's `apply-liability-decision` Action Type via OSDK.
    Caller (`services/orchestrator/liability_actions.py`) has already
    applied the Pydantic-side mutation including the LiabilityAssessment
    apportionment commit; the bridge performs no additional validation.

    Args:
        claim_id: Foundry-side primary key of the Claim.
        accept: True to accept the specialist's apportionment;
            False to reject.
        source_assessment_id: optional LiabilityAssessment / AgentAction
            RID that produced the recommendation. Forwarded for audit.

    Returns:
        Foundry's `operation_id` on success, `None` when the feature
        flag is off.

    Raises:
        LiabilityBridgeError — OSDK call failed.
        FoundryBridgeNotConfigured — env vars missing.
        ImportError — argos_live_sdk not installed.
    """
    if not bridge_is_enabled():
        logger.debug(
            "liability bridge: ARGOS_FOUNDRY_BRIDGE_ENABLED not set; "
            "skipping Foundry write for claim_id=%s accept=%s",
            claim_id,
            accept,
        )
        return None

    client = get_foundry_client()

    try:
        result = client.ontology.actions.apply_liability_decision(
            claim=claim_id,
            accept=accept,
            source_assessment_id=source_assessment_id,
        )
    except Exception as e:
        raise LiabilityBridgeError(
            f"Foundry apply_liability_decision failed for claim_id={claim_id!r} "
            f"accept={accept!r}: {e}"
        ) from e

    raise_if_action_invalid(
        result, LiabilityBridgeError, "apply_liability_decision",
        claim_id=claim_id, accept=accept,
    )
    operation_id = getattr(result, "operation_id", None)
    logger.info(
        "liability bridge: Foundry write committed claim_id=%s accept=%s "
        "operation_id=%s source_assessment_id=%s",
        claim_id,
        accept,
        operation_id,
        source_assessment_id,
    )
    return operation_id


__all__ = [
    "LiabilityBridgeError",
    "propagate_liability_decision_to_foundry",
]
