"""FL doctrine policy engine for the Recovery workflow.

Deterministic step-function gates that take RecoveryInputs +
RecoveryUpstreamContext + ProgramConfig and emit a DoctrineResolution
(SOL regime, recovery-bar status, gates fired, variance flags).

Per [[policy-engine-first-then-llm-extraction]]: every gate is a
specifiable rule with a binary or step-function effect. None of this lives
in the LLM. The LLM extracts facts; this engine routes them through FL
recovery law and emits per-gate evidence for the diligence ledger.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from argos.schemas.workflows.recovery import (
    ApplicableSolRegime,
    DoctrineGateResult,
    DoctrineResolution,
    RecoveryInputs,
    RecoveryUpstreamContext,
    VarianceFlag,
)
from argos.services.recovery.constants import (
    AF_COMPULSORY_CAP_DOLLARS,
    AF_SIGNATORY_ROSTER_V1,
    FL_RECOVERY_DOCTRINE_REGISTRY_V1,
    HB_837_EFFECTIVE_DATE,
    NEAR_BAR_WINDOW_PCT,
    SOL_ACCRUAL_FILING_SPLIT_WINDOW_DAYS,
    SOL_NEGLIGENCE_YEARS_POST_HB837,
    SOL_NEGLIGENCE_YEARS_PRE_HB837,
)


# =============================================================================
# SOL regime selector
# =============================================================================


def _years_to_date(start: date, years: int) -> date:
    try:
        return start.replace(year=start.year + years)
    except ValueError:
        # Feb 29 leap-year edge — fall back to Feb 28
        return start.replace(year=start.year + years, day=28)


def _resolve_sol_regime(
    inputs: RecoveryInputs, *, today: date,
) -> ApplicableSolRegime:
    if inputs.loss_date >= HB_837_EFFECTIVE_DATE:
        deadline = _years_to_date(inputs.loss_date, SOL_NEGLIGENCE_YEARS_POST_HB837)
        version = "post_hb837_2yr"
        cite = FL_RECOVERY_DOCTRINE_REGISTRY_V1["hb837_negligence_sol"].statute_or_case_cite
    else:
        deadline = _years_to_date(inputs.loss_date, SOL_NEGLIGENCE_YEARS_PRE_HB837)
        version = "pre_hb837_4yr"
        cite = "Fla. Stat. §95.11(3)(a) (pre-HB-837)"
    days_remaining = (deadline - today).days
    return ApplicableSolRegime(
        statute_version=version,  # type: ignore[arg-type]
        statute_cite=cite,
        sol_deadline=deadline,
        days_remaining=days_remaining,
    )


# =============================================================================
# Gate helpers — each returns a DoctrineGateResult
# =============================================================================


def _gate(
    gate_id: str,
    result: str,
    *,
    evidence_ref: str = "",
    variance_flag: VarianceFlag | None = None,
) -> DoctrineGateResult:
    seed = FL_RECOVERY_DOCTRINE_REGISTRY_V1[gate_id]
    return DoctrineGateResult(
        gate_id=gate_id,
        result=result,  # type: ignore[arg-type]
        statute_or_case_cite=seed.statute_or_case_cite,
        effect_if_fired=seed.effect,
        evidence_ref=evidence_ref,
        variance_flag_emitted=variance_flag,
    )


# =============================================================================
# Public entry point
# =============================================================================


def apply_fl_recovery_doctrines(
    inputs: RecoveryInputs,
    upstream: RecoveryUpstreamContext,
    *,
    today: date | None = None,
) -> DoctrineResolution:
    """Apply 15 FL recovery doctrines as step-function gates.

    Returns a DoctrineResolution with:
      - sol_regime: statute version, deadline, days remaining
      - recovery_barred + bar_basis: terminal blocking conditions
      - gates: ordered list with per-gate result + cite + evidence_ref
      - variance_flags: routing surfaces for the calculator + runner
    """
    eval_today = today or datetime.now().date()

    gates: list[DoctrineGateResult] = []
    variance_flags: list[VarianceFlag] = []
    recovery_barred = False
    bar_basis = ""

    # SOL regime selector
    sol_regime = _resolve_sol_regime(inputs, today=eval_today)
    gates.append(_gate(
        "hb837_negligence_sol",
        "pass" if sol_regime.days_remaining > 0 else "fail",
        evidence_ref=f"loss_date={inputs.loss_date}; sol_deadline={sol_regime.sol_deadline}",
    ))
    if sol_regime.days_remaining <= 0:
        recovery_barred = True
        bar_basis = "sol_expired"
    elif (
        abs((inputs.loss_date - HB_837_EFFECTIVE_DATE).days)
        <= SOL_ACCRUAL_FILING_SPLIT_WINDOW_DAYS
    ):
        variance_flags.append("sol_accrual_vs_filing_split")

    # Non-FL loss → abstain
    if inputs.loss_state != "FL":
        variance_flags.append("non_fl_loss_routed_to_abstain")
        recovery_barred = True
        bar_basis = "non_fl_loss"

    # HB 837 51% bar (from upstream Liability)
    if upstream.liability is not None:
        claimant_pct = upstream.liability.claimant_fault_pct
        if (
            sol_regime.statute_version == "post_hb837_2yr"
            and claimant_pct is not None
        ):
            if claimant_pct > Decimal("50"):
                gates.append(_gate(
                    "hb837_modified_comparative_bar",
                    "fail",
                    evidence_ref=f"upstream_liability.claimant_fault_pct={claimant_pct}",
                ))
                recovery_barred = True
                bar_basis = "hb_837_51_bar"
            else:
                gates.append(_gate(
                    "hb837_modified_comparative_bar",
                    "pass",
                    evidence_ref=f"claimant_fault_pct={claimant_pct} ≤50%",
                ))
                if abs(claimant_pct - Decimal("50")) <= NEAR_BAR_WINDOW_PCT:
                    variance_flags.append("comparative_fault_cliff_buffer")
        else:
            gates.append(_gate("hb837_modified_comparative_bar", "n_a"))
    else:
        gates.append(_gate(
            "hb837_modified_comparative_bar",
            "n_a",
            evidence_ref="upstream Liability snapshot not provided",
        ))

    # Anti-subrogation (per coverage section)
    omnibus_overlap = _anti_subrogation_overlap(inputs, upstream)
    if omnibus_overlap:
        # Per-coverage-section analysis required if ambiguous
        gates.append(_gate(
            "anti_subrogation_rule",
            "ambiguous_routed_to_senior",
            evidence_ref=f"overlap: {omnibus_overlap}",
            variance_flag="anti_subrogation_per_coverage_section_ambiguity",
        ))
        variance_flags.append("anti_subrogation_per_coverage_section_ambiguity")
    else:
        gates.append(_gate("anti_subrogation_rule", "pass"))

    # Made-whole doctrine
    made_whole_gate, made_whole_variance = _made_whole_gate(inputs, upstream)
    gates.append(made_whole_gate)
    if made_whole_variance is not None:
        variance_flags.append(made_whole_variance)

    # PIP subrogability (§627.7405)
    pip_gate = _pip_subrogability_gate(inputs)
    gates.append(pip_gate)
    if pip_gate.result == "ambiguous_routed_to_senior":
        variance_flags.append("commercial_vehicle_classification_ambiguity")
    # If PIP-only file and not commercial → abstain
    if (
        inputs.subrogation_lane == "627_7405_pip_commercial"
        and inputs.tortfeasor_vehicle_classification != "commercial"
    ):
        recovery_barred = True
        bar_basis = "pip_non_commercial"

    # UM preservation §627.727(6)
    gates.append(_um_preservation_gate(inputs, today=eval_today))

    # Collateral source §768.76(7)
    gates.append(_collateral_source_gate(inputs, today=eval_today))

    # §324.021(9)(b)3 vicarious cap — informational gate (used by calculator)
    gates.append(_vicarious_cap_gate(inputs))

    # §768.81(3) joint-and-several abolished + Fabre — always informational
    gates.append(_gate(
        "joint_several_abolition_768_81_3",
        "pass",
        evidence_ref=f"fabre_candidates={len(inputs.fabre_candidate_nonparties)}",
    ))

    # §627.737 verbal threshold
    gates.append(_verbal_threshold_gate(inputs))

    # §768.0427 paid-not-billed
    gates.append(_gate(
        "paid_not_billed_768_0427",
        "pass" if inputs.loss_date >= HB_837_EFFECTIVE_DATE else "n_a",
        evidence_ref=f"loss_date={inputs.loss_date}; filing_date={inputs.claim_filing_date}",
    ))

    # AF compulsory jurisdiction
    af_gate, af_variance = _af_compulsory_gate(inputs, upstream)
    gates.append(af_gate)
    if af_variance is not None:
        variance_flags.append(af_variance)

    # Spoliation (Valcin / Martino) — preservation duty
    spoliation_gate, spoliation_variance = _spoliation_gate(inputs)
    gates.append(spoliation_gate)
    if spoliation_variance is not None:
        variance_flags.append(spoliation_variance)

    # Deny+subrogate interlock
    deny_gate, deny_variance = _deny_subrogate_gate(inputs, upstream)
    gates.append(deny_gate)
    if deny_variance is not None:
        variance_flags.append(deny_variance)

    # WQBA step-into-shoes — release/settlement screen
    wqba_gate = _wqba_release_screen(inputs)
    gates.append(wqba_gate)
    if wqba_gate.result == "fail":
        recovery_barred = True
        bar_basis = "pre_tender_release"
        variance_flags.append("release_or_pre_tender_settlement_detected")

    return DoctrineResolution(
        gates=gates,
        sol_regime=sol_regime,
        recovery_barred=recovery_barred,
        bar_basis=bar_basis,
        variance_flags=variance_flags,
    )


# =============================================================================
# Per-gate logic
# =============================================================================


def _anti_subrogation_overlap(
    inputs: RecoveryInputs, upstream: RecoveryUpstreamContext,
) -> list[str]:
    """Return omnibus party names overlapping with tortfeasor identifiers."""
    # v1: extractor populates the roster; overlap is structurally surfaced if
    # the tortfeasor operator_id appears in the omnibus roster, AND the paid
    # loss coverage_section was the same one that names them as insured.
    roster = inputs.named_insured_and_omnibus_roster
    if upstream.coverage is not None and upstream.coverage.omnibus_roster:
        roster = roster + upstream.coverage.omnibus_roster
    if not roster:
        return []
    tortfeasor_name = inputs.owner_operator_split.operator_id
    overlap = [
        r.name for r in roster
        if r.name == tortfeasor_name or r.name == inputs.owner_operator_split.owner_id
    ]
    return overlap


def _made_whole_gate(
    inputs: RecoveryInputs, upstream: RecoveryUpstreamContext,
) -> tuple[DoctrineGateResult, VarianceFlag | None]:
    has_waiver = inputs.policy_subrogation_language.has_made_whole_waiver
    has_partial_recovery = any(
        cs.amount > 0 for cs in inputs.collateral_source_payments
    )

    if has_waiver:
        return _gate(
            "made_whole_doctrine", "pass",
            evidence_ref="contractual made-whole waiver present",
        ), None

    if upstream.reserve is None:
        return _gate("made_whole_doctrine", "n_a", evidence_ref="Reserve snapshot absent"), None

    total_paid = sum(upstream.reserve.paid_indemnity_by_component.values(), Decimal("0"))
    economic_loss = upstream.reserve.total_economic_loss
    shortfall = max(Decimal("0"), economic_loss - total_paid)

    if shortfall > 0 and has_partial_recovery and not has_waiver:
        return _gate(
            "made_whole_doctrine", "ambiguous_routed_to_senior",
            evidence_ref=(
                f"shortfall=${shortfall}; partial recovery present; no waiver"
            ),
            variance_flag="made_whole_with_partial_settlement",
        ), "made_whole_with_partial_settlement"

    return _gate(
        "made_whole_doctrine", "pass",
        evidence_ref=f"shortfall=${shortfall}; freestanding direct claim path",
    ), None


def _pip_subrogability_gate(inputs: RecoveryInputs) -> DoctrineGateResult:
    if inputs.subrogation_lane != "627_7405_pip_commercial":
        return _gate("pip_subrogability_627_7405", "n_a")
    if inputs.tortfeasor_vehicle_classification == "commercial":
        return _gate(
            "pip_subrogability_627_7405", "pass",
            evidence_ref="tortfeasor commercial — §627.7405 carve-out applies",
        )
    if inputs.tortfeasor_vehicle_classification == "unknown":
        return _gate(
            "pip_subrogability_627_7405",
            "ambiguous_routed_to_senior",
            evidence_ref="commercial classification ambiguous",
            variance_flag="commercial_vehicle_classification_ambiguity",
        )
    return _gate(
        "pip_subrogability_627_7405", "fail",
        evidence_ref=f"vehicle classification={inputs.tortfeasor_vehicle_classification}",
    )


def _um_preservation_gate(
    inputs: RecoveryInputs, *, today: date,
) -> DoctrineGateResult:
    triggers = inputs.external_event_triggers
    if triggers is None or triggers.liability_carrier_offer_date is None:
        return _gate(
            "um_preservation_627_727_6", "n_a",
            evidence_ref="no liability-carrier offer recorded",
        )
    days_since_offer = (today - triggers.liability_carrier_offer_date).days
    if days_since_offer > 30:
        return _gate(
            "um_preservation_627_727_6", "fail",
            evidence_ref=(
                f"liability_carrier_offer_date={triggers.liability_carrier_offer_date}; "
                f"{days_since_offer}d elapsed > 30-day window"
            ),
        )
    return _gate(
        "um_preservation_627_727_6", "pass",
        evidence_ref=f"{30 - days_since_offer}d remaining in 30-day window",
    )


def _collateral_source_gate(
    inputs: RecoveryInputs, *, today: date,
) -> DoctrineGateResult:
    triggers = inputs.external_event_triggers
    if triggers is None or triggers.section_768_76_notice_date is None:
        return _gate(
            "collateral_source_768_76", "n_a",
            evidence_ref="no §768.76 notice recorded",
        )
    days_since = (today - triggers.section_768_76_notice_date).days
    if days_since > 30:
        return _gate(
            "collateral_source_768_76", "fail",
            evidence_ref=f"notice_date={triggers.section_768_76_notice_date}; {days_since}d > 30",
        )
    return _gate(
        "collateral_source_768_76", "pass",
        evidence_ref=f"{30 - days_since}d remaining in 30-day window",
    )


def _vicarious_cap_gate(inputs: RecoveryInputs) -> DoctrineGateResult:
    split = inputs.owner_operator_split
    if split.are_same:
        return _gate(
            "vicarious_cap_324_021", "n_a",
            evidence_ref="owner == operator; vicarious-cap layer not in play",
        )
    if split.owner_type != "natural_person":
        return _gate(
            "vicarious_cap_324_021", "n_a",
            evidence_ref=f"owner_type={split.owner_type}; §324.021 cap is natural-person-only",
        )
    return _gate(
        "vicarious_cap_324_021", "pass",
        evidence_ref="natural-person owner ≠ operator; cap layer applies",
    )


def _verbal_threshold_gate(inputs: RecoveryInputs) -> DoctrineGateResult:
    ev = inputs.verbal_threshold_evidence
    if ev is None:
        return _gate(
            "verbal_threshold_627_737", "n_a",
            evidence_ref="verbal-threshold evidence not extracted",
        )
    met = (
        ev.permanency_opinion
        or ev.scarring
        or ev.significant_function_loss
        or ev.mri_findings
    )
    return _gate(
        "verbal_threshold_627_737",
        "pass" if met else "fail",
        evidence_ref=(
            f"permanency={ev.permanency_opinion}; scarring={ev.scarring}; "
            f"function_loss={ev.significant_function_loss}; mri={ev.mri_findings}"
        ),
    )


def _af_compulsory_gate(
    inputs: RecoveryInputs, upstream: RecoveryUpstreamContext,
) -> tuple[DoctrineGateResult, VarianceFlag | None]:
    naic = inputs.tortfeasor_carrier_naic
    if naic is None:
        return _gate(
            "af_compulsory_jurisdiction",
            "ambiguous_routed_to_senior",
            evidence_ref="tortfeasor carrier NAIC missing",
            variance_flag="af_signatory_unverifiable",
        ), "af_signatory_unverifiable"
    signatory = AF_SIGNATORY_ROSTER_V1.get(naic)
    if signatory is None:
        return _gate(
            "af_compulsory_jurisdiction",
            "ambiguous_routed_to_senior",
            evidence_ref=f"naic={naic} not in seed signatory roster",
            variance_flag="af_signatory_unverifiable",
        ), "af_signatory_unverifiable"

    # Compute company-paid damages from upstream Reserve
    total_paid = (
        sum(upstream.reserve.paid_indemnity_by_component.values(), Decimal("0"))
        if upstream.reserve is not None else Decimal("0")
    )
    within_cap = total_paid <= AF_COMPULSORY_CAP_DOLLARS

    if signatory and within_cap:
        return _gate(
            "af_compulsory_jurisdiction", "pass",
            evidence_ref=(
                f"naic={naic} signatory; paid=${total_paid} ≤ ${AF_COMPULSORY_CAP_DOLLARS}"
            ),
        ), None
    if signatory and not within_cap:
        return _gate(
            "af_compulsory_jurisdiction", "n_a",
            evidence_ref=f"paid=${total_paid} > AF cap ${AF_COMPULSORY_CAP_DOLLARS}; litigation lane",
        ), None
    return _gate(
        "af_compulsory_jurisdiction", "fail",
        evidence_ref=f"naic={naic} non-signatory; AF not compulsory",
    ), None


def _spoliation_gate(
    inputs: RecoveryInputs,
) -> tuple[DoctrineGateResult, VarianceFlag | None]:
    artifacts = inputs.evidence_artifacts
    if artifacts.vehicle_status in ("released_to_salvage", "scrapped"):
        return _gate(
            "spoliation_valcin_martino",
            "fail",
            evidence_ref=f"vehicle_status={artifacts.vehicle_status}; preservation duty breached",
            variance_flag="preservation_hold_unacknowledged",
        ), "preservation_hold_unacknowledged"
    if artifacts.vehicle_status == "in_storage_yard" and not artifacts.edr_pulled:
        return _gate(
            "spoliation_valcin_martino", "pass",
            evidence_ref="vehicle in storage; preservation hold required before release",
        ), None
    return _gate(
        "spoliation_valcin_martino", "pass",
        evidence_ref=f"vehicle_status={artifacts.vehicle_status}; edr_pulled={artifacts.edr_pulled}",
    ), None


def _deny_subrogate_gate(
    inputs: RecoveryInputs, upstream: RecoveryUpstreamContext,
) -> tuple[DoctrineGateResult, VarianceFlag | None]:
    coverage_denied = (
        (upstream.coverage is not None and upstream.coverage.status == "denied")
        or (
            inputs.coverage_denial_status is not None
            and inputs.coverage_denial_status.denied
        )
    )
    if coverage_denied:
        return _gate(
            "deny_subrogate_interlock",
            "ambiguous_routed_to_senior",
            evidence_ref="coverage denied + recovery pursuit candidate",
            variance_flag="deny_plus_subrogate",
        ), "deny_plus_subrogate"
    return _gate("deny_subrogate_interlock", "pass"), None


def _wqba_release_screen(inputs: RecoveryInputs) -> DoctrineGateResult:
    if not inputs.release_or_settlement_signals:
        return _gate(
            "step_into_shoes_defenses", "pass",
            evidence_ref="no release / pre-tender settlement signals detected",
        )
    # Any release signal → fail, surface for legal review
    signal_summary = ", ".join(
        f"{s.type}@{s.signal_date}" for s in inputs.release_or_settlement_signals
    )
    return _gate(
        "step_into_shoes_defenses", "fail",
        evidence_ref=f"release signals detected: {signal_summary}",
    )
