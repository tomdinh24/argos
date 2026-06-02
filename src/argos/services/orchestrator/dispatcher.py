"""Posture → workflow routing.

Pure function over `RelevanceCall`: given one Reader output, returns
the list of `Job` objects that should be enqueued. The mapping is
small and fixed for v1:

    posture_changed == "coverage"  → [Coverage]
    posture_changed == "reserve"   → [Reserve]
    posture_changed == "liability" → [Liability, Recovery]
                                     (apportionment commit + Powell /
                                     Berges signals re-shape recoverable
                                     basis and bar evaluation)
    posture_changed == "damages"   → [Reserve, Liability, Recovery]
                                     (damages affect reserve adequacy,
                                     liability negotiation, AND the
                                     layered recoverable basis)
    relevant == False              → []

Jobs returned here are NOT enqueued yet — the caller enqueues them
through `JobQueue.enqueue()`, which enforces idempotency. Keeping the
dispatcher pure makes it trivially testable.

Closure is NOT dispatcher-routed: it's adjuster-triggered (review
surface signals "ready_to_close"), so it lives outside the
posture-changed taxonomy. Same pattern as Brief.

The Document Reader's `PostureChanged` literal stays
(`coverage` / `reserve` / `liability` / `damages`) — adding new postures
(`subrogation`, `closure`) requires extending the LLM-facing schema +
adding anchor-pair coverage to the locked eval, deferred until that
investment is justified.
"""
from __future__ import annotations

from argos.schemas.workflows.document_reader import RelevanceCall
from argos.services.orchestrator.job import Job


# Posture → list of workflow names. Tweakable in one place.
POSTURE_TO_WORKFLOWS: dict[str, list[str]] = {
    "coverage": ["coverage"],
    "reserve": ["reserve"],
    "liability": ["liability", "recovery"],
    "damages": ["reserve", "liability", "recovery"],
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
