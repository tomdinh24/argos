"""FL doctrine policy engine for the Liability workflow.

Deterministic, step-function gates that take LiabilityInputs + ProgramConfig
and emit a DoctrineResolution (applicable regime, exposure ceiling, doctrines
applied). The apportionment calculator consumes this to bound and gate its
output.

Per [[policy-engine-first-then-llm-extraction]]: every gate here is a
specifiable rule with a binary or step-function effect. None of this lives in
the LLM. The LLM extracts facts; this engine routes them through FL law.
"""
from __future__ import annotations

from decimal import Decimal

from argos.schemas.workflows.liability import (
    ApplicableRegime,
    DoctrineResolution,
    ExposureCeiling,
    LiabilityInputs,
    ProgramConfig,
)
from argos.services.liability.constants import (
    HB_837_EFFECTIVE_DATE,
    INTOXICATION_BAC_THRESHOLD,
    INTOXICATION_FAULT_PCT_THRESHOLD,
    NATURAL_PERSON_OWNER_CAP_ECONOMIC_CONDITIONAL,
    NATURAL_PERSON_OWNER_CAP_PER_OCCURRENCE,
    NATURAL_PERSON_OWNER_CAP_PER_PERSON,
)


# =============================================================================
# Regime detection
# =============================================================================


def _resolve_regime(
    inputs: LiabilityInputs,
    *,
    insured_fault_pct: Decimal | None,
    claimant_fault_pct: Decimal | None,
) -> ApplicableRegime:
    """Determine which apportionment regime governs + whether recovery is barred.

    Three regimes — med-mal pure comparative, post-HB-837 modified 51% bar, and
    pre-HB-837 pure comparative. Bar detection is sensitive to who is the
    plaintiff (claimant); a >50% claimant-fault triggers the bar under HB 837.
    """
    if inputs.line_of_business == "med_mal":
        return ApplicableRegime(
            statute="med_mal_pure_comparative",
            recovery_bar_triggered=False,
            bar_basis="none",
            date_of_loss_governing=inputs.accrual_date,
            explanation=(
                "Medical-negligence line — pure comparative survives HB 837 "
                "(§768.81 carve-out)."
            ),
        )

    if inputs.accrual_date >= HB_837_EFFECTIVE_DATE:
        bar = (
            claimant_fault_pct is not None
            and claimant_fault_pct > Decimal("50")
        )
        return ApplicableRegime(
            statute="modified_51_bar_hb837",
            recovery_bar_triggered=bar,
            bar_basis="hb837_51_pct" if bar else "none",
            date_of_loss_governing=inputs.accrual_date,
            explanation=(
                f"Accrual date {inputs.accrual_date} ≥ {HB_837_EFFECTIVE_DATE} → "
                "HB 837 modified-comparative 51% bar applies (§768.81(6))."
            ),
        )

    return ApplicableRegime(
        statute="pure_comparative_pre_hb837",
        recovery_bar_triggered=False,
        bar_basis="none",
        date_of_loss_governing=inputs.accrual_date,
        explanation=(
            f"Accrual date {inputs.accrual_date} < {HB_837_EFFECTIVE_DATE} → "
            "pre-HB-837 pure comparative governs."
        ),
    )


# =============================================================================
# Intoxication bar (§768.36)
# =============================================================================


def _intoxication_bar_triggered(
    inputs: LiabilityInputs,
    *,
    claimant_fault_pct: Decimal | None,
) -> bool:
    """§768.36 dual-prong: impairment AND >50% fault-from-impairment causation.

    Either BAC≥0.08 OR observed impairment satisfies the first prong; the
    second prong requires evidence linking impairment to causation AND the
    claimant being >50% at fault. Both prongs must hold.
    """
    intox = inputs.intoxication_evidence
    prong_one = (
        (intox.bac_value is not None and intox.bac_value >= INTOXICATION_BAC_THRESHOLD)
        or intox.impairment_observed
    )
    if not prong_one:
        return False
    has_causation_evidence = len(intox.causation_to_fault_evidence_cites) > 0
    over_threshold = (
        claimant_fault_pct is not None
        and claimant_fault_pct > INTOXICATION_FAULT_PCT_THRESHOLD
    )
    return has_causation_evidence and over_threshold


# =============================================================================
# Exposure ceiling — Dangerous Instrumentality + Graves + Negligent Entrustment
# =============================================================================


def _resolve_exposure_ceiling(inputs: LiabilityInputs) -> ExposureCeiling:
    """Vicarious caps + Graves preemption + negligent-entrustment uncapped path.

    Branch order matters:
      1. Graves preempts FIRST for commercial lessors (unless negligent-maint
         / negligent-rental exception evidenced).
      2. Natural-person owner cap applies if owner is a natural person AND
         driver-is-owner is false (vicarious theory only — direct-driver
         exposure is uncapped).
      3. Negligent-entrustment uncapped path is *available* whenever owner-
         knowledge evidence exists; the calculator surfaces it as an
         alt-scenario but does not silently swap to it.
    """
    owner = inputs.owner_relationship
    neg_ent = inputs.negligent_entrustment_indicators

    # Graves first
    graves_lessor_removed = False
    if owner.owner_type == "commercial_lessor_graves":
        # Exception: any negligent-maintenance or negligent-rental signal
        # blocks preemption. v1 keys this off NegligentEntrustment owner-
        # knowledge evidence — full carve-out per Vargas v. Enterprise is
        # extractor-fed.
        graves_exception = len(neg_ent.owner_knowledge_evidence_cites) > 0
        graves_lessor_removed = not graves_exception

    # Natural-person cap (§324.021(9)(b)3)
    vicarious_cap_applies = (
        owner.owner_type == "natural_person"
        and not owner.driver_is_owner
        and not graves_lessor_removed
    )

    cap_value: Decimal | None = None
    econ_layer: Decimal | None = None
    if vicarious_cap_applies:
        if owner.permissive_user_coverage_limits is not None and (
            owner.permissive_user_coverage_limits
            >= NATURAL_PERSON_OWNER_CAP_PER_PERSON
        ):
            cap_value = NATURAL_PERSON_OWNER_CAP_PER_OCCURRENCE
            econ_layer = NATURAL_PERSON_OWNER_CAP_ECONOMIC_CONDITIONAL
        else:
            cap_value = NATURAL_PERSON_OWNER_CAP_PER_OCCURRENCE
            econ_layer = None

    neg_ent_path_available = (
        neg_ent.driver_unlicensed
        or neg_ent.driver_dui_history
        or neg_ent.driver_known_intoxicated_at_handoff
        or len(neg_ent.owner_knowledge_evidence_cites) > 0
    )

    return ExposureCeiling(
        vicarious_cap_applies=vicarious_cap_applies,
        vicarious_cap_value=cap_value,
        conditional_econ_layer=econ_layer,
        negligent_entrustment_uncapped_path_available=neg_ent_path_available,
        graves_lessor_removed=graves_lessor_removed,
        fabre_defendants=[
            p.party_id for p in inputs.parties if p.role == "fabre_non_party"
        ],
    )


# =============================================================================
# Public entry point
# =============================================================================


def apply_fl_doctrines(
    inputs: LiabilityInputs,
    program_config: ProgramConfig,
    *,
    insured_fault_pct: Decimal | None = None,
    claimant_fault_pct: Decimal | None = None,
) -> DoctrineResolution:
    """Apply FL doctrine gates and emit a DoctrineResolution.

    Optional `insured_fault_pct` / `claimant_fault_pct` let the calculator
    re-run this engine after computing apportionment to detect bar conditions
    (HB 837 >50% bar; §768.36 intoxication bar). On the first pass, omit them
    to get the regime + ceiling; on the second pass, pass them in.
    """
    del program_config  # v1: ProgramConfig only feeds authority routing, not gating

    regime = _resolve_regime(
        inputs,
        insured_fault_pct=insured_fault_pct,
        claimant_fault_pct=claimant_fault_pct,
    )

    intox_bar = _intoxication_bar_triggered(
        inputs, claimant_fault_pct=claimant_fault_pct,
    )
    if intox_bar:
        # §768.36 is the more dispositive substantive bar — when both fire,
        # surface intoxication as the bar basis. HB 837 doctrine is still in
        # doctrines_applied for the audit trail.
        regime = ApplicableRegime(
            statute=regime.statute,
            recovery_bar_triggered=True,
            bar_basis="768_36_intoxication",
            date_of_loss_governing=regime.date_of_loss_governing,
            explanation=(
                regime.explanation
                + " | §768.36 intoxication bar triggered "
                "(impairment + causation evidence + >50% fault)."
            ),
        )

    ceiling = _resolve_exposure_ceiling(inputs)

    doctrines_applied: list[str] = []
    if regime.statute == "modified_51_bar_hb837":
        doctrines_applied.append("hb_837_51_bar")
    elif regime.statute == "pure_comparative_pre_hb837":
        doctrines_applied.append("pure_comparative_pre_hb837")
    elif regime.statute == "med_mal_pure_comparative":
        doctrines_applied.append("med_mal_pure_comparative")

    if regime.bar_basis == "768_36_intoxication":
        doctrines_applied.append("intoxication_bar_768_36")
    if ceiling.graves_lessor_removed:
        doctrines_applied.append("graves_preemption")
    if ceiling.vicarious_cap_applies:
        doctrines_applied.append("natural_person_owner_cap")
        doctrines_applied.append("dangerous_instrumentality")
    if ceiling.negligent_entrustment_uncapped_path_available:
        doctrines_applied.append("negligent_entrustment_uncapped")
    if ceiling.fabre_defendants:
        doctrines_applied.append("fabre_apportionment")
    if inputs.fact_pattern == "rear_end":
        doctrines_applied.append("rear_end_rebuttable_presumption")
    # Joint-and-several is always-on for FL negligence — emit on every assessment
    doctrines_applied.append("joint_several_abolished")

    return DoctrineResolution(
        applicable_regime=regime,
        exposure_ceiling=ceiling,
        doctrines_applied=doctrines_applied,
    )
