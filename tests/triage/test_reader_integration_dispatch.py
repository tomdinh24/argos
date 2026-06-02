"""Tests for `dispatch_screening_results` — the auto-dispatch wire
that turns a Reader screening pass into enqueued specialist jobs.

These tests don't make LLM calls. They construct `RelevanceCall`
objects directly to exercise the glue between Reader output and
the orchestrator's JobQueue.

Decision context: docs/DECISIONS.md → "Auto-dispatch from Reader
→ Orchestrator is the missing wire" + "Build order locked" step 1.
"""
from __future__ import annotations

from argos.schemas.workflows.document_reader import RelevanceCall
from argos.services.orchestrator.queue import JobQueue
from argos.services.triage.reader_integration import (
    ReaderCallRecord,
    ReaderScreeningResult,
    dispatch_screening_results,
)


def _record(
    relevant: bool,
    posture: str | None,
    *,
    claim_id: str = "C1",
    doc_id: str = "D1",
) -> ReaderCallRecord:
    return ReaderCallRecord(
        document_id=doc_id,
        claim_id=claim_id,
        call=RelevanceCall(
            document_id=doc_id,
            relevant=relevant,
            posture_changed=posture,
            reason="r" if not relevant else "relevant reason",
            text_excerpt="" if not relevant else "quoted sentence",
        ),
        model="stub",
        attempts=1,
    )


def _empty_screening(records: list[ReaderCallRecord]) -> ReaderScreeningResult:
    return ReaderScreeningResult(
        relevant_doc_counts={},
        call_records=records,
        docs_screened=len(records),
    )


class TestDispatchScreeningResults:
    def test_empty_call_records_enqueues_nothing(self):
        queue = JobQueue(persistence_path=None)
        enqueued = dispatch_screening_results(_empty_screening([]), queue)
        assert enqueued == []
        assert queue.all_jobs() == []

    def test_all_non_relevant_enqueues_nothing(self):
        queue = JobQueue(persistence_path=None)
        records = [
            _record(False, None, doc_id="D1"),
            _record(False, None, doc_id="D2"),
        ]
        enqueued = dispatch_screening_results(_empty_screening(records), queue)
        assert enqueued == []
        assert queue.all_jobs() == []

    def test_relevant_coverage_enqueues_coverage_job(self):
        queue = JobQueue(persistence_path=None)
        records = [_record(True, "coverage", claim_id="C1", doc_id="D1")]
        enqueued = dispatch_screening_results(_empty_screening(records), queue)
        assert len(enqueued) == 1
        assert enqueued[0].workflow == "coverage"
        assert enqueued[0].claim_id == "C1"
        assert enqueued[0].triggered_by_doc_id == "D1"

    def test_relevant_damages_enqueues_reserve_liability_and_recovery(self):
        """damages posture fans out to three specialists per dispatcher rules
        (damages affect reserve adequacy, liability negotiation, AND the
        layered recoverable basis)."""
        queue = JobQueue(persistence_path=None)
        records = [_record(True, "damages", claim_id="C2", doc_id="D9")]
        enqueued = dispatch_screening_results(_empty_screening(records), queue)
        specialists = sorted(j.workflow for j in enqueued)
        assert specialists == ["liability", "recovery", "reserve"]
        assert all(j.claim_id == "C2" for j in enqueued)
        assert all(j.triggered_by_doc_id == "D9" for j in enqueued)

    def test_idempotent_dispatch_does_not_double_enqueue(self):
        """Running dispatch twice on the same screening is a no-op the
        second time."""
        queue = JobQueue(persistence_path=None)
        records = [_record(True, "coverage", claim_id="C1", doc_id="D1")]
        screening = _empty_screening(records)

        first = dispatch_screening_results(screening, queue)
        second = dispatch_screening_results(screening, queue)

        assert len(first) == 1
        assert second == []
        assert len(queue.all_jobs()) == 1

    def test_per_claim_routing_preserved_across_multiple_records(self):
        """Each Reader call's claim_id flows through to its enqueued
        jobs — no cross-contamination."""
        queue = JobQueue(persistence_path=None)
        records = [
            _record(True, "coverage", claim_id="C1", doc_id="D1"),
            _record(True, "liability", claim_id="C2", doc_id="D2"),
            _record(False, None, claim_id="C3", doc_id="D3"),
        ]
        enqueued = dispatch_screening_results(_empty_screening(records), queue)
        # C1:coverage → 1 job; C2:liability → 2 jobs (liability + recovery);
        # C3 not-relevant → 0.
        assert len(enqueued) == 3
        by_claim = {(j.claim_id, j.workflow) for j in enqueued}
        assert by_claim == {
            ("C1", "coverage"),
            ("C2", "liability"),
            ("C2", "recovery"),
        }

    def test_mixed_relevant_and_non_relevant_only_enqueues_relevant(self):
        queue = JobQueue(persistence_path=None)
        records = [
            _record(False, None, doc_id="D1"),
            _record(True, "reserve", claim_id="C1", doc_id="D2"),
            _record(False, None, doc_id="D3"),
        ]
        enqueued = dispatch_screening_results(_empty_screening(records), queue)
        assert len(enqueued) == 1
        assert enqueued[0].workflow == "reserve"
        assert enqueued[0].triggered_by_doc_id == "D2"
