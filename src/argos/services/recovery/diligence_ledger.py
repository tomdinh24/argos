"""Diligence ledger — Allstate v. Boecher + Ruiz-discoverable artifact.

Co-equal output with the recovery recommendation. Templated,
byte-reproducible. The ledger captures gates evaluated with timestamps,
AF signatory check source + result, anti-subrogation per-coverage-section
cross-reference, made-whole computation, decision rationale, preservation
hold status, sources cited, open requests, and evidence-not-obtained
positive record.

Plaintiff's bad-faith counsel reads this verbatim under Boecher; the
Harvey procedural-diligence defense rides on it.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from argos.schemas.workflows.recovery import (
    AfSignatoryCheckRecord,
    AntiSubroCrossReference,
    EvidenceNotObtained,
    GateEvaluationLedgerEntry,
    MadeWholeComputation,
    OpenRequest,
    RecoveryDiligenceLedger,
    SourceCitation,
)
from argos.services.recovery.apportionment_calculator import CalculationContext
from argos.services.recovery.constants import AF_SIGNATORY_ROSTER_V1


def build_diligence_ledger(
    ctx: CalculationContext, *, trigger_name: str,
) -> RecoveryDiligenceLedger:
    """Build the ledger from CalculationContext + trigger."""
    inputs = ctx.inputs
    upstream = ctx.upstream
    resolution = ctx.resolution

    # Gates evaluated — one ledger entry per gate
    gates_evaluated = [
        GateEvaluationLedgerEntry(
            gate_id=g.gate_id,
            result=g.result,
            cite=g.statute_or_case_cite,
            evidence_ref=g.evidence_ref,
            evaluated_at=ctx.reviewed_as_of,
        )
        for g in resolution.gates
    ]

    # AF signatory check record
    naic = inputs.tortfeasor_carrier_naic
    af_signatory_status = "unverifiable"
    fallback = ""
    if naic is not None:
        roster_hit = AF_SIGNATORY_ROSTER_V1.get(naic)
        if roster_hit is True:
            af_signatory_status = "signatory"
        elif roster_hit is False:
            af_signatory_status = "non_signatory"
        else:
            fallback = "Roster lookup miss — block forum routing until refreshed"
    else:
        fallback = "Tortfeasor carrier NAIC missing — extractor gap"

    af_check = AfSignatoryCheckRecord(
        naic=naic,
        source="AF_SIGNATORY_ROSTER_V1 (seed; production refresh per AF publication)",
        lookup_timestamp=ctx.reviewed_as_of,
        result=af_signatory_status,  # type: ignore[arg-type]
        fallback_action=fallback,
    )

    # Anti-subrogation per-coverage-section cross-reference
    roster = inputs.named_insured_and_omnibus_roster
    if upstream.coverage is not None:
        roster = roster + upstream.coverage.omnibus_roster
    per_section: dict[str, list[str]] = {}
    tortfeasor_ids = {
        inputs.owner_operator_split.operator_id,
        inputs.owner_operator_split.owner_id,
    }
    for r in roster:
        if r.name in tortfeasor_ids:
            per_section.setdefault(r.coverage_section_paid_under, []).append(r.name)
    anti_subro = AntiSubroCrossReference(
        omnibus_roster_snapshot=roster,
        per_coverage_section_overlap=per_section,
    )

    # Made-whole computation
    made_whole = _made_whole_computation(ctx)

    # Sources cited — pull from gates + SOL regime
    sources = [
        SourceCitation(
            statute_or_case=g.statute_or_case_cite,
            claim_doc_id=None,
            quoted_span=g.effect_if_fired,
        )
        for g in resolution.gates
    ]

    # Open requests — structurally inferred from inputs gaps
    open_requests = _open_requests(ctx)

    # Evidence not obtained — empty unless extractor flagged
    evidence_not_obtained = _evidence_not_obtained(ctx)

    decision_rationale = (
        f"Recommendation: {ctx.recommendation}; lane: {ctx.subrogation_lane.lane_id}; "
        f"forum: {ctx.forum_routing.recommendation}; "
        f"net=${ctx.net_economics.net_total}. "
        f"Bar status: {resolution.bar_basis or 'no bar triggered'}. "
        f"Variance flags: {', '.join(ctx.variance_flags) or 'none'}. "
        f"Trigger: {trigger_name}."
    )

    return RecoveryDiligenceLedger(
        gates_evaluated=gates_evaluated,
        af_signatory_check=af_check,
        anti_subrogation_cross_reference=anti_subro,
        made_whole_computation=made_whole,
        decision_rationale=decision_rationale,
        preservation_hold_status=ctx.preservation_hold,
        sources_cited=sources,
        open_requests=open_requests,
        evidence_not_obtained=evidence_not_obtained,
    )


def _made_whole_computation(ctx: CalculationContext) -> MadeWholeComputation | None:
    if ctx.upstream.reserve is None:
        return None
    has_waiver = ctx.inputs.policy_subrogation_language.has_made_whole_waiver
    paid = sum(ctx.upstream.reserve.paid_indemnity_by_component.values(), Decimal("0"))
    economic = ctx.upstream.reserve.total_economic_loss
    shortfall = max(Decimal("0"), economic - paid)
    waiver_status = "waived" if has_waiver else (
        "not_waived" if ctx.inputs.policy_subrogation_language.waiver_text
        else "absent"
    )
    rationale = (
        "Carrier subrogation pursued direct against tortfeasor; shortfall surfaces "
        "but does not reduce recoverable basis under Schonau's freestanding-claim "
        "exception."
    )
    return MadeWholeComputation(
        paid_to_insured=paid,
        total_economic_loss=economic,
        shortfall=shortfall,
        waiver_status=waiver_status,  # type: ignore[arg-type]
        rationale=rationale,
    )


def _open_requests(ctx: CalculationContext) -> list[OpenRequest]:
    """Structural inference — flag asks implied by gaps."""
    out: list[OpenRequest] = []
    review = ctx.reviewed_as_of.date()
    inputs = ctx.inputs

    if inputs.tortfeasor_carrier_naic is None:
        out.append(OpenRequest(
            request_type="tortfeasor_carrier_naic_lookup",
            requested_date=review,
            age_days=0,
            target_party="claim_intake",
        ))
    if inputs.tortfeasor_vehicle_vin is None:
        out.append(OpenRequest(
            request_type="tortfeasor_vehicle_vin_nhtsa_recall_cross_reference",
            requested_date=review,
            age_days=0,
            target_party="evidence_team",
        ))
    if not inputs.evidence_artifacts.edr_pulled and inputs.evidence_artifacts.vehicle_status in (
        "in_storage_yard", "totaled_held", "with_insured", "unknown",
    ):
        out.append(OpenRequest(
            request_type="edr_acm_pull",
            requested_date=review,
            age_days=0,
            target_party="vendor_or_storage_yard",
        ))

    return out


def _evidence_not_obtained(ctx: CalculationContext) -> list[EvidenceNotObtained]:
    """v1: empty unless extractor explicitly flags declined-or-blocked."""
    del ctx
    return []


# =============================================================================
# Render — templated, byte-reproducible
# =============================================================================


def render_diligence_ledger(ledger: RecoveryDiligenceLedger) -> str:
    lines: list[str] = []
    lines.append("DILIGENCE LEDGER:")
    lines.append("  Gates evaluated:")
    for g in ledger.gates_evaluated:
        lines.append(
            f"    [{g.result}] {g.gate_id} | {g.cite}"
            + (f" | evidence: {g.evidence_ref}" if g.evidence_ref else ""),
        )
    if ledger.af_signatory_check is not None:
        c = ledger.af_signatory_check
        lines.append(
            f"  AF signatory check: naic={c.naic} → {c.result} "
            f"(source: {c.source}; ts: {c.lookup_timestamp.isoformat()})",
        )
        if c.fallback_action:
            lines.append(f"    Fallback: {c.fallback_action}")
    if ledger.anti_subrogation_cross_reference is not None:
        a = ledger.anti_subrogation_cross_reference
        if a.per_coverage_section_overlap:
            lines.append("  Anti-subrogation overlap:")
            for section, names in sorted(a.per_coverage_section_overlap.items()):
                lines.append(f"    [{section}] {', '.join(names)}")
        else:
            lines.append("  Anti-subrogation overlap: none")
    if ledger.made_whole_computation is not None:
        m = ledger.made_whole_computation
        lines.append(
            f"  Made-whole: paid=${m.paid_to_insured} / loss=${m.total_economic_loss} / "
            f"shortfall=${m.shortfall} (waiver: {m.waiver_status})",
        )
        lines.append(f"    Rationale: {m.rationale}")

    h = ledger.preservation_hold_status
    lines.append(
        f"  Preservation hold: issued={h.issued}; scope={list(h.hold_scope)}; "
        f"ack={h.acknowledgment_status}; blocks_salvage={h.blocks_salvage_release}",
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
                f"    - {s.date_recorded.isoformat()}: {s.dissent_recommendation} "
                f"— {s.dissent_basis}",
            )
    lines.append(f"  Decision rationale: {ledger.decision_rationale}")
    return "\n".join(lines)
