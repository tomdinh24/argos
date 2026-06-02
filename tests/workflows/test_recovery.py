"""Recovery workflow tests — extractor (mocked LLM) + end-to-end with override.

The pure-Python core (policy engine + calculator + ledger + rationale) is
covered in tests/services/recovery/. This file focuses on:
  - The extractor tool schema is well-formed JSON Schema
  - The Anthropic call shape (system prompt + tool_use forcing)
  - Validation-failure retry path
  - End-to-end orchestration via inputs_override (calculator + ledger +
    rationale wiring → RecoveryAssessment)
  - Runner registry wires the real recovery runner under the "recovery" key
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

import pytest

from argos.ontology.types import (
    CoverageRequest, Document, Policy, PolicyCoverage, PolicyPeriod, SyntheticClaim,
)
from argos.schemas.workflows.recovery import (
    EvidenceArtifacts,
    OwnerOperatorSplit,
    PolicySubrogationLanguage,
    RecoveryInputs,
    RecoveryUpstreamContext,
    UpstreamLiabilitySnapshot,
    UpstreamReserveSnapshot,
)
from argos.workflows.recovery import (
    TOOL_NAME, _recovery_inputs_tool_schema,
    extract_recovery_inputs, run_recovery,
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
    """Hand-built SyntheticClaim for Recovery extractor-shape tests."""
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
                document_id="DOC-PR-1",
                claim_id="CLM-100",
                document_type="police_report",
                received_date=date(2025, 6, 3),
                source="agency",
                body_text="Tortfeasor rear-ended insured at controlled intersection.",
            ),
        ],
        loss_date=date(2025, 6, 2),
        loss_facts="Tortfeasor at fault; insured paid out collision claim.",
    )


def _minimal_recovery_inputs() -> RecoveryInputs:
    return RecoveryInputs(
        loss_date=date(2025, 6, 2),
        loss_state="FL",
        tortfeasor_vehicle_classification="private_passenger",
        tortfeasor_vehicle_vin="1HGCM82633A123456",
        tortfeasor_carrier_naic="25178",  # State Farm seed signatory
        owner_operator_split=OwnerOperatorSplit(
            owner_id="P-tortfeasor",
            operator_id="P-tortfeasor",
            are_same=True,
            owner_type="natural_person",
        ),
        policy_subrogation_language=PolicySubrogationLanguage(
            has_made_whole_waiver=False,
        ),
        subrogation_lane="legal",
        evidence_artifacts=EvidenceArtifacts(vehicle_status="in_storage_yard"),
    )


def _minimal_upstream() -> RecoveryUpstreamContext:
    from decimal import Decimal
    return RecoveryUpstreamContext(
        liability=UpstreamLiabilitySnapshot(
            apportionment_by_party_id={
                "P-insured": Decimal("20"),
                "P-tortfeasor": Decimal("80"),
            },
            insured_fault_pct=Decimal("20"),
            claimant_fault_pct=Decimal("80"),
            operator_party_id="P-tortfeasor",
            owner_party_id="P-tortfeasor",
            regime_statute="modified_51_bar_hb837",
            recovery_bar_triggered=False,
            bar_basis="none",
        ),
        reserve=UpstreamReserveSnapshot(
            paid_indemnity_by_component={"indemnity": Decimal("25000")},
            outstanding_indemnity_by_component={"indemnity": Decimal("5000")},
            total_economic_loss=Decimal("30000"),
        ),
    )


# ---------------------------------------------------------------------------
# Tool schema
# ---------------------------------------------------------------------------


def test_tool_schema_has_correct_name():
    s = _recovery_inputs_tool_schema()
    assert s["name"] == TOOL_NAME
    assert "input_schema" in s
    assert s["input_schema"]["type"] == "object"


def test_tool_schema_input_matches_recovery_inputs():
    s = _recovery_inputs_tool_schema()
    assert s["input_schema"] == RecoveryInputs.model_json_schema()


# ---------------------------------------------------------------------------
# Extractor — Anthropic call shape + validation retry
# ---------------------------------------------------------------------------


def test_extractor_emits_correct_anthropic_call_shape():
    valid_payload = _minimal_recovery_inputs().model_dump(mode="json")
    client = _StubClient(queued=[valid_payload])

    inputs, model, attempts = extract_recovery_inputs(
        _minimal_synthetic_claim(),
        upstream=_minimal_upstream(),
        anthropic_client=client,
    )

    assert isinstance(inputs, RecoveryInputs)
    assert attempts == 1
    call = client.messages.calls[0]
    assert call["tool_choice"] == {"type": "tool", "name": TOOL_NAME}
    assert len(call["tools"]) == 1
    assert call["tools"][0]["name"] == TOOL_NAME
    assert "Recovery extractor" in call["system"]


def test_extractor_includes_upstream_snapshots_in_user_body():
    valid_payload = _minimal_recovery_inputs().model_dump(mode="json")
    client = _StubClient(queued=[valid_payload])

    extract_recovery_inputs(
        _minimal_synthetic_claim(),
        upstream=_minimal_upstream(),
        anthropic_client=client,
    )
    body = client.messages.calls[0]["messages"][0]["content"]
    assert "UPSTREAM CONTEXT" in body
    assert "Liability:" in body
    assert "modified_51_bar_hb837" in body
    assert "Reserve:" in body


def test_extractor_retries_on_validation_failure():
    invalid = {"loss_date": "not-a-date"}
    valid = _minimal_recovery_inputs().model_dump(mode="json")
    client = _StubClient(queued=[invalid, valid])

    inputs, _, attempts = extract_recovery_inputs(
        _minimal_synthetic_claim(),
        upstream=_minimal_upstream(),
        anthropic_client=client,
        max_retries=1,
    )
    assert attempts == 2
    assert isinstance(inputs, RecoveryInputs)
    assert "PRIOR ATTEMPT REJECTED" in client.messages.calls[1]["system"]


def test_extractor_raises_after_max_retries_exhausted():
    invalid = {"loss_date": "not-a-date"}
    client = _StubClient(queued=[invalid, invalid])

    with pytest.raises(RuntimeError, match="failed validation after 2 attempts"):
        extract_recovery_inputs(
            _minimal_synthetic_claim(),
            upstream=_minimal_upstream(),
            anthropic_client=client,
            max_retries=1,
        )


def test_extractor_retries_when_no_tool_use_block():
    valid = _minimal_recovery_inputs().model_dump(mode="json")
    client = _StubClient(queued=[None, valid])

    inputs, _, attempts = extract_recovery_inputs(
        _minimal_synthetic_claim(),
        upstream=_minimal_upstream(),
        anthropic_client=client,
        max_retries=1,
    )
    assert attempts == 2
    assert isinstance(inputs, RecoveryInputs)


# ---------------------------------------------------------------------------
# End-to-end via inputs_override
# ---------------------------------------------------------------------------


def test_run_recovery_with_override_skips_llm():
    result = run_recovery(
        _minimal_synthetic_claim(),
        upstream=_minimal_upstream(),
        inputs_override=_minimal_recovery_inputs(),
        reviewed_as_of=datetime(2025, 7, 1, 10, 0, 0, tzinfo=timezone.utc),
    )
    assert result.extractor_attempts == 0
    assert result.extractor_model == "(override — no LLM call)"
    assert "RECOVERY EVALUATION" in result.assessment.rationale_text
    assert "CLM-100" in result.assessment.rationale_text
    # Recommendation is one of the controlled literals
    assert result.assessment.recommendation in (
        "pursue", "route_to_af", "route_to_litigation",
        "route_to_negotiated_demand", "abstain", "senior_review_required",
    )


def test_run_recovery_end_to_end_with_stub_llm():
    payload = _minimal_recovery_inputs().model_dump(mode="json")
    client = _StubClient(queued=[payload])

    result = run_recovery(
        _minimal_synthetic_claim(),
        upstream=_minimal_upstream(),
        anthropic_client=client,
        reviewed_as_of=datetime(2025, 7, 1, 10, 0, 0, tzinfo=timezone.utc),
    )
    assert result.extractor_attempts == 1
    assert "RECOVERY EVALUATION" in result.assessment.rationale_text
    assert result.raw_inputs.subrogation_lane == "legal"
    # Diligence ledger is populated and co-equal
    assert len(result.assessment.diligence_ledger.gates_evaluated) >= 14
    # AF signatory check recorded
    assert result.assessment.diligence_ledger.af_signatory_check is not None


def test_run_recovery_rationale_is_deterministic_with_fixed_inputs():
    inputs = _minimal_recovery_inputs()
    upstream = _minimal_upstream()
    fixed_now = datetime(2025, 7, 1, 10, 0, 0, tzinfo=timezone.utc)
    r1 = run_recovery(
        _minimal_synthetic_claim(),
        upstream=upstream,
        inputs_override=inputs,
        reviewed_as_of=fixed_now,
    )
    r2 = run_recovery(
        _minimal_synthetic_claim(),
        upstream=upstream,
        inputs_override=inputs,
        reviewed_as_of=fixed_now,
    )
    assert r1.assessment.rationale_text == r2.assessment.rationale_text
    assert r1.assessment.model_dump_json() == r2.assessment.model_dump_json()


def test_run_recovery_without_upstream_runs_degraded():
    """Missing upstream context should NOT crash — degrade gracefully."""
    result = run_recovery(
        _minimal_synthetic_claim(),
        upstream=None,  # No prior Liability/Reserve/Coverage
        inputs_override=_minimal_recovery_inputs(),
        reviewed_as_of=datetime(2025, 7, 1, 10, 0, 0, tzinfo=timezone.utc),
    )
    # Should still produce an assessment
    assert result.assessment.recommendation in (
        "pursue", "route_to_af", "route_to_litigation",
        "route_to_negotiated_demand", "abstain", "senior_review_required",
    )


# ---------------------------------------------------------------------------
# Runner integration
# ---------------------------------------------------------------------------


def test_runner_registry_includes_recovery_runner():
    """The WorkflowRunner registry must include a recovery runner (not stub)."""
    import tempfile
    from pathlib import Path
    from argos.ontology.types import Caseload
    from argos.services.orchestrator.queue import JobQueue
    from argos.services.orchestrator.runner import WorkflowRunner

    with tempfile.TemporaryDirectory() as tmpdir:
        queue = JobQueue(persistence_path=Path(tmpdir) / "queue.db")
        caseload = Caseload(
            as_of=datetime(2025, 7, 1, tzinfo=timezone.utc),
            policies=[], policy_periods=[], coverages=[], parties=[],
            claims=[], requests=[], documents=[],
        )
        runner = WorkflowRunner(
            queue=queue, caseload=caseload, results_root=Path(tmpdir),
        )
        assert "recovery" in runner.registry
        # And it's not the stub
        fn = runner.registry["recovery"]
        assert fn.__name__ != "stub"
