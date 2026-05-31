"""Checks drafted prose for path-recommendation language.

The schema enforces no `recommended_*` field, but the drafted memo and letter
bodies are free text. A model could slip "we recommend ROR" or "the carrier
should issue a denial" into the prose and the schema would accept it. This
check pattern-matches a curated list of recommendation phrases against every
drafted body and flags any hit.

The patterns are deliberately conservative — they look for active
prescription, not analytical description. "The ROR path is supported by X" is
fine; "We recommend the ROR path" is not.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from argos.schemas.specialists.coverage import CoverageReport


# Each pattern is anchored on a verb or phrase that PRESCRIBES a path.
# Phrases like "the file supports", "the analysis indicates", "evidence shows"
# are NOT recommendation — they're analytical description, which the
# specialist is allowed and expected to produce.
RECOMMENDATION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("we recommend",          re.compile(r"\bwe\s+recommend\b", re.I)),
    ("we advise",             re.compile(r"\bwe\s+advise\b", re.I)),
    ("the carrier should",    re.compile(r"\bthe\s+carrier\s+(?:should|must|ought\s+to)\b", re.I)),
    ("our recommendation",    re.compile(r"\bour\s+recommendation\b", re.I)),
    ("our position is",       re.compile(r"\bour\s+position\s+is\b", re.I)),
    ("we propose",            re.compile(r"\bwe\s+propose\b", re.I)),
    ("we suggest",            re.compile(r"\bwe\s+suggest\b", re.I)),
    ("recommended path",      re.compile(r"\brecommended\s+(?:path|course|action|outcome)\b", re.I)),
    ("you should",            re.compile(r"\byou\s+should\b", re.I)),
    ("the file should",       re.compile(r"\bthe\s+(?:file|claim|exposure)\s+should\b", re.I)),
    ("carrier is advised",    re.compile(r"\bcarrier\s+is\s+advised\b", re.I)),
    ("Argos recommends",      re.compile(r"\bargos\s+recommends\b", re.I)),
)


@dataclass
class RecommendationHit:
    """One pattern-match against drafted prose."""

    where: str           # "coverage_analysis_memo" | "ror_letter" | "denial_letter"
    pattern_label: str   # the human-readable label of the matched pattern
    matched_text: str    # the literal text the pattern matched
    surrounding: str     # ±60 chars of context for review


@dataclass
class RecommendationRegexResult:
    """Aggregate result."""

    drafts_checked: int = 0
    hits: list[RecommendationHit] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.hits

    @property
    def summary(self) -> str:
        if self.passed:
            return f"PASS — {self.drafts_checked} draft(s), no recommendation prose"
        return (
            f"FAIL — {len(self.hits)} recommendation phrase(s) detected "
            f"across {self.drafts_checked} draft(s)"
        )


def _scan(body: str, where: str) -> list[RecommendationHit]:
    hits: list[RecommendationHit] = []
    for label, pat in RECOMMENDATION_PATTERNS:
        for m in pat.finditer(body):
            start = max(0, m.start() - 60)
            end = min(len(body), m.end() + 60)
            surrounding = body[start:end].replace("\n", " ")
            hits.append(
                RecommendationHit(
                    where=where,
                    pattern_label=label,
                    matched_text=m.group(0),
                    surrounding=f"…{surrounding}…",
                )
            )
    return hits


def check_recommendation_prose(analysis: CoverageReport) -> RecommendationRegexResult:
    """Scan memo + ROR letter + denial letter bodies for recommendation language."""
    result = RecommendationRegexResult()
    result.drafts_checked = 1
    result.hits.extend(_scan(analysis.coverage_analysis_memo.body, "coverage_analysis_memo"))
    if analysis.ror_letter is not None:
        result.drafts_checked += 1
        result.hits.extend(_scan(analysis.ror_letter.body, "ror_letter"))
    if analysis.denial_letter is not None:
        result.drafts_checked += 1
        result.hits.extend(_scan(analysis.denial_letter.body, "denial_letter"))
    return result
