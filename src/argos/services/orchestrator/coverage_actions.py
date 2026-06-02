"""Coverage → Claim writeback actions.

The Coverage specialist (analytical) emits a `CoverageRecommendation`
the adjuster reviews in the cockpit. When the adjuster commits the
decision ("Issue ROR letter", "Accept coverage", "Deny coverage"),
the cockpit calls `apply_coverage_decision` to flip the claim's
`coverage_posture` field. That posture is the input the Outreach
Drafter reads when framing every subsequent letter (e.g., adding
the reservation-of-rights paragraph once `ROR_issued`).

This function is the **producer** side of the ROR loop. The
**consumer** side (Drafter reading `claim.coverage_posture`) is
already shipped in `outreach_drafter.SYSTEM_PROMPT`.

By design, this is NOT auto-applied by a Coverage workflow result.
Coverage decisions carry legal weight (waiving defenses, binding the
carrier to pay); a human commits them. See feedback memory
[[multi_agent_decision_framework]] — write-side actions stay
single-threaded under human control, even when the analysis that
informed them was multi-agent.

Decision context: docs/DECISIONS.md →
  "Coverage->Claim writeback (apply_coverage_decision)"
  "ROR escalation: coverage_posture on Claim, drafter responds"

Palantir mapping: this is the `ApplyCoverageDecision` Action Type
fired from the cockpit's coverage-review surface. Mutates the
`Claim` ontology object, emits a `CoveragePostureChanged` event,
and (in production) appends an `AgentAction` row to the audit log
with `source_recommendation_id` for provenance.
"""
from __future__ import annotations

from typing import Literal

from argos.ontology.types import Caseload, Claim


CoveragePosture = Literal[
    "under_investigation", "ROR_issued", "denied", "accepted"
]


def apply_coverage_decision(
    caseload: Caseload,
    claim_id: str,
    *,
    new_posture: CoveragePosture,
    source_recommendation_id: str | None = None,
) -> Caseload:
    """Flip `claim.coverage_posture` on the named claim.

    Returns a new caseload with the targeted Claim's `coverage_posture`
    set to `new_posture`. Input caseload is not mutated.

    `source_recommendation_id` is the upstream artifact that justifies
    the decision (typically a `CoverageRecommendation.recommendation_id`).
    In v1 the value is accepted but not persisted on the Claim itself —
    audit-log writes (with provenance) are a downstream concern. The
    parameter exists now so callers don't need a signature change later.

    Raises:
      ValueError — claim_id not present in the caseload, or the
        posture transition is invalid (see below).

    Valid transitions:
      - `under_investigation` → any (this is the only initial state)
      - `accepted` / `denied` → no further transitions (terminal)
      - `ROR_issued` → `accepted` or `denied` (ROR resolves either way)

    Idempotent: setting the posture to its current value is a no-op
    that returns the same caseload (does not raise). Lets the cockpit
    treat "click ROR_issued" as safe even if the operator clicks
    twice.
    """
    target: Claim | None = None
    for c in caseload.claims:
        if c.claim_id == claim_id:
            target = c
            break
    if target is None:
        raise ValueError(
            f"apply_coverage_decision: claim_id={claim_id!r} not present "
            f"in caseload."
        )

    if target.coverage_posture == new_posture:
        # Idempotent — same posture, no-op.
        return caseload

    _validate_transition(target.coverage_posture, new_posture, claim_id)

    new_claim = target.model_copy(update={"coverage_posture": new_posture})
    new_claims = [
        new_claim if c.claim_id == claim_id else c
        for c in caseload.claims
    ]
    return caseload.model_copy(update={"claims": new_claims})


_TERMINAL_POSTURES: frozenset[str] = frozenset({"accepted", "denied"})


def _validate_transition(
    current: str, target: CoveragePosture, claim_id: str
) -> None:
    """Reject incoherent transitions early.

    `under_investigation` → anything is fine. `ROR_issued` resolves
    into `accepted` or `denied` (or stays `ROR_issued`, handled by
    the idempotent branch above). Terminal postures
    (`accepted`/`denied`) don't transition; re-opening a denied claim
    is a separate, deliberate flow that doesn't reuse this entry
    point.
    """
    if current in _TERMINAL_POSTURES:
        raise ValueError(
            f"apply_coverage_decision: claim {claim_id!r} is in terminal "
            f"posture {current!r}; cannot transition to {target!r}. "
            f"Re-opening a closed-coverage claim is a separate flow."
        )
    if current == "ROR_issued" and target == "under_investigation":
        raise ValueError(
            f"apply_coverage_decision: claim {claim_id!r} cannot regress "
            f"from {current!r} back to {target!r}. ROR is a posture "
            f"commitment — resolve to accepted/denied instead."
        )


__all__ = [
    "CoveragePosture",
    "apply_coverage_decision",
]
