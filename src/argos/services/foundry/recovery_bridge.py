"""Recovery workflow's Foundry writeback bridge.

Mirrors `coverage_bridge.py` per the contract in
[`docs/architecture/foundry-bridge-pattern.md`](../../../docs/architecture/foundry-bridge-pattern.md).

Wraps the OSDK call to Foundry's `apply-recovery-decision` Action Type
so `services/orchestrator/recovery_actions.py` doesn't need to know
about OSDK internals.
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


# Mirrors `RecoveryDecisionLiteral` in
# `services/orchestrator/recovery_actions.py`. Re-declared here so the
# bridge boundary self-documents the allowed values without forcing the
# orchestrator module to import the bridge.
RecoveryDecision = Literal[
    "pursue",
    "route_to_af",
    "route_to_litigation",
    "route_to_negotiated_demand",
    "abstain",
    "senior_review_required",
]


class RecoveryBridgeError(RuntimeError):
    """The Foundry-side recovery write failed.

    Includes the OSDK-level cause as `__cause__`.
    """


def propagate_recovery_decision_to_foundry(
    claim_id: str,
    *,
    decision: RecoveryDecision,
    source_assessment_id: str | None = None,
) -> str | None:
    """Mirror Argos's Pydantic-side recovery decision into Foundry.

    Calls Foundry's `apply-recovery-decision` Action Type via OSDK.
    Caller has already applied the Pydantic-side mutation including
    the RecoveryOpportunity pursuit-decision commit.

    Args:
        claim_id: Foundry-side primary key of the Claim.
        decision: one of the six recovery routes.
        source_assessment_id: optional RecoveryOpportunity / AgentAction
            RID that produced the recommendation.

    Returns:
        Foundry's `operation_id` on success, `None` when flag is off.

    Raises:
        RecoveryBridgeError — OSDK call failed.
        FoundryBridgeNotConfigured — env vars missing.
        ImportError — argos_live_sdk not installed.
    """
    if not bridge_is_enabled():
        logger.debug(
            "recovery bridge: ARGOS_FOUNDRY_BRIDGE_ENABLED not set; "
            "skipping Foundry write for claim_id=%s decision=%s",
            claim_id,
            decision,
        )
        return None

    client = get_foundry_client()

    try:
        result = client.ontology.actions.apply_recovery_decision(
            claim=claim_id,
            decision=decision,
            source_assessment_id=source_assessment_id,
        )
    except Exception as e:
        raise RecoveryBridgeError(
            f"Foundry apply_recovery_decision failed for claim_id={claim_id!r} "
            f"decision={decision!r}: {e}"
        ) from e

    raise_if_action_invalid(
        result, RecoveryBridgeError, "apply_recovery_decision",
        claim_id=claim_id, decision=decision,
    )
    operation_id = getattr(result, "operation_id", None)
    logger.info(
        "recovery bridge: Foundry write committed claim_id=%s decision=%s "
        "operation_id=%s source_assessment_id=%s",
        claim_id,
        decision,
        operation_id,
        source_assessment_id,
    )
    return operation_id


__all__ = [
    "RecoveryBridgeError",
    "RecoveryDecision",
    "propagate_recovery_decision_to_foundry",
]
