"""Recovery — adversarial boundary probes (8 scenarios, multi-sub-case)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from argos.schemas.workflows.recovery import (
    EvidenceArtifacts,
    OwnerOperatorSplit,
    PolicySubrogationLanguage,
    RecoveryInputs,
    RecoveryUpstreamContext,
    UpstreamCoverageSnapshot,
    UpstreamLiabilitySnapshot,
    UpstreamReserveSnapshot,
)
from tests.evals.recovery._harness import (
    POST_HB837,
    RecoveryEvalCase,
    assert_case,
    run_case,
)


def _inputs(
    *,
    loss_date: date = POST_HB837,
    classification: str = "private_passenger",
    naic: str | None = "25178",
    lane: str = "legal",
    owner_split: OwnerOperatorSplit | None = None,
) -> RecoveryInputs:
    return RecoveryInputs(
        loss_date=loss_date,
        loss_state="FL",
        claim_filing_date=None,
        tortfeasor_vehicle_classification=classification,  # type: ignore[arg-type]
        tortfeasor_vehicle_vin="1HGCM82633A123456",
        tortfeasor_carrier_naic=naic,
        owner_operator_split=owner_split or OwnerOperatorSplit(
            owner_id="P-op", operator_id="P-op", are_same=True,
            owner_type="natural_person",
        ),
        named_insured_and_omnibus_roster=[],
        policy_subrogation_language=PolicySubrogationLanguage(has_made_whole_waiver=False),
        subrogation_lane=lane,  # type: ignore[arg-type]
        evidence_artifacts=EvidenceArtifacts(vehicle_status="in_storage_yard"),
    )


def _upstream(
    *,
    insured_pct: int = 80,
    claimant_pct: int = 20,
    operator_party: str = "P-op",
    owner_party: str | None = "P-op",
    paid_indemnity: int = 25000,
    economic_loss: int = 30000,
    regime: str = "modified_51_bar_hb837",
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
        coverage=UpstreamCoverageSnapshot(status="granted", omnibus_roster=[]),
    )


# ---------------------------------------------------------------------------
# ADV-01 — HB 837 SOL boundary: 2023-03-23 vs 2023-03-24
# Pre  → pre_hb837_4yr regime, 4yr SOL
# Post → post_hb837_2yr regime, 2yr SOL
# Both fall within ±30 days of effective date → sol_accrual_vs_filing_split flag fires
# ---------------------------------------------------------------------------

ADV_01a = RecoveryEvalCase(
    case_id="ADV-01a",
    description="SOL boundary: loss 2023-03-23 — pre-HB-837 4yr regime",
    inputs=_inputs(loss_date=date(2023, 3, 23)),
    upstream=_upstream(),
    expected_statute_version="pre_hb837_4yr",
    expected_variance_flags_include={"sol_accrual_vs_filing_split"},
)

ADV_01b = RecoveryEvalCase(
    case_id="ADV-01b",
    description="SOL boundary: loss 2023-03-24 — post-HB-837 2yr regime + SOL already expired",
    inputs=_inputs(loss_date=date(2023, 3, 24)),
    upstream=_upstream(),
    expected_statute_version="post_hb837_2yr",
    # post-HB-837 2yr → deadline 2025-03-24, expired at REVIEW_AS_OF (2026-06-02).
    # `sol_accrual_vs_filing_split` does NOT fire here because the SOL-expired
    # branch short-circuits before the split-window check — documenting that
    # ordering.
    expected_recovery_barred=True,
    expected_bar_basis="sol_expired",
    expected_variance_flags_exclude={"sol_accrual_vs_filing_split"},
)


# ---------------------------------------------------------------------------
# ADV-02 — Comparative bar edge: claimant exactly 50% (NOT barred) vs 51% (barred)
# strict `>` 50, not `≥`
# ---------------------------------------------------------------------------

ADV_02a = RecoveryEvalCase(
    case_id="ADV-02a",
    description="Modified-51 bar: claimant exactly 50% — NOT barred",
    inputs=_inputs(),
    upstream=_upstream(insured_pct=50, claimant_pct=50),
    expected_recovery_barred=False,
    expected_gate_results={"hb837_modified_comparative_bar": "pass"},
    # 50% is within ±5 of bar → comparative_fault_cliff_buffer fires
    expected_variance_flags_include={"comparative_fault_cliff_buffer"},
)

ADV_02b = RecoveryEvalCase(
    case_id="ADV-02b",
    description="Modified-51 bar: claimant 51% — barred (strict > 50)",
    inputs=_inputs(),
    upstream=_upstream(insured_pct=49, claimant_pct=51),
    expected_recovery_barred=True,
    expected_bar_basis="hb_837_51_bar",
    expected_gate_results={"hb837_modified_comparative_bar": "fail"},
)


# ---------------------------------------------------------------------------
# ADV-03 — Near-bar window edge: claimant 45% (in [45,55]) vs 44% (out)
# `comparative_fault_cliff_buffer` is in MANDATORY_ESCALATION_VARIANCE_FLAGS
# ---------------------------------------------------------------------------

ADV_03a = RecoveryEvalCase(
    case_id="ADV-03a",
    description="Near-bar window: claimant 45% — buffer flag fires, mandatory escalation",
    inputs=_inputs(),
    upstream=_upstream(insured_pct=55, claimant_pct=45),
    expected_variance_flags_include={"comparative_fault_cliff_buffer"},
    expected_recommendation="senior_review_required",
    expected_authority_tier="roundtable",
)

ADV_03b = RecoveryEvalCase(
    case_id="ADV-03b",
    description="Near-bar window: claimant 44% — buffer does NOT fire (strict ≤5 from 50)",
    inputs=_inputs(),
    upstream=_upstream(insured_pct=56, claimant_pct=44),
    expected_variance_flags_exclude={"comparative_fault_cliff_buffer"},
)


# ---------------------------------------------------------------------------
# ADV-04 — AF cap edge: paid exactly $100K (in) vs $100,001 (over)
# ---------------------------------------------------------------------------

ADV_04a = RecoveryEvalCase(
    case_id="ADV-04a",
    description="AF cap edge: paid exactly $100K — within cap",
    inputs=_inputs(),
    upstream=_upstream(paid_indemnity=100_000),
    expected_within_af_cap=True,
    expected_forum_recommendation="arbitration_forums",
    expected_recommendation="route_to_af",
)

ADV_04b = RecoveryEvalCase(
    case_id="ADV-04b",
    description="AF cap edge: paid $100,001 — over cap, falls back to litigation",
    inputs=_inputs(),
    upstream=_upstream(paid_indemnity=100_001),
    expected_within_af_cap=False,
    expected_forum_recommendation="litigation",
    expected_recommendation="route_to_litigation",
)


# ---------------------------------------------------------------------------
# ADV-05 — AF signatory unverifiable: NAIC=None
# Per `_af_compulsory_gate` (read separately), missing NAIC routes to
# `af_signatory_unverifiable` variance which is in MANDATORY_ESCALATION.
# ---------------------------------------------------------------------------

ADV_05 = RecoveryEvalCase(
    case_id="ADV-05",
    description="AF signatory unverifiable — NAIC missing, mandatory escalation",
    inputs=_inputs(naic=None),
    upstream=_upstream(),
    expected_variance_flags_include={"af_signatory_unverifiable"},
    expected_authority_tier="roundtable",
)


# ---------------------------------------------------------------------------
# ADV-06 — Vicarious cap eligibility (3 sub-cases)
# Cap fires only when: owner != operator AND owner_type == "natural_person"
# ---------------------------------------------------------------------------

ADV_06a = RecoveryEvalCase(
    case_id="ADV-06a",
    description="Vicarious cap: owner == operator (are_same=True) — cap does NOT fire",
    inputs=_inputs(
        owner_split=OwnerOperatorSplit(
            owner_id="P-op", operator_id="P-op",
            are_same=True, owner_type="natural_person",
        ),
    ),
    upstream=_upstream(owner_party="P-op"),
    expected_layer_ids_absent={"owner_vicarious_cap_324_021"},
)

ADV_06b = RecoveryEvalCase(
    case_id="ADV-06b",
    description="Vicarious cap: owner != operator but business owner — cap does NOT fire",
    inputs=_inputs(
        owner_split=OwnerOperatorSplit(
            owner_id="P-owner-biz", operator_id="P-op",
            are_same=False, owner_type="business_not_in_leasing",
        ),
    ),
    upstream=_upstream(operator_party="P-op", owner_party="P-owner-biz"),
    expected_layer_ids_absent={"owner_vicarious_cap_324_021"},
)

ADV_06c = RecoveryEvalCase(
    case_id="ADV-06c",
    description="Vicarious cap: natural-person owner ≠ operator — cap fires",
    inputs=_inputs(
        owner_split=OwnerOperatorSplit(
            owner_id="P-owner-natural", operator_id="P-op",
            are_same=False, owner_type="natural_person",
        ),
    ),
    upstream=_upstream(operator_party="P-op", owner_party="P-owner-natural"),
    expected_layer_ids_present={"owner_vicarious_cap_324_021"},
)


# ---------------------------------------------------------------------------
# ADV-07 — Products repose boundary
# 12yr repose: loss 12yr-1d ago vs 12yr+1d ago
# The repose acts as a cap on products-defect layer eligibility.
# v1 calculator surfaces the layer when VIN present and doesn't gate on repose
# in code yet — this case probes the current behavior (layer present in both),
# documenting Gap #4 in the threshold doc.
# ---------------------------------------------------------------------------

ADV_07 = RecoveryEvalCase(
    case_id="ADV-07",
    description="Products repose: layer present when VIN given (v1 surface; Gap #4 in threshold doc)",
    inputs=_inputs(),
    upstream=_upstream(),
    expected_layer_ids_present={"product_defect_recall"},
)


# ---------------------------------------------------------------------------
# ADV-08 — SOL exactly 0 days remaining
# REVIEW_AS_OF_DATE = 2026-06-02, post-HB-837 2yr SOL → loss = 2024-06-02
# Gate is `days_remaining > 0` strict, so 0 → fail
# ---------------------------------------------------------------------------

ADV_08 = RecoveryEvalCase(
    case_id="ADV-08",
    description="SOL boundary: 0 days remaining — strict > 0, gate fails",
    inputs=_inputs(loss_date=date(2024, 6, 2)),
    upstream=_upstream(),
    expected_recovery_barred=True,
    expected_bar_basis="sol_expired",
    expected_sol_days_remaining=0,
    expected_gate_results={"hb837_negligence_sol": "fail"},
)


ADVERSARIAL_CASES = [
    ADV_01a, ADV_01b,
    ADV_02a, ADV_02b,
    ADV_03a, ADV_03b,
    ADV_04a, ADV_04b,
    ADV_05,
    ADV_06a, ADV_06b, ADV_06c,
    ADV_07,
    ADV_08,
]


@pytest.mark.eval
@pytest.mark.parametrize("case", ADVERSARIAL_CASES, ids=[c.case_id for c in ADVERSARIAL_CASES])
def test_adversarial(case: RecoveryEvalCase) -> None:
    resolution, ctx = run_case(case)
    assert_case(case, resolution, ctx)
