"""Closure workflow tests — extractor (mocked LLM) + end-to-end with override.

Deterministic-core coverage lives in tests/services/closure/. This file
covers:
  - Extractor tool schema shape
  - Anthropic call shape (system prompt + tool_use forcing)
  - Validation-failure retry path
  - End-to-end orchestration via inputs_override
  - Runner registry wires closure
  - closure_actions writeback (apply_closure_decision / apply_reopen_decision)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

import pytest

from argos.ontology.types import (
    Caseload,
    Claim,
    CoverageRequest,
    Document,
    Policy,
    PolicyCoverage,
    PolicyPeriod,
    SyntheticClaim,
)
from argos.schemas.workflows.closure import (
    BostonOldColonyDiligence,
    ClosureInputs,
    ClosureUpstreamContext,
    ExposureClosureState,
    SettlementInfo,
    UpstreamCoverageSnapshotForClosure,
    UpstreamLiabilitySnapshotForClosure,
)
from argos.services.orchestrator.closure_actions import (
    apply_closure_decision,
    apply_reopen_decision,
)
from argos.workflows.closure import (
    TOOL_NAME,
    _closure_inputs_tool_schema,
    extract_closure_inputs,
    run_closure,
)


# ---------------------------------------------------------------------------
# Stub Anthropic client
# ---------------------------------------------------------------------------


@dataclass
class _StubToolBlock:
    type: str
    input: dict[str, Any]


@dataclass
class _StubResponse:
    content: list
    model: str = "claude-sonnet-4-6"


class _StubMessages:
    def __init__(self, queued: list[dict[str, Any] | None]):
        self.queued = list(queued)
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if not self.queued:
            raise AssertionError("No more queued tool inputs")
        tool_input = self.queued.pop(0)
        if tool_input is None:
            return _StubResponse(content=[])
        return _StubResponse(
            content=[_StubToolBlock(type="tool_use", input=tool_input)],
        )


class _StubClient:
    def __init__(self, queued: list[dict[str, Any] | None]):
        self.messages = _StubMessages(queued)


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def _minimal_synthetic_claim() -> SyntheticClaim:
    return SyntheticClaim(
        policy=Policy(
            policy_id="POL-1",
            client_program_id="PROG-A",
            policy_number="AUTO-1001",
            named_insured_party_id="INS-1",
            policy_form="PAP",
            jurisdiction_state="FL",
        ),
        policy_period=PolicyPeriod(
            policy_period_id="PP-1",
            policy_id="POL-1",
            effective_from=date(2025, 1, 1),
            effective_to=date(2026, 1, 1),
            status="in_force",
        ),
        coverages=[
            PolicyCoverage(
                coverage_id="COV-BI-1",
                policy_period_id="PP-1",
                coverage_type="auto_BI",
                limit_per_occurrence=300_000.0,
                limit_per_person=100_000.0,
                deductible=500.0,
            ),
        ],
        request=CoverageRequest(
            request_id="REQ-1",
            claim_id="CLM-100",
            coverage_id="COV-BI-1",
            claimant_party_id="CLT-1",
        ),
        documents=[
            Document(
                document_id="DOC-RELEASE-1",
                claim_id="CLM-100",
                document_type="release",
                received_date=date(2026, 5, 25),
                source="claimant_counsel",
                body_text="Signed general release; settlement $15,000.",
            ),
        ],
        loss_date=date(2025, 6, 2),
        loss_facts="Tortfeasor at fault; insured settled BI claim.",
    )


def _minimal_closure_inputs() -> ClosureInputs:
    return ClosureInputs(
        loss_date=date(2025, 6, 2),
        intended_closure_intent="with_payment",
        coverage_decision="granted",
        liability_apportionment_committed=True,
        boston_old_colony_diligence=BostonOldColonyDiligence(
            insured_notified_of_settlement_opportunities=True,
            insured_warned_of_excess_exposure=True,
            facts_investigated=True,
            settlement_offers_received_fair_consideration=True,
            decision_reflects_reasonable_prudent_person=True,
        ),
        third_party_safe_harbor_tender_made=True,
        settlement=SettlementInfo(
            agreement_date=date(2026, 5, 20),
            agreement_amount=Decimal("15000"),
            release_executed_date=date(2026, 5, 22),
            release_includes_hold_harmless_for_liens=True,
            check_tendered_date=date(2026, 5, 30),
        ),
        exposure_status=ExposureClosureState(
            bi=True, pd=True, mp=True, pip=True, um=True,
        ),
    )


def _minimal_upstream() -> ClosureUpstreamContext:
    return ClosureUpstreamContext(
        coverage=UpstreamCoverageSnapshotForClosure(
            decision_committed=True, decision="granted",
        ),
        liability=UpstreamLiabilitySnapshotForClosure(
            apportionment_committed=True,
            insured_fault_pct=Decimal("20"),
            tender_made=True,
        ),
    )


# ---------------------------------------------------------------------------
# Tool schema
# ---------------------------------------------------------------------------


def test_tool_schema_has_correct_name():
    s = _closure_inputs_tool_schema()
    assert s["name"] == TOOL_NAME
    assert "input_schema" in s
    assert s["input_schema"]["type"] == "object"


def test_tool_schema_input_matches_closure_inputs():
    s = _closure_inputs_tool_schema()
    assert s["input_schema"] == ClosureInputs.model_json_schema()


# ---------------------------------------------------------------------------
# Extractor — Anthropic call shape + validation retry
# ---------------------------------------------------------------------------


def test_extractor_emits_correct_anthropic_call_shape():
    payload = _minimal_closure_inputs().model_dump(mode="json")
    client = _StubClient(queued=[payload])

    inputs, _model, attempts = extract_closure_inputs(
        _minimal_synthetic_claim(),
        upstream=_minimal_upstream(),
        anthropic_client=client,
    )
    assert isinstance(inputs, ClosureInputs)
    assert attempts == 1
    call = client.messages.calls[0]
    assert call["tool_choice"] == {"type": "tool", "name": TOOL_NAME}
    assert call["tools"][0]["name"] == TOOL_NAME
    assert "Closure extractor" in call["system"]


def test_extractor_includes_upstream_snapshots_in_user_body():
    payload = _minimal_closure_inputs().model_dump(mode="json")
    client = _StubClient(queued=[payload])

    extract_closure_inputs(
        _minimal_synthetic_claim(),
        upstream=_minimal_upstream(),
        anthropic_client=client,
    )
    body = client.messages.calls[0]["messages"][0]["content"]
    assert "UPSTREAM CONTEXT" in body
    assert "Coverage:" in body
    assert "Liability:" in body


def test_extractor_retries_on_validation_failure():
    invalid = {"loss_date": "not-a-date"}
    valid = _minimal_closure_inputs().model_dump(mode="json")
    client = _StubClient(queued=[invalid, valid])

    inputs, _, attempts = extract_closure_inputs(
        _minimal_synthetic_claim(),
        upstream=_minimal_upstream(),
        anthropic_client=client,
        max_retries=1,
    )
    assert attempts == 2
    assert isinstance(inputs, ClosureInputs)
    assert "PRIOR ATTEMPT REJECTED" in client.messages.calls[1]["system"]


def test_extractor_raises_after_max_retries():
    invalid = {"loss_date": "not-a-date"}
    client = _StubClient(queued=[invalid, invalid])
    with pytest.raises(RuntimeError, match="failed validation after 2 attempts"):
        extract_closure_inputs(
            _minimal_synthetic_claim(),
            upstream=_minimal_upstream(),
            anthropic_client=client,
            max_retries=1,
        )


def test_extractor_retries_when_no_tool_use_block():
    valid = _minimal_closure_inputs().model_dump(mode="json")
    client = _StubClient(queued=[None, valid])
    inputs, _, attempts = extract_closure_inputs(
        _minimal_synthetic_claim(),
        upstream=_minimal_upstream(),
        anthropic_client=client,
        max_retries=1,
    )
    assert attempts == 2
    assert isinstance(inputs, ClosureInputs)


# ---------------------------------------------------------------------------
# End-to-end via inputs_override
# ---------------------------------------------------------------------------


_FIXED_NOW = datetime(2026, 6, 2, 10, 0, 0, tzinfo=timezone.utc)


def test_run_closure_with_override_skips_llm():
    result = run_closure(
        _minimal_synthetic_claim(),
        upstream=_minimal_upstream(),
        inputs_override=_minimal_closure_inputs(),
        reviewed_as_of=_FIXED_NOW,
    )
    assert result.extractor_attempts == 0
    assert result.extractor_model == "(override — no LLM call)"
    assert result.assessment.recommendation == "ready_to_close_with_payment"


def test_run_closure_end_to_end_with_stub_llm():
    payload = _minimal_closure_inputs().model_dump(mode="json")
    client = _StubClient(queued=[payload])
    result = run_closure(
        _minimal_synthetic_claim(),
        upstream=_minimal_upstream(),
        anthropic_client=client,
        reviewed_as_of=_FIXED_NOW,
    )
    assert result.extractor_attempts == 1
    assert "Ready to close" in result.assessment.rationale_text
    # Diligence ledger enriched
    assert result.assessment.diligence_ledger.gates_evaluated


def test_run_closure_rationale_deterministic_with_fixed_inputs():
    inputs = _minimal_closure_inputs()
    upstream = _minimal_upstream()
    r1 = run_closure(
        _minimal_synthetic_claim(), upstream=upstream,
        inputs_override=inputs, reviewed_as_of=_FIXED_NOW,
    )
    r2 = run_closure(
        _minimal_synthetic_claim(), upstream=upstream,
        inputs_override=inputs, reviewed_as_of=_FIXED_NOW,
    )
    assert r1.assessment.rationale_text == r2.assessment.rationale_text
    assert r1.assessment.model_dump_json() == r2.assessment.model_dump_json()


def test_run_closure_without_upstream_runs_degraded():
    result = run_closure(
        _minimal_synthetic_claim(),
        upstream=None,
        inputs_override=_minimal_closure_inputs(),
        reviewed_as_of=_FIXED_NOW,
    )
    assert result.assessment.recommendation in {
        "ready_to_close_with_payment",
        "ready_to_close_without_payment",
        "closed_with_open_recovery",
        "soft_close_pending_medicare_final_demand",
        "soft_close_pending_section_111_confirmation",
        "soft_close_pending_lien_release_letter",
        "soft_close_pending_release_execution",
        "blocked_by_defects",
        "requires_senior_review",
        "requires_legal_review",
        "recommend_reopen",
    }


# ---------------------------------------------------------------------------
# Runner integration
# ---------------------------------------------------------------------------


def test_runner_registry_includes_closure_runner():
    import tempfile
    from pathlib import Path
    from argos.services.orchestrator.queue import JobQueue
    from argos.services.orchestrator.runner import WorkflowRunner

    with tempfile.TemporaryDirectory() as tmpdir:
        queue = JobQueue(persistence_path=Path(tmpdir) / "queue.db")
        caseload = Caseload(
            as_of=datetime(2026, 6, 2, tzinfo=timezone.utc),
            policies=[], policy_periods=[], coverages=[], parties=[],
            claims=[], requests=[], documents=[],
        )
        runner = WorkflowRunner(
            queue=queue, caseload=caseload, results_root=Path(tmpdir),
        )
        assert "closure" in runner.registry
        fn = runner.registry["closure"]
        assert fn.__name__ != "stub"


# ---------------------------------------------------------------------------
# Closure actions writeback
# ---------------------------------------------------------------------------


def _caseload_with_open_claim() -> Caseload:
    claim = Claim(
        claim_id="CLM-100",
        policy_id="POL-1",
        policy_period_id="PP-1",
        opened_date=date(2025, 6, 3),
        status="open",
    )
    return Caseload(
        as_of=datetime(2026, 6, 2, tzinfo=timezone.utc),
        policies=[], policy_periods=[], coverages=[], parties=[],
        claims=[claim], requests=[], documents=[],
    )


def test_apply_closure_decision_with_payment_flips_to_closed():
    cl = _caseload_with_open_claim()
    out = apply_closure_decision(
        cl, "CLM-100", recommendation="ready_to_close_with_payment",
    )
    assert out.claims[0].status == "closed"


def test_apply_closure_decision_soft_close_keeps_open():
    cl = _caseload_with_open_claim()
    out = apply_closure_decision(
        cl, "CLM-100",
        recommendation="soft_close_pending_medicare_final_demand",
    )
    assert out.claims[0].status == "open"


def test_apply_closure_decision_blocked_raises():
    cl = _caseload_with_open_claim()
    with pytest.raises(ValueError, match="routing signal"):
        apply_closure_decision(
            cl, "CLM-100", recommendation="blocked_by_defects",
        )


def test_apply_closure_decision_unknown_claim_raises():
    cl = _caseload_with_open_claim()
    with pytest.raises(ValueError, match="not present"):
        apply_closure_decision(
            cl, "CLM-DOES-NOT-EXIST",
            recommendation="ready_to_close_with_payment",
        )


def test_apply_closure_decision_idempotent_when_already_closed():
    cl = _caseload_with_open_claim()
    once = apply_closure_decision(
        cl, "CLM-100", recommendation="ready_to_close_with_payment",
    )
    twice = apply_closure_decision(
        once, "CLM-100", recommendation="ready_to_close_with_payment",
    )
    assert twice.claims[0].status == "closed"


def test_apply_reopen_decision_flips_closed_to_reopened():
    cl = _caseload_with_open_claim()
    closed = apply_closure_decision(
        cl, "CLM-100", recommendation="ready_to_close_with_payment",
    )
    reopened = apply_reopen_decision(
        closed, "CLM-100", reopen_reason="post_close_cms_final_demand",
    )
    assert reopened.claims[0].status == "reopened"
    # Same claim ID
    assert reopened.claims[0].claim_id == "CLM-100"


def test_apply_reopen_decision_rejects_open_claim():
    cl = _caseload_with_open_claim()
    with pytest.raises(ValueError, match="only closed claims"):
        apply_reopen_decision(
            cl, "CLM-100", reopen_reason="post_close_demand",
        )
