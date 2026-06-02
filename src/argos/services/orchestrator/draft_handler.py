"""DraftOutreach orchestration wire.

Glue between an `OutboundRequest` in `pending_draft` state and the
Outreach Drafter workflow. Owns the small amount of routing logic
that the drafter itself doesn't:

  1. Validate the outbound is in `pending_draft`.
  2. Resolve the claim from the caseload (programmer error otherwise).
  3. Pre-check: claim has `claimant_name` and `insured_name`
     hydrated (drafter input requires them; soft escalate so an
     un-hydrated claim doesn't crash the loop).
  4. Assemble drafter input via `build_drafter_input_for_outbound`.
  5. Pre-check: open-question set is non-empty (drafter producing a
     letter that asks for nothing is wasted spend; escalate instead).
  6. Call `run_outreach_drafter`.
  7. Catch drafter empty-body `RuntimeError` as a soft escalation.
  8. Produce the `OutboundRequest` state transition
     (`pending_draft` → `drafted`, `draft_body`, `drafted_at`).

This module performs NO live LLM calls itself — it delegates to
`run_outreach_drafter`. Its responsibility is the deterministic
routing around that single workflow call. The shape mirrors
`reply_handler.handle_inbound_reply` so the orchestrator treats
inbound and outbound flows symmetrically.

Identity context lives on the entities: `recipient_name` and
`letter_purpose` are on the `OutboundRequest` (per-outbound facts
set by the info-gap detector at creation); `claimant_name` and
`insured_name` are on the `Claim` (claim-level facts populated by
intake_reader).

Decision context: docs/DECISIONS.md →
  "Outreach Drafter v1 shipped (thread-aware, stateless)"
  "DraftOutreach action shipped" (this module)
  "OutboundRequest schema: recipient_name + letter_purpose persisted"

Palantir mapping: this module is the orchestration logic that, when
moved to Foundry, fires the `DraftOutreach` Action Type on the
target `OutboundRequest` object and emits a `DraftReady` event the
adjuster UI subscribes to.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from openai import OpenAI

from argos.ontology.types import Caseload, Claim, OutboundRequest
from argos.services.info_map.types import InfoMap
from argos.services.info_map.auto_bi_fl import INFO_MAP_AUTO_BI_FL
from argos.workflows.outreach_drafter import (
    DEFAULT_MAX_COMPLETION_TOKENS,
    DEFAULT_MODEL,
    DEFAULT_REASONING_EFFORT,
    THREAD_HISTORY_CAP,
    OutreachDrafterResult,
    build_drafter_input_for_outbound,
    run_outreach_drafter,
)


DraftHandlerOutcome = Literal[
    "drafted",                          # drafter ran, body produced; updated_outbound populated
    "escalate_claim_unhydrated",        # claim is missing claimant_name and/or insured_name
    "escalate_no_open_questions",       # nothing to ask — skip the LLM call
    "escalate_drafter_failed",          # drafter raised (e.g., empty body); needs human attention
]


@dataclass
class DraftOutboundOutcome:
    """What the wire produces from one pending_draft outbound.

    `drafted` outcomes carry `result` and `updated_outbound`.
    Escalations carry `reason` (and `result` is null since the
    workflow either didn't run or didn't produce usable output).
    """

    outcome: DraftHandlerOutcome
    request_id: str
    claim_id: str
    result: OutreachDrafterResult | None = None
    updated_outbound: OutboundRequest | None = None
    open_question_ids: list[str] = field(default_factory=list)
    reason: str = ""


def handle_pending_draft(
    outbound: OutboundRequest,
    caseload: Caseload,
    *,
    now: datetime,
    info_map: InfoMap = INFO_MAP_AUTO_BI_FL,
    thread_history_cap: int = THREAD_HISTORY_CAP,
    model: str = DEFAULT_MODEL,
    reasoning_effort: str = DEFAULT_REASONING_EFFORT,
    max_completion_tokens: int = DEFAULT_MAX_COMPLETION_TOKENS,
    _client: OpenAI | None = None,
) -> DraftOutboundOutcome:
    """Route one pending-draft outbound through the Outreach Drafter.

    `now` is the timestamp recorded as `drafted_at` on the outbound
    when the draft succeeds — passed in explicitly so this function
    is deterministic and easy to test.

    Pre-call hard errors (programmer error, raised — not escalated):
      - outbound.status != "pending_draft"
      - outbound.claim_id not present in caseload.claims

    Soft escalations (returned as outcome, no exception):
      - claim is missing claimant_name and/or insured_name
      - open-question set is empty after info-map filtering
      - drafter raised (e.g., empty body from reasoning-token overrun)
    """
    if outbound.status != "pending_draft":
        raise ValueError(
            f"handle_pending_draft: outbound {outbound.request_id!r} has "
            f"status={outbound.status!r}, expected 'pending_draft'. "
            f"Caller bug — only pending_draft outbounds are draftable."
        )

    claim = _find_claim(caseload, outbound.claim_id)

    if claim.claimant_name is None or claim.insured_name is None:
        missing = [
            f for f, v in (
                ("claimant_name", claim.claimant_name),
                ("insured_name", claim.insured_name),
            )
            if v is None
        ]
        return DraftOutboundOutcome(
            outcome="escalate_claim_unhydrated",
            request_id=outbound.request_id,
            claim_id=outbound.claim_id,
            reason=(
                f"Claim {claim.claim_id!r} is missing required identity "
                f"field(s): {', '.join(missing)}. Run intake_reader on "
                f"the FNOL documents or set the names manually before "
                f"drafting."
            ),
        )

    drafter_input = build_drafter_input_for_outbound(
        outbound=outbound,
        caseload=caseload,
        info_map=info_map,
        thread_history_cap=thread_history_cap,
    )

    open_question_ids = [q.id for q in drafter_input.open_questions]

    if not open_question_ids:
        return DraftOutboundOutcome(
            outcome="escalate_no_open_questions",
            request_id=outbound.request_id,
            claim_id=outbound.claim_id,
            open_question_ids=[],
            reason=(
                f"No open questions remain for claim {outbound.claim_id!r} / "
                f"party {outbound.recipient_party!r}; drafter would produce a "
                f"letter asking nothing. Cancel the outbound or re-check the "
                f"info-map filter."
            ),
        )

    try:
        result = run_outreach_drafter(
            drafter_input,
            now=now,
            model=model,
            reasoning_effort=reasoning_effort,
            max_completion_tokens=max_completion_tokens,
            _client=_client,
        )
    except RuntimeError as e:
        return DraftOutboundOutcome(
            outcome="escalate_drafter_failed",
            request_id=outbound.request_id,
            claim_id=outbound.claim_id,
            open_question_ids=open_question_ids,
            reason=f"Outreach Drafter failed: {e}",
        )

    updated_outbound = outbound.model_copy(
        update={
            "status": "drafted",
            "drafted_at": now,
            "draft_body": result.body_text,
        }
    )

    return DraftOutboundOutcome(
        outcome="drafted",
        request_id=outbound.request_id,
        claim_id=outbound.claim_id,
        result=result,
        updated_outbound=updated_outbound,
        open_question_ids=open_question_ids,
    )


def apply_outcome(caseload: Caseload, outcome: DraftOutboundOutcome) -> Caseload:
    """Apply a `drafted` outcome to a caseload: replace the matched
    outbound with its updated `drafted` state. Returns a new Caseload;
    the input is not mutated.

    Escalation outcomes are no-ops (the outbound stays in
    `pending_draft` for a retry or human review; the caseload is
    unchanged).
    """
    if outcome.outcome != "drafted" or outcome.updated_outbound is None:
        return caseload

    updated_id = outcome.updated_outbound.request_id
    new_outbounds = [
        outcome.updated_outbound if o.request_id == updated_id else o
        for o in caseload.outbound_requests
    ]
    return caseload.model_copy(update={"outbound_requests": new_outbounds})


def _find_claim(caseload: Caseload, claim_id: str) -> Claim:
    for c in caseload.claims:
        if c.claim_id == claim_id:
            return c
    raise ValueError(
        f"handle_pending_draft: claim_id={claim_id!r} not present in caseload. "
        f"Caller bug — the outbound references a claim outside this caseload."
    )


__all__ = [
    "DraftHandlerOutcome",
    "DraftOutboundOutcome",
    "apply_outcome",
    "handle_pending_draft",
]
