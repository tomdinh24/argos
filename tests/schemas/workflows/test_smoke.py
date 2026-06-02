"""Smoke tests for specialist output schemas.

Each test constructs a minimal valid instance to confirm the schema composes
correctly and the citation contract holds at every nesting level. Behavioral
tests for each specialist go alongside the specialist runtimes once those
exist; these tests live with the schemas.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from argos.schemas.contract import (
    Assessment,
    EvidenceCitation,
    Synthesis,
)
from argos.schemas.workflows.brief import (
    ClaimBrief,
    DiffItem,
    FinancialSnapshot,
    MissingInfoItem,
    SinceLastTouch,
    StatusSnapshot,
)
from argos.schemas.workflows.closure import (
    ClosureAnalysis,
    ClosureDefect,
)
from argos.schemas.workflows.coverage import (
    CoverageReport,
    CoverageDraft,
)
from argos.schemas.workflows.liability import (
    ApplicableRegime,
    ApportionmentEntry,
    AuthorityRouting,
    DiligenceLedger,
    EvidencePackClassification,
    ExposureCeiling,
    FactPatternAnchor,
    LiabilityAssessment,
    LiabilityRationale,
)
from argos.schemas.workflows.recovery import (
    ApplicableSolRegime,
    AuthorityRouting as RecoveryAuthorityRouting,
    CrossStreamConflicts,
    DeadlineCalendar,
    DoctrineGateResult,
    EvidenceArtifacts,
    ForumRouting,
    NetEconomics,
    OwnerOperatorSplit,
    PreservationHold,
    RecoverableBasis,
    RecoveryAssessment,
    RecoveryDiligenceLedger,
    RecoveryInputs,
    SubrogationLane,
)
from argos.schemas.workflows.reserve import (
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


def _assessment(text: str, p: float, doc: str = "doc-1") -> Assessment:
    return Assessment(
        claim_text=text,
        probability=p,
        reasoning=f"reasoning for {text}",
        evidence_citations=[_doc_citation(doc)],
    )


NOW = datetime.now(timezone.utc)


class TestCoverageSchema:
    def test_minimal_valid(self) -> None:
        analysis = CoverageReport(
            request_id="exp-1",
            reviewed_as_of=NOW,
            evidence_found=[_doc_citation()],
            assessments=[_assessment("Policy in force", 1.0)],
            synthesis=Synthesis(
                outcomes=[
                    _assessment("Coverage clean", 0.89),
                    _assessment("Coverage with ROR", 0.09, doc="doc-2"),
                    _assessment("Denial defensible", 0.02, doc="doc-3"),
                ],
            ),
            coverage_analysis_memo=CoverageDraft(body="memo body", citations=[_doc_citation()]),
        )
        assert analysis.ror_letter is None  # not required when ROR path is low-prob

    def test_no_recommendation_field(self) -> None:
        """The schema must not have a `recommended_path` field."""
        assert "recommended_path" not in CoverageReport.model_fields
        assert "recommendation" not in CoverageReport.model_fields


def _entry(pct: int | Decimal, low: int | Decimal, high: int | Decimal, conf: float = 0.7) -> ApportionmentEntry:
    return ApportionmentEntry(
        fault_pct=Decimal(pct),
        fault_pct_band_low=Decimal(low),
        fault_pct_band_high=Decimal(high),
        confidence=conf,
    )


def _minimal_regime() -> ApplicableRegime:
    return ApplicableRegime(
        statute="modified_51_bar_hb837",
        recovery_bar_triggered=False,
        bar_basis="none",
        date_of_loss_governing=date(2025, 6, 2),
        explanation="HB 837 (effective 2023-03-24) governs auto-BI accruing after that date.",
    )


def _minimal_ceiling() -> ExposureCeiling:
    return ExposureCeiling(
        vicarious_cap_applies=False,
        negligent_entrustment_uncapped_path_available=False,
        graves_lessor_removed=False,
    )


def _minimal_ledger() -> DiligenceLedger:
    return DiligenceLedger(
        posture_percent_by_party={"P-insured": Decimal("80"), "P-claimant": Decimal("20")},
        change_conditions=["new EDR data", "deposition transcript"],
        next_review_date=date(2025, 8, 1),
        next_review_trigger="EVIDENCE_LANDED_RE_EVAL",
    )


def _minimal_authority() -> AuthorityRouting:
    return AuthorityRouting(
        committable_at_examiner=True,
        required_tier="examiner",
        gross_exposure=Decimal("50000"),
        net_apportioned_exposure=Decimal("40000"),
        basis_for_tier="Within examiner band; no variance flags fired",
    )


def _minimal_rationale() -> LiabilityRationale:
    return LiabilityRationale(
        fact_pattern_anchor=FactPatternAnchor(
            pattern="rear_end",
            anchor_pct=Decimal("95"),
            anchor_party_role="rear_driver",
            controlling_authority="Birge v. Charron, 107 So. 3d 350 (Fla. 2012)",
        ),
        net_apportionment_walk="Anchor 95/5 → no rebuttal evidence → final 80/20 honoring police-report POI",
    )


class TestLiabilitySchema:
    def test_minimal_valid(self) -> None:
        analysis = LiabilityAssessment(
            request_id="exp-1",
            reviewed_as_of=NOW,
            apportionment={
                "P-insured": _entry(80, 70, 90),
                "P-claimant": _entry(20, 10, 30),
            },
            applicable_regime=_minimal_regime(),
            exposure_ceiling=_minimal_ceiling(),
            rationale=_minimal_rationale(),
            diligence_ledger=_minimal_ledger(),
            authority_tier_required=_minimal_authority(),
            evidence_pack_classification=EvidencePackClassification(),
        )
        assert analysis.applicable_regime.statute == "modified_51_bar_hb837"
        assert sum(e.fault_pct for e in analysis.apportionment.values()) == Decimal("100")

    def test_apportionment_must_sum_to_100(self) -> None:
        with pytest.raises(ValidationError, match="sum to 100"):
            LiabilityAssessment(
                request_id="exp-1",
                reviewed_as_of=NOW,
                apportionment={
                    "P-insured": _entry(70, 60, 80),
                    "P-claimant": _entry(20, 10, 30),
                },
                applicable_regime=_minimal_regime(),
                exposure_ceiling=_minimal_ceiling(),
                rationale=_minimal_rationale(),
                diligence_ledger=_minimal_ledger(),
                authority_tier_required=_minimal_authority(),
                evidence_pack_classification=EvidencePackClassification(),
            )

    def test_apportionment_band_must_be_ordered(self) -> None:
        with pytest.raises(ValidationError, match="ordered"):
            ApportionmentEntry(
                fault_pct=Decimal("80"),
                fault_pct_band_low=Decimal("90"),
                fault_pct_band_high=Decimal("70"),
                confidence=0.5,
            )

    def test_no_recommendation_field(self) -> None:
        assert "recommended_bucket" not in LiabilityAssessment.model_fields
        assert "recommended_allocation" not in LiabilityAssessment.model_fields


class TestReserveSchema:
    def test_minimal_valid(self) -> None:
        analysis = ReserveAnalysis(
            request_id="exp-1",
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


def _minimal_recovery_sol_regime() -> ApplicableSolRegime:
    return ApplicableSolRegime(
        statute_version="post_hb837_2yr",
        statute_cite="Fla. Stat. §95.11(4)(a) as amended by HB 837",
        sol_deadline=date(2027, 6, 2),
        days_remaining=365,
    )


def _minimal_recovery_basis() -> RecoverableBasis:
    return RecoverableBasis(
        section_768_0427_capped_damages=Decimal("25000"),
        pip_collateral_source_stripped=Decimal("8000"),
        made_whole_shortfall=Decimal("0"),
        basis=Decimal("17000"),
    )


def _minimal_recovery_net() -> NetEconomics:
    return NetEconomics(
        gross_recoverable_total=Decimal("12000"),
        fee_drag=Decimal("640"),
        fee_shifting_exposure=Decimal("0"),
        net_total=Decimal("11360"),
        fee_model="internal_blended",
    )


def _minimal_recovery_forum() -> ForumRouting:
    return ForumRouting(
        recommendation="arbitration_forums",
        af_signatory_check="signatory",
        company_paid_damages=Decimal("12000"),
        af_cap_dollars=Decimal("100000"),
        within_af_cap=True,
        basis="Both carriers AF signatory; under $100K cap",
    )


def _minimal_recovery_authority() -> RecoveryAuthorityRouting:
    return RecoveryAuthorityRouting(
        committable_at_examiner=True,
        required_tier="examiner",
        net_apportioned_recoverable=Decimal("11360"),
        basis_for_tier="Within examiner authority; no variance flags",
    )


def _minimal_recovery_ledger() -> RecoveryDiligenceLedger:
    return RecoveryDiligenceLedger(
        decision_rationale="Rear-end, claimant 5% fault, AF route.",
        preservation_hold_status=PreservationHold(
            issued=True,
            hold_scope=["vehicle", "scene_photos"],
            blocks_salvage_release=True,
        ),
    )


class TestRecoverySchema:
    def test_minimal_valid_assessment(self) -> None:
        analysis = RecoveryAssessment(
            request_id="REC-1",
            reviewed_as_of=NOW,
            recommendation="route_to_af",
            subrogation_lane=SubrogationLane(
                lane_id="legal",
                cite="FL common-law legal subrogation",
                defense_checklist_anchor="step-into-shoes",
            ),
            doctrinal_gates=[
                DoctrineGateResult(
                    gate_id="hb837_negligence_sol",
                    result="pass",
                    statute_or_case_cite="Fla. Stat. §95.11(4)(a) as amended by HB 837",
                    effect_if_fired="2-year SOL applies post 3/24/2023",
                ),
            ],
            sol_regime=_minimal_recovery_sol_regime(),
            layered_targets=[],
            recoverable_basis=_minimal_recovery_basis(),
            net_economics=_minimal_recovery_net(),
            forum_routing=_minimal_recovery_forum(),
            deadline_calendar=DeadlineCalendar(),
            preservation_hold=PreservationHold(
                issued=True,
                hold_scope=["vehicle", "scene_photos"],
            ),
            diligence_ledger=_minimal_recovery_ledger(),
            authority_tier_required=_minimal_recovery_authority(),
            cross_stream_conflicts=CrossStreamConflicts(),
        )
        assert analysis.recommendation == "route_to_af"
        assert analysis.recoverable_basis.basis == Decimal("17000")

    def test_gate_without_cite_rejected(self) -> None:
        with pytest.raises(ValidationError, match="statute_or_case_cite"):
            RecoveryAssessment(
                request_id="REC-1",
                reviewed_as_of=NOW,
                recommendation="abstain",
                subrogation_lane=SubrogationLane(
                    lane_id="legal", cite="-", defense_checklist_anchor="-",
                ),
                doctrinal_gates=[
                    DoctrineGateResult(
                        gate_id="some_gate",
                        result="fail",
                        statute_or_case_cite="",  # empty cite → reject
                        effect_if_fired="some effect",
                    ),
                ],
                sol_regime=_minimal_recovery_sol_regime(),
                recoverable_basis=_minimal_recovery_basis(),
                net_economics=_minimal_recovery_net(),
                forum_routing=_minimal_recovery_forum(),
                deadline_calendar=DeadlineCalendar(),
                preservation_hold=PreservationHold(issued=False),
                diligence_ledger=_minimal_recovery_ledger(),
                authority_tier_required=_minimal_recovery_authority(),
                cross_stream_conflicts=CrossStreamConflicts(),
            )

    def test_recovery_inputs_minimal_valid(self) -> None:
        inputs = RecoveryInputs(
            loss_date=date(2025, 6, 2),
            loss_state="FL",
            tortfeasor_vehicle_classification="private_passenger",
            owner_operator_split=OwnerOperatorSplit(
                owner_id="O-1", operator_id="O-1",
                are_same=True, owner_type="natural_person",
            ),
            subrogation_lane="legal",
            evidence_artifacts=EvidenceArtifacts(vehicle_status="in_storage_yard"),
        )
        assert inputs.loss_state == "FL"
        assert inputs.subrogation_lane == "legal"


class TestClosureSchema:
    def test_minimal_valid_ready(self) -> None:
        analysis = ClosureAnalysis(
            request_id="exp-1",
            reviewed_as_of=NOW,
            ready_to_close=_assessment("File is ready to close", 0.96),
        )
        assert analysis.blocking_defects == []

    def test_with_blocking_defects(self) -> None:
        analysis = ClosureAnalysis(
            request_id="exp-1",
            reviewed_as_of=NOW,
            ready_to_close=_assessment("File is ready to close", 0.12),
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
