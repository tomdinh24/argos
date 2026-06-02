"""Tests for the Intake Reader specialist.

No live API calls — those go in scripts. These tests cover:

- IntakeExtraction schema invariants (severity_evidence required;
  flag-evidence pairs agree True↔non-empty, False↔empty).
- Runtime parses a well-formed tool_use response into a result.
- Runtime retries once on Pydantic validation failure with the
  error fed back as a corrective system note.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest
from pydantic import ValidationError

from argos.schemas.workflows.intake_reader import IntakeExtraction
from argos.workflows.intake_reader import (
    TOOL_NAME,
    _render_user_body,
    _tool_schema,
    run_intake_reader,
)


# ---------------------------------------------------------------------------
# Schema invariants
# ---------------------------------------------------------------------------


_VALID_PAYLOAD: dict[str, Any] = {
    "loss_date": "2026-04-12",
    "loss_location": "I-95 mile 41",
    "loss_summary": "Rear-end collision with fatality.",
    "severity_tier": "catastrophic",
    "severity_evidence": "Pronounced dead at the scene",
    "litigation_flag": False,
    "litigation_evidence": "",
    "rep_flag": True,
    "rep_evidence": "retained Morgan & Morgan",
    "complaint_flag": False,
    "complaint_evidence": "",
}


def _payload(**overrides: Any) -> dict[str, Any]:
    return {**_VALID_PAYLOAD, **overrides}


class TestIntakeExtractionSchema:
    def test_minimal_valid_payload_parses(self):
        ext = IntakeExtraction.model_validate(_payload())
        assert ext.severity_tier == "catastrophic"
        assert ext.rep_flag is True
        assert ext.litigation_flag is False

    def test_severity_evidence_required_nonempty(self):
        with pytest.raises(ValidationError, match="severity_evidence"):
            IntakeExtraction.model_validate(_payload(severity_evidence=""))

    def test_true_flag_requires_evidence(self):
        with pytest.raises(ValidationError, match="litigation_evidence"):
            IntakeExtraction.model_validate(
                _payload(litigation_flag=True, litigation_evidence="")
            )

    def test_false_flag_forbids_evidence(self):
        with pytest.raises(ValidationError, match="rep_evidence"):
            IntakeExtraction.model_validate(
                _payload(rep_flag=False, rep_evidence="oops"),
            )

    def test_all_flags_can_be_true_with_evidence(self):
        ext = IntakeExtraction.model_validate(
            _payload(
                litigation_flag=True,
                litigation_evidence="filing suit",
                rep_flag=True,
                rep_evidence="retained Morgan & Morgan",
                complaint_flag=True,
                complaint_evidence="filed complaint with FL DOI",
            )
        )
        assert ext.litigation_flag and ext.rep_flag and ext.complaint_flag

    def test_loss_summary_length_capped(self):
        with pytest.raises(ValidationError):
            IntakeExtraction.model_validate(
                _payload(loss_summary="x" * 601),
            )

    def test_severity_tier_enum_enforced(self):
        with pytest.raises(ValidationError):
            IntakeExtraction.model_validate(_payload(severity_tier="urgent"))

    def test_optional_identity_fields_default_to_none(self):
        ext = IntakeExtraction.model_validate(_payload())
        assert ext.policy_number is None
        assert ext.insured_name is None
        assert ext.claimant_name is None

    def test_optional_identity_fields_accept_values(self):
        ext = IntakeExtraction.model_validate(
            _payload(
                policy_number="PL-001234",
                insured_name="Jane Insured",
                claimant_name="John Claimant",
            )
        )
        assert ext.policy_number == "PL-001234"
        assert ext.insured_name == "Jane Insured"
        assert ext.claimant_name == "John Claimant"


# ---------------------------------------------------------------------------
# User-body rendering + tool schema
# ---------------------------------------------------------------------------


class TestPromptRendering:
    def test_user_body_includes_fnol_bundle_section(self):
        body = _render_user_body("Caller reports collision at I-95.")
        assert "=== FNOL BUNDLE ===" in body
        assert "Caller reports collision" in body

    def test_tool_schema_uses_extraction_model(self):
        tool = _tool_schema()
        assert tool["name"] == TOOL_NAME
        assert "input_schema" in tool
        assert "properties" in tool["input_schema"]
        assert "severity_tier" in tool["input_schema"]["properties"]


# ---------------------------------------------------------------------------
# Runtime (stub client, no API calls)
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
    def __init__(self, queued_inputs: list[dict[str, Any]]):
        self.queued = list(queued_inputs)
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        inp = self.queued.pop(0)
        return _StubResponse(content=[_StubToolBlock(type="tool_use", input=inp)])


class _StubClient:
    def __init__(self, queued_inputs: list[dict[str, Any]]):
        self.messages = _StubMessages(queued_inputs)


class TestRunIntakeReader:
    def test_returns_validated_extraction(self):
        client = _StubClient([_VALID_PAYLOAD])
        result = run_intake_reader(
            "Caller reports collision at I-95 mile 41.",
            _client=client,  # type: ignore[arg-type]
        )
        assert result.extraction.severity_tier == "catastrophic"
        assert result.extraction.rep_flag is True
        assert result.attempts == 1
        assert result.model == "claude-sonnet-4-6"

    def test_retries_on_validation_failure_and_succeeds(self):
        """First call returns invalid payload; second call returns valid.
        The retry should pass and surface attempts=2."""
        invalid = {**_VALID_PAYLOAD, "severity_evidence": ""}  # invalid
        client = _StubClient([invalid, _VALID_PAYLOAD])

        result = run_intake_reader("bundle", _client=client)  # type: ignore[arg-type]
        assert result.attempts == 2
        # Second call's system text should include the prior error
        second_system = client.messages.calls[1]["system"]
        assert "PRIOR ATTEMPT REJECTED" in second_system
        assert "severity_evidence" in second_system

    def test_raises_when_all_retries_exhausted(self):
        invalid = {**_VALID_PAYLOAD, "severity_evidence": ""}
        client = _StubClient([invalid, invalid])
        with pytest.raises(RuntimeError, match="after 2 attempts"):
            run_intake_reader("bundle", _client=client)  # type: ignore[arg-type]

    def test_raises_when_model_emits_no_tool_block(self):
        @dataclass
        class _NonToolBlock:
            type: str = "text"

        class _NoToolMessages:
            def create(self, **kwargs):
                return _StubResponse(content=[_NonToolBlock()])

        class _NoToolClient:
            messages = _NoToolMessages()

        with pytest.raises(RuntimeError, match="tool_use"):
            run_intake_reader(
                "bundle",
                max_retries=0,
                _client=_NoToolClient(),  # type: ignore[arg-type]
            )
