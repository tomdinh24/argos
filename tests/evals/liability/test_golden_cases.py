"""Liability — golden eval cases (15 doctrinal scenarios).

Run with:
  uv run pytest tests/evals/liability/ -m eval -q

Pass criteria documented in docs/evals/liability-thresholds.md.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from argos.schemas.workflows.liability import (
    EvidenceItem,
    IntoxicationEvidence,
    LiabilityInputs,
    NegligentEntrustment,
    OwnerRelationship,
    Party,
    PoliceReportFields,
    RearEndRebuttal,
)
from tests.evals.liability._harness import (
    POST_HB837,
    PRE_HB837,
    LiabilityEvalCase,
    assert_case,
    run_case,
)


# ---------------------------------------------------------------------------
# Shared shorthand builders (kept local so cases are readable)
# ---------------------------------------------------------------------------


def _parties_two() -> list[Party]:
    return [
        Party(party_id="P-insured", role="insured_driver", identity_evidence_cite="pr-1"),
        Party(party_id="P-claimant", role="claimant_driver", identity_evidence_cite="pr-1"),
    ]


def _ev(
    kind: str,
    direction: str,
    weight: str,
    *,
    cite: str = "doc-1",
) -> EvidenceItem:
    return EvidenceItem(
        kind=kind,  # type: ignore[arg-type]
        source_doc_id=cite,
        quoted_span="verbatim quote",
        contemporaneity_hours_from_loss=24,
        fl_admissibility="admissible",
        represented_by_counsel_at_capture=False,
        fault_direction=direction,  # type: ignore[arg-type]
        weight_class=weight,  # type: ignore[arg-type]
    )


def _inputs(
    *,
    accrual_date: date = POST_HB837,
    line_of_business: str = "auto_bi",
    fact_pattern: str = "rear_end",
    owner_type: str = "natural_person",
    driver_is_owner: bool = True,
    evidence_items: list[EvidenceItem] | None = None,
    parties: list[Party] | None = None,
    intox: IntoxicationEvidence | None = None,
    neg_ent: NegligentEntrustment | None = None,
    rear_end_rebuttal: RearEndRebuttal | None = None,
    permissive_user_coverage_limits: Decimal | None = None,
) -> LiabilityInputs:
    return LiabilityInputs(
        accrual_date=accrual_date,
        line_of_business=line_of_business,  # type: ignore[arg-type]
        parties=parties or _parties_two(),
        fact_pattern=fact_pattern,  # type: ignore[arg-type]
        owner_relationship=OwnerRelationship(
            driver_is_owner=driver_is_owner,
            owner_type=owner_type,  # type: ignore[arg-type]
            permissive_user_coverage_limits=permissive_user_coverage_limits,
        ),
        negligent_entrustment_indicators=neg_ent or NegligentEntrustment(),
        intoxication_evidence=intox or IntoxicationEvidence(),
        rear_end_rebuttal_evidence=rear_end_rebuttal or RearEndRebuttal(),
        evidence_items=evidence_items or [],
        police_report_structured_fields=PoliceReportFields(
            officer_narrative_text="Narrative.",
        ),
    )


# ---------------------------------------------------------------------------
# Golden cases — 15 scenarios spanning the doctrinal matrix
# ---------------------------------------------------------------------------


GC_01 = LiabilityEvalCase(
    case_id="GC-01",
    description="Rear-end clean (insured = rear driver, no rebuttal)",
    inputs=_inputs(),
    expected_regime="modified_51_bar_hb837",
    expected_bar_triggered=False,
    expected_bar_basis="none",
    expected_insured_fault_pct=Decimal("95"),
    expected_claimant_fault_pct=Decimal("5"),
    expected_doctrines_applied=[
        "rear_end_rebuttable_presumption",
        "hb_837_51_bar",
        "joint_several_abolished",
    ],
)

GC_02 = LiabilityEvalCase(
    case_id="GC-02",
    description="Rear-end + sudden-stop rebuttal evidence shifts pie",
    inputs=_inputs(
        rear_end_rebuttal=RearEndRebuttal(
            category="sudden_stop_unexpected_place",
            evidence_cites=["edr-1"],
        ),
        evidence_items=[
            _ev("edr_download", "claimant_more_fault", "rebuttable_signal"),
        ],
    ),
    # 95→ shifts ~7.5pp toward claimant; no bar
    expected_regime="modified_51_bar_hb837",
    expected_bar_triggered=False,
    expected_insured_fault_pct=Decimal("87.5"),
    expected_claimant_fault_pct=Decimal("12.5"),
)

GC_03 = LiabilityEvalCase(
    case_id="GC-03",
    description="Left-turn-across-traffic (insured = turning driver)",
    inputs=_inputs(fact_pattern="left_turn_across_traffic"),
    expected_regime="modified_51_bar_hb837",
    expected_bar_triggered=False,
    expected_insured_fault_pct=Decimal("90"),
    expected_claimant_fault_pct=Decimal("10"),
)

# Two hard-data items both pointing at the claimant flip 85/15 → ~40/60.
_GC04_EVIDENCE = [
    _ev("citation_issued", "claimant_more_fault", "hard_data", cite="pr-citation"),
    _ev("edr_download", "claimant_more_fault", "hard_data", cite="edr-1"),
]

GC_04 = LiabilityEvalCase(
    case_id="GC-04",
    description="Controlled intersection — claimant ran light (HB 837 bar fires)",
    inputs=_inputs(
        fact_pattern="controlled_intersection",
        evidence_items=_GC04_EVIDENCE,
    ),
    expected_regime="modified_51_bar_hb837",
    expected_bar_triggered=True,
    expected_bar_basis="hb837_51_pct",
    expected_insured_fault_pct=Decimal("40"),
    expected_claimant_fault_pct=Decimal("60"),
    expected_doctrines_applied=["hb_837_51_bar"],
)

GC_05 = LiabilityEvalCase(
    case_id="GC-05",
    description="Pre-HB-837 loss, same facts as GC-04 — pure comparative, NO bar",
    inputs=_inputs(
        accrual_date=PRE_HB837,
        fact_pattern="controlled_intersection",
        evidence_items=_GC04_EVIDENCE,
    ),
    expected_regime="pure_comparative_pre_hb837",
    expected_bar_triggered=False,
    expected_bar_basis="none",
    expected_claimant_fault_pct=Decimal("60"),  # still > 50, but no bar
    expected_doctrines_applied=["pure_comparative_pre_hb837"],
    expected_doctrines_not_applied=["hb_837_51_bar"],
)

GC_06 = LiabilityEvalCase(
    case_id="GC-06",
    description="Med-mal carve-out — pure comparative survives HB 837",
    inputs=_inputs(
        line_of_business="med_mal",
        fact_pattern="other",
        evidence_items=[
            _ev("expert_report_medical_causation", "claimant_more_fault", "hard_data"),
        ],
    ),
    expected_regime="med_mal_pure_comparative",
    expected_bar_triggered=False,
    expected_bar_basis="none",
    expected_doctrines_applied=["med_mal_pure_comparative"],
    expected_doctrines_not_applied=["hb_837_51_bar"],
)

GC_07 = LiabilityEvalCase(
    case_id="GC-07",
    description="§768.36 intoxication bar — BAC 0.12 + causation + claimant >50%",
    inputs=_inputs(
        fact_pattern="controlled_intersection",
        evidence_items=_GC04_EVIDENCE,
        intox=IntoxicationEvidence(
            bac_value=Decimal("0.12"),
            bac_source="blood",
            causation_to_fault_evidence_cites=["er-tox-1"],
            chemical_test_admissible=True,
        ),
    ),
    expected_regime="modified_51_bar_hb837",
    expected_bar_triggered=True,
    expected_bar_basis="768_36_intoxication",
    expected_doctrines_applied=["intoxication_bar_768_36"],
)

GC_08 = LiabilityEvalCase(
    case_id="GC-08",
    description="Intoxication WITHOUT causation evidence — dual-prong fails, no §768.36 bar",
    inputs=_inputs(
        fact_pattern="controlled_intersection",
        evidence_items=_GC04_EVIDENCE,
        intox=IntoxicationEvidence(
            bac_value=Decimal("0.12"),
            bac_source="blood",
            causation_to_fault_evidence_cites=[],  # missing
        ),
    ),
    expected_regime="modified_51_bar_hb837",
    expected_bar_triggered=True,  # HB 837 bar still fires
    expected_bar_basis="hb837_51_pct",  # but on HB 837, NOT intoxication
    expected_doctrines_not_applied=["intoxication_bar_768_36"],
)

GC_09 = LiabilityEvalCase(
    case_id="GC-09",
    description="Low BAC + no impairment — neither prong of §768.36 holds",
    inputs=_inputs(
        fact_pattern="controlled_intersection",
        evidence_items=_GC04_EVIDENCE,
        intox=IntoxicationEvidence(
            bac_value=Decimal("0.05"),
            impairment_observed=False,
            causation_to_fault_evidence_cites=["er-tox-1"],
        ),
    ),
    expected_bar_triggered=True,  # HB 837 still fires on the apportionment
    expected_bar_basis="hb837_51_pct",
    expected_doctrines_not_applied=["intoxication_bar_768_36"],
)

GC_10 = LiabilityEvalCase(
    case_id="GC-10",
    description="Natural-person owner vicarious cap (§324.021(9)(b)3)",
    inputs=_inputs(
        owner_type="natural_person",
        driver_is_owner=False,
        permissive_user_coverage_limits=Decimal("500000"),
    ),
    expected_vicarious_cap_applies=True,
    expected_vicarious_cap_value=Decimal("300000"),  # per-occurrence ceiling
    expected_doctrines_applied=[
        "natural_person_owner_cap", "dangerous_instrumentality",
    ],
)

GC_11 = LiabilityEvalCase(
    case_id="GC-11",
    description="Graves Act preemption — commercial lessor, no neg-ent evidence",
    inputs=_inputs(
        owner_type="commercial_lessor_graves",
        driver_is_owner=False,
    ),
    expected_graves_lessor_removed=True,
    expected_vicarious_cap_applies=False,
    expected_doctrines_applied=["graves_preemption"],
)

GC_12 = LiabilityEvalCase(
    case_id="GC-12",
    description="Graves Act exception — owner-knowledge evidence kills preemption",
    inputs=_inputs(
        owner_type="commercial_lessor_graves",
        driver_is_owner=False,
        neg_ent=NegligentEntrustment(
            owner_knowledge_evidence_cites=["maint-log-1"],
        ),
    ),
    expected_graves_lessor_removed=False,
    expected_neg_ent_path_available=True,
    expected_doctrines_not_applied=["graves_preemption"],
)

GC_13 = LiabilityEvalCase(
    case_id="GC-13",
    description="Negligent entrustment uncapped path (driver unlicensed)",
    inputs=_inputs(
        owner_type="natural_person",
        driver_is_owner=False,
        neg_ent=NegligentEntrustment(driver_unlicensed=True),
    ),
    expected_neg_ent_path_available=True,
    expected_doctrines_applied=["negligent_entrustment_uncapped"],
)

GC_14 = LiabilityEvalCase(
    case_id="GC-14",
    description="Fabre non-party in the pie",
    inputs=_inputs(
        parties=[
            Party(party_id="P-insured", role="insured_driver", identity_evidence_cite="pr"),
            Party(party_id="P-claimant", role="claimant_driver", identity_evidence_cite="pr"),
            Party(party_id="P-fabre-1", role="fabre_non_party", identity_evidence_cite="ar-1"),
        ],
    ),
    expected_fabre_defendants_min_count=1,
    expected_doctrines_applied=["fabre_apportionment"],
)

GC_15 = LiabilityEvalCase(
    case_id="GC-15",
    description="Chain reaction — 50/50 baseline forces matrix view",
    inputs=_inputs(fact_pattern="chain_reaction"),
    expected_insured_fault_pct=Decimal("50"),
    expected_claimant_fault_pct=Decimal("50"),
    expected_bar_triggered=False,
)


GOLDEN_CASES = [
    GC_01, GC_02, GC_03, GC_04, GC_05, GC_06, GC_07, GC_08, GC_09, GC_10,
    GC_11, GC_12, GC_13, GC_14, GC_15,
]


@pytest.mark.eval
@pytest.mark.parametrize("case", GOLDEN_CASES, ids=[c.case_id for c in GOLDEN_CASES])
def test_golden(case: LiabilityEvalCase) -> None:
    ctx = run_case(case)
    assert_case(case, ctx)
