"""Correspondence loop — advance one round of the ask/answer cycle.

Composes the three correspondence wires (`info_gap`, `draft_handler`,
`reply_handler`) into a single `advance_correspondence` function the
orchestrator (or a cron, or a manual adjuster action) can call to
advance one claim by one round.

Order matters:

  1. **Ingest pending inbound replies first** — closes the loop on
     evidence the system already has. Doc ingestion via
     `reply_handler.apply_outcome` populates `caseload.documents`,
     which `is_answered()` reads. Without this, the InfoGap pass
     below would re-propose questions whose answers just arrived.
  2. **Propose new outbounds (InfoGap)** — looks at the now-current
     open-question set and emits fresh `pending_draft` outbounds
     for what's still missing.
  3. **Draft pending_draft outbounds (DraftOutreach)** — body-fills
     every outbound currently in `pending_draft`, including the
     ones InfoGap just proposed and any leftovers from prior ticks.

The function is deterministic in *shape* — same inputs, same outputs
(modulo LLM nondeterminism, which is contained inside the two LLM
wires; structure/sequence stays fixed). Safe to call repeatedly: a
"clean" tick on a fully-handled claim is a near no-op (empty
proposals, empty drafts).

This module does NOT integrate with the existing `JobQueue` /
`dispatcher.py` / `runner.py` machinery — that pipeline is shaped
around document-arrival → posture-change → analysis-workflow. The
correspondence loop is a separate event stream (claim state →
outbound work), with its own composition. Cross-stream integration
(e.g., "Coverage analysis completed → tick correspondence") is the
next architectural piece; both will hang off a higher-level
scheduler.

Decision context: docs/DECISIONS.md →
  "InfoGap detector shipped"
  "IngestReply closes the question-state loop"
  "DraftOutreach action shipped"
  "Correspondence loop composes the three wires" (this module)

Palantir mapping: when moved to Foundry, this is a scheduled
Action that fires on `(Claim, correspondence_advance_event)`,
performs the three sub-Actions atomically per the order above,
and emits a `CorrespondenceAdvanced` event downstream consumers
subscribe to.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from anthropic import Anthropic
from openai import OpenAI

from argos.ontology.types import Caseload, Document
from argos.services.info_map.auto_bi_fl import INFO_MAP_AUTO_BI_FL
from argos.services.info_map.types import InfoMap
from argos.services.orchestrator import draft_handler, info_gap, reply_handler


@dataclass
class CorrespondenceAdvanceReport:
    """What happened in one round of advance. Per-step outcome lists
    let the orchestrator (and the audit log) reconstruct everything
    that moved without re-reading the caseload diff."""

    claim_id: str
    ingest_outcomes: list[reply_handler.ReplyHandlerOutcome] = field(default_factory=list)
    info_gap_outcome: info_gap.InfoGapOutcome | None = None
    draft_outcomes: list[draft_handler.DraftOutboundOutcome] = field(default_factory=list)

    def summary(self) -> str:
        """One-line audit log summary."""
        ingested = len(self.ingest_outcomes)
        matched = sum(1 for o in self.ingest_outcomes if o.outcome == "matched")
        proposed = (
            len(self.info_gap_outcome.proposals) if self.info_gap_outcome else 0
        )
        gap_skipped = (
            len(self.info_gap_outcome.skipped) if self.info_gap_outcome else 0
        )
        drafted = sum(1 for o in self.draft_outcomes if o.outcome == "drafted")
        draft_escalations = sum(
            1 for o in self.draft_outcomes if o.outcome != "drafted"
        )
        return (
            f"Correspondence({self.claim_id}): "
            f"ingested={ingested} (matched={matched}), "
            f"proposed={proposed} (skipped={gap_skipped}), "
            f"drafted={drafted} (escalated={draft_escalations})"
        )


def advance_correspondence(
    caseload: Caseload,
    claim_id: str,
    *,
    recipient_directory: dict[str, str],
    now: datetime,
    inbound_replies: list[Document] | None = None,
    info_map: InfoMap = INFO_MAP_AUTO_BI_FL,
    request_id_prefix: str = "OBR-",
    openai_client: OpenAI | None = None,
    anthropic_client: Anthropic | None = None,
) -> tuple[Caseload, CorrespondenceAdvanceReport]:
    """Advance one claim through one cycle of the correspondence loop.

    Returns `(new_caseload, report)`. The input caseload is not
    mutated — each step returns a fresh model via `model_copy`.

    `inbound_replies` are inbound `Document`s the caller has on hand
    that may be replies to outbounds. The caller decides which docs
    qualify (in production: derived from email-thread routing, fax
    cover sheets, or human triage). If `None` or empty, step 1 is
    skipped and the loop runs against the caseload as-is.

    The LLM client kwargs are optional injection points for testing
    — production callers leave them None so the wires construct
    clients from environment.
    """
    report = CorrespondenceAdvanceReport(claim_id=claim_id)
    current = caseload

    # ------------------------------------------------------------------
    # 1. Ingest pending inbound replies (closes the loop on new evidence)
    # ------------------------------------------------------------------
    for inbound in inbound_replies or []:
        if inbound.claim_id != claim_id:
            continue  # caller passed a doc for a different claim
        outcome = reply_handler.handle_inbound_reply(
            inbound,
            current,
            now=now,
            _client=anthropic_client,
        )
        current = reply_handler.apply_outcome(current, outcome)
        report.ingest_outcomes.append(outcome)

    # ------------------------------------------------------------------
    # 2. Propose new pending_draft outbounds (InfoGap)
    # ------------------------------------------------------------------
    claim = _find_claim(current, claim_id)
    next_id_start = _next_obr_id_seed(current, claim_id, request_id_prefix)
    gap_outcome = info_gap.propose_pending_outbounds(
        claim,
        current,
        recipient_directory=recipient_directory,
        info_map=info_map,
        request_id_prefix=request_id_prefix,
        request_id_start=next_id_start,
    )
    current = info_gap.apply_outcome(current, gap_outcome)
    report.info_gap_outcome = gap_outcome

    # ------------------------------------------------------------------
    # 3. Draft every pending_draft outbound (DraftOutreach)
    # ------------------------------------------------------------------
    # Snapshot the pending list — apply_outcome below replaces them
    # so we'd iterate over a moving target without the snapshot.
    pending = [
        o for o in current.outbound_requests
        if o.claim_id == claim_id and o.status == "pending_draft"
    ]
    for outbound in pending:
        outcome = draft_handler.handle_pending_draft(
            outbound,
            current,
            now=now,
            info_map=info_map,
            _client=openai_client,
        )
        current = draft_handler.apply_outcome(current, outcome)
        report.draft_outcomes.append(outcome)

    return current, report


def _find_claim(caseload: Caseload, claim_id: str):
    for c in caseload.claims:
        if c.claim_id == claim_id:
            return c
    raise ValueError(
        f"advance_correspondence: claim_id={claim_id!r} not present "
        f"in caseload."
    )


def _next_obr_id_seed(caseload: Caseload, claim_id: str, prefix: str) -> int:
    """Find the next free integer suffix for OBR IDs on this claim.

    Looks at existing outbound IDs matching `{prefix}NNN` and returns
    `max(NNN) + 1`. Returns 1 when no prior outbounds exist for the
    claim under this prefix. Lets repeated advances coexist with
    manually-created outbounds without collisions, as long as
    everyone uses the same prefix scheme.
    """
    max_n = 0
    for o in caseload.outbounds_for_claim(claim_id):
        if not o.request_id.startswith(prefix):
            continue
        suffix = o.request_id[len(prefix):]
        try:
            n = int(suffix)
        except ValueError:
            continue
        if n > max_n:
            max_n = n
    return max_n + 1


__all__ = [
    "CorrespondenceAdvanceReport",
    "advance_correspondence",
]
