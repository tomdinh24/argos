"""InfoGap detector — the upstream policy that creates pending_draft outbounds.

The third orchestration wire (after `draft_handler` and
`reply_handler`). Closes the loop on the other side: where
`reply_handler` brings new evidence in and shrinks the open-question
set, `info_gap` looks at what's still open and proposes the
outbounds the adjuster needs to send to close those gaps.

This module is **fully deterministic** — no LLM calls. Per
`[[policy-engine-first-then-llm-extraction]]`: question→party
mapping lives in the info map; bundling and dependency rules are
policy; the LLM is reserved for prose generation (drafter) and
extraction (parser).

Algorithm:

  1. Compute the open-question set for the claim via the
     deterministic `is_answered()` check.
  2. Drop questions whose `depends_on` IDs are still open (don't
     ask Q-LIA-002 if Q-LIA-001 hasn't been answered).
  3. Drop questions already covered by an in-flight outbound
     (pending_draft, drafted, sent, overdue). A `replied` outbound
     whose question is still open is treated as not-in-flight —
     re-ask is the correct move.
  4. Pick the best deliverable source per question: highest
     fidelity, with a channel that actually generates outbound
     correspondence (excludes `internal_lookup`, `api`).
  5. Look up the recipient's display name in the caller-supplied
     directory. Skip with a logged gap if no entry — the
     orchestrator's signal to populate the directory or escalate.
  6. Bundle remaining (question, source) pairs by
     (party, recipient_name) → one `OutboundRequest` per group.
  7. Generate a short letter purpose from the bundled question
     descriptions (deterministic template, no LLM).

The function returns a structured outcome with `proposals`
(ready-to-create outbounds) and `skipped` (audit trail of every
question that didn't make the cut, with reason). `apply_outcome`
appends proposals to `Caseload.outbound_requests` for downstream
consumption by `draft_handler`.

Decision context: docs/DECISIONS.md →
  "DraftOutreach action shipped"
  "IngestReply closes the question-state loop"
  "InfoGap detector shipped" (this module)

Palantir mapping: when moved to Foundry, this is the `ProposeOutreach`
Action Type — emits N `OutboundRequest` objects in pending_draft
state, one per (party, recipient_name) bundle, and a single
`OutreachProposalsReady` event the adjuster UI subscribes to.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from argos.ontology.types import Caseload, Claim, OutboundChannel, OutboundRequest
from argos.services.info_map.auto_bi_fl import INFO_MAP_AUTO_BI_FL
from argos.services.info_map.types import InfoMap, OpenQuestion, Source
from argos.workflows.brief.answer_detector import is_answered


# Channels that correspond to a real outbound (mirrors the
# OutboundChannel literal so the type checker catches drift). The
# info-map Channel enum is a superset; these are the deliverable
# ones.
_DELIVERABLE_CHANNELS: frozenset[OutboundChannel] = frozenset({
    "email", "phone", "portal", "fax", "mail", "in_person",
    "subpoena", "court_record",
})

# In-flight outbound statuses block re-asking the same question on
# a new outbound. `replied` is intentionally NOT here: if the reply
# didn't actually answer the question (deterministic check still
# says open), we DO want to re-ask.
_IN_FLIGHT_STATUSES: frozenset[str] = frozenset({
    "pending_draft", "drafted", "sent", "overdue",
})

_FIDELITY_RANK: dict[str, int] = {
    "authoritative": 0,
    "primary": 1,
    "secondary": 2,
    "tertiary": 3,
}


SkipReason = Literal[
    "blocked_on_dependency",
    "no_deliverable_source",
    "no_recipient_in_directory",
    "already_in_flight",
]


@dataclass
class SkippedQuestion:
    """One question the detector did not include in any proposal,
    with the reason. Audit trail for the orchestrator."""

    question_id: str
    reason: SkipReason
    detail: str


@dataclass
class InfoGapOutcome:
    """What the detector produces from a claim's open-question set.

    `proposals` are fresh OutboundRequests in `pending_draft` state,
    ready for `draft_handler.handle_pending_draft` to body-fill.
    `skipped` is the parallel audit trail — every open question
    that the detector chose NOT to bundle, with the reason.
    """

    claim_id: str
    proposals: list[OutboundRequest] = field(default_factory=list)
    skipped: list[SkippedQuestion] = field(default_factory=list)


def propose_pending_outbounds(
    claim: Claim,
    caseload: Caseload,
    *,
    recipient_directory: dict[str, str],
    info_map: InfoMap = INFO_MAP_AUTO_BI_FL,
    request_id_prefix: str = "OBR-",
    request_id_start: int = 1,
) -> InfoGapOutcome:
    """Propose `pending_draft` outbounds to close this claim's open
    questions.

    `recipient_directory` is a `party → recipient_name` mapping the
    caller has on hand (e.g., 'claimant_counsel' → 'Marisol Trent,
    Esq.'). The detector does not invent recipients; if a party
    has open questions and no directory entry, those questions are
    skipped with a `no_recipient_in_directory` reason — the
    orchestrator can then prompt the human or look up the name.

    `request_id_start` is the integer seed for OBR-{prefix}{N:03d}
    IDs on the new proposals. Caller is responsible for ensuring
    uniqueness across calls (real systems use a sequence/UUID).
    """
    claim_docs = [d for d in caseload.documents if d.claim_id == claim.claim_id]

    # Step 1: open-question set for this claim.
    open_questions = [
        q for q in info_map.questions
        if not is_answered(q, claim, claim_docs)
    ]
    open_ids: frozenset[str] = frozenset(q.id for q in open_questions)

    # Step 3 precompute: which question_ids are already in-flight on
    # an OutboundRequest, grouped by party (so we don't accidentally
    # block a different party from asking the same question).
    in_flight_by_party: dict[str, dict[str, str]] = {}  # party → (qid → OBR id)
    for o in caseload.outbounds_for_claim(claim.claim_id):
        if o.status not in _IN_FLIGHT_STATUSES:
            continue
        party_map = in_flight_by_party.setdefault(o.recipient_party, {})
        for qid in o.question_ids_asked:
            party_map.setdefault(qid, o.request_id)

    outcome = InfoGapOutcome(claim_id=claim.claim_id)

    # (question, source, recipient_name, party) tuples that survived
    # filtering, in info-map order, ready to be grouped.
    survivors: list[tuple[OpenQuestion, Source, str]] = []

    for q in open_questions:
        # Step 2: dependencies must be satisfied first.
        blocking = [dep for dep in q.depends_on if dep in open_ids]
        if blocking:
            outcome.skipped.append(SkippedQuestion(
                question_id=q.id,
                reason="blocked_on_dependency",
                detail=(
                    f"{q.id} depends on {blocking} which is still open. "
                    f"Ask the dependency first."
                ),
            ))
            continue

        # Step 4: best deliverable source.
        source = _pick_best_source(q.sources)
        if source is None:
            outcome.skipped.append(SkippedQuestion(
                question_id=q.id,
                reason="no_deliverable_source",
                detail=(
                    f"{q.id} has no source with a deliverable channel "
                    f"(channels seen: {sorted({s.channel for s in q.sources})}). "
                    f"Internal lookups don't produce outbounds."
                ),
            ))
            continue

        # Step 5: recipient directory lookup.
        recipient_name = recipient_directory.get(source.party)
        if recipient_name is None:
            outcome.skipped.append(SkippedQuestion(
                question_id=q.id,
                reason="no_recipient_in_directory",
                detail=(
                    f"{q.id} routes to party={source.party!r} but the "
                    f"recipient_directory has no entry. Add a name or "
                    f"escalate to the adjuster."
                ),
            ))
            continue

        # Step 3 check: already in-flight on a same-party outbound.
        in_flight_obr = in_flight_by_party.get(source.party, {}).get(q.id)
        if in_flight_obr is not None:
            outcome.skipped.append(SkippedQuestion(
                question_id=q.id,
                reason="already_in_flight",
                detail=(
                    f"{q.id} is already asked on {in_flight_obr} "
                    f"(party={source.party!r}); awaiting reply before "
                    f"re-asking."
                ),
            ))
            continue

        survivors.append((q, source, recipient_name))

    # Step 6: bundle by (party, recipient_name), preserving info-map
    # order within each group.
    groups: dict[tuple[str, str], list[tuple[OpenQuestion, Source]]] = {}
    for q, source, recipient_name in survivors:
        key = (source.party, recipient_name)
        groups.setdefault(key, []).append((q, source))

    # Step 7: materialize one OutboundRequest per group.
    counter = request_id_start
    for (party, recipient_name), bundle in groups.items():
        questions = [q for q, _ in bundle]
        outcome.proposals.append(OutboundRequest(
            request_id=f"{request_id_prefix}{counter:03d}",
            claim_id=claim.claim_id,
            recipient_party=party,
            recipient_name=recipient_name,
            letter_purpose=_render_letter_purpose(recipient_name, questions),
            question_ids_asked=[q.id for q in questions],
        ))
        counter += 1

    return outcome


def apply_outcome(caseload: Caseload, outcome: InfoGapOutcome) -> Caseload:
    """Append proposed outbounds to the caseload. Returns a new
    Caseload; the input is not mutated.

    Outcomes with no proposals are a no-op. Skipped-only outcomes
    are still informational — surface them via the outcome's
    `skipped` field, not via the caseload.
    """
    if not outcome.proposals:
        return caseload
    return caseload.model_copy(update={
        "outbound_requests": caseload.outbound_requests + outcome.proposals,
    })


def _pick_best_source(sources: list[Source]) -> Source | None:
    """Pick the highest-fidelity source with a deliverable channel.

    Returns None when every source uses an internal channel
    (`internal_lookup`, `api`) — those don't produce outbounds.
    """
    deliverable = [s for s in sources if s.channel in _DELIVERABLE_CHANNELS]
    if not deliverable:
        return None
    return min(deliverable, key=lambda s: _FIDELITY_RANK.get(s.fidelity, 99))


def _render_letter_purpose(recipient_name: str, questions: list[OpenQuestion]) -> str:
    """Deterministic letter-purpose template. No LLM — the drafter
    will rephrase this into the actual letter body using the
    question descriptions directly. This string is just a one-line
    intent the drafter consumes as framing.
    """
    if len(questions) == 1:
        return (
            f"Request information from {recipient_name} regarding "
            f"{questions[0].description.lower().rstrip('.')}."
        )
    return (
        f"Request information from {recipient_name} on "
        f"{len(questions)} outstanding items needed to advance the claim."
    )


__all__ = [
    "InfoGapOutcome",
    "SkipReason",
    "SkippedQuestion",
    "apply_outcome",
    "propose_pending_outbounds",
]
