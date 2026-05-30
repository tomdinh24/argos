"""Ontology types — Python shapes that mirror the Foundry object types.

Minimal subset, expanded as specialists need more. The eventual Foundry-backed
implementation reads OSDK-typed objects and adapts them to these shapes; the
synthetic fixtures construct them directly. Specialists code against these
types, not against the OSDK or the fixture layer.

Source of truth for the full set: foundry/ontology/object-types.yaml.
"""
from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


CoverageType = Literal[
    "auto_BI", "auto_PD", "auto_UM_UIM", "auto_collision",
    "auto_comprehensive", "auto_medpay", "auto_rental",
    "flood_building", "flood_contents", "flood_ICC",
]

CoverageStatus = Literal[
    "pending", "accepted", "denied", "reservation_of_rights"
]


class Policy(BaseModel):
    policy_id: str
    client_program_id: str
    policy_number: str
    named_insured_party_id: str
    policy_form: str  # e.g., "CA00" commercial auto, "PAP" personal auto
    jurisdiction_state: str


class PolicyPeriod(BaseModel):
    policy_period_id: str
    policy_id: str
    effective_from: date
    effective_to: date
    status: Literal["in_force", "expired", "cancelled", "non_renewed"]


class CoveragePart(BaseModel):
    coverage_part_id: str
    policy_period_id: str
    coverage_type: CoverageType
    limit_per_occurrence: float
    limit_per_person: float | None = None
    limit_aggregate: float | None = None
    deductible: float
    SIR: float | None = None
    sublimits_json: str | None = None
    exclusions_json: str | None = None


class ClaimExposure(BaseModel):
    exposure_id: str
    claim_id: str
    coverage_part_id: str
    claimant_party_id: str | None = None
    coverage_status: CoverageStatus = "pending"


class Document(BaseModel):
    document_id: str
    claim_id: str
    document_type: str
    received_date: date
    source: str
    body_text: str = Field(
        description="Plaintext content the specialist reads. In production this "
        "is post-extraction; here it's authored directly for the fixture.",
    )


class SyntheticClaim(BaseModel):
    """A populated in-memory claim, sufficient input for one specialist run.

    The fields included are the minimum a Coverage specialist needs to read.
    Other specialists will read additional state from the same fixture; we'll
    extend this type as they come online.
    """

    policy: Policy
    policy_period: PolicyPeriod
    coverage_parts: list[CoveragePart]
    exposure: ClaimExposure
    documents: list[Document]
    loss_date: date
    loss_facts: str

    def coverage_part_for_exposure(self) -> CoveragePart:
        for cp in self.coverage_parts:
            if cp.coverage_part_id == self.exposure.coverage_part_id:
                return cp
        raise ValueError(
            f"Exposure {self.exposure.exposure_id} references "
            f"coverage_part_id={self.exposure.coverage_part_id!r} which is not "
            f"in the fixture"
        )
