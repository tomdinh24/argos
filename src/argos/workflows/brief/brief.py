"""Brief specialist entry-point: assemble → narrative → gaps → ClaimBrief.

`run_brief` is the public surface. Callers (the orchestrator runner, a
script, or a future UI handler) pass a `Caseload` + claim_id; this
module orchestrates the read-only assembler and the two LLM calls and
returns a fully-populated `ClaimBrief`.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from anthropic import Anthropic

from argos.ontology.types import Caseload
from argos.schemas.workflows.brief import ClaimBrief
from argos.workflows.brief.assembler import assemble
from argos.workflows.brief.gaps import run_gaps
from argos.workflows.brief.narrative import run_narrative


@dataclass
class BriefResult:
    """What `run_brief` returns: validated ClaimBrief plus run metadata."""

    brief: ClaimBrief
    narrative_attempts: int
    gaps_attempts: int
    narrative_raw: dict[str, Any]
    gaps_raw: dict[str, Any]


def run_brief(
    caseload: Caseload,
    claim_id: str,
    *,
    results_root: Path | None = None,
    _client: Anthropic | None = None,
) -> BriefResult:
    """Build a `ClaimBrief` for `claim_id` end-to-end.

    Side-effect-free: reads `caseload` + optional `results_root`,
    makes two LLM calls (narrative + gaps), returns the assembled
    brief. Persistence is the caller's responsibility (the
    orchestrator runner writes the JSON to disk).
    """
    draft = assemble(caseload, claim_id, results_root=results_root)

    narrative = run_narrative(draft, _client=_client)
    gaps = run_gaps(draft, _client=_client)

    brief = ClaimBrief(
        request_id=draft.request_id,
        claim_id=draft.claim_id,
        generated_at=draft.generated_at,
        story_paragraph=narrative.story_paragraph,
        story_citations=narrative.story_citations,
        since_last_touch=draft.since_last_touch,
        current_status_snapshot=draft.status_snapshot,
        financial_snapshot=draft.financial_snapshot,
        workflow_recommendations_summary=draft.workflow_recommendations,
        missing_info=gaps.missing_info,
        pending_communications=[],
    )

    return BriefResult(
        brief=brief,
        narrative_attempts=narrative.attempts,
        gaps_attempts=gaps.attempts,
        narrative_raw=narrative.raw_tool_input,
        gaps_raw=gaps.raw_tool_input,
    )
