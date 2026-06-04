"""Liability → Claim writeback action.

The Liability workflow emits a `LiabilityAssessment` with per-party
fault percentages, the applicable regime, and the bar status. When
the adjuster commits the apportionment, the cockpit calls
`apply_liability_decision` to flip
`claim.liability_apportionment_committed` from False → True.

This is the **producer** side of the apportionment commit loop. The
**consumer** side is:
  - Closure gate A2 (`liability_apportionment_uncommitted`) — fails
    when this field is False at close.
  - Recovery's recoverable-basis math — Recovery's calculator reads
    the upstream Liability snapshot, which is sourced from the
    committed apportionment.

Apportionment commits are not auto-applied — they carry bad-faith
weight (Boston Old Colony, Macola). A human commits them. See
feedback memory [[multi_agent_decision_framework]].
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from argos.ontology.types import Caseload, Claim
from argos.services.foundry.liability_bridge import (
    LiabilityBridgeError,
    propagate_liability_decision_to_foundry,
)
from argos.services.orchestrator.audit_log import (
    VALIDATOR_PASS,
    append_agent_action,
    build_agent_action,
)

logger = logging.getLogger(__name__)


def apply_liability_decision(
    caseload: Caseload,
    claim_id: str,
    *,
    accept: bool,
    source_assessment_id: str | None = None,
    audit_log_root: Path | None = None,
    now: datetime | None = None,
) -> Caseload:
    """Commit (or defer) the Liability workflow's apportionment.

    Returns a new caseload with the targeted Claim's
    `liability_apportionment_committed` field set. Input caseload is
    not mutated.

    Behavior:
      - `accept=True` → flip the field to True.
      - `accept=False` → no-op (defer).

    When `audit_log_root` is provided AND `accept=True`, an
    AgentAction(`validator_pass`) row is appended.

    Raises:
      ValueError — claim_id not present.

    Idempotent: re-committing already-True is a no-op.
    """
    target: Claim | None = None
    for c in caseload.claims:
        if c.claim_id == claim_id:
            target = c
            break
    if target is None:
        raise ValueError(
            f"apply_liability_decision: claim_id={claim_id!r} not present "
            f"in caseload.",
        )

    if not accept:
        return caseload

    if target.liability_apportionment_committed:
        return caseload

    new_claim = target.model_copy(update={
        "liability_apportionment_committed": True,
    })
    new_claims = [
        new_claim if c.claim_id == claim_id else c
        for c in caseload.claims
    ]
    new_caseload = caseload.model_copy(update={"claims": new_claims})

    # Foundry-side propagation. Feature-flagged inside the bridge.
    # Errors are logged, not raised — the Pydantic substrate has
    # already committed and downstream Argos consumers read from it.
    try:
        operation_id = propagate_liability_decision_to_foundry(
            claim_id=claim_id,
            accept=True,
            source_assessment_id=source_assessment_id,
        )
        if operation_id is not None:
            logger.info(
                "liability decision propagated to Foundry: claim_id=%s "
                "operation_id=%s source_assessment_id=%s",
                claim_id,
                operation_id,
                source_assessment_id,
            )
    except LiabilityBridgeError as e:
        logger.error(
            "liability decision Pydantic-side committed but Foundry "
            "propagation failed: claim_id=%s err=%s",
            claim_id,
            e,
        )
    except Exception as e:  # noqa: BLE001 — surface unexpected bridge failures via log, don't crash caller
        logger.exception(
            "liability decision: unexpected error during Foundry "
            "propagation for claim_id=%s: %s",
            claim_id,
            e,
        )

    if audit_log_root is not None:
        summary = "Liability apportionment committed"
        if source_assessment_id:
            summary += f" (assessment={source_assessment_id})"
        append_agent_action(
            build_agent_action(
                claim_id=claim_id,
                workflow="liability",
                action_type=VALIDATOR_PASS,
                summary=summary,
                success=True,
                timestamp=now or datetime.now(timezone.utc),
            ),
            log_root=audit_log_root,
        )

    return new_caseload


__all__ = ["apply_liability_decision"]
