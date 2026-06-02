"""Tests for the Brief gap-rationale LLM call — no live API."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from argos.ontology.caseload_with_realistic_docs import (
    build_caseload_with_realistic_docs,
)
from argos.workflows.brief.assembler import assemble
from argos.workflows.brief.gaps import (
    _render_user_body,
    humanize_variable,
    run_gaps,
)


# ---------------------------------------------------------------------------
# Stub Anthropic client (same shape as test_narrative)
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
        tool_input = self.queued.pop(0)
        if tool_input is None:
            return _StubResponse(content=[])
        return _StubResponse(
            content=[_StubToolBlock(type="tool_use", input=tool_input)]
        )


class _StubClient:
    def __init__(self, queued: list[dict[str, Any] | None]):
        self.messages = _StubMessages(queued)


def _build_stub_output(draft, excerpt_for: dict[str, str] | None = None) -> dict:
    """Helper: build a valid stub output that emits every input variable."""
    excerpts = excerpt_for or {}
    return {
        "gaps": [
            {
                "variable": g.variable,
                "item": humanize_variable(g.variable),
                "requested_from": g.requested_from,
                "why_it_matters": f"Stub rationale for {g.variable}.",
                "citations": [
                    {
                        "document_id": draft.documents[0].document_id,
                        "text_excerpt": excerpts.get(g.variable, ""),
                    }
                ],
            }
            for g in draft.raw_gaps
        ]
    }


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


class TestRenderUserBody:
    def test_includes_gaps_and_doc_excerpts(self):
        caseload = build_caseload_with_realistic_docs()
        draft = assemble(caseload, "CLM-007")
        body = _render_user_body(draft)
        assert "GAPS TO RATIONALIZE" in body
        assert "DOCUMENTS ON FILE" in body
        for g in draft.raw_gaps:
            assert g.variable in body

    def test_truncates_long_doc_bodies(self):
        caseload = build_caseload_with_realistic_docs()
        draft = assemble(caseload, "CLM-007")
        body = _render_user_body(draft)
        # If any doc body in the fixture is > 600 chars, the truncated marker appears
        if any(len(d.body_text) > 600 for d in draft.documents):
            assert "[truncated]" in body


# ---------------------------------------------------------------------------
# Skip paths (no LLM call when nothing to do)
# ---------------------------------------------------------------------------


class TestRunGapsSkipPaths:
    def test_returns_empty_when_no_raw_gaps(self):
        caseload = build_caseload_with_realistic_docs()
        draft = assemble(caseload, "CLM-007")
        draft.raw_gaps = []  # force empty
        result = run_gaps(draft)
        assert result.missing_info == []
        assert result.attempts == 0

    def test_returns_empty_when_no_documents_on_file(self):
        caseload = build_caseload_with_realistic_docs()
        # Find a claim with no docs
        no_doc_claim = next(
            c for c in caseload.claims
            if not any(d.claim_id == c.claim_id for d in caseload.documents)
        )
        draft = assemble(caseload, no_doc_claim.claim_id)
        result = run_gaps(draft)
        assert result.missing_info == []
        assert result.attempts == 0


# ---------------------------------------------------------------------------
# run_gaps — happy path + retry paths
# ---------------------------------------------------------------------------


class TestRunGaps:
    def test_happy_path_returns_one_item_per_gap(self):
        caseload = build_caseload_with_realistic_docs()
        draft = assemble(caseload, "CLM-007")
        client = _StubClient([_build_stub_output(draft)])

        result = run_gaps(draft, _client=client)  # type: ignore[arg-type]
        assert result.attempts == 1
        assert len(result.missing_info) == len(draft.raw_gaps)
        for item in result.missing_info:
            assert item.correspondence_status == "not_yet_drafted"
            assert len(item.evidence_citations) >= 1

    def test_empty_excerpt_yields_contextual_relation(self):
        caseload = build_caseload_with_realistic_docs()
        draft = assemble(caseload, "CLM-007")
        client = _StubClient([_build_stub_output(draft)])  # excerpts default to ""
        result = run_gaps(draft, _client=client)  # type: ignore[arg-type]
        # No excerpts → all citations should be "contextual"
        for item in result.missing_info:
            for c in item.evidence_citations:
                assert c.relation == "contextual"

    def test_nonempty_excerpt_yields_supports_relation(self):
        caseload = build_caseload_with_realistic_docs()
        draft = assemble(caseload, "CLM-007")
        excerpts = {g.variable: "verbatim quote" for g in draft.raw_gaps}
        client = _StubClient([_build_stub_output(draft, excerpts)])
        result = run_gaps(draft, _client=client)  # type: ignore[arg-type]
        for item in result.missing_info:
            for c in item.evidence_citations:
                assert c.relation == "supports"

    def test_retry_when_emitted_variables_mismatch_input(self):
        caseload = build_caseload_with_realistic_docs()
        draft = assemble(caseload, "CLM-007")

        # First attempt drops a variable; second is correct
        bad_output = _build_stub_output(draft)
        bad_output["gaps"] = bad_output["gaps"][:-1]  # drop last gap

        client = _StubClient([bad_output, _build_stub_output(draft)])
        result = run_gaps(draft, _client=client)  # type: ignore[arg-type]
        assert result.attempts == 2
        assert len(result.missing_info) == len(draft.raw_gaps)

    def test_retry_on_unknown_doc_id_in_citation(self):
        caseload = build_caseload_with_realistic_docs()
        draft = assemble(caseload, "CLM-007")

        bad_output = _build_stub_output(draft)
        bad_output["gaps"][0]["citations"][0]["document_id"] = "DOC-NONEXIST"

        client = _StubClient([bad_output, _build_stub_output(draft)])
        result = run_gaps(draft, _client=client)  # type: ignore[arg-type]
        assert result.attempts == 2

    def test_raises_after_exhausting_retries(self):
        caseload = build_caseload_with_realistic_docs()
        draft = assemble(caseload, "CLM-007")

        bad = _build_stub_output(draft)
        bad["gaps"] = []  # variables won't match
        client = _StubClient([bad, bad])

        with pytest.raises(RuntimeError, match="failed after"):
            run_gaps(draft, _client=client)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Pure helper
# ---------------------------------------------------------------------------


class TestHumanizeVariable:
    def test_replaces_underscores_and_capitalizes(self):
        assert humanize_variable("policy_declarations") == "Policy declarations"
        assert humanize_variable("iso_claim_search") == "Iso claim search"
