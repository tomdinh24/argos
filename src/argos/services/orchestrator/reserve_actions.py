"""Reserve → Claim writeback action.

The Reserve workflow emits a `ReserveAnalysis` the adjuster reviews in
the cockpit. When the adjuster commits the recommended outstanding
band ("Accept reserve change", "Defer reserve change"), the cockpit
calls `apply_reserve_decision` to flip
`claim.reserve_decision_committed` from False → True.

This is the **producer** side of the reserve commit loop. Reserve
decisions are not auto-applied — they carry financial weight
(authority tier, regulatory disclosure under NAIC Reg 902), so a
human commits them. See feedback memory
[[multi_agent_decision_framework]].

In v1 the value stored on the Claim is a single boolean — the
specific reserve amounts live in the workflow result JSON. Promotion
to typed fields (per-component bands on Claim) is part of the
Foundry projection (§0.2 #8).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from argos.ontology.types import Caseload, Claim
from argos.services.foundry.reserve_bridge import (
    ReserveBridgeError,
    propagate_reserve_decision_to_foundry,
)
from argos.services.orchestrator.audit_log import (
    VALIDATOR_PASS,
    append_agent_action,
    build_agent_action,
)

logger = logging.getLogger(__name__)


def apply_reserve_decision(
    caseload: Caseload,
    claim_id: str,
    *,
    accept: bool,
    source_assessment_id: str | None = None,
    audit_log_root: Path | None = None,
    now: datetime | None = None,
) -> Caseload:
    """Commit (or defer) the Reserve workflow's recommended outstanding band.

    Returns a new caseload with the targeted Claim's
    `reserve_decision_committed` field set. Input caseload is not
    mutated.

    Behavior:
      - `accept=True` → flip `reserve_decision_committed` to True.
      - `accept=False` → no-op (defer). Field stays False.

    When `audit_log_root` is provided AND `accept=True`, an
    AgentAction(`validator_pass`) row is appended documenting the
    commit. The action's `summary` carries the
    `source_assessment_id` for provenance.

    Raises:
      ValueError — claim_id not present.

    Idempotent: re-committing a claim already at True is a no-op.
    """
    target: Claim | None = None
    for c in caseload.claims:
        if c.claim_id == claim_id:
            target = c
            break
    if target is None:
        raise ValueError(
            f"apply_reserve_decision: claim_id={claim_id!r} not present "
            f"in caseload.",
        )

    if not accept:
        # Defer — no field change, no audit row.
        return caseload

    if target.reserve_decision_committed:
        # Idempotent — already committed.
        return caseload

    new_claim = target.model_copy(update={"reserve_decision_committed": True})
    new_claims = [
        new_claim if c.claim_id == claim_id else c
        for c in caseload.claims
    ]
    new_caseload = caseload.model_copy(update={"claims": new_claims})

    # Foundry-side propagation. Feature-flagged inside the bridge.
    # Errors are logged, not raised — the Pydantic substrate has
    # already committed and downstream Argos consumers read from it.
    try:
        operation_id = propagate_reserve_decision_to_foundry(
            claim_id=claim_id,
            accept=True,
            source_assessment_id=source_assessment_id,
        )
        if operation_id is not None:
            logger.info(
                "reserve decision propagated to Foundry: claim_id=%s "
                "operation_id=%s source_assessment_id=%s",
                claim_id,
                operation_id,
                source_assessment_id,
            )
    except ReserveBridgeError as e:
        logger.error(
            "reserve decision Pydantic-side committed but Foundry "
            "propagation failed: claim_id=%s err=%s",
            claim_id,
            e,
        )
    except Exception as e:  # noqa: BLE001 — surface unexpected bridge failures via log, don't crash caller
        logger.exception(
            "reserve decision: unexpected error during Foundry "
            "propagation for claim_id=%s: %s",
            claim_id,
            e,
        )

    if audit_log_root is not None:
        summary = "Reserve decision committed"
        if source_assessment_id:
            summary += f" (assessment={source_assessment_id})"
        append_agent_action(
            build_agent_action(
                claim_id=claim_id,
                workflow="reserve",
                action_type=VALIDATOR_PASS,
                summary=summary,
                success=True,
                timestamp=now or datetime.now(timezone.utc),
            ),
            log_root=audit_log_root,
        )

    return new_caseload


__all__ = ["apply_reserve_decision"]
