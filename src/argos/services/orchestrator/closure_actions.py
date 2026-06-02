"""Closure → Claim writeback actions.

The Closure workflow emits a `ClosureAssessment` the adjuster reviews
in the cockpit. When the adjuster commits the decision
("Close with payment", "Close without payment", "Soft-close pending
lien release", "Reopen claim"), the cockpit calls
`apply_closure_decision` or `apply_reopen_decision` to flip the
claim's `status` field.

This is the **producer** side of the close-loop. Closure decisions
carry legal weight (waiver, MSP exposure, bad-faith timing, OIR
classification); a human commits them. See feedback memory
[[multi_agent_decision_framework]] — write-side actions stay
single-threaded under human control, even when the analysis that
informed them was multi-agent.

Decision context: docs/DECISIONS.md →
  "2026-06-02 — Closure workflow architecture"

Palantir mapping: this is the `ApplyClosureDecision` Action Type
fired from the cockpit's closure-review surface. Mutates the
`Claim` ontology object and (in production) appends an
`AgentAction` row to the audit log with `source_assessment_id`
for provenance.
"""
from __future__ import annotations

from typing import Literal

from argos.ontology.types import Caseload, Claim
from argos.schemas.workflows.closure import Recommendation


# Recommendations that flip Claim.status to "closed"
_CLOSE_RECOMMENDATIONS: frozenset[Recommendation] = frozenset({
    "ready_to_close_with_payment",
    "ready_to_close_without_payment",
    "closed_with_open_recovery",
})

# Recommendations that keep the claim open pending a future condition
_SOFT_CLOSE_RECOMMENDATIONS: frozenset[Recommendation] = frozenset({
    "soft_close_pending_medicare_final_demand",
    "soft_close_pending_section_111_confirmation",
    "soft_close_pending_lien_release_letter",
    "soft_close_pending_release_execution",
})

# Recommendations that block close and route to humans
_BLOCK_RECOMMENDATIONS: frozenset[Recommendation] = frozenset({
    "blocked_by_defects",
    "requires_senior_review",
    "requires_legal_review",
    "recommend_reopen",
})


def apply_closure_decision(
    caseload: Caseload,
    claim_id: str,
    *,
    recommendation: Recommendation,
    source_assessment_id: str | None = None,
) -> Caseload:
    """Flip `claim.status` based on the committed closure recommendation.

    Returns a new caseload with the targeted Claim's `status` updated.
    Input caseload is not mutated.

    Behavior by recommendation literal:
      - ready_to_close_with_payment / ready_to_close_without_payment /
        closed_with_open_recovery → status="closed".
      - soft_close_pending_* → status stays "open"; soft-close state is
        tracked in the upstream ClosureAssessment, not on Claim.status.
      - blocked_by_defects / requires_*_review / recommend_reopen →
        ValueError; these recommendations are not adjuster-commit
        actions, they're routing signals.

    `source_assessment_id` is the upstream ClosureAssessment.request_id
    that justifies the decision. In v1 the value is accepted but not
    persisted on the Claim itself — audit-log writes (with provenance)
    are a downstream concern. The parameter exists now so callers
    don't need a signature change later.

    Raises:
      ValueError — claim_id not present in the caseload, recommendation
        is a routing signal (not a commit action), or the claim is
        already in a terminal state.

    Idempotent: setting status to its current value is a no-op that
    returns the same caseload (does not raise).
    """
    target: Claim | None = None
    for c in caseload.claims:
        if c.claim_id == claim_id:
            target = c
            break
    if target is None:
        raise ValueError(
            f"apply_closure_decision: claim_id={claim_id!r} not present "
            f"in caseload.",
        )

    if recommendation in _BLOCK_RECOMMENDATIONS:
        raise ValueError(
            f"apply_closure_decision: recommendation={recommendation!r} is a "
            f"routing signal, not an adjuster-commit action. Resolve the "
            f"underlying defects / review escalation first.",
        )

    if recommendation in _SOFT_CLOSE_RECOMMENDATIONS:
        # Soft-close keeps the claim open in Claim.status.
        # Per-state tracking lives in the assessment itself.
        return caseload

    if recommendation not in _CLOSE_RECOMMENDATIONS:
        raise ValueError(
            f"apply_closure_decision: unrecognized recommendation "
            f"{recommendation!r}.",
        )

    if target.status == "closed":
        # Idempotent — already closed.
        return caseload

    if target.status == "suspended":
        raise ValueError(
            f"apply_closure_decision: claim {claim_id!r} is suspended; "
            f"resolve the suspension before closing.",
        )

    new_claim = target.model_copy(update={"status": "closed"})
    new_claims = [
        new_claim if c.claim_id == claim_id else c
        for c in caseload.claims
    ]
    return caseload.model_copy(update={"claims": new_claims})


def apply_reopen_decision(
    caseload: Caseload,
    claim_id: str,
    *,
    reopen_reason: Literal[
        "post_close_demand",
        "post_close_lien_surfaced",
        "post_close_cms_final_demand",
        "post_close_litigation_filed",
        "material_new_information",
    ],
    source_assessment_id: str | None = None,
) -> Caseload:
    """Flip a closed claim back to status="reopened" — same Claim ID.

    Per ClaimCenter precedent, reopen reuses the original Claim ID
    rather than spawning a new one, so the claim's history,
    AgentAction ledger, and reserves remain attached.

    Raises:
      ValueError — claim not present, or claim is currently "open" /
        "suspended" (only "closed" → "reopened" is a valid transition
        through this entry point).
    """
    target: Claim | None = None
    for c in caseload.claims:
        if c.claim_id == claim_id:
            target = c
            break
    if target is None:
        raise ValueError(
            f"apply_reopen_decision: claim_id={claim_id!r} not present "
            f"in caseload.",
        )

    if target.status == "reopened":
        # Idempotent.
        return caseload

    if target.status != "closed":
        raise ValueError(
            f"apply_reopen_decision: claim {claim_id!r} is in status "
            f"{target.status!r}; only closed claims can be reopened.",
        )

    new_claim = target.model_copy(update={"status": "reopened"})
    new_claims = [
        new_claim if c.claim_id == claim_id else c
        for c in caseload.claims
    ]
    return caseload.model_copy(update={"claims": new_claims})


__all__ = [
    "apply_closure_decision",
    "apply_reopen_decision",
]
