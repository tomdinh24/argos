"""Smoke tests for specialist output schemas.

Each test constructs a minimal valid instance to confirm the schema composes
correctly and the citation contract holds at every nesting level. Behavioral
tests for each specialist go alongside the specialist runtimes once those
exist; these tests live with the schemas.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from argos.schemas.legally_bearing import (
    EvidenceCitation,
    OutcomePathDistribution,
    ProbabilisticClaim,
)
from argos.schemas.specialists.brief import (
    ClaimBrief,
    DiffItem,
    FinancialSnapshot,
    MissingInfoItem,
    SinceLastTouch,
    StatusSnapshot,
)
from argos.schemas.specialists.closure import (
    ClosureAnalysis,
    ClosureDefect,
)
from argos.schemas.specialists.coverage import (
    CoverageAnalysis,
    CoverageDraft,
)
from argos.schemas.specialists.liability import (
    FaultAllocationBucket,
    FaultAllocationDistribution,
    LiabilityAnalysis,
    LiabilityDraftAssessment,
)
from argos.schemas.specialists.recovery import (
    RecoveryAmountBand,
    RecoveryAnalysis,
    RecoveryDemandDraft,
    SOLStatus,
)
from argos.schemas.specialists.reserve import (
    NoticeObligationTriggered,
    ReserveAnalysis,
    ReserveBand,
    ReserveComponentAnalysis,
    TriggerFired,
)


def _doc_citation(doc_id: str = "doc-1", relation: str = "supports") -> EvidenceCitation:
    return EvidenceCitation(
        document_id=doc_id,
        locator="page 1",
        text_excerpt="...",
        relation=relation,  # type: ignore[arg-type]
    )


def _rule_citation(rule_id: str = "FL_negligence_modified_51_2023") -> EvidenceCitation:
    return EvidenceCitation(
        sourced_rule_id=rule_id,
        locator="rule body",
        text_excerpt="Modified-51 comparative fault",
        relation="supports",
    )


def _claim(text: str, p: float, doc: str = "doc-1") -> ProbabilisticClaim:
    return ProbabilisticClaim(
        claim_text=text,
        probability=p,
        reasoning=f"reasoning for {text}",
        evidence_citations=[_doc_citation(doc)],
    )


NOW = datetime.now(timezone.utc)


class TestCoverageSchema:
    def test_minimal_valid(self) -> None:
        analysis = CoverageAnalysis(
            exposure_id="exp-1",
            reviewed_as_of=NOW,
            evidence_found=[_doc_citation()],
            per_question_probabilities=[_claim("Policy in force", 1.0)],
            outcome_path_distribution=OutcomePathDistribution(
                paths=[
                    _claim("Coverage clean", 0.89),
                    _claim("Coverage with ROR", 0.09, doc="doc-2"),
                    _claim("Denial defensible", 0.02, doc="doc-3"),
                ],
            ),
            coverage_analysis_memo=CoverageDraft(body="memo body", citations=[_doc_citation()]),
        )
        assert analysis.ror_letter is None  # not required when ROR path is low-prob

    def test_no_recommendation_field(self) -> None:
        """The schema must not have a `recommended_path` field."""
        assert "recommended_path" not in CoverageAnalysis.model_fields
        assert "recommendation" not in CoverageAnalysis.model_fields


class TestLiabilitySchema:
    def test_minimal_valid(self) -> None:
        analysis = LiabilityAnalysis(
            exposure_id="exp-1",
            reviewed_as_of=NOW,
            jurisdiction="FL",
            comparative_fault_rule="modified_51",
            comparative_fault_rule_citation=_rule_citation(),
            evidence_found=[_doc_citation()],
            per_question_probabilities=[_claim("Insured following too close", 0.85)],
            fault_allocation_distribution=FaultAllocationDistribution(
                paths=[
                    FaultAllocationBucket(
                        insured_fault_pct=100,
                        claimant_fault_pct=0,
                        probability=0.18,
                        reasoning="Pure-rear-end interpretation",
                        evidence_citations=[_doc_citation()],
                    ),
                    FaultAllocationBucket(
                        insured_fault_pct=80,
                        claimant_fault_pct=20,
                        probability=0.82,
                        reasoning="Police-report-aligned",
                        evidence_citations=[_doc_citation("doc-2")],
                    ),
                ],
            ),
            recovery_barred_probability=0.0,
            draft_assessment=LiabilityDraftAssessment(
                body="...", citations=[_doc_citation()]
            ),
        )
        assert analysis.comparative_fault_rule == "modified_51"

    def test_rule_citation_must_be_sourced(self) -> None:
        with pytest.raises(ValidationError, match="sourced legal rule"):
            LiabilityAnalysis(
                exposure_id="exp-1",
                reviewed_as_of=NOW,
                jurisdiction="FL",
                comparative_fault_rule="modified_51",
                comparative_fault_rule_citation=_doc_citation(),  # doc, not rule
                evidence_found=[_doc_citation()],
                per_question_probabilities=[_claim("foo", 0.5)],
                fault_allocation_distribution=FaultAllocationDistribution(
                    paths=[
                        FaultAllocationBucket(
                            insured_fault_pct=100,
                            claimant_fault_pct=0,
                            probability=0.5,
                            reasoning="...",
                            evidence_citations=[_doc_citation()],
                        ),
                        FaultAllocationBucket(
                            insured_fault_pct=50,
                            claimant_fault_pct=50,
                            probability=0.5,
                            reasoning="...",
                            evidence_citations=[_doc_citation()],
                        ),
                    ],
                ),
                recovery_barred_probability=0.0,
                draft_assessment=LiabilityDraftAssessment(
                    body="...", citations=[_doc_citation()]
                ),
            )

    def test_no_recommendation_field(self) -> None:
        assert "recommended_bucket" not in LiabilityAnalysis.model_fields
        assert "recommended_allocation" not in LiabilityAnalysis.model_fields

    def test_bucket_percentages_must_sum_to_100(self) -> None:
        with pytest.raises(ValidationError, match="sum to 100"):
            FaultAllocationBucket(
                insured_fault_pct=70,
                claimant_fault_pct=20,
                probability=0.5,
                reasoning="...",
                evidence_citations=[_doc_citation()],
            )


class TestReserveSchema:
    def test_minimal_valid(self) -> None:
        analysis = ReserveAnalysis(
            exposure_id="exp-1",
            reviewed_as_of=NOW,
            per_component=[
                ReserveComponentAnalysis(
                    component="indemnity",
                    current_outstanding=28_000.0,
                    recommended_outstanding_band=ReserveBand(p10=42_000, p50=46_500, p90=51_000),
                    rationale="Demand received, attorney rep on file",
                    triggers_fired=[
                        TriggerFired(
                            trigger_id="demand_package_received",
                            evidence_citations=[_doc_citation()],
                        ),
                    ],
                    evidence_citations=[_doc_citation()],
                ),
            ],
            notice_obligations_triggered=[
                NoticeObligationTriggered(
                    notice_type="client",
                    probability=0.95,
                    reasoning="Incurred crosses large-loss threshold",
                    required_by_date=NOW,
                    evidence_citations=[_doc_citation()],
                ),
            ],
            authority_required_level="handler",
        )
        assert analysis.per_component[0].recommended_outstanding_band.p50 == 46_500

    def test_band_must_be_ordered(self) -> None:
        with pytest.raises(ValidationError, match="ordered"):
            ReserveBand(p10=50_000, p50=46_500, p90=42_000)


class TestRecoverySchema:
    def test_minimal_valid_with_sourced_sol(self) -> None:
        analysis = RecoveryAnalysis(
            exposure_id="exp-1",
            reviewed_as_of=NOW,
            opportunity=_claim("Recovery opportunity exists (subrogation)", 0.88),
            recovery_type="subrogation",
            adverse_party_id="party-99",
            amount_band=RecoveryAmountBand(gross_low=11_000, gross_median=14_000, gross_high=17_000),
            sol_status=SOLStatus(
                sourced_rule_applied=_rule_citation("FL_negligence_SOL_2023"),
                deadline_date=NOW,
                days_remaining=688,
            ),
            draft_demand=RecoveryDemandDraft(
                body="demand body",
                recipient_party_id="party-100",
                citations=[_doc_citation()],
            ),
        )
        assert analysis.recovery_type == "subrogation"

    def test_unknown_sol_acceptable(self) -> None:
        # Unsourced jurisdictions: specialist must surface "unknown", not assert
        analysis = RecoveryAnalysis(
            exposure_id="exp-1",
            reviewed_as_of=NOW,
            opportunity=_claim("Recovery opportunity exists", 0.75),
            recovery_type="subrogation",
            amount_band=RecoveryAmountBand(gross_low=8_000, gross_median=10_000, gross_high=12_000),
            sol_status=SOLStatus(
                unknown_note="No sourced SOL rule for this jurisdiction; please review",
            ),
        )
        assert analysis.sol_status.deadline_date is None


class TestClosureSchema:
    def test_minimal_valid_ready(self) -> None:
        analysis = ClosureAnalysis(
            exposure_id="exp-1",
            reviewed_as_of=NOW,
            ready_to_close=_claim("File is ready to close", 0.96),
        )
        assert analysis.blocking_defects == []

    def test_with_blocking_defects(self) -> None:
        analysis = ClosureAnalysis(
            exposure_id="exp-1",
            reviewed_as_of=NOW,
            ready_to_close=_claim("File is ready to close", 0.12),
            blocking_defects=[
                ClosureDefect(
                    kind="open_recovery",
                    description="Recovery R-4218-1 status=potential, never resolved",
                    evidence_citations=[_doc_citation()],
                    resolution_hint="Resolve the recovery (pursue or abandon)",
                ),
                ClosureDefect(
                    kind="outstanding_reserve",
                    description="Outstanding indemnity = $2,400",
                    evidence_citations=[_doc_citation("doc-ledger")],
                ),
            ],
        )
        assert len(analysis.blocking_defects) == 2


class TestBriefSchema:
    def test_minimal_valid(self) -> None:
        brief = ClaimBrief(
            claim_id="claim-1",
            generated_at=NOW,
            story_paragraph="Rear-end collision...",
            story_citations=[_doc_citation()],
            since_last_touch=SinceLastTouch(
                last_touch_at=NOW,
                diff_items=[
                    DiffItem(
                        change_text="Demand received 05-27",
                        occurred_at=NOW,
                        evidence_citations=[_doc_citation("demand-pkg")],
                    ),
                ],
            ),
            current_status_snapshot=StatusSnapshot(
                coverage_status="accepted",
                handling_status="in_negotiation",
                settlement_status="in_progress",
                representation_status="represented",
                litigation_status="none",
                recovery_status="not_screened",
                financial_status="reserves_outstanding",
            ),
            financial_snapshot=FinancialSnapshot(
                as_of_effective=NOW,
                as_of_recorded=NOW,
                outstanding_indemnity=28_000.0,
                paid_indemnity=0.0,
                outstanding_alae=4_000.0,
                paid_alae=0.0,
                recovered=0.0,
            ),
            missing_info=[
                MissingInfoItem(
                    item="Renewed medical authorization",
                    requested_from="claimant's attorney",
                    requested_at=NOW,
                    response_due=NOW,
                    correspondence_status="auto_sent",
                    evidence_citations=[_doc_citation()],
                ),
            ],
        )
        assert brief.claim_id == "claim-1"
