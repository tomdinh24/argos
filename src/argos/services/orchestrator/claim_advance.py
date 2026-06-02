"""Cross-stream scheduler — advance one claim by one round.

Argos has two event streams that move a claim forward:

  1. **Analysis pipeline** — inbound docs (Reader → dispatcher →
     JobQueue → Coverage/Reserve/Liability/Brief workflows).
     Handled by the existing `runner.WorkflowRunner` machinery.
  2. **Correspondence loop** — ingest replies → propose outbounds →
     draft, handled by `correspondence_loop.advance_correspondence`.

`advance_claim` is the single entry point a cron, an event handler,
or an adjuster's "Refresh this claim" button calls. It does NOT run
analysis LLM calls inline (those are expensive and have their own
runner cadence). It DOES:

  - Classify every new inbound document on this claim: reply
    candidate vs. disclosure (see `_classify_inbound`)
  - For disclosures, ingest into `caseload.documents` so the next
    `is_answered()` pass picks them up
  - For reply candidates, hand them to the correspondence advance
    as `inbound_replies`
  - Run the correspondence advance (ingest → propose → draft) over
    the post-classification caseload
  - Return one combined `ClaimAdvanceReport` so an upstream caller
    can see what moved without diffing the caseload

The reply-vs-disclosure classifier is intentionally simple for v1
(see `_classify_inbound`). When a real reply-routing signal arrives
— email-thread metadata, fax cover sheet, document intake classifier
— the heuristic becomes a one-line swap.

Decision context: docs/DECISIONS.md →
  "Cross-stream scheduler shipped (advance_claim)"
  "Correspondence loop composes the three wires"
  "Coverage->Claim writeback (apply_coverage_decision)"

Palantir mapping: this is the `AdvanceClaim` Action Type — fires on
`(Claim, scheduled_advance)` or `(Claim, inbound_doc_arrived)`,
performs all sub-Actions of both streams, and emits a `ClaimAdvanced`
event.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from anthropic import Anthropic
from openai import OpenAI

from argos.ontology.types import Caseload, Document
from argos.services.info_map.auto_bi_fl import INFO_MAP_AUTO_BI_FL
from argos.services.info_map.types import InfoMap
from argos.services.orchestrator.correspondence_loop import (
    CorrespondenceAdvanceReport,
    advance_correspondence,
)
from argos.services.orchestrator.job import Job
from argos.services.orchestrator.queue import JobQueue
from argos.services.triage.reader_integration import (
    ReaderFn,
    retrigger_analysis_for_docs,
)


DocClassification = Literal["reply_candidate", "disclosure"]


@dataclass
class ClassifiedDoc:
    """One inbound document plus the scheduler's routing call."""

    document: Document
    classification: DocClassification
    reason: str


@dataclass
class ClaimAdvanceReport:
    """What happened across both streams in one round of advance.

    `classified_docs` is the per-document routing audit. `correspondence`
    is the nested correspondence-loop report (ingest outcomes, info-gap
    proposals/skips, draft outcomes). `disclosures_added` counts new
    docs that landed in `caseload.documents` as fresh evidence (not
    reply candidates). `analysis_jobs_enqueued` is the list of analysis
    Jobs (Coverage / Reserve / Liability / Brief) the Reader dispatched
    onto newly-arrived docs this round; empty when no `job_queue` was
    supplied or the Reader marked nothing relevant.
    """

    claim_id: str
    classified_docs: list[ClassifiedDoc] = field(default_factory=list)
    correspondence: CorrespondenceAdvanceReport | None = None
    disclosures_added: int = 0
    analysis_jobs_enqueued: list[Job] = field(default_factory=list)

    def summary(self) -> str:
        replies = sum(
            1 for d in self.classified_docs if d.classification == "reply_candidate"
        )
        disclosures = sum(
            1 for d in self.classified_docs if d.classification == "disclosure"
        )
        corr = self.correspondence.summary() if self.correspondence else "(skipped)"
        analysis_bit = (
            f"; analysis jobs enqueued={len(self.analysis_jobs_enqueued)}"
            if self.analysis_jobs_enqueued else ""
        )
        return (
            f"Advance({self.claim_id}): "
            f"docs classified {replies} replies + {disclosures} disclosures; "
            f"correspondence → {corr}{analysis_bit}"
        )


def advance_claim(
    caseload: Caseload,
    claim_id: str,
    *,
    new_inbound_docs: list[Document] | None = None,
    recipient_directory: dict[str, str],
    now: datetime,
    info_map: InfoMap = INFO_MAP_AUTO_BI_FL,
    request_id_prefix: str = "OBR-",
    openai_client: OpenAI | None = None,
    anthropic_client: Anthropic | None = None,
    job_queue: JobQueue | None = None,
    reader_fn: ReaderFn | None = None,
) -> tuple[Caseload, ClaimAdvanceReport]:
    """Advance one claim through one round of forward progress.

    Returns `(new_caseload, report)`. The input caseload is not
    mutated.

    Inbound docs are classified deterministically:
      - If any open outbound (`sent` / `overdue`) exists on this
        claim, the doc is a `reply_candidate` — the Reply Parser
        decides whether it actually matches.
      - Otherwise it's a `disclosure` — fresh evidence not tied
        to any specific outbound.

    Disclosures are added directly to `caseload.documents` so the
    next deterministic `is_answered()` pass picks them up. Reply
    candidates are NOT added directly — `IngestReply.apply_outcome`
    inside the correspondence advance does that after the parser
    attempts a match (closing the question state at the same time).

    Analysis Jobs (Coverage / Reserve / Liability / Brief) are
    enqueued onto `job_queue` when one is supplied. The Reader runs
    inline on every doc newly added to `caseload.documents` this
    round — disclosures from Step 2 AND docs that landed via
    `IngestReply.apply_outcome` in Step 3. The heavy analytical
    workflows do NOT run inline; they drain on the runner's cadence.
    When `job_queue` is None, the re-trigger is skipped entirely
    (preserves the original cheap-coordination behavior).
    """
    report = ClaimAdvanceReport(claim_id=claim_id)
    current = caseload
    pre_doc_ids = {d.document_id for d in current.documents}

    # ------------------------------------------------------------------
    # Step 1: classify each inbound doc
    # ------------------------------------------------------------------
    reply_candidates: list[Document] = []
    disclosures: list[Document] = []

    for doc in new_inbound_docs or []:
        if doc.claim_id != claim_id:
            # Off-claim doc — ignored at this layer; not even classified.
            continue
        classification, reason = _classify_inbound(doc, current)
        report.classified_docs.append(ClassifiedDoc(
            document=doc,
            classification=classification,
            reason=reason,
        ))
        if classification == "reply_candidate":
            reply_candidates.append(doc)
        else:
            disclosures.append(doc)

    # ------------------------------------------------------------------
    # Step 2: ingest disclosures into caseload.documents (idempotent)
    # ------------------------------------------------------------------
    if disclosures:
        existing_ids = {d.document_id for d in current.documents}
        added = [d for d in disclosures if d.document_id not in existing_ids]
        if added:
            current = current.model_copy(update={
                "documents": current.documents + added,
            })
            report.disclosures_added = len(added)

    # ------------------------------------------------------------------
    # Step 3: advance correspondence with reply candidates
    # ------------------------------------------------------------------
    current, corr_report = advance_correspondence(
        current,
        claim_id,
        recipient_directory=recipient_directory,
        now=now,
        inbound_replies=reply_candidates,
        info_map=info_map,
        request_id_prefix=request_id_prefix,
        openai_client=openai_client,
        anthropic_client=anthropic_client,
    )
    report.correspondence = corr_report

    # ------------------------------------------------------------------
    # Step 4: re-trigger analysis on every doc newly in the file
    # ------------------------------------------------------------------
    # Catches BOTH disclosures (Step 2) and docs that landed via
    # `IngestReply.apply_outcome` in Step 3. The Reader's materiality
    # call is independent of how the doc got into the caseload.
    if job_queue is not None:
        new_docs = [
            d for d in current.documents if d.document_id not in pre_doc_ids
        ]
        if new_docs:
            report.analysis_jobs_enqueued = retrigger_analysis_for_docs(
                new_docs,
                claim_id,
                caseload=current,
                queue=job_queue,
                reader_fn=reader_fn,
            )

    return current, report


def _classify_inbound(doc: Document, caseload: Caseload) -> tuple[DocClassification, str]:
    """Reply-vs-disclosure heuristic.

    `reply_candidate` when there's an open outbound (`sent` /
    `overdue`) on the claim — the Reply Parser then sorts out
    whether it actually matches. False positives are recoverable:
    the parser escalates with `escalate_low_confidence`, and the
    doc still lands in the file via `IngestReply.apply_outcome`.

    `disclosure` when no open outbounds exist — there's nothing
    for it to be a reply to.

    Intentionally permissive in the reply direction. False
    negatives (treating a real reply as a disclosure) would skip
    the question-state loop closure, which is worse than running
    the parser on a disclosure and escalating.
    """
    open_obs = caseload.open_outbounds_for_claim(doc.claim_id)
    if not open_obs:
        return "disclosure", (
            f"No open outbounds on {doc.claim_id!r}; nothing for this "
            f"doc to be a reply to."
        )

    parties = sorted({o.recipient_party for o in open_obs})
    return "reply_candidate", (
        f"{len(open_obs)} open outbound(s) on claim ({', '.join(parties)}); "
        f"Reply Parser will attempt match against {doc.document_id!r}."
    )


__all__ = [
    "ClaimAdvanceReport",
    "ClassifiedDoc",
    "DocClassification",
    "advance_claim",
]
