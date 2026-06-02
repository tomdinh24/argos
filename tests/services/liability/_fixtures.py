"""Shared minimal LiabilityInputs builders for the deterministic-core tests."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from argos.schemas.workflows.liability import (
    EvidenceItem,
    IntoxicationEvidence,
    LiabilityInputs,
    NegligentEntrustment,
    OwnerRelationship,
    Party,
    PoliceReportFields,
    PostureSnapshot,
    RearEndRebuttal,
)


POST_HB837_LOSS = date(2025, 6, 2)
PRE_HB837_LOSS = date(2022, 6, 2)


def make_party(party_id: str, role: str, doc_id: str = "doc-id") -> Party:
    return Party(
        party_id=party_id,
        role=role,  # type: ignore[arg-type]
        identity_evidence_cite=doc_id,
    )


def make_inputs(
    *,
    accrual_date: date = POST_HB837_LOSS,
    line_of_business: str = "auto_bi",
    fact_pattern: str = "rear_end",
    owner_type: str = "natural_person",
    driver_is_owner: bool = True,
    evidence_items: list[EvidenceItem] | None = None,
    parties: list[Party] | None = None,
    police_report: bool = True,
    prior_posture: list[PostureSnapshot] | None = None,
    intox: IntoxicationEvidence | None = None,
    neg_ent: NegligentEntrustment | None = None,
    rear_end_rebuttal: RearEndRebuttal | None = None,
) -> LiabilityInputs:
    if parties is None:
        parties = [
            make_party("P-insured", "insured_driver", "police-rpt-1"),
            make_party("P-claimant", "claimant_driver", "police-rpt-1"),
        ]
    if evidence_items is None:
        evidence_items = []
    return LiabilityInputs(
        accrual_date=accrual_date,
        line_of_business=line_of_business,  # type: ignore[arg-type]
        parties=parties,
        fact_pattern=fact_pattern,  # type: ignore[arg-type]
        owner_relationship=OwnerRelationship(
            driver_is_owner=driver_is_owner,
            owner_type=owner_type,  # type: ignore[arg-type]
        ),
        negligent_entrustment_indicators=neg_ent or NegligentEntrustment(),
        intoxication_evidence=intox or IntoxicationEvidence(),
        rear_end_rebuttal_evidence=rear_end_rebuttal or RearEndRebuttal(),
        evidence_items=evidence_items,
        police_report_structured_fields=(
            PoliceReportFields(officer_narrative_text="Narrative.")
            if police_report
            else None
        ),
        prior_posture_history=prior_posture or [],
    )


def make_evidence(
    kind: str,
    *,
    fault_direction: str = "neutral",
    weight_class: str = "independent",
    admissibility: str = "admissible",
    source_doc_id: str = "doc-1",
    quoted_span: str = "verbatim quote",
) -> EvidenceItem:
    return EvidenceItem(
        kind=kind,  # type: ignore[arg-type]
        source_doc_id=source_doc_id,
        quoted_span=quoted_span,
        contemporaneity_hours_from_loss=24,
        fl_admissibility=admissibility,  # type: ignore[arg-type]
        represented_by_counsel_at_capture=False,
        fault_direction=fault_direction,  # type: ignore[arg-type]
        weight_class=weight_class,  # type: ignore[arg-type]
    )


def posture_snapshot(
    insured_pct: int, claimant_pct: int, *, eval_date: date = date(2025, 5, 1),
) -> PostureSnapshot:
    return PostureSnapshot(
        eval_date=eval_date,
        posture_by_party_id={
            "P-insured": Decimal(insured_pct),
            "P-claimant": Decimal(claimant_pct),
        },
        basis_summary="Prior posture (test fixture)",
    )
