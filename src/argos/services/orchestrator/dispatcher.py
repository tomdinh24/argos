"""Posture → workflow routing.

Pure function over `RelevanceCall`: given one Reader output, returns
the list of `Job` objects that should be enqueued. The mapping is
small and fixed for v1:

    posture_changed == "coverage"  → [Coverage]
    posture_changed == "reserve"   → [Reserve]
    posture_changed == "liability" → [Liability]
    posture_changed == "damages"   → [Reserve, Liability]
                                     (damages affect both reserve
                                     adequacy and liability negotiation)
    relevant == False              → []

Jobs returned here are NOT enqueued yet — the caller enqueues them
through `JobQueue.enqueue()`, which enforces idempotency. Keeping the
dispatcher pure makes it trivially testable.
"""
from __future__ import annotations

from argos.schemas.workflows.document_reader import RelevanceCall
from argos.services.orchestrator.job import Job


# Posture → list of workflow names. Tweakable in one place.
POSTURE_TO_WORKFLOWS: dict[str, list[str]] = {
    "coverage": ["coverage"],
    "reserve": ["reserve"],
    "liability": ["liability"],
    "damages": ["reserve", "liability"],
}


def dispatch(call: RelevanceCall, claim_id: str) -> list[Job]:
    """Translate one Reader call into the jobs it implies.

    Returns an empty list when `call.relevant == False`. Otherwise
    returns one Job per workflow named in `POSTURE_TO_WORKFLOWS`
    for the posture the Reader flagged.
    """
    if not call.relevant or call.posture_changed is None:
        return []

    workflows = POSTURE_TO_WORKFLOWS.get(call.posture_changed, [])
    return [
        Job(
            workflow=name,
            claim_id=claim_id,
            triggered_by_doc_id=call.document_id,
            posture_changed=call.posture_changed,
        )
        for name in workflows
    ]
