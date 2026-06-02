"""Diligence ledger — the Allstate v. Ruiz discoverable artifact.

Co-equal output with apportionment. Templated, byte-reproducible. The ledger
captures posture, basis evidence, change conditions, next-review trigger,
open requests, evidence-not-obtained-with-reason, prior-posture delta,
and supervisor-disagreement record. Plaintiff's bad-faith counsel reads
this verbatim under Ruiz; Harvey procedural-diligence defense rides on it.

The build function emits a `DiligenceLedger` Pydantic model from the
CalculationContext + the original LiabilityInputs. The render function turns
that into the templated text block embedded in the LiabilityAssessment
rationale_text. Both are deterministic.
"""
from __future__ import annotations

from datetime import date, timedelta

from argos.schemas.workflows.liability import (
    BasisEvidenceEntry,
    DiligenceLedger,
    EvidenceNotObtained,
    OpenRequest,
    PriorPostureDelta,
)
from argos.services.liability.apportionment_calculator import CalculationContext


# =============================================================================
# Build
# =============================================================================


def build_diligence_ledger(
    ctx: CalculationContext,
    *,
    trigger_name: str,
) -> DiligenceLedger:
    """Build the ledger from CalculationContext + trigger.

    The ledger captures the contemporaneous state of investigation. Posture
    comes from apportionment. Basis evidence is the top-weighted subset of
    evidence items. Change conditions describe what new facts would shift
    the posture. Open requests + evidence-not-obtained are extractor-fed.
    Prior-posture delta is derived from inputs.prior_posture_history.
    """
    inputs = ctx.inputs
    apport = ctx.apportionment

    posture = {pid: ap.fault_pct for pid, ap in apport.items()}

    # Basis evidence: rank weight class with hard_data > party_admission >
    # independent > rebuttable_signal > credibility_only. Take all that are
    # at least 'independent' tier — anything weaker becomes change-condition
    # signal, not basis.
    tier_rank = {
        "hard_data": 0,
        "party_admission": 1,
        "independent": 2,
        "rebuttable_signal": 3,
        "credibility_only": 4,
    }
    basis: list[BasisEvidenceEntry] = []
    for item in inputs.evidence_items:
        if tier_rank[item.weight_class] <= 2:
            basis.append(
                BasisEvidenceEntry(
                    source_doc_id=item.source_doc_id,
                    quoted_span=item.quoted_span,
                    weight_class=item.weight_class,
                ),
            )

    change_conditions = _derive_change_conditions(ctx)
    next_review_date, next_review_trigger = _derive_next_review(
        ctx, trigger_name=trigger_name,
    )

    prior_delta: PriorPostureDelta | None = None
    if inputs.prior_posture_history:
        last = inputs.prior_posture_history[-1]
        prior_delta = PriorPostureDelta(
            prior_pct_by_party=last.posture_by_party_id,
            prior_date=last.eval_date,
            what_changed_evidence_idx=_index_of_first_directional_evidence(ctx),
        )

    # v1: open_requests + evidence_not_obtained are extractor-fed. Surface
    # whatever was in inputs.consistency_checks.details + structured gaps.
    open_requests = _derive_open_requests(ctx)
    evidence_not_obtained = _derive_evidence_not_obtained(ctx)

    return DiligenceLedger(
        posture_percent_by_party=posture,
        basis_evidence=basis,
        change_conditions=change_conditions,
        next_review_date=next_review_date,
        next_review_trigger=next_review_trigger,
        prior_posture_delta=prior_delta,
        open_requests=open_requests,
        evidence_not_obtained=evidence_not_obtained,
    )


def _derive_change_conditions(ctx: CalculationContext) -> list[str]:
    out: list[str] = []
    inputs = ctx.inputs

    # Rear-end with no rebuttal evidence: name what could rebut
    if inputs.fact_pattern == "rear_end" and inputs.rear_end_rebuttal_evidence.category == "none":
        out.append(
            "If Birge-category rebuttal evidence lands "
            "(mechanical failure / sudden stop / lane-change-by-lead / illegal-stop), "
            "rear-driver anchor shifts down materially.",
        )

    # Police report present but missing structured fields
    if inputs.police_report_structured_fields is None:
        out.append(
            "If FL HSMV 90010S structured fields (driver action codes, area of "
            "initial impact, citation) land, evidence weight on police-report "
            "items reclassifies upward.",
        )

    # Consistency gaps (not contradictions) — those are SIU flags, not change conds
    cc = inputs.consistency_checks
    for check_name, result in (
        ("er_mechanism", cc.er_mechanism_vs_claimant_statement),
        ("damage_vs_mechanism", cc.damage_pattern_vs_claimed_mechanism),
        ("poi_vs_claimant", cc.police_poi_vs_claimant_statement),
    ):
        if result == "gap":
            out.append(
                f"If {check_name} consistency check resolves "
                "(corroborated or contradicted), apportionment may shift.",
            )

    # Powell clarity zone
    if "powell_duty_clarity" in ctx.variance_flags:
        out.append(
            "If excess-judgment likelihood becomes clearer "
            "(damages evidence + low-limits confirmed), Powell duty to initiate "
            "tender solidifies.",
        )

    # Demand received
    if inputs.demand_received is not None:
        out.append(
            "Demand on file — sufficient-evidence assessment is the gating "
            "next decision; new evidence may flip the §624.155(4) call.",
        )

    return out


def _derive_next_review(
    ctx: CalculationContext, *, trigger_name: str,
) -> tuple[date, str]:
    """Default: 90-day calendar diary fallback, refined by trigger context.

    Specific triggers (demand received, CRN filed) compress the timeline.
    """
    base_date = ctx.reviewed_as_of.date()
    inputs = ctx.inputs

    # CRN cure window — 60 days from filing per §624.155(3)
    if inputs.ror_and_crn_state is not None and inputs.ror_and_crn_state.cure_deadline is not None:
        return inputs.ror_and_crn_state.cure_deadline, "CRN_CURE_DEADLINE"

    # Demand received — compress to demand deadline if it exists
    if inputs.demand_received is not None and inputs.demand_received.demand_deadline is not None:
        return inputs.demand_received.demand_deadline, "DEMAND_DEADLINE"

    # Variance — 30 days
    if ctx.variance_flags:
        return base_date + timedelta(days=30), "VARIANCE_REVIEW"

    # Default 90-day diary
    return base_date + timedelta(days=90), f"CALENDAR_DIARY_90_DAY (from {trigger_name})"


def _index_of_first_directional_evidence(ctx: CalculationContext) -> int | None:
    for idx, item in enumerate(ctx.inputs.evidence_items):
        if item.fault_direction != "neutral":
            return idx
    return None


def _derive_open_requests(ctx: CalculationContext) -> list[OpenRequest]:
    """v1: structural inference — flag asks implied by gaps.

    Extractor-fed open requests with ages are roadmap. v1 surfaces what an
    examiner would have requested given the gap pattern.
    """
    out: list[OpenRequest] = []
    inputs = ctx.inputs
    review_date = ctx.reviewed_as_of.date()

    if inputs.police_report_structured_fields is None:
        out.append(
            OpenRequest(
                request_type="police_report_full_HSMV_90010S",
                requested_date=review_date,
                age_days=0,
                target_party="investigating_agency",
            ),
        )
    has_insured_stmt = any(
        e.kind == "recorded_statement_insured" for e in inputs.evidence_items
    )
    if not has_insured_stmt:
        out.append(
            OpenRequest(
                request_type="recorded_statement_insured",
                requested_date=review_date,
                age_days=0,
                target_party="insured",
            ),
        )
    return out


def _derive_evidence_not_obtained(ctx: CalculationContext) -> list[EvidenceNotObtained]:
    """v1: empty unless extractor flags specifically.

    The Harvey-defense use of this field is positive-record-of-declined.
    Inferring 'we didn't get X' without a documented reason would invert the
    defense — leave empty until the extractor populates it explicitly.
    """
    del ctx
    return []


# =============================================================================
# Render — templated, byte-reproducible
# =============================================================================


def render_diligence_ledger(ledger: DiligenceLedger) -> str:
    lines: list[str] = []
    lines.append("DILIGENCE LEDGER:")
    lines.append("  Posture by party:")
    for pid, pct in sorted(ledger.posture_percent_by_party.items()):
        lines.append(f"    {pid}: {pct}%")
    lines.append(f"  Basis evidence ({len(ledger.basis_evidence)} items):")
    for be in ledger.basis_evidence:
        snippet = be.quoted_span[:120].replace("\n", " ")
        lines.append(
            f"    [{be.weight_class}] {be.source_doc_id}: \"{snippet}\"",
        )
    lines.append("  Change conditions:")
    for cc in ledger.change_conditions:
        lines.append(f"    - {cc}")
    lines.append(
        f"  Next review: {ledger.next_review_date.isoformat()} "
        f"(trigger: {ledger.next_review_trigger})",
    )
    if ledger.prior_posture_delta is not None:
        d = ledger.prior_posture_delta
        prior_summary = ", ".join(
            f"{pid}={pct}%" for pid, pct in sorted(d.prior_pct_by_party.items())
        )
        lines.append(
            f"  Prior posture ({d.prior_date.isoformat()}): {prior_summary}",
        )
        if d.what_changed_evidence_idx is not None:
            lines.append(
                f"    What changed: evidence_items[{d.what_changed_evidence_idx}]",
            )
    if ledger.open_requests:
        lines.append("  Open requests:")
        for r in ledger.open_requests:
            lines.append(
                f"    - {r.request_type} → {r.target_party} "
                f"(age {r.age_days}d, requested {r.requested_date.isoformat()})",
            )
    if ledger.evidence_not_obtained:
        lines.append("  Evidence not obtained (with reason):")
        for e in ledger.evidence_not_obtained:
            lines.append(
                f"    - {e.evidence_kind}: {e.reason_declined} "
                f"({e.date_decision.isoformat()})",
            )
    if ledger.supervisor_disagreement_record:
        lines.append("  Supervisor disagreement record:")
        for s in ledger.supervisor_disagreement_record:
            lines.append(
                f"    - {s.date_recorded.isoformat()}: {s.dissent_basis} "
                f"(dissent: {s.dissent_pct_by_party})",
            )
    return "\n".join(lines)
