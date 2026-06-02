"""Liability workflow tests — extractor (mocked LLM) + end-to-end with override.

The pure-Python core (policy engine + calculator + ledger + rationale) is
covered in tests/services/liability/. This file focuses on:
  - The extractor tool schema is well-formed JSON Schema
  - The Anthropic call shape (system prompt + tool_use forcing)
  - Validation-failure retry path
  - End-to-end orchestration via inputs_override (calculator + ledger +
    rationale wiring → LiabilityAssessment)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

import pytest

from argos.ontology.types import (
    CoverageRequest, Document, Policy, PolicyCoverage, PolicyPeriod, SyntheticClaim,
)
from argos.schemas.workflows.liability import (
    EvidenceItem, IntoxicationEvidence, LiabilityInputs, NegligentEntrustment,
    OwnerRelationship, Party, PoliceReportFields, RearEndRebuttal,
)
from argos.workflows.liability import (
    TOOL_NAME, _liability_inputs_tool_schema, extract_liability_inputs, run_liability,
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
                document_id="DOC-PR-1",
                claim_id="CLM-100",
                document_type="police_report",
                received_date=date(2025, 6, 3),
                source="agency",
                body_text="Insured rear-ended claimant. Claimant stopped at red light.",
            ),
        ],
        loss_date=date(2025, 6, 2),
        loss_facts="Rear-end at controlled intersection.",
    )


def _minimal_liability_inputs() -> LiabilityInputs:
    return LiabilityInputs(
        accrual_date=date(2025, 6, 2),
        line_of_business="auto_bi",
        parties=[
            Party(party_id="P-insured", role="insured_driver", identity_evidence_cite="DOC-PR-1"),
            Party(party_id="P-claimant", role="claimant_driver", identity_evidence_cite="DOC-PR-1"),
        ],
        fact_pattern="rear_end",
        owner_relationship=OwnerRelationship(
            driver_is_owner=True,
            owner_type="natural_person",
        ),
        negligent_entrustment_indicators=NegligentEntrustment(),
        intoxication_evidence=IntoxicationEvidence(),
        rear_end_rebuttal_evidence=RearEndRebuttal(),
        evidence_items=[
            EvidenceItem(
                kind="police_report_narrative",
                source_doc_id="DOC-PR-1",
                quoted_span="Insured rear-ended claimant at controlled intersection.",
                contemporaneity_hours_from_loss=24,
                fl_admissibility="admissible",
                represented_by_counsel_at_capture=False,
                fault_direction="insured_more_fault",
                weight_class="independent",
            ),
        ],
        police_report_structured_fields=PoliceReportFields(
            officer_narrative_text="Insured rear-ended claimant.",
        ),
    )


# ---------------------------------------------------------------------------
# Tool schema
# ---------------------------------------------------------------------------


def test_tool_schema_has_correct_name():
    s = _liability_inputs_tool_schema()
    assert s["name"] == TOOL_NAME
    assert "input_schema" in s
    assert s["input_schema"]["type"] == "object"


def test_tool_schema_input_matches_liability_inputs():
    s = _liability_inputs_tool_schema()
    assert s["input_schema"] == LiabilityInputs.model_json_schema()


# ---------------------------------------------------------------------------
# Extractor — Anthropic call shape + validation retry
# ---------------------------------------------------------------------------


def test_extractor_emits_correct_anthropic_call_shape():
    valid_payload = _minimal_liability_inputs().model_dump(mode="json")
    client = _StubClient(queued=[valid_payload])

    inputs, model, attempts = extract_liability_inputs(
        _minimal_synthetic_claim(),
        anthropic_client=client,
    )

    assert isinstance(inputs, LiabilityInputs)
    assert attempts == 1
    call = client.messages.calls[0]
    assert call["tool_choice"] == {"type": "tool", "name": TOOL_NAME}
    assert len(call["tools"]) == 1
    assert call["tools"][0]["name"] == TOOL_NAME
    assert "Liability extractor" in call["system"]


def test_extractor_retries_on_validation_failure():
    invalid = {"accrual_date": "not-a-date"}
    valid = _minimal_liability_inputs().model_dump(mode="json")
    client = _StubClient(queued=[invalid, valid])

    inputs, _, attempts = extract_liability_inputs(
        _minimal_synthetic_claim(),
        anthropic_client=client,
        max_retries=1,
    )
    assert attempts == 2
    assert isinstance(inputs, LiabilityInputs)
    assert "PRIOR ATTEMPT REJECTED" in client.messages.calls[1]["system"]


def test_extractor_raises_after_max_retries_exhausted():
    invalid = {"accrual_date": "not-a-date"}
    client = _StubClient(queued=[invalid, invalid])

    with pytest.raises(RuntimeError, match="failed validation after 2 attempts"):
        extract_liability_inputs(
            _minimal_synthetic_claim(),
            anthropic_client=client,
            max_retries=1,
        )


def test_extractor_retries_when_no_tool_use_block():
    valid = _minimal_liability_inputs().model_dump(mode="json")
    client = _StubClient(queued=[None, valid])

    inputs, _, attempts = extract_liability_inputs(
        _minimal_synthetic_claim(),
        anthropic_client=client,
        max_retries=1,
    )
    assert attempts == 2
    assert isinstance(inputs, LiabilityInputs)


# ---------------------------------------------------------------------------
# End-to-end via inputs_override
# ---------------------------------------------------------------------------


def test_run_liability_with_override_skips_llm():
    inputs = _minimal_liability_inputs()
    result = run_liability(
        _minimal_synthetic_claim(),
        inputs_override=inputs,
        reviewed_as_of=datetime(2025, 7, 1, 10, 0, 0, tzinfo=timezone.utc),
        gross_exposure=Decimal("25000"),
    )
    assert result.extractor_attempts == 0
    assert result.extractor_model == "(override — no LLM call)"
    # Assessment composed from calculator + ledger + rationale
    assert "P-insured" in result.assessment.apportionment
    assert result.assessment.applicable_regime.statute == "modified_51_bar_hb837"
    assert result.assessment.rationale_text != ""
    assert "LIABILITY EVALUATION" in result.assessment.rationale_text
    assert "CLM-100" in result.assessment.rationale_text


def test_run_liability_end_to_end_with_stub_llm():
    payload = _minimal_liability_inputs().model_dump(mode="json")
    client = _StubClient(queued=[payload])

    result = run_liability(
        _minimal_synthetic_claim(),
        anthropic_client=client,
        reviewed_as_of=datetime(2025, 7, 1, 10, 0, 0, tzinfo=timezone.utc),
        gross_exposure=Decimal("25000"),
    )
    assert result.extractor_attempts == 1
    assert "LIABILITY EVALUATION" in result.assessment.rationale_text
    assert result.raw_inputs.fact_pattern == "rear_end"
    # Diligence ledger is populated and co-equal
    assert len(result.assessment.diligence_ledger.posture_percent_by_party) >= 2


def test_run_liability_rationale_is_deterministic_with_fixed_inputs():
    inputs = _minimal_liability_inputs()
    fixed_now = datetime(2025, 7, 1, 10, 0, 0, tzinfo=timezone.utc)
    r1 = run_liability(
        _minimal_synthetic_claim(),
        inputs_override=inputs,
        reviewed_as_of=fixed_now,
        gross_exposure=Decimal("25000"),
    )
    r2 = run_liability(
        _minimal_synthetic_claim(),
        inputs_override=inputs,
        reviewed_as_of=fixed_now,
        gross_exposure=Decimal("25000"),
    )
    assert r1.assessment.rationale_text == r2.assessment.rationale_text
    assert r1.assessment.model_dump_json() == r2.assessment.model_dump_json()


# ---------------------------------------------------------------------------
# Runner integration
# ---------------------------------------------------------------------------


def test_runner_registry_has_real_liability():
    """The orchestrator runner must register the real liability function,
    not _stub_workflow('liability')."""
    from argos.services.orchestrator.runner import (
        WORKFLOW_REGISTRY, _run_liability_via_adapter,
    )
    assert WORKFLOW_REGISTRY["liability"] is _run_liability_via_adapter
