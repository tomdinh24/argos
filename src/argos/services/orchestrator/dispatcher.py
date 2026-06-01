"""Posture → specialist routing.

Pure function over `MaterialityCall`: given one Reader output, returns
the list of `Job` objects that should be enqueued. The mapping is
small and fixed for v1:

    posture_changed == "coverage"  → [Coverage]
    posture_changed == "reserve"   → [Reserve]
    posture_changed == "liability" → [Liability]
    posture_changed == "damages"   → [Reserve, Liability]
                                     (damages affect both reserve
                                     adequacy and liability negotiation)
    material == False              → []

Jobs returned here are NOT enqueued yet — the caller enqueues them
through `JobQueue.enqueue()`, which enforces idempotency. Keeping the
dispatcher pure makes it trivially testable.
"""
from __future__ import annotations

from argos.schemas.specialists.document_reader import MaterialityCall
from argos.services.orchestrator.job import Job


# Posture → list of specialist names. Tweakable in one place.
POSTURE_TO_SPECIALISTS: dict[str, list[str]] = {
    "coverage": ["coverage"],
    "reserve": ["reserve"],
    "liability": ["liability"],
    "damages": ["reserve", "liability"],
}


def dispatch(call: MaterialityCall, claim_id: str) -> list[Job]:
    """Translate one Reader call into the jobs it implies.

    Returns an empty list when `call.material == False`. Otherwise
    returns one Job per specialist named in `POSTURE_TO_SPECIALISTS`
    for the posture the Reader flagged.
    """
    if not call.material or call.posture_changed is None:
        return []

    specialists = POSTURE_TO_SPECIALISTS.get(call.posture_changed, [])
    return [
        Job(
            specialist=spec,
            claim_id=claim_id,
            triggered_by_doc_id=call.document_id,
            posture_changed=call.posture_changed,
        )
        for spec in specialists
    ]
