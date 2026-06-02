"""Recovery → Claim writeback action.

The Recovery workflow emits a `RecoveryAssessment` with a pursuit
recommendation (pursue / route_to_af / route_to_litigation /
route_to_negotiated_demand / abstain / senior_review_required). When
the adjuster commits the pursuit decision, the cockpit calls
`apply_recovery_decision` to flip
`claim.recovery_pursuit_decision_committed` from False → True AND
mirror the committed literal onto `claim.recovery_pursuit_decision`.

This is the **producer** side of the recovery commit loop. The
**consumer** side is Closure's `closed_with_open_recovery` decoupling
logic — Closure can close the indemnity ledger while keeping the
subro file open iff the recovery decision was `pursue`.

Pursuit decisions are not auto-applied — they carry SOL and forum
weight (AF compulsory jurisdiction, §768.0427 paid-not-billed). A
human commits them. See feedback memory
[[multi_agent_decision_framework]].
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from argos.ontology.types import Caseload, Claim
from argos.services.orchestrator.audit_log import (
    VALIDATOR_PASS,
    append_agent_action,
    build_agent_action,
)


RecoveryDecisionLiteral = Literal[
    "pursue",
    "route_to_af",
    "route_to_litigation",
    "route_to_negotiated_demand",
    "abstain",
    "senior_review_required",
]


def apply_recovery_decision(
    caseload: Caseload,
    claim_id: str,
    *,
    decision: RecoveryDecisionLiteral,
    source_assessment_id: str | None = None,
    audit_log_root: Path | None = None,
    now: datetime | None = None,
) -> Caseload:
    """Commit the Recovery workflow's pursuit decision.

    Returns a new caseload with the targeted Claim's
    `recovery_pursuit_decision_committed` set to True and
    `recovery_pursuit_decision` set to `decision`. Input caseload is
    not mutated.

    `senior_review_required` is a routing signal, not a commit
    action — use the cockpit's escalation path; this entry point
    rejects it.

    When `audit_log_root` is provided, an AgentAction(`validator_pass`)
    row is appended.

    Raises:
      ValueError — claim_id not present, or decision is
        `senior_review_required` (routing signal).

    Idempotent: re-committing the same decision is a no-op.
    """
    target: Claim | None = None
    for c in caseload.claims:
        if c.claim_id == claim_id:
            target = c
            break
    if target is None:
        raise ValueError(
            f"apply_recovery_decision: claim_id={claim_id!r} not present "
            f"in caseload.",
        )

    if decision == "senior_review_required":
        raise ValueError(
            f"apply_recovery_decision: decision={decision!r} is a routing "
            f"signal, not a commit action. Resolve the escalation first.",
        )

    if (
        target.recovery_pursuit_decision_committed
        and target.recovery_pursuit_decision == decision
    ):
        return caseload

    new_claim = target.model_copy(update={
        "recovery_pursuit_decision_committed": True,
        "recovery_pursuit_decision": decision,
    })
    new_claims = [
        new_claim if c.claim_id == claim_id else c
        for c in caseload.claims
    ]
    new_caseload = caseload.model_copy(update={"claims": new_claims})

    if audit_log_root is not None:
        summary = f"Recovery decision committed: {decision}"
        if source_assessment_id:
            summary += f" (assessment={source_assessment_id})"
        append_agent_action(
            build_agent_action(
                claim_id=claim_id,
                workflow="recovery",
                action_type=VALIDATOR_PASS,
                summary=summary,
                success=True,
                timestamp=now or datetime.now(timezone.utc),
            ),
            log_root=audit_log_root,
        )

    return new_caseload


__all__ = [
    "RecoveryDecisionLiteral",
    "apply_recovery_decision",
]
