"""Closure workflow — diligence ledger enrichment.

The ledger is a Boecher/Ruiz-discoverable artifact co-equal with the
recommendation. This module fills in per-lien / per-CRN / per-notice
records the calculator skeleton left empty.

Spec: docs/specs/closure-workflow.md §6.
"""
from __future__ import annotations

from argos.schemas.workflows.closure import (
    ClosureAssessment,
    ClosureDiligenceLedger,
    ClosureInputs,
    CrnStateRecord,
    LienResolutionRecord,
    MultiClaimantArtifactCheck,
    NoticeDeliveryRecord,
)


def enrich_diligence_ledger(
    assessment: ClosureAssessment,
    inputs: ClosureInputs,
) -> ClosureDiligenceLedger:
    """Fill per-lien, per-CRN, per-notice records from inputs."""
    base = assessment.diligence_ledger

    lien_records = [
        LienResolutionRecord(
            kind=l.kind,
            identified=True,
            notice_sent=l.notice_sent_date is not None,
            response_status=(
                "release_received" if l.release_letter_on_file
                else ("response_received" if l.response_received_date else "pending")
            ),
            release_letter_on_file=l.release_letter_on_file,
            satisfaction_amount=l.satisfaction_amount,
        )
        for l in inputs.liens
    ]

    crn_state = None
    if inputs.open_crns:
        # Surface the oldest unresolved CRN as the ledger snapshot.
        primary = sorted(
            inputs.open_crns,
            key=lambda c: c.days_since_dfs_filing,
            reverse=True,
        )[0]
        crn_state = CrnStateRecord(
            crn_id=primary.crn_id,
            dfs_filing_date=primary.dfs_filing_date,
            days_since_dfs_filing=primary.days_since_dfs_filing,
            alleged_violations=list(primary.alleged_statutory_violations),
            cure_status=primary.cure_status,
        )

    notice_records: list[NoticeDeliveryRecord] = []

    # §627.4137 affidavit
    aff = inputs.section_627_4137_state
    if aff.claimant_written_request_on_file:
        notice_records.append(NoticeDeliveryRecord(
            notice_kind="section_627_4137_affidavit",
            delivered=aff.affidavit_delivered,
            delivery_date=aff.affidavit_delivery_date,
            content_audit_pass=aff.affidavit_delivered,
            cite="Fla. Stat. §627.4137(1)-(2)",
        ))

    # §768.76 collateral source
    if inputs.collateral_source_notice_sent_date:
        notice_records.append(NoticeDeliveryRecord(
            notice_kind="section_768_76_collateral_source",
            delivered=True,
            delivery_date=inputs.collateral_source_notice_sent_date,
            content_audit_pass=inputs.collateral_source_responses_logged,
            cite="Fla. Stat. §768.76(6)+(7)",
        ))

    # Denial letter
    if inputs.denial_letter_audit.on_file:
        notice_records.append(NoticeDeliveryRecord(
            notice_kind="denial_letter",
            delivered=True,
            delivery_date=None,
            content_audit_pass=(
                inputs.denial_letter_audit.cites_policy_provision
                and inputs.denial_letter_audit.cites_facts
                and inputs.denial_letter_audit.cites_applicable_law
            ),
            cite="Fla. Stat. §626.9541(1)(i)3.f",
        ))

    multi_claimant_check = None
    mc = inputs.multi_claimant_state
    if mc.is_multi_claimant:
        multi_claimant_check = MultiClaimantArtifactCheck(
            global_tender_letter_sent=mc.global_tender_letter_sent_to_all_claimants,
            per_claimant_responses_logged=mc.per_claimant_responses_logged,
            priority_memo_on_file=mc.priority_memo_on_file,
            insured_notice_of_strategy_on_file=mc.insured_notice_of_strategy_on_file,
        )

    return ClosureDiligenceLedger(
        gates_evaluated=list(base.gates_evaluated),
        lien_resolution_records=lien_records,
        crn_state=crn_state,
        notice_delivery_audit=notice_records,
        multi_claimant_artifacts=multi_claimant_check,
        preservation_plan=base.preservation_plan,
        record_classification=base.record_classification,
        decision_rationale=base.decision_rationale,
    )
