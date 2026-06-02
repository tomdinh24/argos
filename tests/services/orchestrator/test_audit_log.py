"""AgentAction audit log — append/load/lookup tests."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from argos.services.orchestrator.audit_log import (
    ANALYSIS_EMITTED,
    VALIDATOR_FAIL,
    append_agent_action,
    build_agent_action,
    count_workflow_actions,
    has_workflow_evidence,
    load_agent_actions,
)


def _build(claim_id: str, workflow: str, action_type: str = ANALYSIS_EMITTED):
    return build_agent_action(
        claim_id=claim_id,
        workflow=workflow,
        action_type=action_type,
        summary=f"{workflow} ran on {claim_id}",
        timestamp=datetime(2026, 6, 2, 10, 0, 0, tzinfo=timezone.utc),
    )


def test_append_creates_log_dir_and_file(tmp_path: Path):
    log_root = tmp_path / "agent-actions"
    assert not log_root.exists()
    path = append_agent_action(_build("CLM-1", "coverage"), log_root=log_root)
    assert log_root.exists()
    assert path == log_root / "CLM-1.jsonl"
    assert path.exists()


def test_load_returns_empty_when_no_file(tmp_path: Path):
    assert load_agent_actions("CLM-MISSING", log_root=tmp_path) == []


def test_append_then_load_roundtrip(tmp_path: Path):
    a = _build("CLM-1", "coverage")
    append_agent_action(a, log_root=tmp_path)
    rows = load_agent_actions("CLM-1", log_root=tmp_path)
    assert len(rows) == 1
    assert rows[0].action_id == a.action_id
    assert rows[0].workflow == "coverage"
    assert rows[0].action_type == ANALYSIS_EMITTED


def test_append_preserves_order(tmp_path: Path):
    append_agent_action(_build("CLM-1", "coverage"), log_root=tmp_path)
    append_agent_action(_build("CLM-1", "liability"), log_root=tmp_path)
    append_agent_action(_build("CLM-1", "reserve"), log_root=tmp_path)
    rows = load_agent_actions("CLM-1", log_root=tmp_path)
    assert [r.workflow for r in rows] == ["coverage", "liability", "reserve"]


def test_append_is_append_only(tmp_path: Path):
    """A second append on the same claim does not overwrite the first."""
    a1 = _build("CLM-1", "coverage")
    a2 = _build("CLM-1", "coverage")
    append_agent_action(a1, log_root=tmp_path)
    append_agent_action(a2, log_root=tmp_path)
    rows = load_agent_actions("CLM-1", log_root=tmp_path)
    assert len(rows) == 2
    assert {r.action_id for r in rows} == {a1.action_id, a2.action_id}


def test_load_skips_malformed_lines(tmp_path: Path):
    """One bad line should not block reading the rest of the log."""
    log = tmp_path / "CLM-1.jsonl"
    append_agent_action(_build("CLM-1", "coverage"), log_root=tmp_path)
    with log.open("a", encoding="utf-8") as f:
        f.write("{garbage not valid json\n")
        f.write("\n")  # blank line
    append_agent_action(_build("CLM-1", "liability"), log_root=tmp_path)
    rows = load_agent_actions("CLM-1", log_root=tmp_path)
    assert [r.workflow for r in rows] == ["coverage", "liability"]


def test_count_workflow_actions(tmp_path: Path):
    append_agent_action(_build("CLM-1", "coverage"), log_root=tmp_path)
    append_agent_action(
        _build("CLM-1", "coverage", VALIDATOR_FAIL), log_root=tmp_path,
    )
    append_agent_action(_build("CLM-1", "liability"), log_root=tmp_path)
    assert count_workflow_actions("CLM-1", "coverage", log_root=tmp_path) == 2
    assert count_workflow_actions(
        "CLM-1", "coverage", log_root=tmp_path, action_type=ANALYSIS_EMITTED,
    ) == 1
    assert count_workflow_actions(
        "CLM-1", "coverage", log_root=tmp_path, action_type=VALIDATOR_FAIL,
    ) == 1
    assert count_workflow_actions("CLM-1", "missing", log_root=tmp_path) == 0


def test_has_workflow_evidence_true_when_every_workflow_emitted(tmp_path: Path):
    append_agent_action(_build("CLM-1", "coverage"), log_root=tmp_path)
    append_agent_action(_build("CLM-1", "liability"), log_root=tmp_path)
    append_agent_action(_build("CLM-1", "reserve"), log_root=tmp_path)
    append_agent_action(_build("CLM-1", "recovery"), log_root=tmp_path)
    assert has_workflow_evidence(
        "CLM-1",
        ["coverage", "liability", "reserve", "recovery"],
        log_root=tmp_path,
    )


def test_has_workflow_evidence_false_when_one_missing(tmp_path: Path):
    append_agent_action(_build("CLM-1", "coverage"), log_root=tmp_path)
    append_agent_action(_build("CLM-1", "liability"), log_root=tmp_path)
    assert not has_workflow_evidence(
        "CLM-1",
        ["coverage", "liability", "reserve"],
        log_root=tmp_path,
    )


def test_has_workflow_evidence_ignores_validator_fail_rows(tmp_path: Path):
    """A workflow that only failed validation does NOT count as emitted."""
    append_agent_action(_build("CLM-1", "coverage"), log_root=tmp_path)
    append_agent_action(
        _build("CLM-1", "liability", VALIDATOR_FAIL), log_root=tmp_path,
    )
    assert not has_workflow_evidence(
        "CLM-1", ["coverage", "liability"], log_root=tmp_path,
    )


def test_per_claim_isolation(tmp_path: Path):
    append_agent_action(_build("CLM-1", "coverage"), log_root=tmp_path)
    append_agent_action(_build("CLM-2", "coverage"), log_root=tmp_path)
    rows_1 = load_agent_actions("CLM-1", log_root=tmp_path)
    rows_2 = load_agent_actions("CLM-2", log_root=tmp_path)
    assert len(rows_1) == 1
    assert len(rows_2) == 1
    assert rows_1[0].claim_id == "CLM-1"
    assert rows_2[0].claim_id == "CLM-2"
