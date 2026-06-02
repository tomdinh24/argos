"""Tests for the specialist orchestrator (Job, JobQueue, Dispatcher,
WorkflowRunner).

No live API calls. The runner is exercised with a stub specialist
registry so the orchestration logic is validated independent of any
real LLM call.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from argos.ontology.synthetic_caseload import build_caseload
from argos.schemas.workflows.document_reader import RelevanceCall
from argos.services.orchestrator.dispatcher import dispatch
from argos.services.orchestrator.job import Job, JobStatus
from argos.services.orchestrator.queue import JobQueue
from argos.services.orchestrator.runner import WorkflowRunner


# ---------------------------------------------------------------------------
# Job + idempotency key
# ---------------------------------------------------------------------------


class TestJob:
    def test_job_id_auto_generated(self):
        a = Job(workflow="coverage", claim_id="C1", triggered_by_doc_id="D1", posture_changed="coverage")
        b = Job(workflow="coverage", claim_id="C1", triggered_by_doc_id="D1", posture_changed="coverage")
        assert a.job_id != b.job_id
        assert a.job_id.startswith("JOB-")

    def test_idempotency_key_is_triple(self):
        j = Job(workflow="reserve", claim_id="C2", triggered_by_doc_id="D5", posture_changed="reserve")
        assert j.idempotency_key() == ("reserve", "C2", "D5")

    def test_starts_pending(self):
        j = Job(workflow="coverage", claim_id="C1", triggered_by_doc_id="D1", posture_changed="coverage")
        assert j.status == JobStatus.PENDING
        assert j.started_at is None and j.completed_at is None

    def test_round_trip_through_dict(self):
        j = Job(workflow="coverage", claim_id="C1", triggered_by_doc_id="D1", posture_changed="coverage")
        restored = Job.from_dict(j.to_dict())
        assert restored.job_id == j.job_id
        assert restored.workflow == j.workflow
        assert restored.status == j.status


# ---------------------------------------------------------------------------
# JobQueue
# ---------------------------------------------------------------------------


class TestJobQueueBasics:
    def test_enqueue_appends(self):
        q = JobQueue()
        j = Job(workflow="coverage", claim_id="C1", triggered_by_doc_id="D1", posture_changed="coverage")
        q.enqueue(j)
        assert q.all_jobs() == [j]
        assert q.pending() == [j]

    def test_next_pending_returns_oldest_pending(self):
        q = JobQueue()
        a = Job(workflow="coverage", claim_id="C1", triggered_by_doc_id="D1", posture_changed="coverage")
        b = Job(workflow="coverage", claim_id="C2", triggered_by_doc_id="D2", posture_changed="coverage")
        q.enqueue(a); q.enqueue(b)
        assert q.next_pending() == a
        q.mark_running(a.job_id)
        # next pending now skips running
        assert q.next_pending() == b

    def test_status_transitions(self):
        q = JobQueue()
        j = Job(workflow="coverage", claim_id="C1", triggered_by_doc_id="D1", posture_changed="coverage")
        q.enqueue(j)
        q.mark_running(j.job_id)
        assert j.status == JobStatus.RUNNING and j.started_at is not None
        q.mark_done(j.job_id, result_path="/tmp/x.json", result_summary="ok")
        assert j.status == JobStatus.DONE and j.completed_at is not None
        assert j.result_path == "/tmp/x.json"


class TestJobQueueIdempotency:
    def test_duplicate_triple_returns_existing_job(self):
        q = JobQueue()
        a = Job(workflow="coverage", claim_id="C1", triggered_by_doc_id="D1", posture_changed="coverage")
        b = Job(workflow="coverage", claim_id="C1", triggered_by_doc_id="D1", posture_changed="coverage")
        q.enqueue(a)
        result = q.enqueue(b)
        assert result is a  # the existing job, not the new one
        assert len(q.all_jobs()) == 1

    def test_done_job_does_not_block_new_enqueue_on_same_triple(self):
        q = JobQueue()
        a = Job(workflow="coverage", claim_id="C1", triggered_by_doc_id="D1", posture_changed="coverage")
        q.enqueue(a)
        q.mark_done(a.job_id, result_summary="ok")
        b = Job(workflow="coverage", claim_id="C1", triggered_by_doc_id="D1", posture_changed="coverage")
        result = q.enqueue(b)
        assert result is b  # new job allowed because the prior one is DONE
        assert len(q.all_jobs()) == 2

    def test_different_specialist_same_doc_creates_separate_jobs(self):
        q = JobQueue()
        a = Job(workflow="reserve", claim_id="C1", triggered_by_doc_id="D1", posture_changed="damages")
        b = Job(workflow="liability", claim_id="C1", triggered_by_doc_id="D1", posture_changed="damages")
        q.enqueue(a); q.enqueue(b)
        assert len(q.all_jobs()) == 2


class TestJobQueuePersistence:
    def test_round_trip_through_disk(self, tmp_path: Path):
        path = tmp_path / "queue.json"
        q1 = JobQueue(path)
        j = Job(workflow="coverage", claim_id="C1", triggered_by_doc_id="D1", posture_changed="coverage")
        q1.enqueue(j)
        q1.mark_running(j.job_id)

        q2 = JobQueue(path)
        loaded = q2.all_jobs()
        assert len(loaded) == 1
        assert loaded[0].job_id == j.job_id
        assert loaded[0].status == JobStatus.RUNNING


# ---------------------------------------------------------------------------
# Dispatcher (pure function)
# ---------------------------------------------------------------------------


def _call(relevant: bool, posture: str | None, doc_id: str = "D1") -> RelevanceCall:
    return RelevanceCall(
        document_id=doc_id,
        relevant=relevant,
        posture_changed=posture,
        reason="r" if not relevant else "relevant reason",
        text_excerpt="" if not relevant else "quoted sentence",
    )


class TestDispatcher:
    def test_not_relevant_returns_empty(self):
        jobs = dispatch(_call(False, None), claim_id="C1")
        assert jobs == []

    def test_coverage_posture_enqueues_coverage_only(self):
        jobs = dispatch(_call(True, "coverage"), claim_id="C1")
        assert len(jobs) == 1
        assert jobs[0].workflow == "coverage"
        assert jobs[0].claim_id == "C1"
        assert jobs[0].triggered_by_doc_id == "D1"

    def test_reserve_posture_enqueues_reserve_only(self):
        jobs = dispatch(_call(True, "reserve"), claim_id="C1")
        assert [j.workflow for j in jobs] == ["reserve"]

    def test_liability_posture_enqueues_liability_and_recovery(self):
        # Liability commit re-shapes recoverable basis + bar evaluation,
        # so Recovery must be re-evaluated on every liability change.
        jobs = dispatch(_call(True, "liability"), claim_id="C1")
        assert [j.workflow for j in jobs] == ["liability", "recovery"]

    def test_damages_posture_enqueues_reserve_liability_and_recovery(self):
        # Damages flow into reserve adequacy, liability negotiation,
        # AND the layered recoverable basis.
        jobs = dispatch(_call(True, "damages"), claim_id="C1")
        assert {j.workflow for j in jobs} == {"reserve", "liability", "recovery"}

    def test_subrogation_posture_enqueues_recovery_only(self):
        # Subro-only artifacts (consent-to-settle, AF eligibility,
        # made-whole waiver) re-shape the recoverable basis without
        # touching fault or damages. Liability does NOT re-run.
        jobs = dispatch(_call(True, "subrogation"), claim_id="C1")
        assert [j.workflow for j in jobs] == ["recovery"]
        assert jobs[0].posture_changed == "subrogation"


# ---------------------------------------------------------------------------
# Runner (with stub specialist registry — no live API)
# ---------------------------------------------------------------------------


def _make_stub_registry():
    """Stub specialists that record what they were called with."""
    calls: list[tuple[str, str]] = []

    def make_stub(name: str):
        def stub(caseload, claim_id):
            calls.append((name, claim_id))
            return f"stub {name} ran on {claim_id}", {"workflow": name, "claim_id": claim_id}
        return stub

    registry = {
        "coverage": make_stub("coverage"),
        "reserve": make_stub("reserve"),
        "liability": make_stub("liability"),
    }
    return registry, calls


class TestWorkflowRunner:
    def test_process_one_runs_and_persists_result(self, tmp_path: Path):
        registry, calls = _make_stub_registry()
        q = JobQueue()
        j = Job(workflow="coverage", claim_id="CLM-001", triggered_by_doc_id="D1", posture_changed="coverage")
        q.enqueue(j)
        runner = WorkflowRunner(q, build_caseload(), tmp_path, registry=registry)

        processed = runner.process_one()
        assert processed is not None
        assert processed.status == JobStatus.DONE
        assert processed.result_summary == "stub coverage ran on CLM-001"
        # Result file exists
        result_path = tmp_path / "CLM-001" / "coverage.json"
        assert result_path.exists()
        assert json.loads(result_path.read_text())["claim_id"] == "CLM-001"
        # Stub was called with the right args
        assert calls == [("coverage", "CLM-001")]

    def test_process_all_drains_the_queue(self, tmp_path: Path):
        registry, calls = _make_stub_registry()
        q = JobQueue()
        for cid, spec in [("CLM-001", "coverage"), ("CLM-002", "reserve"), ("CLM-003", "liability")]:
            q.enqueue(Job(workflow=spec, claim_id=cid, triggered_by_doc_id="D1", posture_changed=spec))
        runner = WorkflowRunner(q, build_caseload(), tmp_path, registry=registry)

        processed = runner.process_all()
        assert len(processed) == 3
        assert all(p.status == JobStatus.DONE for p in processed)
        assert {c[0] for c in calls} == {"coverage", "reserve", "liability"}
        assert q.pending() == []

    def test_runner_marks_failed_on_specialist_exception(self, tmp_path: Path):
        def boom(_caseload, _claim_id):
            raise RuntimeError("specialist crashed")
        registry = {"coverage": boom}
        q = JobQueue()
        j = Job(workflow="coverage", claim_id="CLM-001", triggered_by_doc_id="D1", posture_changed="coverage")
        q.enqueue(j)
        runner = WorkflowRunner(q, build_caseload(), tmp_path, registry=registry)

        processed = runner.process_one()
        assert processed.status == JobStatus.FAILED
        assert "specialist crashed" in (processed.error or "")
        # No result file written
        assert not (tmp_path / "CLM-001" / "coverage.json").exists()

    def test_unknown_specialist_marks_failed(self, tmp_path: Path):
        q = JobQueue()
        j = Job(workflow="nonexistent", claim_id="CLM-001", triggered_by_doc_id="D1", posture_changed="coverage")
        q.enqueue(j)
        runner = WorkflowRunner(q, build_caseload(), tmp_path, registry={})

        processed = runner.process_one()
        assert processed.status == JobStatus.FAILED
        assert "No workflow registered" in (processed.error or "")

    def test_runner_appends_analysis_emitted_on_success(self, tmp_path: Path):
        """Successful workflow run writes one analysis_emitted row."""
        from argos.services.orchestrator.audit_log import (
            ANALYSIS_EMITTED,
            load_agent_actions,
        )

        registry, _ = _make_stub_registry()
        q = JobQueue()
        q.enqueue(Job(
            workflow="coverage", claim_id="CLM-001",
            triggered_by_doc_id="D1", posture_changed="coverage",
        ))
        results_root = tmp_path / "results"
        audit_root = tmp_path / "audit"
        runner = WorkflowRunner(
            q, build_caseload(), results_root, registry=registry,
            audit_log_root=audit_root,
        )
        runner.process_one()

        rows = load_agent_actions("CLM-001", log_root=audit_root)
        assert len(rows) == 1
        assert rows[0].workflow == "coverage"
        assert rows[0].action_type == ANALYSIS_EMITTED
        assert rows[0].success is True
        assert "stub coverage ran on CLM-001" in rows[0].summary

    def test_runner_appends_validator_fail_on_specialist_exception(
        self, tmp_path: Path,
    ):
        from argos.services.orchestrator.audit_log import (
            VALIDATOR_FAIL,
            load_agent_actions,
        )

        def boom(_caseload, _claim_id):
            raise RuntimeError("specialist crashed")
        q = JobQueue()
        q.enqueue(Job(
            workflow="coverage", claim_id="CLM-001",
            triggered_by_doc_id="D1", posture_changed="coverage",
        ))
        results_root = tmp_path / "results"
        audit_root = tmp_path / "audit"
        runner = WorkflowRunner(
            q, build_caseload(), results_root, registry={"coverage": boom},
            audit_log_root=audit_root,
        )
        runner.process_one()

        rows = load_agent_actions("CLM-001", log_root=audit_root)
        assert len(rows) == 1
        assert rows[0].action_type == VALIDATOR_FAIL
        assert rows[0].success is False
        assert "specialist crashed" in rows[0].summary

    def test_runner_appends_validator_fail_on_unknown_workflow(
        self, tmp_path: Path,
    ):
        from argos.services.orchestrator.audit_log import (
            VALIDATOR_FAIL,
            load_agent_actions,
        )

        q = JobQueue()
        q.enqueue(Job(
            workflow="nonexistent", claim_id="CLM-001",
            triggered_by_doc_id="D1", posture_changed="coverage",
        ))
        results_root = tmp_path / "results"
        audit_root = tmp_path / "audit"
        runner = WorkflowRunner(
            q, build_caseload(), results_root, registry={},
            audit_log_root=audit_root,
        )
        runner.process_one()

        rows = load_agent_actions("CLM-001", log_root=audit_root)
        assert len(rows) == 1
        assert rows[0].action_type == VALIDATOR_FAIL
        assert "No workflow registered" in rows[0].summary

    def test_audit_log_root_defaults_to_sibling_of_results_root(
        self, tmp_path: Path,
    ):
        """When audit_log_root not provided, it parks next to results_root."""
        registry, _ = _make_stub_registry()
        q = JobQueue()
        q.enqueue(Job(
            workflow="coverage", claim_id="CLM-001",
            triggered_by_doc_id="D1", posture_changed="coverage",
        ))
        results_root = tmp_path / "workflow-results"
        runner = WorkflowRunner(
            q, build_caseload(), results_root, registry=registry,
        )
        assert runner.audit_log_root == tmp_path / "agent-actions"
        runner.process_one()
        assert (tmp_path / "agent-actions" / "CLM-001.jsonl").exists()


# ---------------------------------------------------------------------------
# Adapter (no live API)
# ---------------------------------------------------------------------------


class TestCaseloadAdapter:
    def test_adapts_caseload_claim_to_synthetic_claim(self):
        from argos.services.orchestrator.adapter import caseload_to_synthetic_claim

        caseload = build_caseload()
        # Pick any claim that has at least one document in the v3 fixture
        # (REQ-013/014/015 carry placeholder docs in v3)
        synth = caseload_to_synthetic_claim(caseload, "CLM-013")
        assert synth.request.claim_id == "CLM-013"
        assert synth.policy.jurisdiction_state == "FL"
        assert len(synth.coverages) >= 1
        assert synth.coverages[0].coverage_id == synth.request.coverage_id

    def test_adapter_raises_on_unknown_claim(self):
        from argos.services.orchestrator.adapter import caseload_to_synthetic_claim

        caseload = build_caseload()
        with pytest.raises(ValueError):
            caseload_to_synthetic_claim(caseload, "CLM-999")
