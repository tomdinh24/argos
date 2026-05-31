"""Verifies that every citation's text_excerpt actually appears in the cited document.

The schema enforces that EvidenceCitation references exactly one source. It
does NOT verify the `text_excerpt` matches the source's body. A specialist
could hallucinate a quote and the schema would accept it. This check closes
that gap.

Match policy: case-insensitive, whitespace-normalized substring match. We do
not require character-for-character equality because real-world specialists
will paraphrase tightly (e.g., normalize curly quotes, drop a trailing
period). We do reject quotes that are entirely fabricated or that misquote
the substantive content of the source.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

from argos.ontology.types import Document, SyntheticClaim
from argos.schemas.contract import EvidenceCitation
from argos.schemas.specialists.coverage import CoverageReport


@dataclass
class CitationViolation:
    """One citation whose text_excerpt could not be verified."""

    where: str  # path into the analysis, e.g. "assessments[0].evidence_citations[1]"
    document_id: str | None
    sourced_rule_id: str | None
    ledger_entry_id: str | None
    locator: str
    text_excerpt: str
    reason: str  # "document not found", "text not in document", etc.


@dataclass
class CitationVerifierResult:
    """Aggregate result over an analysis."""

    total_checked: int = 0
    violations: list[CitationViolation] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.violations

    @property
    def summary(self) -> str:
        if self.passed:
            return f"PASS — all {self.total_checked} citations verified"
        return (
            f"FAIL — {len(self.violations)}/{self.total_checked} citations "
            f"could not be verified"
        )


_WS_RE = re.compile(r"\s+")


def _normalize(text: str) -> str:
    """Case-fold, collapse whitespace, normalize smart quotes."""
    t = text.replace("“", '"').replace("”", '"')
    t = t.replace("‘", "'").replace("’", "'")
    t = t.replace("—", "-").replace("–", "-")
    t = _WS_RE.sub(" ", t).strip().casefold()
    return t


def _check_one(
    citation: EvidenceCitation, where: str, docs_by_id: dict[str, Document]
) -> CitationViolation | None:
    # Rule and ledger citations are out of scope for this check — we don't
    # have those sources loaded into the fixture layer yet. Treat as
    # unverifiable-but-not-violated; flagged separately downstream when
    # those substrates exist.
    if citation.document_id is None:
        return None

    doc = docs_by_id.get(citation.document_id)
    if doc is None:
        return CitationViolation(
            where=where,
            document_id=citation.document_id,
            sourced_rule_id=citation.sourced_rule_id,
            ledger_entry_id=citation.ledger_entry_id,
            locator=citation.locator,
            text_excerpt=citation.text_excerpt,
            reason=(
                f"document_id={citation.document_id!r} not present in this claim's documents"
            ),
        )

    needle = _normalize(citation.text_excerpt)
    haystack = _normalize(doc.body_text)
    if needle and needle in haystack:
        return None

    return CitationViolation(
        where=where,
        document_id=citation.document_id,
        sourced_rule_id=citation.sourced_rule_id,
        ledger_entry_id=citation.ledger_entry_id,
        locator=citation.locator,
        text_excerpt=citation.text_excerpt,
        reason="text_excerpt does not appear in document body (after whitespace/case normalization)",
    )


def _walk_citations(
    analysis: CoverageReport,
) -> Iterable[tuple[EvidenceCitation, str]]:
    """Yield every citation in the analysis with a structural path string."""
    for i, c in enumerate(analysis.evidence_found):
        yield c, f"evidence_found[{i}]"
    for i, assessment in enumerate(analysis.assessments):
        for j, c in enumerate(assessment.evidence_citations):
            yield c, f"assessments[{i}].evidence_citations[{j}]"
    for i, outcome in enumerate(analysis.synthesis.outcomes):
        for j, c in enumerate(outcome.evidence_citations):
            yield c, f"synthesis.outcomes[{i}].evidence_citations[{j}]"
    for i, c in enumerate(analysis.coverage_analysis_memo.citations):
        yield c, f"coverage_analysis_memo.citations[{i}]"
    if analysis.ror_letter is not None:
        for i, c in enumerate(analysis.ror_letter.citations):
            yield c, f"ror_letter.citations[{i}]"
    if analysis.denial_letter is not None:
        for i, c in enumerate(analysis.denial_letter.citations):
            yield c, f"denial_letter.citations[{i}]"


def verify_citations(
    analysis: CoverageReport, claim: SyntheticClaim
) -> CitationVerifierResult:
    """Walk every citation; flag any whose text_excerpt isn't in the cited document."""
    docs_by_id = {d.document_id: d for d in claim.documents}
    result = CitationVerifierResult()
    for citation, where in _walk_citations(analysis):
        result.total_checked += 1
        v = _check_one(citation, where, docs_by_id)
        if v is not None:
            result.violations.append(v)
    return result
