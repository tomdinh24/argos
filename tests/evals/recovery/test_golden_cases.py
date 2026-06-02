"""Recovery — golden eval cases (15 scenarios)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from argos.schemas.workflows.recovery import (
    CollateralSourcePayment,
    CoverageDenialStatus,
    EvidenceArtifacts,
    ExternalEventTriggers,
    FabreCandidate,
    OmnibusPartyEntry,
    OwnerKnowledgeIndicator,
    OwnerOperatorSplit,
    PolicySubrogationLanguage,
    RecoveryInputs,
    RecoveryUpstreamContext,
    ReleaseSettlementSignal,
    UpstreamCoverageSnapshot,
    UpstreamLiabilitySnapshot,
    UpstreamReserveSnapshot,
)
from tests.evals.recovery._harness import (
    POST_HB837,
    PRE_HB837,
    RecoveryEvalCase,
    assert_case,
    run_case,
)


# ---------------------------------------------------------------------------
# Fixture builders (kept local; not a shared module so each case is readable)
# ---------------------------------------------------------------------------


def _inputs(
    *,
    loss_date: date = POST_HB837,
    loss_state: str = "FL",
    classification: str = "private_passenger",
    naic: str | None = "25178",  # State Farm — signatory in seed
    lane: str = "legal",
    owner_split: OwnerOperatorSplit | None = None,
    omnibus: list[OmnibusPartyEntry] | None = None,
    has_made_whole_waiver: bool = False,
    coverage_denial: CoverageDenialStatus | None = None,
    releases: list[ReleaseSettlementSignal] | None = None,
    collateral: list[CollateralSourcePayment] | None = None,
    triggers: ExternalEventTriggers | None = None,
    fabre: list[FabreCandidate] | None = None,
    owner_knowledge: list[OwnerKnowledgeIndicator] | None = None,
    vehicle_status: str = "in_storage_yard",
    vin: str | None = "1HGCM82633A123456",
) -> RecoveryInputs:
    return RecoveryInputs(
        loss_date=loss_date,
        loss_state=loss_state,  # type: ignore[arg-type]
        claim_filing_date=None,
        tortfeasor_vehicle_classification=classification,  # type: ignore[arg-type]
        tortfeasor_vehicle_vin=vin,
        tortfeasor_carrier_naic=naic,
        owner_operator_split=owner_split or OwnerOperatorSplit(
            owner_id="P-tortfeasor-operator",
            operator_id="P-tortfeasor-operator",
            are_same=True,
            owner_type="natural_person",
        ),
        owner_knowledge_indicators=owner_knowledge or [],
        named_insured_and_omnibus_roster=omnibus or [],
        policy_subrogation_language=PolicySubrogationLanguage(
            has_made_whole_waiver=has_made_whole_waiver,
        ),
        subrogation_lane=lane,  # type: ignore[arg-type]
        release_or_settlement_signals=releases or [],
        collateral_source_payments=collateral or [],
        evidence_artifacts=EvidenceArtifacts(vehicle_status=vehicle_status),  # type: ignore[arg-type]
        external_event_triggers=triggers,
        fabre_candidate_nonparties=fabre or [],
        coverage_denial_status=coverage_denial,
    )


def _upstream(
    *,
    insured_pct: int = 80,
    claimant_pct: int = 20,
    regime: str = "modified_51_bar_hb837",
    operator_party: str = "P-tortfeasor-operator",
    owner_party: str | None = "P-tortfeasor-operator",
    paid_indemnity: int = 25000,
    economic_loss: int = 30000,
    coverage_status: str = "granted",
    coverage_omnibus: list[OmnibusPartyEntry] | None = None,
) -> RecoveryUpstreamContext:
    apport = {
        "P-insured": Decimal(insured_pct),
        operator_party: Decimal(claimant_pct),
    }
    if owner_party is not None and owner_party != operator_party:
        apport[owner_party] = Decimal("0")
    return RecoveryUpstreamContext(
        liability=UpstreamLiabilitySnapshot(
            apportionment_by_party_id=apport,
            insured_fault_pct=Decimal(insured_pct),
            claimant_fault_pct=Decimal(claimant_pct),
            operator_party_id=operator_party,
            owner_party_id=owner_party,
            regime_statute=regime,
            recovery_bar_triggered=False,
            bar_basis="none",
            calibration_confidence=0.75,
        ),
        reserve=UpstreamReserveSnapshot(
            paid_indemnity_by_component={"indemnity": Decimal(paid_indemnity)},
            outstanding_indemnity_by_component={"indemnity": Decimal("5000")},
            total_economic_loss=Decimal(economic_loss),
        ),
        coverage=UpstreamCoverageSnapshot(
            status=coverage_status,  # type: ignore[arg-type]
            omnibus_roster=coverage_omnibus or [],
        ),
    )


# ---------------------------------------------------------------------------
# GC-01 — Clean post-HB-837, both signatories, within AF cap → route_to_af
# ---------------------------------------------------------------------------

GC_01 = RecoveryEvalCase(
    case_id="GC-01",
    description="Clean post-HB-837, both signatories, within AF cap",
    inputs=_inputs(),
    upstream=_upstream(),  # paid 25000 < AF cap 100000
    expected_recommendation="route_to_af",
    expected_recovery_barred=False,
    expected_bar_basis="",
    expected_statute_version="post_hb837_2yr",
    expected_forum_recommendation="arbitration_forums",
    expected_within_af_cap=True,
    expected_af_signatory_check="signatory",
    expected_fee_model="af_flat",
    expected_authority_tier="examiner",
    expected_committable_at_examiner=True,
    expected_preservation_issued=True,
    expected_preservation_scope_includes={"vehicle"},
    expected_variance_flags_exclude={
        "hb_837_51_bar",  # not a flag literal but proof of clean
        "comparative_fault_cliff_buffer",
    },
    expected_gate_results={
        "hb837_negligence_sol": "pass",
        "hb837_modified_comparative_bar": "pass",
        "anti_subrogation_rule": "pass",
    },
    expected_deadline_ids_present={"sol_drop_dead"},
)


# ---------------------------------------------------------------------------
# GC-02 — Pre-HB-837, claimant 60%, pure comparative — NOT barred
# ---------------------------------------------------------------------------

GC_02 = RecoveryEvalCase(
    case_id="GC-02",
    description="Pre-HB-837, claimant 60% pure comparative — recoverable",
    # Use 2023-01-01 (before HB 837 effective) so we get pre-HB-837 4yr SOL
    # with plenty of runway. PRE_HB837 (2022-06-02) is exactly on the SOL
    # boundary at REVIEW_AS_OF and barred.
    inputs=_inputs(loss_date=date(2023, 1, 1)),
    upstream=_upstream(insured_pct=40, claimant_pct=60),
    expected_statute_version="pre_hb837_4yr",
    expected_recovery_barred=False,
    expected_gate_results={
        "hb837_modified_comparative_bar": "n_a",  # only applies post-HB-837
    },
)


# ---------------------------------------------------------------------------
# GC-03 — Post-HB-837, claimant 60% → §768.81 bar fires → abstain
# ---------------------------------------------------------------------------

GC_03 = RecoveryEvalCase(
    case_id="GC-03",
    description="Post-HB-837, claimant 60% — §768.81 modified-51 bar fires",
    inputs=_inputs(),
    upstream=_upstream(insured_pct=40, claimant_pct=60),
    expected_recommendation="abstain",
    expected_recovery_barred=True,
    expected_bar_basis="hb_837_51_bar",
    expected_gate_results={
        "hb837_modified_comparative_bar": "fail",
    },
    expected_forum_recommendation="abstain",
)


# ---------------------------------------------------------------------------
# GC-04 — Non-FL loss → abstain (non_fl_loss bar)
# ---------------------------------------------------------------------------

GC_04 = RecoveryEvalCase(
    case_id="GC-04",
    description="Non-FL loss — non_fl_loss bar fires, mandatory escalation",
    inputs=_inputs(loss_state="other"),
    upstream=_upstream(),
    # `recovery_barred=True` short-circuits to "abstain" in _recommendation()
    # BEFORE the mandatory-escalation check, even when a mandatory-escalation
    # variance flag is set. The variance still drives authority routing to
    # roundtable.
    expected_recommendation="abstain",
    expected_recovery_barred=True,
    expected_bar_basis="non_fl_loss",
    expected_variance_flags_include={"non_fl_loss_routed_to_abstain"},
    expected_authority_tier="roundtable",
)


# ---------------------------------------------------------------------------
# GC-05 — SOL expired (loss > 2yr ago) → abstain
# REVIEW_AS_OF_DATE = 2026-06-02, post-HB-837 2yr SOL
# Loss 2024-01-01 → deadline 2026-01-01 → expired
# ---------------------------------------------------------------------------

GC_05 = RecoveryEvalCase(
    case_id="GC-05",
    description="SOL expired — post-HB-837 2yr clock past deadline",
    inputs=_inputs(loss_date=date(2024, 1, 1)),
    upstream=_upstream(),
    expected_recommendation="abstain",
    expected_recovery_barred=True,
    expected_bar_basis="sol_expired",
    expected_gate_results={"hb837_negligence_sol": "fail"},
    expected_sol_deadline=date(2026, 1, 1),
)


# ---------------------------------------------------------------------------
# GC-06 — Anti-subrogation overlap: tortfeasor operator appears on omnibus roster
# ---------------------------------------------------------------------------

_overlap_roster = [
    OmnibusPartyEntry(
        name="P-tortfeasor-operator",
        role="permissive",
        coverage_section_paid_under="collision",
    ),
]

GC_06 = RecoveryEvalCase(
    case_id="GC-06",
    description="Anti-subrogation overlap — tortfeasor on insured's omnibus roster",
    inputs=_inputs(omnibus=_overlap_roster),
    upstream=_upstream(),
    expected_gate_results={"anti_subrogation_rule": "ambiguous_routed_to_senior"},
    expected_variance_flags_include={"anti_subrogation_per_coverage_section_ambiguity"},
    # anti_subrogation_per_coverage_section_ambiguity is NOT in
    # MANDATORY_ESCALATION_VARIANCE_FLAGS, so this routes to senior_examiner
    # (non-mandatory variance), not roundtable.
    expected_authority_tier="senior_examiner",
    expected_committable_at_examiner=False,
)


# ---------------------------------------------------------------------------
# GC-07 — PIP-only commercial (subrogation_lane = 627_7405_pip_commercial)
# ---------------------------------------------------------------------------

GC_07 = RecoveryEvalCase(
    case_id="GC-07",
    description="PIP-only commercial — §627.7405 lane passes",
    inputs=_inputs(
        classification="commercial",
        lane="627_7405_pip_commercial",
    ),
    upstream=_upstream(),
    expected_recovery_barred=False,
    expected_subrogation_lane_id="627_7405_pip_commercial",
    expected_subrogation_lane_cite_substr="§627.7405",
    expected_gate_results={"pip_subrogability_627_7405": "pass"},
)


# ---------------------------------------------------------------------------
# GC-08 — PIP-only non-commercial (private_passenger + PIP lane) → barred
# ---------------------------------------------------------------------------

GC_08 = RecoveryEvalCase(
    case_id="GC-08",
    description="PIP-only non-commercial — §627.7405 bar fires",
    inputs=_inputs(
        classification="private_passenger",
        lane="627_7405_pip_commercial",
    ),
    upstream=_upstream(),
    expected_recovery_barred=True,
    expected_bar_basis="pip_non_commercial",
    expected_recommendation="abstain",
)


# ---------------------------------------------------------------------------
# GC-09 — Pre-tender release detected → WQBA bar
# ---------------------------------------------------------------------------

GC_09 = RecoveryEvalCase(
    case_id="GC-09",
    description="Pre-tender release signal — WQBA step-into-shoes bar fires",
    inputs=_inputs(
        releases=[
            ReleaseSettlementSignal(
                type="release_executed",
                party="P-insured",
                signal_date=date(2026, 1, 15),
                source_doc_id="release-1",
                quoted_span="The undersigned releases...",
            ),
        ],
    ),
    upstream=_upstream(),
    expected_recovery_barred=True,
    expected_bar_basis="pre_tender_release",
    # Bar short-circuits to abstain even though release_or_pre_tender_settlement_detected
    # is in MANDATORY_ESCALATION_VARIANCE_FLAGS; variance still drives authority.
    expected_recommendation="abstain",
    expected_variance_flags_include={"release_or_pre_tender_settlement_detected"},
    expected_authority_tier="roundtable",
)


# ---------------------------------------------------------------------------
# GC-10 — Negligent entrustment: owner != operator + owner_knowledge_indicators
# Adds `owner_negligent_entrustment_uncapped` layer
# ---------------------------------------------------------------------------

GC_10 = RecoveryEvalCase(
    case_id="GC-10",
    description="Negligent entrustment — owner ≠ operator + knowledge indicators present",
    inputs=_inputs(
        owner_split=OwnerOperatorSplit(
            owner_id="P-tortfeasor-owner",
            operator_id="P-tortfeasor-operator",
            are_same=False,
            owner_type="natural_person",
        ),
        owner_knowledge=[
            OwnerKnowledgeIndicator(
                indicator="suspended_dl",
                source_doc_id="mvr-1",
                quoted_span="DL suspended 2025-01-15",
            ),
        ],
    ),
    upstream=_upstream(
        operator_party="P-tortfeasor-operator",
        owner_party="P-tortfeasor-owner",
    ),
    expected_layer_ids_present={
        "operator_policy",
        "owner_vicarious_cap_324_021",
        "owner_negligent_entrustment_uncapped",
    },
)


# ---------------------------------------------------------------------------
# GC-11 — Fabre non-party present
# ---------------------------------------------------------------------------

GC_11 = RecoveryEvalCase(
    case_id="GC-11",
    description="Fabre non-party in apportionment — adds fabre_non_party layer",
    inputs=_inputs(
        fabre=[
            FabreCandidate(
                party="P-third-party",
                evidence_basis="Police report identifies third driver",
                estimated_fault_share=Decimal("25"),
            ),
        ],
    ),
    upstream=_upstream(),
    expected_layer_ids_present={"fabre_non_party"},
    expected_layer_assertions={
        "fabre_non_party": {
            "apportioned_fault_pct": Decimal("25"),
            "probability_of_recovery": 0.40,
            "evidence_completeness": 0.4,
        },
    },
)


# ---------------------------------------------------------------------------
# GC-12 — Vicarious cap layer present (natural-person owner, separate from operator)
# Cap = NATURAL_PERSON_OWNER_CAP_PER_OCCURRENCE (300000) + NATURAL_PERSON_OWNER_CAP_PD (50000)
# = 350000
# ---------------------------------------------------------------------------

GC_12 = RecoveryEvalCase(
    case_id="GC-12",
    description="Vicarious cap layer — natural-person owner ≠ operator",
    inputs=_inputs(
        owner_split=OwnerOperatorSplit(
            owner_id="P-tortfeasor-owner",
            operator_id="P-tortfeasor-operator",
            are_same=False,
            owner_type="natural_person",
        ),
    ),
    upstream=_upstream(
        operator_party="P-tortfeasor-operator",
        owner_party="P-tortfeasor-owner",
    ),
    expected_layer_ids_present={"owner_vicarious_cap_324_021"},
    expected_layer_assertions={
        "owner_vicarious_cap_324_021": {
            "cap_applied": Decimal("350000"),  # per-occurrence + PD
            "target_party_id": "P-tortfeasor-owner",
        },
    },
)


# ---------------------------------------------------------------------------
# GC-13 — AF non-signatory tortfeasor → negotiated_demand
# Seeded non-signatory NAIC: 11185 (National General)
# ---------------------------------------------------------------------------

GC_13 = RecoveryEvalCase(
    case_id="GC-13",
    description="AF non-signatory carrier → negotiated_demand",
    inputs=_inputs(naic="11185"),  # seeded non-signatory
    upstream=_upstream(),
    expected_recommendation="route_to_negotiated_demand",
    expected_forum_recommendation="negotiated_demand",
    expected_af_signatory_check="non_signatory",
    expected_gate_results={"af_compulsory_jurisdiction": "fail"},
)


# ---------------------------------------------------------------------------
# GC-14 — Deny+subrogate cross-stream conflict
# Coverage denied AND Recovery pursuing same loss → variance + senior review
# ---------------------------------------------------------------------------

GC_14 = RecoveryEvalCase(
    case_id="GC-14",
    description="Deny+subrogate cross-stream conflict — mandatory escalation",
    inputs=_inputs(
        coverage_denial=CoverageDenialStatus(
            denied=True,
            basis="cooperation_failure",
            date_denied=date(2026, 4, 1),
        ),
    ),
    upstream=_upstream(coverage_status="denied"),
    expected_recommendation="senior_review_required",
    expected_variance_flags_include={"deny_plus_subrogate"},
    expected_interlock="active_conflict_senior_review_required",
    expected_authority_tier="roundtable",
)


# ---------------------------------------------------------------------------
# GC-15 — Made-whole partial settlement (tortfeasor paid < total loss; no waiver)
# Drives `made_whole_with_partial_settlement` variance (mandatory escalation)
# ---------------------------------------------------------------------------

GC_15 = RecoveryEvalCase(
    case_id="GC-15",
    description="Made-whole partial settlement (no waiver) — mandatory escalation",
    inputs=_inputs(
        # No waiver; collateral_source non-empty with partial-settlement signal
        collateral=[
            CollateralSourcePayment(
                payer="tortfeasor_carrier",
                amount=Decimal("30000"),
                type="health",  # treat as partial-settlement counterparty (non-stripped)
                has_subro_right=False,
            ),
        ],
        has_made_whole_waiver=False,
    ),
    upstream=_upstream(
        paid_indemnity=20000,
        economic_loss=80000,  # total > paid → shortfall exists
    ),
    expected_variance_flags_include={"made_whole_with_partial_settlement"},
    expected_recommendation="senior_review_required",
)


GOLDEN_CASES = [
    GC_01, GC_02, GC_03, GC_04, GC_05, GC_06, GC_07, GC_08,
    GC_09, GC_10, GC_11, GC_12, GC_13, GC_14, GC_15,
]


@pytest.mark.eval
@pytest.mark.parametrize("case", GOLDEN_CASES, ids=[c.case_id for c in GOLDEN_CASES])
def test_golden(case: RecoveryEvalCase) -> None:
    resolution, ctx = run_case(case)
    assert_case(case, resolution, ctx)
