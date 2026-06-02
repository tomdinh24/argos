"""Reserve workflow tests — extractor (mocked LLM) + end-to-end with override.

The pure-Python core (calculator + rationale) is covered in
tests/services/reserve/. This file focuses on:
  - The extractor tool schema is well-formed JSON Schema
  - The Anthropic call shape (system prompt + tool_use forcing)
  - Validation-failure retry path
  - End-to-end orchestration via inputs_override (calculator + rationale wiring)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

import pytest

from argos.ontology.types import (
    Document, Policy, PolicyCoverage, PolicyPeriod, SyntheticClaim,
    CoverageRequest,
)
from argos.schemas.workflows.reserve import (
    LitStatus, MedicalBill, PermanencyStatus, PipStatus, PolicyLimits,
    RepStatus, ReserveInputs, WageLoss,
)
from argos.workflows.reserve import (
    TOOL_NAME, _reserve_inputs_tool_schema, extract_reserve_inputs, run_reserve,
)


# ---------------------------------------------------------------------------
# Stub Anthropic client (same shape as tests/workflows/brief/test_narrative.py)
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
    """Hand-built SyntheticClaim for extractor-shape tests."""
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
                document_id="DOC-1",
                claim_id="CLM-100",
                document_type="police_report",
                received_date=date(2025, 6, 3),
                source="agency",
                body_text="Insured rear-ended claimant at low speed.",
            ),
        ],
        loss_date=date(2025, 6, 2),
        loss_facts="Routine rear-end, claimant reported neck pain at scene.",
    )


def _minimal_reserve_inputs() -> ReserveInputs:
    return ReserveInputs(
        accrual_date=date(2025, 6, 2),
        fnol_date=date(2025, 6, 3),
        venue_county="hillsborough",
        policy_limits=PolicyLimits(
            per_person=Decimal("100000"),
            per_occurrence=Decimal("300000"),
            property=Decimal("50000"),
        ),
        claimant_count=1,
        insured_liability_pct=Decimal("100"),
        tortfeasor_pip_compliant=True,
        pip_status=PipStatus(
            cap_applicable=10000, paid_to_date=Decimal("4000"),
            exhausted=False, emc_determination=True,
            treatment_within_14_days=True,
        ),
        permanency_status=PermanencyStatus(
            opinion_present=True, rating_pct=Decimal("3"),
            mmi_date=date(2025, 12, 1),
        ),
        medical_specials=[
            MedicalBill(
                billed=Decimal("6000"), paid=Decimal("2800"),
                payer="health_ins", provider="ER",
                lop_flag=False, date_of_service=date(2025, 6, 3),
            ),
        ],
        wage_loss=WageLoss(
            documented_to_date=Decimal("1500"),
            occupation="clerk", employer_verified=True,
        ),
        injury_bucket="minor_soft_tissue",
        representation_status=RepStatus(represented=False),
        litigation_status=LitStatus(phase="pre_suit"),
    )


# ---------------------------------------------------------------------------
# Tool schema
# ---------------------------------------------------------------------------


def test_tool_schema_has_correct_name():
    s = _reserve_inputs_tool_schema()
    assert s["name"] == TOOL_NAME
    assert "input_schema" in s
    assert s["input_schema"]["type"] == "object"


def test_tool_schema_input_matches_reserve_inputs():
    s = _reserve_inputs_tool_schema()
    assert s["input_schema"] == ReserveInputs.model_json_schema()


# ---------------------------------------------------------------------------
# Extractor — Anthropic call shape + validation retry
# ---------------------------------------------------------------------------


def test_extractor_emits_correct_anthropic_call_shape():
    valid_payload = _minimal_reserve_inputs().model_dump(mode="json")
    client = _StubClient(queued=[valid_payload])

    inputs, model, attempts = extract_reserve_inputs(
        _minimal_synthetic_claim(),
        anthropic_client=client,
    )

    assert isinstance(inputs, ReserveInputs)
    assert attempts == 1
    call = client.messages.calls[0]
    assert call["tool_choice"] == {"type": "tool", "name": TOOL_NAME}
    assert len(call["tools"]) == 1
    assert call["tools"][0]["name"] == TOOL_NAME
    assert "Reserve extractor" in call["system"]


def test_extractor_retries_on_validation_failure():
    invalid = {"accrual_date": "not-a-date"}  # blatantly invalid
    valid = _minimal_reserve_inputs().model_dump(mode="json")
    client = _StubClient(queued=[invalid, valid])

    inputs, _, attempts = extract_reserve_inputs(
        _minimal_synthetic_claim(),
        anthropic_client=client,
        max_retries=1,
    )
    assert attempts == 2
    assert isinstance(inputs, ReserveInputs)
    # Second call should include the corrective system note
    assert "PRIOR ATTEMPT REJECTED" in client.messages.calls[1]["system"]


def test_extractor_raises_after_max_retries_exhausted():
    invalid = {"accrual_date": "not-a-date"}
    client = _StubClient(queued=[invalid, invalid])

    with pytest.raises(RuntimeError, match="failed validation after 2 attempts"):
        extract_reserve_inputs(
            _minimal_synthetic_claim(),
            anthropic_client=client,
            max_retries=1,
        )


def test_extractor_retries_when_no_tool_use_block():
    valid = _minimal_reserve_inputs().model_dump(mode="json")
    client = _StubClient(queued=[None, valid])  # None → empty content

    inputs, _, attempts = extract_reserve_inputs(
        _minimal_synthetic_claim(),
        anthropic_client=client,
        max_retries=1,
    )
    assert attempts == 2
    assert isinstance(inputs, ReserveInputs)


# ---------------------------------------------------------------------------
# End-to-end via inputs_override (skip LLM, exercise calculator + rationale wiring)
# ---------------------------------------------------------------------------


def test_run_reserve_with_override_skips_llm():
    inputs = _minimal_reserve_inputs()
    result = run_reserve(
        _minimal_synthetic_claim(),
        inputs_override=inputs,
        reviewed_as_of=datetime(2026, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
    )
    assert result.extractor_attempts == 0
    assert result.extractor_model == "(override — no LLM call)"
    # Analysis populated from calculator
    assert result.analysis.authority_required_level == "handler"
    # Rationale attached and templated
    assert result.analysis.rationale != ""
    assert "RESERVE EVALUATION" in result.analysis.rationale
    assert "CLM-100" in result.analysis.rationale


def test_run_reserve_with_extractor_stub_end_to_end():
    """Full chain: stub LLM → ReserveInputs → calculator → rationale."""
    payload = _minimal_reserve_inputs().model_dump(mode="json")
    client = _StubClient(queued=[payload])

    result = run_reserve(
        _minimal_synthetic_claim(),
        anthropic_client=client,
        reviewed_as_of=datetime(2026, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
    )
    assert result.extractor_attempts == 1
    assert "RESERVE EVALUATION" in result.analysis.rationale
    assert result.raw_inputs.injury_bucket == "minor_soft_tissue"


def test_run_reserve_rationale_is_deterministic_with_fixed_inputs():
    inputs = _minimal_reserve_inputs()
    fixed_now = datetime(2026, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
    r1 = run_reserve(
        _minimal_synthetic_claim(), inputs_override=inputs, reviewed_as_of=fixed_now,
    )
    r2 = run_reserve(
        _minimal_synthetic_claim(), inputs_override=inputs, reviewed_as_of=fixed_now,
    )
    assert r1.analysis.rationale == r2.analysis.rationale
    assert r1.analysis.model_dump_json() == r2.analysis.model_dump_json()


# ---------------------------------------------------------------------------
# Runner integration
# ---------------------------------------------------------------------------


def test_runner_registry_has_real_reserve():
    """The orchestrator runner must register the real reserve function,
    not _stub_workflow('reserve')."""
    from argos.services.orchestrator.runner import (
        WORKFLOW_REGISTRY, _run_reserve_via_adapter,
    )
    assert WORKFLOW_REGISTRY["reserve"] is _run_reserve_via_adapter
