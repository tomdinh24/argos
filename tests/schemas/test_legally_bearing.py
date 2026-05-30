from __future__ import annotations

import pytest
from pydantic import ValidationError

from argos.schemas.legally_bearing import (
    EvidenceCitation,
    OutcomePathDistribution,
    ProbabilisticClaim,
)


def _citation(document_id: str = "doc-1") -> EvidenceCitation:
    return EvidenceCitation(
        document_id=document_id,
        locator="page 1 ¶3",
        text_excerpt="...",
        relation="supports",
    )


class TestEvidenceCitation:
    def test_document_source_ok(self) -> None:
        c = _citation()
        assert c.document_id == "doc-1"

    def test_sourced_rule_source_ok(self) -> None:
        c = EvidenceCitation(
            sourced_rule_id="FL_negligence_SOL_2023",
            locator="rule",
            text_excerpt="2-year SOL post-HB-837",
            relation="supports",
        )
        assert c.sourced_rule_id == "FL_negligence_SOL_2023"

    def test_ledger_entry_source_ok(self) -> None:
        c = EvidenceCitation(
            ledger_entry_id="txn-99",
            locator="postings",
            text_excerpt="outstanding_indemnity +18500",
            relation="supports",
        )
        assert c.ledger_entry_id == "txn-99"

    def test_no_source_rejected(self) -> None:
        with pytest.raises(ValidationError, match="exactly one of"):
            EvidenceCitation(
                locator="page 1",
                text_excerpt="...",
                relation="supports",
            )

    def test_multiple_sources_rejected(self) -> None:
        with pytest.raises(ValidationError, match="exactly one of"):
            EvidenceCitation(
                document_id="doc-1",
                ledger_entry_id="txn-1",
                locator="page 1",
                text_excerpt="...",
                relation="supports",
            )


class TestProbabilisticClaim:
    def test_with_citations_ok(self) -> None:
        c = ProbabilisticClaim(
            claim_text="Coverage applies, clean",
            probability=0.89,
            reasoning="Policy in force; Part A covers; no exclusion fires",
            evidence_citations=[_citation()],
        )
        assert c.probability == 0.89

    def test_missing_citations_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ProbabilisticClaim(
                claim_text="Coverage applies, clean",
                probability=0.89,
                reasoning="...",
                evidence_citations=[],
            )

    def test_probability_must_be_unit_interval(self) -> None:
        with pytest.raises(ValidationError):
            ProbabilisticClaim(
                claim_text="...",
                probability=1.5,
                reasoning="...",
                evidence_citations=[_citation()],
            )
        with pytest.raises(ValidationError):
            ProbabilisticClaim(
                claim_text="...",
                probability=-0.1,
                reasoning="...",
                evidence_citations=[_citation()],
            )


class TestOutcomePathDistribution:
    def _path(self, claim: str, p: float, doc: str = "doc-1") -> ProbabilisticClaim:
        return ProbabilisticClaim(
            claim_text=claim,
            probability=p,
            reasoning=f"reasoning for {claim}",
            evidence_citations=[_citation(doc)],
        )

    def test_sums_to_one_ok(self) -> None:
        dist = OutcomePathDistribution(
            paths=[
                self._path("Coverage clean", 0.89),
                self._path("Coverage with ROR", 0.09, doc="doc-2"),
                self._path("Denial defensible", 0.02, doc="doc-3"),
            ],
            would_shift_distribution=["Personal-use docs would drop ROR toward 0%"],
        )
        assert len(dist.paths) == 3

    def test_floating_point_tolerance(self) -> None:
        # 0.333 * 3 = 0.999 — within ±0.01 tolerance
        OutcomePathDistribution(
            paths=[
                self._path("a", 0.333),
                self._path("b", 0.333, doc="d2"),
                self._path("c", 0.334, doc="d3"),
            ],
        )

    def test_does_not_sum_to_one_rejected(self) -> None:
        with pytest.raises(ValidationError, match="sum to 1.0"):
            OutcomePathDistribution(
                paths=[
                    self._path("a", 0.5),
                    self._path("b", 0.3, doc="d2"),
                ],
            )

    def test_overshoot_rejected(self) -> None:
        with pytest.raises(ValidationError, match="sum to 1.0"):
            OutcomePathDistribution(
                paths=[
                    self._path("a", 0.6),
                    self._path("b", 0.6, doc="d2"),
                ],
            )

    def test_single_path_rejected(self) -> None:
        with pytest.raises(ValidationError):
            OutcomePathDistribution(paths=[self._path("only", 1.0)])
