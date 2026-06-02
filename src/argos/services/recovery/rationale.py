"""Templated rationale for the Recovery workflow.

Byte-reproducible interpolation. NOT LLM-generated. The rationale text is
the audit-trail surface — it must survive model swaps and constant-version
bumps without semantic drift.

Structure follows docs/specs/recovery-workflow.md §Templated rationale:
  header → loss posture → upstream consumption → doctrinal gates →
  layered targets → recoverable basis → net economics → forum routing →
  deadline calendar → preservation hold → variance flags →
  cross-stream conflicts → diligence ledger → recommendation →
  downstream handoffs.
"""
from __future__ import annotations

from datetime import date

from argos.schemas.workflows.recovery import RecoveryDiligenceLedger
from argos.services.recovery.apportionment_calculator import CalculationContext
from argos.services.recovery.constants import VERSION
from argos.services.recovery.diligence_ledger import render_diligence_ledger


def render_recovery_rationale(
    ctx: CalculationContext,
    ledger: RecoveryDiligenceLedger,
    *,
    claim_id: str,
    eval_seq: int,
    trigger_name: str,
    trigger_event_date: date,
    examiner_id: str = "system",
) -> str:
    inputs = ctx.inputs
    upstream = ctx.upstream
    resolution = ctx.resolution
    eval_date = ctx.reviewed_as_of.date().isoformat()

    out: list[str] = []
    out.append(
        f"RECOVERY EVALUATION — Claim {claim_id} | Eval #{eval_seq} | "
        f"{eval_date} | Examiner: {examiner_id} | constants {VERSION}",
    )
    out.append(f"TRIGGER: {trigger_name} ({trigger_event_date.isoformat()})")
    out.append("")

    # Loss posture
    out.append("LOSS POSTURE:")
    out.append(
        f"  loss_date: {inputs.loss_date} → SOL version: "
        f"{resolution.sol_regime.statute_version}",
    )
    out.append(f"  loss_state: {inputs.loss_state}")
    out.append(
        f"  filing_date: {inputs.claim_filing_date or '(not filed)'} → "
        f"§768.0427 trigger: "
        f"{'active' if inputs.claim_filing_date is not None else 'pending_filing'}",
    )
    out.append(f"  subrogation_lane: {ctx.subrogation_lane.lane_id}")
    out.append("")

    # Upstream consumption
    out.append("UPSTREAM CONSUMPTION:")
    if upstream.liability is not None:
        out.append(
            f"  Liability: insured_fault={upstream.liability.insured_fault_pct}%, "
            f"claimant_fault={upstream.liability.claimant_fault_pct}%, "
            f"regime={upstream.liability.regime_statute}, "
            f"bar_basis={upstream.liability.bar_basis}",
        )
    else:
        out.append("  Liability: (no snapshot)")
    if upstream.reserve is not None:
        paid_total = sum(upstream.reserve.paid_indemnity_by_component.values())
        out_total = sum(upstream.reserve.outstanding_indemnity_by_component.values())
        out.append(
            f"  Reserve: paid_indemnity=${paid_total}, outstanding=${out_total}, "
            f"total_economic_loss=${upstream.reserve.total_economic_loss}",
        )
    else:
        out.append("  Reserve: (no snapshot)")
    if upstream.coverage is not None:
        out.append(
            f"  Coverage: status={upstream.coverage.status}, "
            f"omnibus_roster=[{len(upstream.coverage.omnibus_roster)} entries], "
            f"cooperation_window_open={upstream.coverage.cooperation_defense_window_open}",
        )
    else:
        out.append("  Coverage: (no snapshot)")
    out.append("")

    # Doctrinal gates
    out.append("DOCTRINAL GATES (evaluated in order):")
    for g in resolution.gates:
        line = f"  [{g.result}] {g.gate_id} — {g.statute_or_case_cite}"
        if g.evidence_ref:
            line += f" | evidence: {g.evidence_ref}"
        if g.variance_flag_emitted is not None:
            line += f" | variance: {g.variance_flag_emitted}"
        out.append(line)
    out.append("")

    # Layered targets
    out.append("LAYERED TARGETS:")
    if ctx.layered_targets:
        for t in ctx.layered_targets:
            cap_str = f", capped at ${t.cap_applied}" if t.cap_applied else ""
            out.append(
                f"  {t.layer_id}: party={t.target_party_id}, "
                f"apportioned={t.apportioned_fault_pct}% × ${ctx.recoverable_basis.basis} = "
                f"${t.apportioned_share}{cap_str}; "
                f"gross=${t.gross_recoverable}; P(recovery)={t.probability_of_recovery:.2f}; "
                f"EV=${t.expected_value}",
            )
    else:
        out.append("  (no targets — upstream Liability snapshot absent or no parties identified)")
    out.append("")

    # Recoverable basis
    rb = ctx.recoverable_basis
    out.append("RECOVERABLE BASIS:")
    out.append(f"  §768.0427-capped economic damages: ${rb.section_768_0427_capped_damages}")
    out.append(f"  − PIP collateral source stripped: ${rb.pip_collateral_source_stripped}")
    out.append(f"  − Made-whole shortfall: ${rb.made_whole_shortfall}")
    out.append(f"  = Recoverable basis: ${rb.basis}")
    out.append("")

    # Net economics
    ne = ctx.net_economics
    out.append("NET ECONOMICS:")
    out.append(f"  Gross recoverable (sum of layer EVs): ${ne.gross_recoverable_total}")
    out.append(f"  − Fee drag ({ne.fee_model}): ${ne.fee_drag}")
    out.append(f"  − Fee-shifting exposure: ${ne.fee_shifting_exposure}")
    out.append(f"  = Net: ${ne.net_total}")
    out.append("")

    # Forum routing
    fr = ctx.forum_routing
    out.append("FORUM ROUTING:")
    out.append(
        f"  AF signatory check: naic={inputs.tortfeasor_carrier_naic} → {fr.af_signatory_check}",
    )
    out.append(
        f"  Company-paid damages: ${fr.company_paid_damages} vs AF $100K cap: "
        + ("within" if fr.within_af_cap else "over"),
    )
    out.append(f"  Recommendation: {fr.recommendation} — basis: {fr.basis}")
    out.append("")

    # Deadline calendar
    out.append("DEADLINE CALENDAR:")
    if ctx.deadline_calendar.entries:
        for e in ctx.deadline_calendar.entries:
            out.append(
                f"  {e.deadline_id}: {e.deadline_date.isoformat()} (T-{e.days_remaining}d) "
                f"| {e.statute_or_rule_cite}",
            )
    else:
        out.append("  (no deadlines computed)")
    out.append("")

    # Preservation hold
    h = ctx.preservation_hold
    out.append("PRESERVATION HOLD:")
    out.append(
        f"  issued={h.issued}; scope={list(h.hold_scope)}; ack={h.acknowledgment_status}; "
        f"blocks_salvage_release={h.blocks_salvage_release}",
    )
    if h.storage_yard_letter_text:
        out.append(f"  Letter: {h.storage_yard_letter_text[:120]}...")
    out.append("")

    # Variance flags
    out.append(f"VARIANCE FLAGS ({len(ctx.variance_flags)} active):")
    for f in ctx.variance_flags:
        out.append(f"  - {f}")
    if not ctx.variance_flags:
        out.append("  (none)")
    out.append("")

    # Cross-stream
    cs = ctx.cross_stream_conflicts
    out.append("CROSS-STREAM CONFLICTS:")
    out.append(f"  Coverage denial + Recovery pursuit interlock: {cs.coverage_denial_recovery_pursuit_interlock}")
    out.append(
        f"  Anti-subrogation omnibus overlap: "
        + (", ".join(cs.anti_subrogation_omnibus_overlap) or "none"),
    )
    out.append(f"  §627.426(2) cooperation-defense window open: {cs.section_627_426_2_cooperation_window_open}")
    out.append("")

    # Diligence ledger
    out.append(render_diligence_ledger(ledger))
    out.append("")

    # Recommendation + authority
    a = ctx.authority_routing
    out.append(f"RECOMMENDATION: {ctx.recommendation}")
    out.append(f"  Net apportioned recoverable: ${a.net_apportioned_recoverable}")
    out.append(f"  Required tier: {a.required_tier}")
    out.append(f"  Committable at examiner: {a.committable_at_examiner}")
    out.append(f"  Basis: {a.basis_for_tier}")
    out.append("")

    # Downstream handoffs
    out.append("DOWNSTREAM HANDOFFS:")
    out.append(
        f"  Brief: full RecoveryAssessment + diligence ledger "
        f"+ {len(ctx.layered_targets)} layered targets",
    )
    out.append(
        f"  Claim system: preservation_hold (issued={h.issued}; blocks_salvage_release={h.blocks_salvage_release})",
    )
    out.append(
        f"  Runner: deadline_calendar ({len(ctx.deadline_calendar.entries)} entries) "
        "with T-90/T-60/T-30 trigger thresholds",
    )

    return "\n".join(out)
