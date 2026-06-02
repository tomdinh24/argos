"""Tests for the Brief narrative LLM call — no live API.

Stubs the Anthropic client to exercise the retry + validation paths.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from argos.ontology.caseload_with_realistic_docs import (
    build_caseload_with_realistic_docs,
)
from argos.workflows.brief.assembler import assemble
from argos.workflows.brief.narrative import (
    _NarrativeOutput,
    _render_user_body,
    run_narrative,
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
    def __init__(self, queued_tool_inputs: list[dict[str, Any] | None]):
        self.queued = list(queued_tool_inputs)
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if not self.queued:
            raise AssertionError("No more queued tool inputs")
        tool_input = self.queued.pop(0)
        if tool_input is None:
            return _StubResponse(content=[])  # no tool_use → triggers retry
        return _StubResponse(
            content=[_StubToolBlock(type="tool_use", input=tool_input)]
        )


class _StubClient:
    def __init__(self, queued_tool_inputs: list[dict[str, Any] | None]):
        self.messages = _StubMessages(queued_tool_inputs)


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


class TestRenderUserBody:
    def test_includes_loss_facts_hint_and_documents(self):
        caseload = build_caseload_with_realistic_docs()
        draft = assemble(caseload, "CLM-007")
        body = _render_user_body(draft)
        assert "LOSS FACTS HINT" in body
        assert "DOCUMENTS ON FILE" in body
        for d in draft.documents:
            assert d.document_id in body
            assert d.body_text in body

    def test_handles_claim_with_no_documents(self):
        caseload = build_caseload_with_realistic_docs()
        # Find a claim with no docs in the extended fixture
        no_doc_claim = next(
            c for c in caseload.claims
            if not any(d.claim_id == c.claim_id for d in caseload.documents)
        )
        draft = assemble(caseload, no_doc_claim.claim_id)
        body = _render_user_body(draft)
        assert "(none)" in body


# ---------------------------------------------------------------------------
# Output schema
# ---------------------------------------------------------------------------


class TestNarrativeOutputSchema:
    def test_requires_at_least_one_citation(self):
        with pytest.raises(Exception):
            _NarrativeOutput.model_validate({
                "story_paragraph": "x",
                "citations": [],
            })

    def test_requires_nonempty_story(self):
        with pytest.raises(Exception):
            _NarrativeOutput.model_validate({
                "story_paragraph": "",
                "citations": [{"document_id": "d1", "text_excerpt": "q"}],
            })


# ---------------------------------------------------------------------------
# run_narrative — happy path + retry paths
# ---------------------------------------------------------------------------


class TestRunNarrative:
    def test_happy_path_returns_citations(self):
        caseload = build_caseload_with_realistic_docs()
        draft = assemble(caseload, "CLM-007")
        doc_id = draft.documents[0].document_id
        excerpt = draft.documents[0].body_text[:40]

        client = _StubClient([{
            "story_paragraph": "Catastrophic auto BI claim opened 2026-05-30. Plaintiff is represented.",
            "citations": [{"document_id": doc_id, "text_excerpt": excerpt}],
        }])

        result = run_narrative(draft, _client=client)  # type: ignore[arg-type]
        assert result.attempts == 1
        assert result.story_paragraph.startswith("Catastrophic")
        assert len(result.story_citations) == 1
        assert result.story_citations[0].document_id == doc_id
        assert result.story_citations[0].relation == "supports"
        assert result.story_citations[0].locator == "body"

    def test_retry_on_unknown_document_id(self):
        caseload = build_caseload_with_realistic_docs()
        draft = assemble(caseload, "CLM-007")
        good_doc = draft.documents[0].document_id

        # First call cites a nonexistent doc, second cites a valid one
        client = _StubClient([
            {
                "story_paragraph": "First try.",
                "citations": [{"document_id": "DOC-NONEXIST", "text_excerpt": "x"}],
            },
            {
                "story_paragraph": "Second try with real cite.",
                "citations": [{"document_id": good_doc, "text_excerpt": "x"}],
            },
        ])

        result = run_narrative(draft, _client=client)  # type: ignore[arg-type]
        assert result.attempts == 2
        assert result.story_citations[0].document_id == good_doc

    def test_retry_on_missing_tool_use(self):
        caseload = build_caseload_with_realistic_docs()
        draft = assemble(caseload, "CLM-007")
        good_doc = draft.documents[0].document_id

        client = _StubClient([
            None,  # no tool_use block — triggers retry
            {
                "story_paragraph": "Recovered.",
                "citations": [{"document_id": good_doc, "text_excerpt": "x"}],
            },
        ])

        result = run_narrative(draft, _client=client)  # type: ignore[arg-type]
        assert result.attempts == 2

    def test_raises_after_exhausting_retries(self):
        caseload = build_caseload_with_realistic_docs()
        draft = assemble(caseload, "CLM-007")

        # Both attempts return invalid schema
        client = _StubClient([
            {"story_paragraph": "", "citations": []},
            {"story_paragraph": "", "citations": []},
        ])

        with pytest.raises(RuntimeError, match="failed after"):
            run_narrative(draft, _client=client)  # type: ignore[arg-type]
