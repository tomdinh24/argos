"""Closure workflow — assessment calculator.

Pure-Python composition of:
- DoctrineResolution (from policy engine)
- ClosureInputs + upstream snapshots

into a ClosureAssessment with:
- recommendation literal (one of 11)
- ranked blocking_defects
- ready_probability (tier-capped)
- indemnity / defense / OIR statuses
- AuthorityRouting
- PreservationPlan

Spec: docs/specs/closure-workflow.md §5.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from argos.schemas.workflows.closure import (
    AuthorityRouting,
    AuthorityTier,
    BlockingDefect,
    ClosureAssessment,
    ClosureDiligenceLedger,
    ClosureGateResult,
    ClosureInputs,
    ClosureProgramConfig,
    ClosureUpstreamContext,
    DefenseStatus,
    DoctrineResolution,
    IndemnityStatus,
    OirClassification,
    PreservationPlan,
    Recommendation,
)
from argos.services.closure.constants import (
    FL_ADMIN_CODE_RECORD_RETENTION_YEARS,
    FL_CLOSURE_GATE_REGISTRY_V1,
    HIPAA_RETENTION_YEARS,
    MSP_RECOVERY_TAIL_YEARS,
    SOL_NEGLIGENCE_YEARS_POST_HB837,
    TIER_FAILURE_PROBABILITY_CAP,
    TPA_CONTRACT_RETENTION_YEARS_AFTER_TERMINATION,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


TIER_RANK = {"A": 0, "B": 1, "C": 2, "D": 3, "E": 4, "F": 5}


def _rank_defects(gates: list[ClosureGateResult]) -> list[BlockingDefect]:
    """Promote every failed gate into a BlockingDefect; rank A→F."""
    fails = [g for g in gates if g.result == "fail"]
    fails.sort(key=lambda g: (TIER_RANK.get(g.tier, 9), g.gate_id))
    return [
        BlockingDefect(
            gate_id=g.gate_id,
            tier=g.tier,
            description=FL_CLOSURE_GATE_REGISTRY_V1[g.gate_id].description
            if g.gate_id in FL_CLOSURE_GATE_REGISTRY_V1
            else g.gate_id,
            statute_or_case_cite=g.statute_or_case_cite,
            evidence_ref=g.evidence_ref,
            remediation_action=g.remediation_action,
        )
        for g in fails
    ]


def _ready_probability(doc: DoctrineResolution) -> float:
    """Cap ready_probability by worst-tier failure."""
    fail_tiers = {g.tier for g in doc.gates if g.result == "fail"}
    if not fail_tiers:
        return 0.95
    worst = min(fail_tiers, key=lambda t: TIER_RANK.get(t, 9))
    return TIER_FAILURE_PROBABILITY_CAP.get(worst, 0.50)


def _route_authority(
    inputs: ClosureInputs,
    program_config: ClosureProgramConfig,
) -> AuthorityRouting:
    """Pick tier ladder by settlement amount."""
    amt = inputs.settlement.agreement_amount or Decimal("0")
    if amt <= program_config.closure_examiner_authority_dollars:
        tier: AuthorityTier = "examiner"
        committable = True
    elif amt <= program_config.closure_senior_examiner_authority_dollars:
        tier = "senior_examiner"
        committable = False
    elif amt <= program_config.closure_supervisor_authority_dollars:
        tier = "supervisor"
        committable = False
    elif amt <= program_config.closure_manager_authority_dollars:
        tier = "manager"
        committable = False
    else:
        tier = "roundtable"
        committable = False
    return AuthorityRouting(
        committable_at_examiner=committable,
        required_tier=tier,
        settlement_amount=amt,
        basis_for_tier=(
            f"settlement_amount=${amt} routed against examiner=$"
            f"{program_config.closure_examiner_authority_dollars}, "
            f"senior=${program_config.closure_senior_examiner_authority_dollars}, "
            f"supervisor=${program_config.closure_supervisor_authority_dollars}, "
            f"manager=${program_config.closure_manager_authority_dollars}"
        ),
    )


def _build_preservation_plan(
    inputs: ClosureInputs,
    *,
    today: date,
) -> PreservationPlan:
    """Compute retention-floor max + held-data-source list."""
    floor: dict[str, date] = {}
    floor["sol_post_hb837"] = inputs.loss_date + timedelta(
        days=365 * SOL_NEGLIGENCE_YEARS_POST_HB837,
    )
    if inputs.last_cms_cpn_date:
        floor["msp_recovery_tail"] = inputs.last_cms_cpn_date + timedelta(
            days=365 * MSP_RECOVERY_TAIL_YEARS,
        )
    if inputs.last_phi_authorization_end_date:
        floor["hipaa_retention"] = inputs.last_phi_authorization_end_date + timedelta(
            days=365 * HIPAA_RETENTION_YEARS,
        )
    if inputs.tpa_contract_termination_date:
        floor["tpa_contract_floor"] = inputs.tpa_contract_termination_date + timedelta(
            days=365 * TPA_CONTRACT_RETENTION_YEARS_AFTER_TERMINATION,
        )
    floor["fl_admin_code_regulatory_floor"] = today + timedelta(
        days=365 * FL_ADMIN_CODE_RECORD_RETENTION_YEARS,
    )
    preservation_until = max(floor.values()) if floor else None

    data_sources_held = [
        "claim_file_complete",
        "recorded_statements",
        "adjuster_notes",
        "diligence_ledger",
        "denial_letter_correspondence" if inputs.denial_letter_audit.on_file else "",
        "lien_correspondence" if inputs.liens else "",
        "settlement_release" if inputs.settlement.release_executed_date else "",
        "section_111_transmit_log" if inputs.section_111_log else "",
    ]
    data_sources_held = [s for s in data_sources_held if s]

    return PreservationPlan(
        preservation_until_date=preservation_until,
        floor_components=floor,
        data_sources_held=data_sources_held,
    )


def _pick_recommendation(
    doc: DoctrineResolution,
    inputs: ClosureInputs,
    upstream: ClosureUpstreamContext,
    authority: AuthorityRouting,
) -> Recommendation:
    """Pick from the 11 recommendation literals.

    Decision lattice (top to bottom; first match wins):
    1. recommend_reopen — caller signals reopen posture (handled upstream of this).
    2. requires_legal_review — Macola pattern, Powell unfulfilled with damages exceeding limits,
       or insurer in apparent excess trajectory.
    3. requires_senior_review — variance flags requiring escalation OR authority above examiner.
    4. blocked_by_defects — any Tier A/B/C fail with no soft-close path.
    5. soft_close_pending_medicare_final_demand — only Medicare unresolved.
    6. soft_close_pending_section_111_confirmation — only §111 transmit pending.
    7. soft_close_pending_lien_release_letter — only lien releases outstanding.
    8. soft_close_pending_release_execution — agreement reached, release not signed yet.
    9. closed_with_open_recovery — close ledger, recovery file remains open.
    10. ready_to_close_with_payment / ready_to_close_without_payment — clean path.
    """
    # Macola or Powell-unfulfilled or open-defense-track → legal review
    gate_ids_fail = {g.gate_id for g in doc.gates if g.result == "fail"}
    if (
        "macola_settlement_after_excess_trajectory" in gate_ids_fail
        or "powell_duty_unfulfilled" in gate_ids_fail
        or "open_defense_track_post_interpleader" in gate_ids_fail
    ):
        return "requires_legal_review"

    # Escalation flags / above-examiner authority → senior review
    from argos.services.closure.constants import MANDATORY_ESCALATION_VARIANCE_FLAGS

    if any(f in MANDATORY_ESCALATION_VARIANCE_FLAGS for f in doc.variance_flags):
        return "requires_senior_review"
    if not authority.committable_at_examiner and not gate_ids_fail:
        return "requires_senior_review"

    # Classify the failing gates to see if a soft-close path applies.
    medicare_gates = {"medicare_msp_unresolved", "section_111_tpoc_unreported"}
    lien_gates = {
        "florida_medicaid_lien_unresolved",
        "workers_comp_lien_unsatisfied",
        "erisa_self_funded_lien_unresolved",
        "hospital_lien_unresolved",
        "va_tricare_recovery_pending",
        "release_does_not_address_known_liens",
    }
    medicare_only = (
        gate_ids_fail
        and gate_ids_fail.issubset(medicare_gates)
        and "medicare_msp_unresolved" in gate_ids_fail
    )
    section_111_only = gate_ids_fail == {"section_111_tpoc_unreported"}
    lien_only = gate_ids_fail and gate_ids_fail.issubset(lien_gates)
    release_only = gate_ids_fail == {"missing_signed_release"}

    if medicare_only:
        return "soft_close_pending_medicare_final_demand"
    if section_111_only:
        return "soft_close_pending_section_111_confirmation"
    if lien_only:
        return "soft_close_pending_lien_release_letter"
    if release_only:
        return "soft_close_pending_release_execution"

    if gate_ids_fail:
        return "blocked_by_defects"

    # Recovery decoupling — close ledger but keep recovery file open
    rec = upstream.recovery
    if rec and rec.pursuit_decision_committed and rec.decision == "pursue":
        return "closed_with_open_recovery"

    # Clean path
    if doc.oir_classification == "closed_with_payment":
        return "ready_to_close_with_payment"
    if doc.oir_classification == "closed_without_payment":
        return "ready_to_close_without_payment"
    # Default fall-through
    return "blocked_by_defects"


def _pick_indemnity_defense(
    doc: DoctrineResolution,
    inputs: ClosureInputs,
    recommendation: Recommendation,
) -> tuple[IndemnityStatus, DefenseStatus]:
    """Bifurcate indemnity vs defense per §624.155(6)(a)."""
    if inputs.interpleader_indemnity_deposited and inputs.underlying_tort_actions_unresolved:
        return ("closed", "open")
    if recommendation in {"ready_to_close_with_payment", "ready_to_close_without_payment"}:
        return ("ready", "n_a")
    if recommendation.startswith("soft_close_"):
        return ("soft_closed_pending", "n_a")
    if recommendation == "closed_with_open_recovery":
        return ("closed", "n_a")
    return ("open", "n_a")


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------


def build_closure_assessment(
    inputs: ClosureInputs,
    upstream: ClosureUpstreamContext,
    program_config: ClosureProgramConfig,
    doctrine: DoctrineResolution,
    *,
    request_id: str,
    today: date,
    reviewed_as_of: datetime | None = None,
) -> ClosureAssessment:
    """Compose all calculator outputs into a ClosureAssessment.

    Diligence ledger is built here (skeleton); rationale text is set
    downstream by render_rationale().
    """
    blocking = _rank_defects(doctrine.gates)
    ready_p = _ready_probability(doctrine)
    authority = _route_authority(inputs, program_config)
    preservation = _build_preservation_plan(inputs, today=today)
    # PreservationPlan from policy engine carries the same until-date;
    # we keep the doctrine's value authoritative if set.
    if doctrine.preservation_until_date:
        preservation = PreservationPlan(
            preservation_until_date=doctrine.preservation_until_date,
            floor_components=preservation.floor_components,
            data_sources_held=preservation.data_sources_held,
        )
    recommendation = _pick_recommendation(doctrine, inputs, upstream, authority)
    indemnity, defense = _pick_indemnity_defense(doctrine, inputs, recommendation)

    # Skeleton diligence ledger; rationale.render_ledger will enrich.
    ledger = ClosureDiligenceLedger(
        gates_evaluated=list(doctrine.gates),
        preservation_plan=preservation,
        record_classification=doctrine.oir_classification,
    )

    return ClosureAssessment(
        request_id=request_id,
        reviewed_as_of=reviewed_as_of or datetime.now(timezone.utc),
        recommendation=recommendation,
        ready_probability=ready_p,
        blocking_defects=blocking,
        indemnity_status=indemnity,
        defense_status=defense,
        oir_classification=doctrine.oir_classification,
        doctrinal_gates=list(doctrine.gates),
        preservation_plan=preservation,
        diligence_ledger=ledger,
        variance_flags=list(doctrine.variance_flags),
        authority_tier_required=authority,
    )
