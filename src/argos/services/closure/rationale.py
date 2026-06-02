"""Closure workflow — templated rationale renderer.

Renders deterministic English from the ClosureAssessment for both:
- ClosureAssessment.rationale_text (top-level explanation)
- ClosureDiligenceLedger.decision_rationale (audit-trail explanation)

Spec: docs/specs/closure-workflow.md §7.
"""
from __future__ import annotations

from argos.schemas.workflows.closure import ClosureAssessment
from argos.services.closure.constants import VERSION


_RECOMMENDATION_HEADLINE: dict[str, str] = {
    "ready_to_close_with_payment": "Ready to close — with payment.",
    "ready_to_close_without_payment": "Ready to close — without payment.",
    "closed_with_open_recovery": "Close ledger; recovery file remains open.",
    "soft_close_pending_medicare_final_demand": (
        "Soft-close pending Medicare Final Demand."
    ),
    "soft_close_pending_section_111_confirmation": (
        "Soft-close pending Section 111 TPOC transmit-success."
    ),
    "soft_close_pending_lien_release_letter": (
        "Soft-close pending outstanding lien release letter(s)."
    ),
    "soft_close_pending_release_execution": (
        "Soft-close pending signed release execution."
    ),
    "blocked_by_defects": "Cannot close — blocking defects must be cured.",
    "requires_senior_review": "Requires senior review prior to close.",
    "requires_legal_review": "Requires legal review prior to close.",
    "recommend_reopen": "Recommend reopen — material new information surfaced.",
}


def render_rationale(assessment: ClosureAssessment) -> str:
    """Top-level prose for ClosureAssessment.rationale_text."""
    headline = _RECOMMENDATION_HEADLINE.get(
        assessment.recommendation, assessment.recommendation,
    )
    lines = [
        f"[constants {VERSION}] {headline}",
        f"Ready-to-close probability: {assessment.ready_probability:.2f}.",
        (
            f"OIR classification: {assessment.oir_classification}. "
            f"Indemnity status: {assessment.indemnity_status}. "
            f"Defense status: {assessment.defense_status}."
        ),
    ]
    if assessment.blocking_defects:
        lines.append(
            f"Blocking defects ({len(assessment.blocking_defects)}, ranked A→F):",
        )
        for d in assessment.blocking_defects[:10]:
            lines.append(
                f"  • [{d.tier}] {d.gate_id} — {d.statute_or_case_cite}. "
                f"Remediation: {d.remediation_action}",
            )
        if len(assessment.blocking_defects) > 10:
            lines.append(
                f"  • …{len(assessment.blocking_defects) - 10} more in diligence ledger.",
            )
    if assessment.variance_flags:
        lines.append(
            "Variance flags: " + ", ".join(assessment.variance_flags),
        )
    if assessment.preservation_plan.preservation_until_date:
        lines.append(
            f"Preservation hold through "
            f"{assessment.preservation_plan.preservation_until_date}.",
        )
    lines.append(
        f"Authority required: {assessment.authority_tier_required.required_tier} "
        f"(settlement=${assessment.authority_tier_required.settlement_amount}).",
    )
    return "\n".join(lines)


def render_ledger_rationale(assessment: ClosureAssessment) -> str:
    """Audit-trail prose for ClosureDiligenceLedger.decision_rationale."""
    lines = [
        f"[Closure diligence — constants {VERSION}]",
        f"Recommendation: {assessment.recommendation}.",
        f"Gates evaluated: {len(assessment.doctrinal_gates)}.",
        (
            f"  pass={sum(1 for g in assessment.doctrinal_gates if g.result == 'pass')}, "
            f"fail={sum(1 for g in assessment.doctrinal_gates if g.result == 'fail')}, "
            f"n_a={sum(1 for g in assessment.doctrinal_gates if g.result == 'n_a')}."
        ),
    ]
    if assessment.diligence_ledger.lien_resolution_records:
        lines.append(
            f"Lien resolution records: "
            f"{len(assessment.diligence_ledger.lien_resolution_records)}",
        )
        for l in assessment.diligence_ledger.lien_resolution_records:
            lines.append(
                f"  • {l.kind}: identified={l.identified}, notice_sent={l.notice_sent}, "
                f"release_on_file={l.release_letter_on_file}, status={l.response_status}",
            )
    if assessment.diligence_ledger.crn_state:
        c = assessment.diligence_ledger.crn_state
        lines.append(
            f"CRN snapshot: {c.crn_id} filed {c.dfs_filing_date} "
            f"(day {c.days_since_dfs_filing}, status={c.cure_status})",
        )
    if assessment.diligence_ledger.notice_delivery_audit:
        lines.append(
            f"Notice delivery audit: "
            f"{len(assessment.diligence_ledger.notice_delivery_audit)} records",
        )
        for n in assessment.diligence_ledger.notice_delivery_audit:
            lines.append(
                f"  • {n.notice_kind}: delivered={n.delivered}, "
                f"content_audit_pass={n.content_audit_pass}, cite={n.cite}",
            )
    if assessment.diligence_ledger.multi_claimant_artifacts:
        m = assessment.diligence_ledger.multi_claimant_artifacts
        lines.append(
            f"Multi-claimant artifacts: tender_sent={m.global_tender_letter_sent}, "
            f"responses_logged={m.per_claimant_responses_logged}, "
            f"priority_memo={m.priority_memo_on_file}, "
            f"insured_notice={m.insured_notice_of_strategy_on_file}",
        )
    preservation = assessment.preservation_plan
    if preservation.preservation_until_date:
        lines.append(
            f"Preservation until {preservation.preservation_until_date}. "
            f"Components: "
            + ", ".join(
                f"{k}={v}" for k, v in preservation.floor_components.items()
            ),
        )
    return "\n".join(lines)


def finalize_assessment(assessment: ClosureAssessment) -> ClosureAssessment:
    """Stamp rationale_text + ledger.decision_rationale on a built assessment.

    Returns a new ClosureAssessment (Pydantic models are frozen-by-default
    semantics in our codebase). Caller should swap in the returned value.
    """
    new_ledger = assessment.diligence_ledger.model_copy(
        update={"decision_rationale": render_ledger_rationale(assessment)},
    )
    return assessment.model_copy(update={
        "rationale_text": render_rationale(assessment),
        "diligence_ledger": new_ledger,
    })
