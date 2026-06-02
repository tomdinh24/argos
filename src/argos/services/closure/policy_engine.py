"""Closure workflow — FL closure-gate policy engine.

Pure-Python deterministic evaluation of ~25 closure gates organized
into 6 tiers. Spec: docs/specs/closure-workflow.md §4.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from argos.schemas.workflows.closure import (
    ClosureGateResult,
    ClosureInputs,
    ClosureProgramConfig,
    ClosureUpstreamContext,
    DoctrineResolution,
    OirClassification,
    VarianceFlag,
)
from argos.services.closure.constants import (
    AUTHORITY_TIER_RANK,
    CRN_CURE_WINDOW_DAYS,
    FL_ADMIN_CODE_RECORD_RETENTION_YEARS,
    FL_CLOSURE_GATE_REGISTRY_V1,
    HB_837_MULTI_CLAIMANT_SAFE_HARBOR_DAYS,
    HB_837_THIRD_PARTY_SAFE_HARBOR_DAYS,
    HIPAA_RETENTION_YEARS,
    MSP_RECOVERY_TAIL_YEARS,
    SECTION_111_TPOC_THRESHOLD_DOLLARS,
    SECTION_627_4137_AFFIDAVIT_DELIVERY_DAYS,
    SECTION_627_4265_TENDER_WINDOW_DAYS,
    SECTION_768_76_COLLATERAL_SOURCE_WAIVER_DAYS,
    SOL_NEGLIGENCE_YEARS_POST_HB837,
    TPA_CONTRACT_RETENTION_YEARS_AFTER_TERMINATION,
)


def _gate(
    gate_id: str,
    result: str,
    *,
    evidence_ref: str = "",
    remediation: str = "",
) -> ClosureGateResult:
    """Build a ClosureGateResult from the registry seed."""
    seed = FL_CLOSURE_GATE_REGISTRY_V1[gate_id]
    return ClosureGateResult(
        gate_id=gate_id,
        tier=seed.tier,
        result=result,  # type: ignore[arg-type]
        statute_or_case_cite=seed.statute_or_case_cite,
        evidence_ref=evidence_ref,
        defect_emitted=(result == "fail"),
        remediation_action=remediation,
    )


def apply_fl_closure_gates(
    inputs: ClosureInputs,
    upstream: ClosureUpstreamContext,
    program_config: ClosureProgramConfig,
    *,
    today: date,
) -> DoctrineResolution:
    """Evaluate all 25+ closure gates and bundle into a DoctrineResolution."""
    gates: list[ClosureGateResult] = []
    flags: list[VarianceFlag] = []

    # -----------------------------------------------------------------
    # Tier A — Statutory FL + bad-faith
    # -----------------------------------------------------------------

    # A1 — coverage_decision_uncommitted
    cov = upstream.coverage
    coverage_committed = (
        (cov.decision_committed if cov else False)
        or inputs.coverage_decision != "uncommitted"
    )
    gates.append(_gate(
        "coverage_decision_uncommitted",
        "fail" if not coverage_committed else "pass",
        evidence_ref=f"coverage.decision={inputs.coverage_decision}",
        remediation="Adjuster must commit coverage decision (grant/deny/ROR-final).",
    ))

    # A2 — liability_apportionment_uncommitted
    lia = upstream.liability
    liability_committed = (
        (lia.apportionment_committed if lia else False)
        or inputs.liability_apportionment_committed
    )
    gates.append(_gate(
        "liability_apportionment_uncommitted",
        "fail" if not liability_committed else "pass",
        evidence_ref=f"liability.apportionment_committed={liability_committed}",
        remediation="Adjuster must pick fault percentages from Liability distribution.",
    ))

    # A3 — denial_letter_deficient (only when closure_without_payment)
    is_without_payment = (
        inputs.intended_closure_intent == "without_payment"
        or (cov is not None and cov.decision == "denied")
    )
    if is_without_payment:
        letter = inputs.denial_letter_audit
        sufficient = (
            letter.on_file
            and letter.cites_policy_provision
            and letter.cites_facts
            and letter.cites_applicable_law
        )
        gates.append(_gate(
            "denial_letter_deficient",
            "fail" if not sufficient else "pass",
            evidence_ref=(
                f"on_file={letter.on_file}, cites: provision={letter.cites_policy_provision}, "
                f"facts={letter.cites_facts}, law={letter.cites_applicable_law}"
            ),
            remediation=(
                "Author denial letter citing the specific policy provision, "
                "the facts giving rise to denial, and the applicable law."
            ),
        ))
    else:
        gates.append(_gate("denial_letter_deficient", "n_a"))

    # A4 — open_crn_within_cure_window
    open_crn_blocking = None
    for crn in inputs.open_crns:
        if crn.cure_status in ("uncured", "partial_cure"):
            if crn.days_since_dfs_filing < CRN_CURE_WINDOW_DAYS:
                open_crn_blocking = crn
                break
    if open_crn_blocking:
        gates.append(_gate(
            "open_crn_within_cure_window",
            "fail",
            evidence_ref=(
                f"CRN {open_crn_blocking.crn_id} filed {open_crn_blocking.dfs_filing_date} "
                f"(day {open_crn_blocking.days_since_dfs_filing}/60), status="
                f"{open_crn_blocking.cure_status}"
            ),
            remediation=(
                "Document specific cure of the alleged statutory violation "
                "OR pay full damages within the 60-day cure window."
            ),
        ))
    else:
        gates.append(_gate(
            "open_crn_within_cure_window",
            "pass" if not inputs.open_crns else "pass",
            evidence_ref=f"open_crns={len(inputs.open_crns)}, none within active cure window",
        ))

    # A5 — third_party_safe_harbor_window_expiring_unotendered
    notice_date = (
        (lia.first_actual_notice_date if lia else None)
        or inputs.claim_first_actual_notice_date
    )
    powell_or_safe_harbor_active = (
        (lia.powell_duty_potentially_triggered if lia else False)
        or inputs.powell_analysis.liability_clear
    )
    if notice_date and powell_or_safe_harbor_active:
        days_since_notice = (today - notice_date).days
        if days_since_notice > HB_837_THIRD_PARTY_SAFE_HARBOR_DAYS and not inputs.third_party_safe_harbor_tender_made:
            gates.append(_gate(
                "third_party_safe_harbor_window_expiring_unotendered",
                "fail",
                evidence_ref=(
                    f"days_since_actual_notice={days_since_notice}, tender_made=False"
                ),
                remediation=(
                    "Tender policy limits OR document why §624.155(4) safe harbor "
                    "does not apply before closing."
                ),
            ))
        else:
            gates.append(_gate(
                "third_party_safe_harbor_window_expiring_unotendered",
                "pass",
                evidence_ref=f"days_since_notice={days_since_notice}, tender={inputs.third_party_safe_harbor_tender_made}",
            ))
    else:
        gates.append(_gate("third_party_safe_harbor_window_expiring_unotendered", "n_a"))

    # A6 — multi_claimant_safe_harbor_not_invoked
    mc = inputs.multi_claimant_state
    if mc.is_multi_claimant and mc.competing_demands_exceed_aggregate:
        invoked = mc.interpleader_filed or mc.binding_arbitration_submitted
        if not invoked:
            if (mc.days_since_competing_claims_notice or 0) > HB_837_MULTI_CLAIMANT_SAFE_HARBOR_DAYS:
                gates.append(_gate(
                    "multi_claimant_safe_harbor_not_invoked",
                    "fail",
                    evidence_ref=(
                        f"days_since_competing_claims_notice="
                        f"{mc.days_since_competing_claims_notice}, "
                        f"interpleader=False, arbitration=False"
                    ),
                    remediation=(
                        "File Rule 1.240 interpleader OR submit limits to binding "
                        "arbitration; document global-tender attempt to all claimants."
                    ),
                ))
            else:
                gates.append(_gate(
                    "multi_claimant_safe_harbor_not_invoked",
                    "pass",
                    evidence_ref="within 90-day safe-harbor window",
                ))
                flags.append("multi_claimant_competing_limits_ambiguity")
        else:
            gates.append(_gate(
                "multi_claimant_safe_harbor_not_invoked",
                "pass",
                evidence_ref=(
                    f"interpleader={mc.interpleader_filed}, "
                    f"arbitration={mc.binding_arbitration_submitted}"
                ),
            ))
    else:
        gates.append(_gate("multi_claimant_safe_harbor_not_invoked", "n_a"))

    # A7 — section_627_4137_affidavit_missing_or_stale
    aff = inputs.section_627_4137_state
    if aff.claimant_written_request_on_file:
        delivered_ok = (
            aff.affidavit_delivered
            and aff.affidavit_delivery_date is not None
            and aff.claimant_request_date is not None
            and (aff.affidavit_delivery_date - aff.claimant_request_date).days <= SECTION_627_4137_AFFIDAVIT_DELIVERY_DAYS
        )
        # Must also be amended if there was aggregate erosion
        amended_ok = (
            (not mc.is_multi_claimant) or aff.amended_for_aggregate_erosion
        )
        if not (delivered_ok and amended_ok):
            gates.append(_gate(
                "section_627_4137_affidavit_missing_or_stale",
                "fail",
                evidence_ref=f"delivered={aff.affidavit_delivered}, amended={aff.amended_for_aggregate_erosion}",
                remediation=(
                    "Deliver §627.4137 sworn affidavit within 30 days of request; "
                    "amend on aggregate-limit erosion from sibling claimants."
                ),
            ))
        else:
            gates.append(_gate("section_627_4137_affidavit_missing_or_stale", "pass"))
    else:
        gates.append(_gate("section_627_4137_affidavit_missing_or_stale", "n_a"))

    # A8 — pip_exposure_not_drained
    pip_bills = inputs.pip_bill_ledger or (
        upstream.reserve.pip_bill_ledger if upstream.reserve else []
    )
    undrained_pip = [b for b in pip_bills if b.status == "open_past_30"]
    if pip_bills:
        if undrained_pip:
            gates.append(_gate(
                "pip_exposure_not_drained",
                "fail",
                evidence_ref=f"{len(undrained_pip)} of {len(pip_bills)} PIP bills past 30-day window",
                remediation="Pay or formally deny every PIP bill within its own 30-day clock.",
            ))
        else:
            gates.append(_gate("pip_exposure_not_drained", "pass"))
    else:
        gates.append(_gate("pip_exposure_not_drained", "n_a"))

    # A9 — section_627_4265_tender_window_violated
    s = inputs.settlement
    tender_violation = False
    tender_evidence = ""
    if s.agreement_date and not s.check_tendered_date:
        days = (today - s.agreement_date).days
        if days > SECTION_627_4265_TENDER_WINDOW_DAYS:
            tender_violation = True
            tender_evidence = f"agreement {s.agreement_date}, no tender after {days} days"
    if s.release_executed_date and not s.check_tendered_date:
        days_rel = (today - s.release_executed_date).days
        if days_rel > SECTION_627_4265_TENDER_WINDOW_DAYS:
            tender_violation = True
            tender_evidence = (
                tender_evidence + (
                    f"; release {s.release_executed_date}, no tender after {days_rel} days"
                    if tender_evidence else
                    f"release {s.release_executed_date}, no tender after {days_rel} days"
                )
            )
    if s.agreement_date or s.release_executed_date:
        gates.append(_gate(
            "section_627_4265_tender_window_violated",
            "fail" if tender_violation else "pass",
            evidence_ref=tender_evidence or "tender within 20-day window",
            remediation=(
                "Tender check within 20 days of settlement agreement / release. "
                "12% statutory interest accrues otherwise."
            ),
        ))
    else:
        gates.append(_gate("section_627_4265_tender_window_violated", "n_a"))

    # A10 — open_exposure_at_any_coverage_section
    e = inputs.exposure_status
    all_exposures_closed = e.bi and e.pd and e.mp and e.pip and e.um
    # An exposure is "n_a" if the coverage doesn't exist on the policy.
    # For v1 we treat any False as a fail unless the field is structurally absent.
    if any([e.bi, e.pd, e.mp, e.pip, e.um]):
        gates.append(_gate(
            "open_exposure_at_any_coverage_section",
            "pass" if all_exposures_closed else "fail",
            evidence_ref=f"bi={e.bi}, pd={e.pd}, mp={e.mp}, pip={e.pip}, um={e.um}",
            remediation="Close/deny/pay every exposure before claim-level close.",
        ))
    else:
        gates.append(_gate("open_exposure_at_any_coverage_section", "n_a"))

    # A11 — boston_old_colony_diligence_incomplete
    boc = inputs.boston_old_colony_diligence
    all_boc = all([
        boc.insured_notified_of_settlement_opportunities,
        boc.insured_warned_of_excess_exposure,
        boc.facts_investigated,
        boc.settlement_offers_received_fair_consideration,
        boc.decision_reflects_reasonable_prudent_person,
    ])
    gates.append(_gate(
        "boston_old_colony_diligence_incomplete",
        "fail" if not all_boc else "pass",
        evidence_ref=(
            f"notified={boc.insured_notified_of_settlement_opportunities}, "
            f"warned={boc.insured_warned_of_excess_exposure}, "
            f"investigated={boc.facts_investigated}, "
            f"fair_consideration={boc.settlement_offers_received_fair_consideration}, "
            f"prudent_person={boc.decision_reflects_reasonable_prudent_person}"
        ),
        remediation=(
            "Document all five Boston Old Colony preconditions before close: "
            "insured notice + excess warning + investigation + fair consideration + "
            "prudent-person decision rationale."
        ),
    ))

    # A12 — powell_duty_unfulfilled
    p = inputs.powell_analysis
    insured_fault = lia.insured_fault_pct if lia and lia.insured_fault_pct else None
    clear_liability = (
        p.liability_clear
        or (insured_fault is not None and insured_fault >= program_config.powell_clear_liability_threshold_pct)
    )
    if clear_liability and p.damages_plausibly_exceed_limits:
        ok = p.affirmative_policy_limits_offer_made or p.why_powell_does_not_apply_memo_on_file
        gates.append(_gate(
            "powell_duty_unfulfilled",
            "fail" if not ok else "pass",
            evidence_ref=(
                f"clear={clear_liability}, exceed_limits={p.damages_plausibly_exceed_limits}, "
                f"offer={p.affirmative_policy_limits_offer_made}, "
                f"memo={p.why_powell_does_not_apply_memo_on_file}"
            ),
            remediation=(
                "Make affirmative policy-limits offer OR file a memo explaining why "
                "Powell does not apply (e.g., disputed coverage)."
            ),
        ))
        flags.append("powell_duty_arguably_triggered")
    else:
        gates.append(_gate("powell_duty_unfulfilled", "n_a"))

    # A13 — harvey_communication_delay
    h = inputs.harvey_communication_log
    delay = h.received_count > h.answered_count or h.received_count > h.relayed_to_insured_count
    if h.received_count > 0:
        gates.append(_gate(
            "harvey_communication_delay",
            "fail" if delay else "pass",
            evidence_ref=(
                f"received={h.received_count}, answered={h.answered_count}, "
                f"relayed_to_insured={h.relayed_to_insured_count}"
            ),
            remediation=(
                "Answer every claimant communication pre-close; relay every "
                "settlement-relevant communication to the insured."
            ),
        ))
    else:
        gates.append(_gate("harvey_communication_delay", "n_a"))

    # A14 — macola_settlement_after_excess_trajectory
    m = inputs.macola_signals
    macola_pattern = (
        m.powell_duty_arguably_triggered_earlier
        and m.tender_came_only_after_suit_or_demand_pressure
        and m.close_memo_treats_payment_as_resolution
    )
    if macola_pattern:
        gates.append(_gate(
            "macola_settlement_after_excess_trajectory",
            "fail",
            evidence_ref="all three Macola signals present",
            remediation=(
                "Route to legal review — payment does not retroactively cure prior "
                "bad-faith failure on an excess-trajectory file."
            ),
        ))
        flags.append("macola_post_excess_trajectory_pattern")
    else:
        gates.append(_gate("macola_settlement_after_excess_trajectory", "n_a"))

    # -----------------------------------------------------------------
    # Tier B — Federal lien / MSP
    # -----------------------------------------------------------------

    # B1 — medicare_msp_unresolved
    if inputs.medicare_beneficiary_identified:
        settlement_amt = s.agreement_amount or Decimal("0")
        if settlement_amt >= SECTION_111_TPOC_THRESHOLD_DOLLARS:
            medicare_lien_resolved = any(
                l.kind == "medicare_conditional_payment" and l.release_letter_on_file
                for l in inputs.liens
            )
            if not medicare_lien_resolved:
                gates.append(_gate(
                    "medicare_msp_unresolved",
                    "fail",
                    evidence_ref=f"settlement=${settlement_amt}, no Final Demand release on file",
                    remediation=(
                        "Obtain CMS Final Demand letter; pay or dispute within 60 days. "
                        "Soft-close as pending_medicare_final_demand until resolved."
                    ),
                ))
            else:
                gates.append(_gate("medicare_msp_unresolved", "pass"))
        else:
            gates.append(_gate(
                "medicare_msp_unresolved",
                "n_a",
                evidence_ref=f"settlement=${settlement_amt} below $750 threshold",
            ))
    else:
        gates.append(_gate(
            "medicare_msp_unresolved",
            "n_a",
            evidence_ref="medicare_beneficiary_identified=False",
        ))

    # B2 — section_111_tpoc_unreported
    settlement_amt2 = s.agreement_amount or Decimal("0")
    if settlement_amt2 >= SECTION_111_TPOC_THRESHOLD_DOLLARS and inputs.medicare_beneficiary_identified:
        log = inputs.section_111_log
        if not (log and log.transmit_success):
            gates.append(_gate(
                "section_111_tpoc_unreported",
                "fail",
                evidence_ref=f"TPOC ${settlement_amt2}, no transmit-success log",
                remediation=(
                    "Submit Section 111 TPOC report via RRE within 135 days. "
                    "$1,000/claim/day CMP exposure otherwise."
                ),
            ))
        else:
            gates.append(_gate("section_111_tpoc_unreported", "pass"))
    else:
        gates.append(_gate("section_111_tpoc_unreported", "n_a"))

    # B3 — florida_medicaid_lien_unresolved
    if inputs.medicaid_beneficiary_identified:
        fahca_release = any(
            l.kind == "florida_medicaid" and l.release_letter_on_file for l in inputs.liens
        )
        gates.append(_gate(
            "florida_medicaid_lien_unresolved",
            "pass" if fahca_release else "fail",
            evidence_ref=f"medicaid_identified=True, fahca_release={fahca_release}",
            remediation=(
                "Obtain FAHCA satisfaction letter for §409.910(11)(f) formula amount "
                "OR §409.910(17)(b) DOAH reduction order. Gallardo: past + future medicals."
            ),
        ))
    else:
        gates.append(_gate("florida_medicaid_lien_unresolved", "n_a"))

    # B4 — workers_comp_lien_unsatisfied
    if inputs.in_scope_of_employment_at_loss:
        wc_release = any(
            l.kind == "workers_compensation" and l.release_letter_on_file for l in inputs.liens
        )
        gates.append(_gate(
            "workers_comp_lien_unsatisfied",
            "pass" if wc_release else "fail",
            evidence_ref=f"in_scope_of_employment=True, wc_release={wc_release}",
            remediation=(
                "Obtain §440.39 lien statement + waiver; document BI vs UM allocation "
                "(lien excludes UM proceeds per Aetna v. Norman)."
            ),
        ))
    else:
        gates.append(_gate("workers_comp_lien_unsatisfied", "n_a"))

    # B5 — erisa_self_funded_lien_unresolved
    if inputs.erisa_self_funded_plan_identified:
        erisa_release = any(
            l.kind == "erisa_self_funded" and l.release_letter_on_file for l in inputs.liens
        )
        if not inputs.erisa_plan_funding_type_confirmed:
            flags.append("erisa_funding_type_undetermined")
        ok = inputs.erisa_plan_funding_type_confirmed and (
            erisa_release or s.release_includes_hold_harmless_for_liens
        )
        gates.append(_gate(
            "erisa_self_funded_lien_unresolved",
            "pass" if ok else "fail",
            evidence_ref=(
                f"erisa_identified=True, funding_confirmed="
                f"{inputs.erisa_plan_funding_type_confirmed}, "
                f"release_letter={erisa_release}, hold_harmless="
                f"{s.release_includes_hold_harmless_for_liens}"
            ),
            remediation=(
                "Confirm plan funding type (SPD or TPA letter); obtain written "
                "reimbursement agreement OR ensure release carries hold-harmless. "
                "§768.76 waiver does NOT apply to self-funded ERISA."
            ),
        ))
    else:
        gates.append(_gate("erisa_self_funded_lien_unresolved", "n_a"))

    # B6 — hospital_lien_unresolved
    if inputs.hospital_lien_county_search_status == "searched_lien_found":
        hosp_release = any(
            l.kind == "hospital_county_specific" and l.release_letter_on_file
            for l in inputs.liens
        )
        gates.append(_gate(
            "hospital_lien_unresolved",
            "pass" if hosp_release else "fail",
            evidence_ref=f"county={inputs.hospital_lien_search_county}, release={hosp_release}",
            remediation="Obtain recorded release for the county-specific hospital lien.",
        ))
    else:
        if inputs.hospital_lien_county_search_status == "pending":
            flags.append("hospital_lien_county_search_pending")
        gates.append(_gate("hospital_lien_unresolved", "n_a"))

    # B7 — va_tricare_recovery_pending
    if inputs.veteran_or_tricare_beneficiary:
        va_release = any(
            l.kind in ("veterans_affairs", "tricare") and l.release_letter_on_file
            for l in inputs.liens
        )
        gates.append(_gate(
            "va_tricare_recovery_pending",
            "pass" if va_release else "fail",
            evidence_ref=f"va_tricare=True, release_letter={va_release}",
            remediation=(
                "Obtain VA Form 10-7959f-1 or TRICARE HHC zero-balance letter."
            ),
        ))
    else:
        gates.append(_gate("va_tricare_recovery_pending", "n_a"))

    # -----------------------------------------------------------------
    # Tier C — Release evidence
    # -----------------------------------------------------------------

    # C1 — missing_signed_release
    if s.agreement_date:
        gates.append(_gate(
            "missing_signed_release",
            "pass" if s.release_executed_date else "fail",
            evidence_ref=f"agreement_date={s.agreement_date}, release={s.release_executed_date}",
            remediation="Obtain signed release before tendering settlement check.",
        ))
        if s.release_executed_date and not s.check_tendered_date:
            flags.append("release_executed_but_tender_pending")
    else:
        gates.append(_gate("missing_signed_release", "n_a"))

    # C2 — release_does_not_address_known_liens
    identified_liens = [l for l in inputs.liens if l.status != "not_applicable"]
    if s.release_executed_date and identified_liens:
        ok = s.release_includes_hold_harmless_for_liens
        gates.append(_gate(
            "release_does_not_address_known_liens",
            "pass" if ok else "fail",
            evidence_ref=f"identified_liens={len(identified_liens)}, hold_harmless={ok}",
            remediation=(
                "Amend release to include hold-harmless / indemnity for identified "
                "lien holders. ERISA §502(a)(3) exposure otherwise."
            ),
        ))
    else:
        gates.append(_gate("release_does_not_address_known_liens", "n_a"))

    # C3 — section_768_76_window_open
    cs_notice = inputs.collateral_source_notice_sent_date
    if cs_notice:
        days = (today - cs_notice).days
        if days < SECTION_768_76_COLLATERAL_SOURCE_WAIVER_DAYS and not inputs.collateral_source_responses_logged:
            gates.append(_gate(
                "section_768_76_window_open",
                "fail",
                evidence_ref=f"notice {cs_notice}, day {days}/30, responses_logged=False",
                remediation="Wait for 30-day §768.76 waiver window to expire OR resolve responding liens.",
            ))
        else:
            gates.append(_gate("section_768_76_window_open", "pass"))
    else:
        gates.append(_gate("section_768_76_window_open", "n_a"))

    # C4 — outstanding_obr_with_legal_weight
    legal_obrs = [o for o in inputs.open_obrs if o.legal_weight == "legally_required"]
    if legal_obrs:
        gates.append(_gate(
            "outstanding_obr_with_legal_weight",
            "fail",
            evidence_ref=f"{len(legal_obrs)} legally-required OBRs open",
            remediation="Resolve every legally-required OutboundRequest before close.",
        ))
    else:
        gates.append(_gate(
            "outstanding_obr_with_legal_weight",
            "pass",
            evidence_ref=f"informational only: {len(inputs.open_obrs)} open",
        ))

    # -----------------------------------------------------------------
    # Tier D — Audit + authority
    # -----------------------------------------------------------------

    # D1 — agent_action_ledger_incomplete (blocking since 2026-06-02)
    if not inputs.agent_action_ledger_complete:
        gates.append(_gate(
            "agent_action_ledger_incomplete",
            "fail",
            evidence_ref="No AgentAction(analysis_emitted) rows for upstream workflows",
            remediation=(
                "Re-run upstream workflows so each emits an AgentAction(analysis_emitted) "
                "row. Closure cannot commit on an empty Boecher/Ruiz ledger."
            ),
        ))
    else:
        gates.append(_gate("agent_action_ledger_incomplete", "pass"))

    # D2 — settlement_authority_exceeded
    # Routing ladder (must match _route_authority in closure_calculator.py):
    # examiner ≤ examiner_cap < senior_examiner ≤ senior_cap < supervisor
    # ≤ supervisor_cap < manager ≤ manager_cap < roundtable
    settlement_amt3 = s.agreement_amount or Decimal("0")
    if settlement_amt3 <= program_config.closure_examiner_authority_dollars:
        gates.append(_gate(
            "settlement_authority_exceeded",
            "pass" if settlement_amt3 > 0 else "n_a",
            evidence_ref=f"settlement=${settlement_amt3} within examiner authority",
        ))
    else:
        # Above examiner — required tier = lowest tier whose cap ≥ settlement.
        if settlement_amt3 <= program_config.closure_senior_examiner_authority_dollars:
            required_tier = "senior_examiner"
            cap_label = f"senior ${program_config.closure_senior_examiner_authority_dollars}"
        elif settlement_amt3 <= program_config.closure_supervisor_authority_dollars:
            required_tier = "supervisor"
            cap_label = f"supervisor ${program_config.closure_supervisor_authority_dollars}"
        elif settlement_amt3 <= program_config.closure_manager_authority_dollars:
            required_tier = "manager"
            cap_label = f"manager ${program_config.closure_manager_authority_dollars}"
        else:
            required_tier = "roundtable"
            cap_label = f"> manager ${program_config.closure_manager_authority_dollars}"

        required_rank = AUTHORITY_TIER_RANK[required_tier]
        covering = [
            auth for auth in s.authorizations
            if auth.approved_amount >= settlement_amt3
            and AUTHORITY_TIER_RANK.get(auth.approver_role, -1) >= required_rank
        ]
        if covering:
            approvers = ", ".join(f"{a.approver_role}:{a.approver_id}" for a in covering)
            gates.append(_gate(
                "settlement_authority_exceeded",
                "pass",
                evidence_ref=(
                    f"settlement=${settlement_amt3} routed to {required_tier} ({cap_label}); "
                    f"escalation on file from {approvers}"
                ),
            ))
        else:
            gates.append(_gate(
                "settlement_authority_exceeded",
                "fail",
                evidence_ref=(
                    f"settlement=${settlement_amt3} > examiner "
                    f"${program_config.closure_examiner_authority_dollars}; "
                    f"required_tier={required_tier}; no SettlementAuthorizationRecord "
                    f"on file covering both amount AND tier"
                ),
                remediation=(
                    f"Obtain {required_tier}-tier authorization (or higher) for "
                    f"${settlement_amt3}; record as SettlementAuthorizationRecord."
                ),
            ))

    # D3 — record_classification_missing — derived later by calculator; gate is here so
    # we can carry the OIR classification into the ledger.
    classification: OirClassification = "not_yet_classifiable"
    if inputs.intended_closure_intent == "with_payment":
        classification = "closed_with_payment"
    elif inputs.intended_closure_intent == "without_payment":
        classification = "closed_without_payment"
    gates.append(_gate(
        "record_classification_missing",
        "pass" if classification != "not_yet_classifiable" else "fail",
        evidence_ref=f"oir_classification={classification}",
        remediation="Adjuster must declare closure intent (with_payment or without_payment).",
    ))

    # -----------------------------------------------------------------
    # Tier E — Defense-track bifurcation
    # -----------------------------------------------------------------

    # E1 — open_defense_track_post_interpleader
    if inputs.interpleader_indemnity_deposited:
        if inputs.underlying_tort_actions_unresolved:
            gates.append(_gate(
                "open_defense_track_post_interpleader",
                "fail",
                evidence_ref="interpleader deposited but tort actions vs insured unresolved",
                remediation=(
                    "Bifurcate close: indemnity_status=closed; defense_status=open. "
                    "Defense file stays open until underlying tort actions resolved."
                ),
            ))
        else:
            gates.append(_gate("open_defense_track_post_interpleader", "pass"))
    else:
        gates.append(_gate("open_defense_track_post_interpleader", "n_a"))

    # -----------------------------------------------------------------
    # Tier F — Preservation
    # -----------------------------------------------------------------

    # F1 — spoliation_preservation_hold_pre_sol_expiry
    floor_components: list[date] = []
    # DOL + SOL
    floor_components.append(
        inputs.loss_date + timedelta(days=365 * SOL_NEGLIGENCE_YEARS_POST_HB837)
    )
    if inputs.last_cms_cpn_date:
        floor_components.append(
            inputs.last_cms_cpn_date + timedelta(days=365 * MSP_RECOVERY_TAIL_YEARS)
        )
    if inputs.last_phi_authorization_end_date:
        floor_components.append(
            inputs.last_phi_authorization_end_date + timedelta(days=365 * HIPAA_RETENTION_YEARS)
        )
    if inputs.tpa_contract_termination_date:
        floor_components.append(
            inputs.tpa_contract_termination_date
            + timedelta(days=365 * TPA_CONTRACT_RETENTION_YEARS_AFTER_TERMINATION)
        )
    # Regulatory floor
    floor_components.append(
        today + timedelta(days=365 * FL_ADMIN_CODE_RECORD_RETENTION_YEARS)
    )
    preservation_until = max(floor_components) if floor_components else None

    if preservation_until is None:
        flags.append("preservation_hold_floor_undeterminable")
    gates.append(_gate(
        "spoliation_preservation_hold_pre_sol_expiry",
        "pass" if preservation_until and preservation_until > today else "fail",
        evidence_ref=f"preservation_until={preservation_until}",
        remediation="Hold all evidence + recorded statements + adjuster notes until preservation_until.",
    ))

    # -----------------------------------------------------------------
    # Final bookkeeping
    # -----------------------------------------------------------------

    any_a = any(g.tier == "A" and g.result == "fail" for g in gates)
    any_b = any(g.tier == "B" and g.result == "fail" for g in gates)
    any_c = any(g.tier == "C" and g.result == "fail" for g in gates)

    return DoctrineResolution(
        gates=gates,
        variance_flags=flags,
        preservation_until_date=preservation_until,
        oir_classification=classification,
        any_tier_a_failure=any_a,
        any_tier_b_failure=any_b,
        any_tier_c_failure=any_c,
    )
