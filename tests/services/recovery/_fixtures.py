"""Shared minimal RecoveryInputs + upstream context builders for tests."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from argos.schemas.workflows.recovery import (
    CoverageDenialStatus,
    EvidenceArtifacts,
    ExternalEventTriggers,
    OmnibusPartyEntry,
    OwnerOperatorSplit,
    PolicySubrogationLanguage,
    RecoveryInputs,
    RecoveryUpstreamContext,
    UpstreamCoverageSnapshot,
    UpstreamLiabilitySnapshot,
    UpstreamReserveSnapshot,
)


POST_HB837_LOSS = date(2025, 6, 2)
PRE_HB837_LOSS = date(2022, 6, 2)


def make_inputs(
    *,
    loss_date: date = POST_HB837_LOSS,
    loss_state: str = "FL",
    tortfeasor_vehicle_classification: str = "private_passenger",
    tortfeasor_carrier_naic: str | None = "25178",  # State Farm seed signatory
    subrogation_lane: str = "legal",
    owner_operator_split: OwnerOperatorSplit | None = None,
    omnibus_roster: list[OmnibusPartyEntry] | None = None,
    external_event_triggers: ExternalEventTriggers | None = None,
    evidence_artifacts: EvidenceArtifacts | None = None,
    has_made_whole_waiver: bool = False,
    coverage_denial: CoverageDenialStatus | None = None,
    vin: str | None = "1HGCM82633A123456",
) -> RecoveryInputs:
    return RecoveryInputs(
        loss_date=loss_date,
        loss_state=loss_state,  # type: ignore[arg-type]
        claim_filing_date=None,
        tortfeasor_vehicle_classification=tortfeasor_vehicle_classification,  # type: ignore[arg-type]
        tortfeasor_vehicle_vin=vin,
        tortfeasor_carrier_naic=tortfeasor_carrier_naic,
        owner_operator_split=owner_operator_split or OwnerOperatorSplit(
            owner_id="P-tortfeasor-operator",
            operator_id="P-tortfeasor-operator",
            are_same=True,
            owner_type="natural_person",
        ),
        named_insured_and_omnibus_roster=omnibus_roster or [],
        policy_subrogation_language=PolicySubrogationLanguage(
            has_made_whole_waiver=has_made_whole_waiver,
        ),
        subrogation_lane=subrogation_lane,  # type: ignore[arg-type]
        evidence_artifacts=evidence_artifacts or EvidenceArtifacts(
            vehicle_status="in_storage_yard",
        ),
        external_event_triggers=external_event_triggers,
        coverage_denial_status=coverage_denial,
    )


def make_upstream(
    *,
    insured_pct: int = 80,
    claimant_pct: int = 20,
    regime: str = "modified_51_bar_hb837",
    bar_basis: str = "none",
    paid_indemnity: int = 25000,
    economic_loss: int = 30000,
    coverage_status: str = "granted",
    coverage_omnibus: list[OmnibusPartyEntry] | None = None,
) -> RecoveryUpstreamContext:
    apport = {
        "P-insured": Decimal(insured_pct),
        "P-tortfeasor-operator": Decimal(claimant_pct),
    }
    return RecoveryUpstreamContext(
        liability=UpstreamLiabilitySnapshot(
            apportionment_by_party_id=apport,
            insured_fault_pct=Decimal(insured_pct),
            claimant_fault_pct=Decimal(claimant_pct),
            operator_party_id="P-tortfeasor-operator",
            owner_party_id="P-tortfeasor-operator",
            regime_statute=regime,
            recovery_bar_triggered=False,
            bar_basis=bar_basis,
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
