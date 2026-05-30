"""Coverage specialist output schema.

The Coverage specialist reads the policy structure, loss facts, and documentary
evidence; surfaces evidence and probabilities; and drafts the analysis memo,
the ROR letter, and the denial letter. It does *not* recommend a path. The
adjuster picks the path with the full distribution and evidence in front of
them.

Source of truth: AGENT_ARCHITECTURE.md §7.4.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from argos.schemas.legally_bearing import (
    EvidenceCitation,
    OutcomePathDistribution,
    ProbabilisticClaim,
)


class CoverageDraft(BaseModel):
    """One of the three drafted artifacts: memo, ROR letter, or denial letter.

    The cockpit attaches the chosen draft to the file when the adjuster picks a
    path. The other two stay linked to the AgentAction as audit history — the
    cost of being able to pivot instantly if the human had chosen differently.
    """

    body: str
    citations: list[EvidenceCitation] = Field(min_length=1)


class CoverageAnalysis(BaseModel):
    """Coverage specialist's complete output for one exposure.

    There is no `recommended_path` field. By design. The schema is enforced;
    a future change that tries to add one fails the §7.4 contract.
    """

    exposure_id: str
    reviewed_as_of: datetime

    evidence_found: list[EvidenceCitation] = Field(
        min_length=1,
        description="Layer 1 of the cockpit data: everything the AI read",
    )

    per_question_probabilities: list[ProbabilisticClaim] = Field(
        min_length=1,
        description="Layer 2: each underlying question with its probability and citations",
    )

    outcome_path_distribution: OutcomePathDistribution = Field(
        description=(
            "Layer 3: distribution over {clean coverage, ROR, denial}. "
            "Probabilities sum to 1.0."
        ),
    )

    coverage_analysis_memo: CoverageDraft
    ror_letter: CoverageDraft | None = Field(
        default=None,
        description="Drafted when the ROR path carries non-trivial probability",
    )
    denial_letter: CoverageDraft | None = Field(
        default=None,
        description="Drafted when the denial path carries non-trivial probability",
    )
