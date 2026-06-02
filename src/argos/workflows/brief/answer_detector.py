"""Deterministic detection of which info-map questions have answers on file.

The Brief assembler and the Outreach Drafter both need to know which
open questions are still open vs. answered. v1's signal is narrow:
"is a document of an answering type on file?" That covers ~12 of the
39 questions in INFO_MAP_AUTO_BI_FL; the rest are marked as
not-yet-detectable and surface as open until we wire richer signals
(outbound-request tracking, parsed extractions, etc.).

This is intentionally permissive in the "open" direction: when in
doubt, surface the question. False-positive opens cost an extra entry
in the Brief; false-negative answered would hide work from the
adjuster.
"""
from __future__ import annotations

from argos.ontology.types import Claim, Document
from argos.services.info_map import INFO_MAP_AUTO_BI_FL, OpenQuestion


# ---------------------------------------------------------------------------
# Question -> doc-type signals
# ---------------------------------------------------------------------------
#
# Each entry maps an info-map question id to the set of document_types
# whose presence on the claim answers the question. Membership is
# enough — we don't yet parse content to verify the doc actually
# contains the answer.
#
# Coverage of v1: the structured documents we generate in the
# realistic-docs caseload (declarations_page, police_report,
# recorded_statement, medical_records) cover the questions that load-
# bearing for the day-1 adjuster brief. Everything else stays open
# until we add richer signals.

QUESTION_DOC_TYPE_SIGNALS: dict[str, frozenset[str]] = {
    # Coverage — declarations page is the source of truth for policy
    # in-force status, limits, UM/UIM, excess, SIR/deductible, defense
    # duty triggers, and named-insured / driver-of-record questions.
    "Q-COV-001": frozenset({"declarations_page"}),
    "Q-COV-002": frozenset({"declarations_page"}),
    "Q-COV-006": frozenset({"declarations_page"}),
    "Q-COV-012": frozenset({"declarations_page"}),
    "Q-COV-013": frozenset({"declarations_page"}),
    "Q-COV-014": frozenset({"declarations_page"}),
    "Q-COV-015": frozenset({"declarations_page"}),
    # Cooperation — answered by a recorded statement on file.
    "Q-COV-011": frozenset({"recorded_statement"}),
    # Liability — most of the scene-level facts come from the police
    # report (date/time/location, traffic control, paths of travel,
    # citations, officer fault determination, witnesses listed).
    "Q-LIA-001": frozenset({"police_report"}),
    "Q-LIA-002": frozenset({"police_report"}),
    "Q-LIA-003": frozenset({"police_report"}),
    "Q-LIA-004": frozenset({"police_report"}),
    "Q-LIA-006": frozenset({"police_report"}),
    "Q-LIA-007": frozenset({"police_report"}),
    # Damages — initial diagnosis + treatment-to-date are the first
    # signals we get from medical records. Bills, future treatment,
    # permanency, wage loss, liens, demand all need richer signals.
    "Q-DAM-001": frozenset({"medical_records"}),
    "Q-DAM-002": frozenset({"medical_records"}),
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def is_answered(
    question: OpenQuestion,
    claim: Claim,
    documents: list[Document],
) -> bool:
    """Return True iff a document on file satisfies this question.

    Returns False for any question not in QUESTION_DOC_TYPE_SIGNALS —
    those are "not yet detectable" and remain open by design.
    """
    signal = QUESTION_DOC_TYPE_SIGNALS.get(question.id)
    if signal is None:
        return False
    doc_types_on_file = {d.document_type for d in documents}
    return bool(signal & doc_types_on_file)


def detect_open_questions(
    claim: Claim,
    documents: list[Document],
) -> list[OpenQuestion]:
    """Slice INFO_MAP_AUTO_BI_FL down to the questions still open.

    Order is critical-path: perishable atoms first, then longest
    cycle-time descending. Callers that want a different grouping
    (e.g., by recipient party for outreach drafting) should re-sort.
    """
    return [
        q for q in INFO_MAP_AUTO_BI_FL.critical_path_order()
        if not is_answered(q, claim, documents)
    ]


__all__ = [
    "QUESTION_DOC_TYPE_SIGNALS",
    "detect_open_questions",
    "is_answered",
]
