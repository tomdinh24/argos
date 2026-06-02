"""Liability — adversarial boundary probes (8 off-by-one seam tests).

Each case sits one click away from a doctrinal threshold and asserts
the threshold fires on the correct side.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from argos.schemas.workflows.liability import (
    EvidenceItem,
    IntoxicationEvidence,
    LiabilityInputs,
    OwnerRelationship,
    Party,
    PoliceReportFields,
    RearEndRebuttal,
)
from tests.evals.liability._harness import (
    LiabilityEvalCase,
    assert_case,
    run_case,
)


def _parties() -> list[Party]:
    return [
        Party(party_id="P-insured", role="insured_driver", identity_evidence_cite="pr-1"),
        Party(party_id="P-claimant", role="claimant_driver", identity_evidence_cite="pr-1"),
    ]


def _hard_data_for_claimant() -> list[EvidenceItem]:
    """Two hard-data items moving fault TO the claimant — enough to cross 50%."""
    return [
        EvidenceItem(
            kind="citation_issued",
            source_doc_id="pr-citation",
            quoted_span="Officer cited claimant.",
            contemporaneity_hours_from_loss=2,
            fl_admissibility="admissible",
            fault_direction="claimant_more_fault",
            weight_class="hard_data",
        ),
        EvidenceItem(
            kind="edr_download",
            source_doc_id="edr-1",
            quoted_span="EDR shows claimant pre-impact speed.",
            contemporaneity_hours_from_loss=24,
            fl_admissibility="admissible",
            fault_direction="claimant_more_fault",
            weight_class="hard_data",
        ),
    ]


def _shift_signal_for_claimant() -> list[EvidenceItem]:
    """One rebuttable signal moving fault TO the claimant (~7.5pp shift)."""
    return [
        EvidenceItem(
            kind="recorded_statement_witness",
            source_doc_id="wit-1",
            quoted_span="Witness saw claimant make an unexpected move.",
            contemporaneity_hours_from_loss=4,
            fl_admissibility="admissible",
            fault_direction="claimant_more_fault",
            weight_class="rebuttable_signal",
        ),
    ]


def _inputs(
    *,
    accrual_date: date,
    fact_pattern: str = "controlled_intersection",
    evidence_items: list[EvidenceItem] | None = None,
    owner_type: str = "natural_person",
    driver_is_owner: bool = True,
    intox: IntoxicationEvidence | None = None,
) -> LiabilityInputs:
    return LiabilityInputs(
        accrual_date=accrual_date,
        line_of_business="auto_bi",
        parties=_parties(),
        fact_pattern=fact_pattern,  # type: ignore[arg-type]
        owner_relationship=OwnerRelationship(
            driver_is_owner=driver_is_owner,
            owner_type=owner_type,  # type: ignore[arg-type]
        ),
        intoxication_evidence=intox or IntoxicationEvidence(),
        rear_end_rebuttal_evidence=RearEndRebuttal(),
        evidence_items=evidence_items or [],
        police_report_structured_fields=PoliceReportFields(
            officer_narrative_text="Narrative.",
        ),
    )


# HB 837 boundary triplet (effective 2023-03-24)
ADV_01 = LiabilityEvalCase(
    case_id="ADV-01",
    description="HB 837 boundary: loss 2023-03-23 → pre-HB-837 regime",
    inputs=_inputs(
        accrual_date=date(2023, 3, 23),
        evidence_items=_hard_data_for_claimant(),
    ),
    expected_regime="pure_comparative_pre_hb837",
    expected_bar_triggered=False,
    expected_bar_basis="none",
)

ADV_02 = LiabilityEvalCase(
    case_id="ADV-02",
    description="HB 837 boundary: loss 2023-03-24 → modified-51 regime",
    inputs=_inputs(
        accrual_date=date(2023, 3, 24),
        evidence_items=_hard_data_for_claimant(),
    ),
    expected_regime="modified_51_bar_hb837",
    expected_bar_triggered=True,
    expected_bar_basis="hb837_51_pct",
)

ADV_03 = LiabilityEvalCase(
    case_id="ADV-03",
    description="HB 837 boundary: loss 2023-03-25, claimant >50% → bar fires",
    inputs=_inputs(
        accrual_date=date(2023, 3, 25),
        evidence_items=_hard_data_for_claimant(),
    ),
    expected_regime="modified_51_bar_hb837",
    expected_bar_triggered=True,
    expected_bar_basis="hb837_51_pct",
)

# Modified-51 edge: 50% vs 51% (strict `>`)
ADV_04 = LiabilityEvalCase(
    case_id="ADV-04",
    description="Modified-51 edge: claimant exactly 50% — NO bar",
    inputs=_inputs(
        accrual_date=date(2025, 6, 2),
        fact_pattern="uncontrolled_intersection",  # 50/50 anchor
        evidence_items=[],
    ),
    expected_regime="modified_51_bar_hb837",
    expected_bar_triggered=False,
    expected_claimant_fault_pct=Decimal("50"),
    fault_tolerance_pp=Decimal("0"),
)

ADV_05 = LiabilityEvalCase(
    case_id="ADV-05",
    description="Modified-51 edge: claimant just past 50% — bar fires",
    inputs=_inputs(
        accrual_date=date(2025, 6, 2),
        fact_pattern="uncontrolled_intersection",  # 50/50 anchor
        evidence_items=_shift_signal_for_claimant(),  # ~7.5pp toward claimant
    ),
    expected_regime="modified_51_bar_hb837",
    expected_bar_triggered=True,
    expected_bar_basis="hb837_51_pct",
)

# §768.36 intoxication threshold
ADV_06 = LiabilityEvalCase(
    case_id="ADV-06",
    description="Intoxication threshold: BAC exactly 0.08 + causation + >50% → bar",
    inputs=_inputs(
        accrual_date=date(2025, 6, 2),
        evidence_items=_hard_data_for_claimant(),
        intox=IntoxicationEvidence(
            bac_value=Decimal("0.08"),
            bac_source="blood",
            causation_to_fault_evidence_cites=["er-tox-1"],
            chemical_test_admissible=True,
        ),
    ),
    expected_bar_triggered=True,
    expected_bar_basis="768_36_intoxication",
)

ADV_07 = LiabilityEvalCase(
    case_id="ADV-07",
    description="Intoxication threshold: BAC 0.07, no impairment → §768.36 bar does NOT fire",
    inputs=_inputs(
        accrual_date=date(2025, 6, 2),
        evidence_items=[],  # apportionment stays clean (no claimant majority)
        intox=IntoxicationEvidence(
            bac_value=Decimal("0.07"),
            bac_source="blood",
            impairment_observed=False,
            causation_to_fault_evidence_cites=["er-tox-1"],
        ),
    ),
    expected_bar_triggered=False,
    expected_bar_basis="none",
    expected_doctrines_not_applied=["intoxication_bar_768_36"],
)

# Vicarious cap eligibility
ADV_08 = LiabilityEvalCase(
    case_id="ADV-08",
    description="Driver-is-owner kills vicarious cap (no vicarious theory)",
    inputs=_inputs(
        accrual_date=date(2025, 6, 2),
        owner_type="natural_person",
        driver_is_owner=True,
    ),
    expected_vicarious_cap_applies=False,
    expected_doctrines_not_applied=["natural_person_owner_cap"],
)


ADVERSARIAL_CASES = [
    ADV_01, ADV_02, ADV_03, ADV_04, ADV_05, ADV_06, ADV_07, ADV_08,
]


@pytest.mark.eval
@pytest.mark.parametrize("case", ADVERSARIAL_CASES, ids=[c.case_id for c in ADVERSARIAL_CASES])
def test_adversarial(case: LiabilityEvalCase) -> None:
    ctx = run_case(case)
    assert_case(case, ctx)
