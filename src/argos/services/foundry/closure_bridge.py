"""Closure workflow's Foundry writeback bridge.

Mirrors `coverage_bridge.py` per the contract in
[`docs/architecture/foundry-bridge-pattern.md`](../../../docs/architecture/foundry-bridge-pattern.md).

Two functions — closure and reopen — share one bridge module because
they belong to the same workflow and call paired Foundry Action Types
(`apply-closure-decision` and `apply-reopen-decision`).
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


# Mirrors `Recommendation` in `schemas/workflows/closure.py`. Re-declared
# here so the bridge boundary self-documents the full enum without
# pulling in the schemas package.
ClosureRecommendation = Literal[
    "ready_to_close_with_payment",
    "ready_to_close_without_payment",
    "closed_with_open_recovery",
    "soft_close_pending_medicare_final_demand",
    "soft_close_pending_section_111_confirmation",
    "soft_close_pending_lien_release_letter",
    "soft_close_pending_release_execution",
    "blocked_by_defects",
    "requires_senior_review",
    "requires_legal_review",
    "recommend_reopen",
]


# Mirrors the inline `reopen_reason` Literal in
# `services/orchestrator/closure_actions.py`.
ReopenReason = Literal[
    "post_close_demand",
    "post_close_lien_surfaced",
    "post_close_cms_final_demand",
    "post_close_litigation_filed",
    "material_new_information",
]


class ClosureBridgeError(RuntimeError):
    """The Foundry-side closure (or reopen) write failed.

    One error type for both functions; callers in
    `closure_actions.py` already distinguish via the function they
    invoked.
    """


def propagate_closure_decision_to_foundry(
    claim_id: str,
    *,
    recommendation: ClosureRecommendation,
    source_assessment_id: str | None = None,
) -> str | None:
    """Mirror Argos's Pydantic-side closure decision into Foundry.

    Calls Foundry's `apply-closure-decision` Action Type via OSDK.
    Caller has already applied the Pydantic-side mutation including
    the ClosureAnalysis recommendation commit.

    Args:
        claim_id: Foundry-side primary key of the Claim.
        recommendation: one of the 11 closure recommendations.
        source_assessment_id: optional ClosureAnalysis / AgentAction
            RID that produced the recommendation.

    Returns:
        Foundry's `operation_id` on success, `None` when flag is off.

    Raises:
        ClosureBridgeError — OSDK call failed.
        FoundryBridgeNotConfigured — env vars missing.
        ImportError — argos_live_sdk not installed.
    """
    if not bridge_is_enabled():
        logger.debug(
            "closure bridge: ARGOS_FOUNDRY_BRIDGE_ENABLED not set; "
            "skipping Foundry write for claim_id=%s recommendation=%s",
            claim_id,
            recommendation,
        )
        return None

    client = get_foundry_client()

    try:
        result = client.ontology.actions.apply_closure_decision(
            claim=claim_id,
            recommendation=recommendation,
            source_assessment_id=source_assessment_id,
        )
    except Exception as e:
        raise ClosureBridgeError(
            f"Foundry apply_closure_decision failed for claim_id={claim_id!r} "
            f"recommendation={recommendation!r}: {e}"
        ) from e

    raise_if_action_invalid(
        result, ClosureBridgeError, "apply_closure_decision",
        claim_id=claim_id, recommendation=recommendation,
    )
    operation_id = getattr(result, "operation_id", None)
    logger.info(
        "closure bridge: Foundry write committed claim_id=%s recommendation=%s "
        "operation_id=%s source_assessment_id=%s",
        claim_id,
        recommendation,
        operation_id,
        source_assessment_id,
    )
    return operation_id


def propagate_reopen_decision_to_foundry(
    claim_id: str,
    *,
    reopen_reason: ReopenReason,
    source_assessment_id: str | None = None,
) -> str | None:
    """Mirror Argos's Pydantic-side reopen decision into Foundry.

    Calls Foundry's `apply-reopen-decision` Action Type via OSDK.
    Caller has already moved the Claim out of terminal closure state
    in the Pydantic substrate.

    Args:
        claim_id: Foundry-side primary key of the Claim.
        reopen_reason: one of the five reopen reasons.
        source_assessment_id: optional AgentAction RID that surfaced
            the reopen trigger.

    Returns:
        Foundry's `operation_id` on success, `None` when flag is off.

    Raises:
        ClosureBridgeError — OSDK call failed (shared with closure
            since they're paired functions of the same workflow).
        FoundryBridgeNotConfigured — env vars missing.
        ImportError — argos_live_sdk not installed.
    """
    if not bridge_is_enabled():
        logger.debug(
            "reopen bridge: ARGOS_FOUNDRY_BRIDGE_ENABLED not set; "
            "skipping Foundry write for claim_id=%s reopen_reason=%s",
            claim_id,
            reopen_reason,
        )
        return None

    client = get_foundry_client()

    try:
        result = client.ontology.actions.apply_reopen_decision(
            claim=claim_id,
            reopen_reason=reopen_reason,
            source_assessment_id=source_assessment_id,
        )
    except Exception as e:
        raise ClosureBridgeError(
            f"Foundry apply_reopen_decision failed for claim_id={claim_id!r} "
            f"reopen_reason={reopen_reason!r}: {e}"
        ) from e

    raise_if_action_invalid(
        result, ClosureBridgeError, "apply_reopen_decision",
        claim_id=claim_id, reopen_reason=reopen_reason,
    )
    operation_id = getattr(result, "operation_id", None)
    logger.info(
        "reopen bridge: Foundry write committed claim_id=%s reopen_reason=%s "
        "operation_id=%s source_assessment_id=%s",
        claim_id,
        reopen_reason,
        operation_id,
        source_assessment_id,
    )
    return operation_id


__all__ = [
    "ClosureBridgeError",
    "ClosureRecommendation",
    "ReopenReason",
    "propagate_closure_decision_to_foundry",
    "propagate_reopen_decision_to_foundry",
]
