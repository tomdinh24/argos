"""Shared minimal ClosureInputs + upstream-context builders for tests."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from argos.schemas.workflows.closure import (
    BostonOldColonyDiligence,
    ClosureInputs,
    ClosureUpstreamContext,
    CommunicationLog,
    DenialLetterAudit,
    ExposureClosureState,
    MacolaSignals,
    MultiClaimantState,
    PowellAnalysis,
    Section_627_4137_AffidavitState,
    SettlementInfo,
    UpstreamCoverageSnapshotForClosure,
    UpstreamLiabilitySnapshotForClosure,
    UpstreamRecoverySnapshotForClosure,
    UpstreamReserveSnapshotForClosure,
)


# Default eval date: a stable post-HB-837 date so SOL math is deterministic.
EVAL_TODAY = date(2026, 6, 2)
DEFAULT_LOSS = date(2025, 6, 2)  # 365 days before EVAL_TODAY


def make_inputs(
    *,
    loss_date: date = DEFAULT_LOSS,
    intended_closure_intent: str = "with_payment",
    coverage_decision: str = "granted",
    liability_apportionment_committed: bool = True,
    settlement_amount: Decimal | None = Decimal("15000"),
    settlement_agreement_date: date | None = date(2026, 5, 20),
    release_executed_date: date | None = date(2026, 5, 22),
    check_tendered_date: date | None = date(2026, 5, 30),
    all_exposures_closed: bool = True,
    boston_old_colony_all_yes: bool = True,
    open_crns: list | None = None,
    open_obrs: list | None = None,
    liens: list | None = None,
    medicare_beneficiary_identified: bool = False,
    medicaid_beneficiary_identified: bool = False,
    in_scope_of_employment_at_loss: bool = False,
    erisa_self_funded_plan_identified: bool = False,
    veteran_or_tricare_beneficiary: bool = False,
    hospital_lien_county_search_status: str = "searched_clean",
    hospital_lien_search_county: str | None = "Miami-Dade",
    multi_claimant_state: MultiClaimantState | None = None,
    section_627_4137_state: Section_627_4137_AffidavitState | None = None,
    macola_signals: MacolaSignals | None = None,
    powell_analysis: PowellAnalysis | None = None,
    harvey_communication_log: CommunicationLog | None = None,
    denial_letter_audit: DenialLetterAudit | None = None,
    last_cms_cpn_date: date | None = None,
    tpa_contract_termination_date: date | None = None,
    interpleader_indemnity_deposited: bool = False,
    underlying_tort_actions_unresolved: bool = False,
) -> ClosureInputs:
    boc = (
        BostonOldColonyDiligence(
            insured_notified_of_settlement_opportunities=True,
            insured_warned_of_excess_exposure=True,
            facts_investigated=True,
            settlement_offers_received_fair_consideration=True,
            decision_reflects_reasonable_prudent_person=True,
        )
        if boston_old_colony_all_yes
        else BostonOldColonyDiligence()
    )
    settlement = SettlementInfo(
        agreement_date=settlement_agreement_date,
        agreement_amount=settlement_amount,
        release_executed_date=release_executed_date,
        release_includes_hold_harmless_for_liens=True,
        check_tendered_date=check_tendered_date,
    )
    return ClosureInputs(
        loss_date=loss_date,
        intended_closure_intent=intended_closure_intent,  # type: ignore[arg-type]
        coverage_decision=coverage_decision,  # type: ignore[arg-type]
        denial_letter_audit=denial_letter_audit or DenialLetterAudit(),
        liability_apportionment_committed=liability_apportionment_committed,
        boston_old_colony_diligence=boc,
        powell_analysis=powell_analysis or PowellAnalysis(),
        macola_signals=macola_signals or MacolaSignals(),
        harvey_communication_log=harvey_communication_log or CommunicationLog(),
        open_crns=open_crns or [],
        third_party_safe_harbor_tender_made=True,
        multi_claimant_state=multi_claimant_state or MultiClaimantState(),
        section_627_4137_state=section_627_4137_state or Section_627_4137_AffidavitState(),
        pip_bill_ledger=[],
        settlement=settlement,
        exposure_status=ExposureClosureState(
            bi=all_exposures_closed,
            pd=all_exposures_closed,
            mp=all_exposures_closed,
            pip=all_exposures_closed,
            um=all_exposures_closed,
        ),
        liens=liens or [],
        section_111_log=None,
        medicare_beneficiary_identified=medicare_beneficiary_identified,
        medicaid_beneficiary_identified=medicaid_beneficiary_identified,
        in_scope_of_employment_at_loss=in_scope_of_employment_at_loss,
        erisa_self_funded_plan_identified=erisa_self_funded_plan_identified,
        erisa_plan_funding_type_confirmed=False,
        veteran_or_tricare_beneficiary=veteran_or_tricare_beneficiary,
        hospital_lien_county_search_status=hospital_lien_county_search_status,  # type: ignore[arg-type]
        hospital_lien_search_county=hospital_lien_search_county,
        collateral_source_notice_sent_date=None,
        collateral_source_responses_logged=False,
        open_obrs=open_obrs or [],
        agent_action_ledger_complete=True,
        examiner_id="examiner-1",
        interpleader_indemnity_deposited=interpleader_indemnity_deposited,
        underlying_tort_actions_unresolved=underlying_tort_actions_unresolved,
        last_cms_cpn_date=last_cms_cpn_date,
        last_phi_authorization_end_date=None,
        tpa_contract_termination_date=tpa_contract_termination_date,
    )


def make_upstream(
    *,
    coverage_committed: bool = True,
    coverage_decision: str = "granted",
    liability_committed: bool = True,
    insured_fault_pct: Decimal | None = Decimal("0"),
    recovery_pursuit: str = "abstain",
    recovery_committed: bool = True,
) -> ClosureUpstreamContext:
    return ClosureUpstreamContext(
        coverage=UpstreamCoverageSnapshotForClosure(
            decision_committed=coverage_committed,
            decision=coverage_decision,  # type: ignore[arg-type]
        ),
        liability=UpstreamLiabilitySnapshotForClosure(
            apportionment_committed=liability_committed,
            insured_fault_pct=insured_fault_pct,
            powell_duty_potentially_triggered=False,
            tender_made=True,
        ),
        reserve=UpstreamReserveSnapshotForClosure(),
        recovery=UpstreamRecoverySnapshotForClosure(
            pursuit_decision_committed=recovery_committed,
            decision=recovery_pursuit,  # type: ignore[arg-type]
        ),
    )
