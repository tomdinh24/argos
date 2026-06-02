"""Apportionment calculator — recoverable basis + layered targets + net economics.

Pure-function deterministic stage. Takes RecoveryInputs + RecoveryUpstreamContext
+ DoctrineResolution + ProgramConfig, emits a CalculationContext bundling:
  - recoverable_basis: §768.0427-capped damages − PIP collateral − made-whole shortfall
  - layered_targets: 5 layers with apportioned share + per-layer net economics
  - net_economics: gross − fee drag − fee-shifting exposure
  - forum_routing: AF vs litigation vs negotiated demand
  - deadline_calendar: SOL + AF + §768.76 + §627.727(6) + products repose
  - preservation_hold: scope + storage-yard letter + ack status
  - recommendation: pursue | route_to_af | abstain | senior_review_required | ...
  - authority_routing: tier + net apportioned recoverable
  - variance_flags + cross_stream_conflicts
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import NamedTuple

from argos.schemas.workflows.recovery import (
    AuthorityRouting,
    AuthorityTier,
    CrossStreamConflicts,
    DeadlineCalendar,
    DeadlineEntry,
    DoctrineResolution,
    ForumRouting,
    LayeredTarget,
    NetEconomics,
    PreservationHold,
    ProgramConfig,
    Recommendation,
    RecoverableBasis,
    RecoveryInputs,
    RecoveryUpstreamContext,
    SubrogationLane,
    VarianceFlag,
)
from argos.services.recovery.constants import (
    AF_COMPULSORY_CAP_DOLLARS,
    AF_FILING_FLAT_FEE_DOLLARS,
    MANDATORY_ESCALATION_VARIANCE_FLAGS,
    NATURAL_PERSON_OWNER_CAP_PD,
    NATURAL_PERSON_OWNER_CAP_PER_OCCURRENCE,
)


class CalculationContext(NamedTuple):
    """Everything rationale.py + diligence_ledger.py need to render."""

    inputs: RecoveryInputs
    upstream: RecoveryUpstreamContext
    resolution: DoctrineResolution
    program_config: ProgramConfig
    reviewed_as_of: datetime

    recommendation: Recommendation
    subrogation_lane: SubrogationLane
    layered_targets: list[LayeredTarget]
    recoverable_basis: RecoverableBasis
    net_economics: NetEconomics
    forum_routing: ForumRouting
    deadline_calendar: DeadlineCalendar
    preservation_hold: PreservationHold
    authority_routing: AuthorityRouting
    cross_stream_conflicts: CrossStreamConflicts
    variance_flags: list[VarianceFlag]


def _round2(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# =============================================================================
# Recoverable basis
# =============================================================================


def _compute_recoverable_basis(
    inputs: RecoveryInputs,
    upstream: RecoveryUpstreamContext,
) -> RecoverableBasis:
    """§768.0427-capped damages − PIP collateral source − made-whole shortfall."""
    # Capped damages — use Reserve's total_economic_loss as the
    # §768.0427-capped basis. v1 assumes upstream Reserve has already applied
    # the cap; if Reserve absent, use 0.
    capped_damages = (
        upstream.reserve.total_economic_loss
        if upstream.reserve is not None else Decimal("0")
    )

    # PIP / Medicare / Medicaid / WC collateral stripping
    stripped = sum(
        (cs.amount for cs in inputs.collateral_source_payments
         if cs.type in ("pip", "medicare", "medicaid", "workers_comp")),
        Decimal("0"),
    )

    # Made-whole shortfall — only when there's a contractual waiver gap
    has_waiver = inputs.policy_subrogation_language.has_made_whole_waiver
    shortfall = Decimal("0")
    if not has_waiver and upstream.reserve is not None:
        total_paid = sum(upstream.reserve.paid_indemnity_by_component.values(), Decimal("0"))
        shortfall = max(Decimal("0"), upstream.reserve.total_economic_loss - total_paid)
        # Carrier subrogation pursued direct against tortfeasor doesn't
        # subtract shortfall; this field is informational for ledger.
        # Keep at 0 for the basis math; the ledger surfaces it.
        shortfall = Decimal("0")

    basis = max(Decimal("0"), capped_damages - stripped - shortfall)
    return RecoverableBasis(
        section_768_0427_capped_damages=_round2(capped_damages),
        pip_collateral_source_stripped=_round2(stripped),
        made_whole_shortfall=_round2(shortfall),
        basis=_round2(basis),
    )


# =============================================================================
# Layered targets
# =============================================================================


def _layered_targets(
    inputs: RecoveryInputs,
    upstream: RecoveryUpstreamContext,
    basis: RecoverableBasis,
    program_config: ProgramConfig,
) -> list[LayeredTarget]:
    targets: list[LayeredTarget] = []
    if upstream.liability is None:
        return targets

    apport = upstream.liability.apportionment_by_party_id
    operator_id = upstream.liability.operator_party_id
    owner_id = upstream.liability.owner_party_id

    # Layer 1 — operator policy
    if operator_id is not None and operator_id in apport:
        op_pct = apport[operator_id]
        op_share = _round2(basis.basis * op_pct / Decimal("100"))
        targets.append(LayeredTarget(
            layer_id="operator_policy",
            target_party_id=operator_id,
            apportioned_fault_pct=op_pct,
            apportioned_share=op_share,
            cap_applied=None,
            gross_recoverable=op_share,
            probability_of_recovery=program_config.p_recovery_operator_policy,
            expected_value=_round2(op_share * Decimal(str(program_config.p_recovery_operator_policy))),
            evidence_completeness=upstream.liability.calibration_confidence,
        ))

    # Layer 2 — §324.021(9)(b)3 owner vicarious cap layer
    split = inputs.owner_operator_split
    if (
        owner_id is not None
        and owner_id in apport
        and not split.are_same
        and split.owner_type == "natural_person"
    ):
        owner_pct = apport[owner_id]
        owner_share = _round2(basis.basis * owner_pct / Decimal("100"))
        cap = NATURAL_PERSON_OWNER_CAP_PER_OCCURRENCE + NATURAL_PERSON_OWNER_CAP_PD
        capped = min(owner_share, cap)
        targets.append(LayeredTarget(
            layer_id="owner_vicarious_cap_324_021",
            target_party_id=owner_id,
            apportioned_fault_pct=owner_pct,
            apportioned_share=owner_share,
            cap_applied=cap,
            gross_recoverable=capped,
            probability_of_recovery=program_config.p_recovery_vicarious_cap,
            expected_value=_round2(capped * Decimal(str(program_config.p_recovery_vicarious_cap))),
            evidence_completeness=upstream.liability.calibration_confidence,
        ))

    # Layer 3 — owner direct-negligence (negligent entrustment) — uncapped
    neg_ent_evidenced = len(inputs.owner_knowledge_indicators) > 0
    if (
        neg_ent_evidenced
        and owner_id is not None
        and owner_id in apport
        and not split.are_same
    ):
        owner_pct = apport[owner_id]
        owner_share = _round2(basis.basis * owner_pct / Decimal("100"))
        targets.append(LayeredTarget(
            layer_id="owner_negligent_entrustment_uncapped",
            target_party_id=owner_id,
            apportioned_fault_pct=owner_pct,
            apportioned_share=owner_share,
            cap_applied=None,
            gross_recoverable=owner_share,
            probability_of_recovery=program_config.p_recovery_negligent_entrustment,
            expected_value=_round2(owner_share * Decimal(str(program_config.p_recovery_negligent_entrustment))),
            evidence_completeness=min(
                upstream.liability.calibration_confidence,
                0.5 + 0.1 * min(len(inputs.owner_knowledge_indicators), 5),
            ),
        ))

    # Layer 4 — Fabre non-parties
    for cand in inputs.fabre_candidate_nonparties:
        share = _round2(basis.basis * cand.estimated_fault_share / Decimal("100"))
        targets.append(LayeredTarget(
            layer_id="fabre_non_party",
            target_party_id=cand.party,
            apportioned_fault_pct=cand.estimated_fault_share,
            apportioned_share=share,
            cap_applied=None,
            gross_recoverable=share,
            probability_of_recovery=program_config.p_recovery_fabre_non_party,
            expected_value=_round2(share * Decimal(str(program_config.p_recovery_fabre_non_party))),
            evidence_completeness=0.4,  # Fabre non-parties carry lower evidence baseline
        ))

    # Layer 5 — product-defect / recall
    if inputs.tortfeasor_vehicle_vin is not None:
        # v1: no VIN → recall cross-reference; structural surface only
        targets.append(LayeredTarget(
            layer_id="product_defect_recall",
            target_party_id=None,
            apportioned_fault_pct=Decimal("0"),
            apportioned_share=Decimal("0"),
            cap_applied=None,
            gross_recoverable=Decimal("0"),
            probability_of_recovery=program_config.p_recovery_products_defect,
            expected_value=Decimal("0"),
            evidence_completeness=0.2,
        ))

    return targets


# =============================================================================
# Net economics
# =============================================================================


def _net_economics(
    targets: list[LayeredTarget],
    program_config: ProgramConfig,
    *,
    fee_model: str,
    is_pre_hb837: bool,
) -> NetEconomics:
    gross = sum((t.expected_value for t in targets), Decimal("0"))

    if fee_model == "af_flat":
        fee_drag = program_config.fee_drag_af_flat
    elif fee_model == "vendor_contingency":
        fee_drag = _round2(gross * program_config.fee_drag_vendor_contingency_pct)
    else:  # internal_blended
        fee_drag = _round2(
            program_config.fee_drag_internal_hourly_rate
            * program_config.fee_drag_internal_hours_per_file
        )

    # Pre-HB-837 §627.428 fee-shifting exposure — substantial reform repealed
    # this for post-3/24/2023 policies. v1 surfaces a fixed scalar for pre-
    # HB-837 only; per-program tuning is roadmap.
    fee_shifting = (
        _round2(gross * Decimal("0.10")) if is_pre_hb837 else Decimal("0")
    )

    net = max(Decimal("0"), gross - fee_drag - fee_shifting)
    return NetEconomics(
        gross_recoverable_total=_round2(gross),
        fee_drag=fee_drag,
        fee_shifting_exposure=fee_shifting,
        net_total=_round2(net),
        fee_model=fee_model,  # type: ignore[arg-type]
    )


# =============================================================================
# Forum routing
# =============================================================================


def _forum_routing(
    inputs: RecoveryInputs,
    upstream: RecoveryUpstreamContext,
    resolution: DoctrineResolution,
) -> ForumRouting:
    af_gate = next(
        (g for g in resolution.gates if g.gate_id == "af_compulsory_jurisdiction"),
        None,
    )
    total_paid = (
        sum(upstream.reserve.paid_indemnity_by_component.values(), Decimal("0"))
        if upstream.reserve is not None else Decimal("0")
    )
    within_cap = total_paid <= AF_COMPULSORY_CAP_DOLLARS

    if resolution.recovery_barred:
        return ForumRouting(
            recommendation="abstain",
            af_signatory_check="non_signatory" if (
                af_gate is not None and af_gate.result == "fail"
            ) else "unverifiable",
            company_paid_damages=_round2(total_paid),
            af_cap_dollars=AF_COMPULSORY_CAP_DOLLARS,
            within_af_cap=within_cap,
            basis=f"Recovery barred ({resolution.bar_basis})",
        )

    if af_gate is None or af_gate.result == "n_a":
        # Over-cap or signatory-N/A → litigation
        return ForumRouting(
            recommendation="litigation",
            af_signatory_check="signatory" if (
                inputs.tortfeasor_carrier_naic is not None
            ) else "unverifiable",
            company_paid_damages=_round2(total_paid),
            af_cap_dollars=AF_COMPULSORY_CAP_DOLLARS,
            within_af_cap=within_cap,
            basis="AF cap exceeded OR signatory check N/A",
        )

    if af_gate.result == "pass":
        return ForumRouting(
            recommendation="arbitration_forums",
            af_signatory_check="signatory",
            company_paid_damages=_round2(total_paid),
            af_cap_dollars=AF_COMPULSORY_CAP_DOLLARS,
            within_af_cap=within_cap,
            basis="Both carriers signatory; within compulsory cap",
        )

    if af_gate.result == "fail":
        return ForumRouting(
            recommendation="negotiated_demand",
            af_signatory_check="non_signatory",
            company_paid_damages=_round2(total_paid),
            af_cap_dollars=AF_COMPULSORY_CAP_DOLLARS,
            within_af_cap=within_cap,
            basis="Tortfeasor carrier non-signatory; AF not compulsory",
        )

    return ForumRouting(
        recommendation="tbd_signatory_check_pending",
        af_signatory_check="unverifiable",
        company_paid_damages=_round2(total_paid),
        af_cap_dollars=AF_COMPULSORY_CAP_DOLLARS,
        within_af_cap=within_cap,
        basis="Signatory check unverifiable; block forum routing until resolved",
    )


# =============================================================================
# Deadline calendar
# =============================================================================


def _deadline_calendar(
    inputs: RecoveryInputs,
    resolution: DoctrineResolution,
    *,
    today: date,
) -> DeadlineCalendar:
    entries: list[DeadlineEntry] = []

    # SOL drop-dead
    entries.append(DeadlineEntry(
        deadline_id="sol_drop_dead",
        deadline_date=resolution.sol_regime.sol_deadline,
        days_remaining=resolution.sol_regime.days_remaining,
        statute_or_rule_cite=resolution.sol_regime.statute_cite,
    ))

    triggers = inputs.external_event_triggers
    if triggers is not None:
        if triggers.liability_carrier_offer_date is not None:
            d = triggers.liability_carrier_offer_date + timedelta(days=30)
            entries.append(DeadlineEntry(
                deadline_id="section_627_727_6_30_day",
                deadline_date=d,
                days_remaining=(d - today).days,
                statute_or_rule_cite="Fla. Stat. §627.727(6)",
            ))
        if triggers.section_768_76_notice_date is not None:
            d = triggers.section_768_76_notice_date + timedelta(days=30)
            entries.append(DeadlineEntry(
                deadline_id="section_768_76_30_day",
                deadline_date=d,
                days_remaining=(d - today).days,
                statute_or_rule_cite="Fla. Stat. §768.76(7)",
            ))
        if triggers.af_dismissal_date is not None:
            d = triggers.af_dismissal_date + timedelta(days=60)
            entries.append(DeadlineEntry(
                deadline_id="af_60_day_refile",
                deadline_date=d,
                days_remaining=(d - today).days,
                statute_or_rule_cite="AF Reference Guide",
            ))

    return DeadlineCalendar(entries=entries)


# =============================================================================
# Preservation hold
# =============================================================================


def _preservation_hold(inputs: RecoveryInputs) -> PreservationHold:
    artifacts = inputs.evidence_artifacts
    if artifacts.vehicle_status in ("released_to_salvage", "scrapped"):
        return PreservationHold(
            issued=False,
            hold_scope=[],
            storage_yard_letter_text="",
            blocks_salvage_release=False,
            acknowledgment_status="not_required",
        )

    scope: list[str] = []
    if artifacts.vehicle_status in ("in_storage_yard", "totaled_held", "with_insured", "unknown"):
        scope.append("vehicle")
    if not artifacts.edr_pulled:
        scope.append("edr_acm")
    if not artifacts.scene_photos:
        scope.append("scene_photos")
    if artifacts.witness_contacts:
        scope.append("witness_statements")
    if artifacts.dashcam:
        scope.append("dashcam")

    letter = (
        "Storage Yard Preservation Notice: do not release, scrap, or otherwise dispose "
        "of the subject vehicle, its event data recorder (EDR/ACM), or any physical "
        "components without prior written authorization from the carrier. "
        "Failure to preserve may give rise to spoliation sanctions under "
        "Public Health Trust v. Valcin, 507 So. 2d 596 (Fla. 1987)."
    )
    return PreservationHold(
        issued=True,
        hold_scope=scope,  # type: ignore[arg-type]
        storage_yard_letter_text=letter,
        blocks_salvage_release=True,
        acknowledgment_status="pending",
    )


# =============================================================================
# Subrogation lane
# =============================================================================


def _subrogation_lane(inputs: RecoveryInputs) -> SubrogationLane:
    cite_map = {
        "legal": "FL common-law legal subrogation",
        "equitable": "Garrity / common-fund doctrine; equitable subrogation",
        "contractual": "Policy subrogation clause + Fla. Stat. §95.11(2)(b)",
        "627_7405_pip_commercial": "Fla. Stat. §627.7405 (PIP commercial carve-out)",
        "768_76_collateral_source": "Fla. Stat. §768.76(7)",
    }
    return SubrogationLane(
        lane_id=inputs.subrogation_lane,
        cite=cite_map[inputs.subrogation_lane],
        defense_checklist_anchor=f"step_into_shoes:{inputs.subrogation_lane}",
    )


# =============================================================================
# Recommendation + authority + cross-stream
# =============================================================================


def _recommendation(
    resolution: DoctrineResolution,
    forum: ForumRouting,
    net_economics: NetEconomics,
    variance_flags: list[VarianceFlag],
) -> Recommendation:
    if resolution.recovery_barred:
        return "abstain"
    if any(f in MANDATORY_ESCALATION_VARIANCE_FLAGS for f in variance_flags):
        return "senior_review_required"
    if net_economics.net_total <= 0:
        return "abstain"
    if forum.recommendation == "arbitration_forums":
        return "route_to_af"
    if forum.recommendation == "litigation":
        return "route_to_litigation"
    if forum.recommendation == "negotiated_demand":
        return "route_to_negotiated_demand"
    if forum.recommendation == "tbd_signatory_check_pending":
        return "senior_review_required"
    return "pursue"


def _authority_routing(
    net_economics: NetEconomics,
    program_config: ProgramConfig,
    variance_flags: list[VarianceFlag],
) -> AuthorityRouting:
    net = net_economics.net_total
    has_mandatory = any(f in MANDATORY_ESCALATION_VARIANCE_FLAGS for f in variance_flags)
    has_any_variance = bool(variance_flags) and any(
        f not in ("senior_review_recommended",) for f in variance_flags
    )

    if has_mandatory:
        return AuthorityRouting(
            committable_at_examiner=False,
            required_tier="roundtable",
            net_apportioned_recoverable=net,
            basis_for_tier=(
                "Mandatory-escalation variance flag active: "
                + ", ".join(f for f in variance_flags if f in MANDATORY_ESCALATION_VARIANCE_FLAGS)
            ),
        )
    if has_any_variance:
        return AuthorityRouting(
            committable_at_examiner=False,
            required_tier="senior_examiner",
            net_apportioned_recoverable=net,
            basis_for_tier=f"Non-mandatory variance flag active: {', '.join(variance_flags)}",
        )

    tier: AuthorityTier
    if net <= program_config.examiner_authority_dollars:
        tier = "examiner"
        committable = True
        basis = "Within examiner net authority; no variance flags"
    elif net <= program_config.senior_examiner_authority_dollars:
        tier = "senior_examiner"
        committable = False
        basis = "Within senior examiner authority"
    elif net <= program_config.supervisor_authority_dollars:
        tier = "supervisor"
        committable = False
        basis = "Within supervisor authority"
    elif net <= program_config.manager_authority_dollars:
        tier = "manager"
        committable = False
        basis = "Within manager authority"
    else:
        tier = "large_loss_committee"
        committable = False
        basis = "Net recoverable exceeds manager authority"

    return AuthorityRouting(
        committable_at_examiner=committable,
        required_tier=tier,
        net_apportioned_recoverable=net,
        basis_for_tier=basis,
    )


def _cross_stream_conflicts(
    inputs: RecoveryInputs,
    upstream: RecoveryUpstreamContext,
    variance_flags: list[VarianceFlag],
) -> CrossStreamConflicts:
    denial_interlock = "no_conflict"
    if "deny_plus_subrogate" in variance_flags:
        denial_interlock = "active_conflict_senior_review_required"

    omnibus_overlap: list[str] = []
    roster = inputs.named_insured_and_omnibus_roster
    if upstream.coverage is not None:
        roster = roster + upstream.coverage.omnibus_roster
    tortfeasor_ids = {
        inputs.owner_operator_split.operator_id,
        inputs.owner_operator_split.owner_id,
    }
    omnibus_overlap = [r.name for r in roster if r.name in tortfeasor_ids]

    cooperation_open = (
        upstream.coverage is not None
        and upstream.coverage.cooperation_defense_window_open
    )

    return CrossStreamConflicts(
        coverage_denial_recovery_pursuit_interlock=denial_interlock,  # type: ignore[arg-type]
        anti_subrogation_omnibus_overlap=omnibus_overlap,
        section_627_426_2_cooperation_window_open=cooperation_open,
    )


# =============================================================================
# Public entry point
# =============================================================================


def compute_recovery(
    inputs: RecoveryInputs,
    upstream: RecoveryUpstreamContext,
    resolution: DoctrineResolution,
    program_config: ProgramConfig,
    *,
    reviewed_as_of: datetime,
) -> CalculationContext:
    """Compute recoverable basis + layered targets + net economics + recommendation."""
    today = reviewed_as_of.date()

    basis = _compute_recoverable_basis(inputs, upstream)
    targets = _layered_targets(inputs, upstream, basis, program_config)

    # Fee model — examiner default is internal_blended; AF route uses flat;
    # vendor contingency is per-program.
    fee_model = "internal_blended"
    af_gate = next(
        (g for g in resolution.gates if g.gate_id == "af_compulsory_jurisdiction"),
        None,
    )
    if af_gate is not None and af_gate.result == "pass":
        fee_model = "af_flat"

    is_pre_hb837 = resolution.sol_regime.statute_version == "pre_hb837_4yr"
    net = _net_economics(targets, program_config, fee_model=fee_model, is_pre_hb837=is_pre_hb837)

    forum = _forum_routing(inputs, upstream, resolution)
    calendar = _deadline_calendar(inputs, resolution, today=today)
    hold = _preservation_hold(inputs)
    lane = _subrogation_lane(inputs)

    variance_flags = list(resolution.variance_flags)
    recommendation = _recommendation(resolution, forum, net, variance_flags)
    authority = _authority_routing(net, program_config, variance_flags)
    cross_stream = _cross_stream_conflicts(inputs, upstream, variance_flags)

    return CalculationContext(
        inputs=inputs,
        upstream=upstream,
        resolution=resolution,
        program_config=program_config,
        reviewed_as_of=reviewed_as_of,
        recommendation=recommendation,
        subrogation_lane=lane,
        layered_targets=targets,
        recoverable_basis=basis,
        net_economics=net,
        forum_routing=forum,
        deadline_calendar=calendar,
        preservation_hold=hold,
        authority_routing=authority,
        cross_stream_conflicts=cross_stream,
        variance_flags=variance_flags,
    )


__all__ = ["CalculationContext", "compute_recovery"]
