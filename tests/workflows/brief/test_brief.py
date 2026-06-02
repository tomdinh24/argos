"""Integration tests for the Brief specialist end-to-end and its
orchestrator registration. No live API."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from argos.ontology.caseload_with_realistic_docs import (
    build_caseload_with_realistic_docs,
)
from argos.services.orchestrator.runner import WorkflowRunner
from argos.workflows.brief.assembler import assemble
from argos.workflows.brief.brief import run_brief
from argos.workflows.brief.gaps import humanize_variable


# Reuse the stub client shape from the other brief tests
@dataclass
class _StubToolBlock:
    type: str
    input: dict[str, Any]


@dataclass
class _StubResponse:
    content: list
    model: str = "claude-sonnet-4-6"


class _StubMessages:
    def __init__(self, queued: list[dict[str, Any]]):
        self.queued = list(queued)

    def create(self, **kwargs):
        return _StubResponse(
            content=[_StubToolBlock(type="tool_use", input=self.queued.pop(0))]
        )


class _StubClient:
    def __init__(self, queued):
        self.messages = _StubMessages(queued)


def _stub_for(caseload, claim_id):
    """Build the two queued outputs (narrative, gaps) for a given claim."""
    draft = assemble(caseload, claim_id)
    doc_id = draft.documents[0].document_id
    return [
        {
            "story_paragraph": f"Synthesized story for {claim_id}.",
            "citations": [{"document_id": doc_id, "text_excerpt": ""}],
        },
        {
            "gaps": [
                {
                    "variable": g.variable,
                    "item": humanize_variable(g.variable),
                    "requested_from": g.requested_from,
                    "why_it_matters": f"Why {g.variable} matters.",
                    "citations": [{"document_id": doc_id, "text_excerpt": ""}],
                }
                for g in draft.raw_gaps
            ]
        },
    ]


# ---------------------------------------------------------------------------
# run_brief end-to-end
# ---------------------------------------------------------------------------


class TestRunBrief:
    def test_assembles_full_claim_brief(self):
        caseload = build_caseload_with_realistic_docs()
        client = _StubClient(_stub_for(caseload, "CLM-007"))

        result = run_brief(caseload, "CLM-007", _client=client)  # type: ignore[arg-type]
        brief = result.brief

        assert brief.claim_id == "CLM-007"
        assert brief.story_paragraph.startswith("Synthesized")
        assert len(brief.story_citations) >= 1
        # missing_info derived from raw_gaps
        assert len(brief.missing_info) == len(
            assemble(caseload, "CLM-007").raw_gaps
        )
        # The defaults we wired in
        assert brief.since_last_touch.last_touch_at is None
        assert brief.pending_communications == []

    def test_runs_when_no_specialist_results_present(self, tmp_path: Path):
        caseload = build_caseload_with_realistic_docs()
        client = _StubClient(_stub_for(caseload, "CLM-007"))
        result = run_brief(
            caseload, "CLM-007", results_root=tmp_path, _client=client
        )  # type: ignore[arg-type]
        # No coverage.json on disk → recommendations empty
        assert result.brief.workflow_recommendations_summary == []


# ---------------------------------------------------------------------------
# Orchestrator runner picks up Brief from the default registry
# ---------------------------------------------------------------------------


class TestBriefRegisteredInRunner:
    def test_runner_default_registry_includes_brief(self, tmp_path: Path):
        from argos.services.orchestrator.queue import JobQueue

        caseload = build_caseload_with_realistic_docs()
        runner = WorkflowRunner(
            queue=JobQueue(),
            caseload=caseload,
            results_root=tmp_path,
        )
        assert "brief" in runner.registry

    def test_dispatcher_does_not_route_to_brief(self):
        """Brief is not posture-triggered. Dispatcher mapping must not
        include it."""
        from argos.services.orchestrator.dispatcher import POSTURE_TO_WORKFLOWS
        for postures in POSTURE_TO_WORKFLOWS.values():
            assert "brief" not in postures
