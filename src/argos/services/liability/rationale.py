"""Templated rationale for the Liability workflow.

Byte-reproducible interpolation. NOT LLM-generated. The rationale text is
the audit-trail surface — it must survive model swaps and constant-version
bumps without semantic drift.

Structure follows the spec's rationale template (see
docs/specs/liability-workflow.md):
  header → parties → fact pattern → applicable regime → exposure ceiling →
  apportionment walk → confidence band → variance flags → prior posture
  delta → §316.066(4) classification → diligence ledger → authority →
  downstream handoffs
"""
from __future__ import annotations

from datetime import date

from argos.schemas.workflows.liability import DiligenceLedger
from argos.services.liability.apportionment_calculator import CalculationContext
from argos.services.liability.constants import VERSION
from argos.services.liability.diligence_ledger import render_diligence_ledger


def render_liability_rationale(
    ctx: CalculationContext,
    ledger: DiligenceLedger,
    *,
    claim_id: str,
    eval_seq: int,
    trigger_name: str,
    trigger_event_date: date,
    examiner_id: str = "system",
) -> str:
    inputs = ctx.inputs
    apport = ctx.apportionment
    regime = ctx.resolution.applicable_regime
    ceiling = ctx.resolution.exposure_ceiling
    rat = ctx.rationale

    eval_date = ctx.reviewed_as_of.date().isoformat()

    out: list[str] = []
    out.append(
        f"LIABILITY EVALUATION — Claim {claim_id} | Eval #{eval_seq} | "
        f"{eval_date} | Examiner: {examiner_id} | constants {VERSION}",
    )
    out.append(f"TRIGGER: {trigger_name} ({trigger_event_date.isoformat()})")
    out.append("")

    # Parties
    out.append(f"PARTIES (N={len(inputs.parties)}):")
    for p in inputs.parties:
        out.append(
            f"  {p.party_id} | role={p.role} | identity_cite={p.identity_evidence_cite}",
        )
    out.append("")

    # Fact pattern
    out.append(
        f"FACT PATTERN: {inputs.fact_pattern} "
        f"(anchor: {rat.fact_pattern_anchor.anchor_pct}% "
        f"{rat.fact_pattern_anchor.anchor_party_role}; "
        f"controlling: {rat.fact_pattern_anchor.controlling_authority})",
    )
    out.append("")

    # Applicable regime
    out.append("APPLICABLE REGIME:")
    out.append(f"  Statute: {regime.statute}")
    out.append(
        f"  Accrual date {regime.date_of_loss_governing.isoformat()} → "
        f"{regime.explanation}",
    )
    out.append(
        f"  Recovery bar triggered: {regime.bar_basis} "
        f"(triggered={regime.recovery_bar_triggered})",
    )
    out.append("")

    # Exposure ceiling
    out.append("EXPOSURE CEILING:")
    if ceiling.graves_lessor_removed:
        cap_status = "graves_preempted"
    elif ceiling.vicarious_cap_applies:
        econ = ceiling.conditional_econ_layer
        cap_status = (
            f"natural_person_cap = {ceiling.vicarious_cap_value} "
            f"(econ conditional layer: {econ if econ is not None else 'unavailable'})"
        )
    else:
        cap_status = "none"
    out.append(f"  Vicarious cap: {cap_status}")
    neg_ent_status = (
        "uncapped_path_available_with_evidence"
        if ceiling.negligent_entrustment_uncapped_path_available
        else "not_evidenced"
    )
    out.append(f"  Negligent entrustment path: {neg_ent_status}")
    fabre_list = (
        ", ".join(ceiling.fabre_defendants)
        if ceiling.fabre_defendants
        else "none pled"
    )
    out.append(f"  Fabre defendants: {fabre_list}")
    out.append("")

    # Apportionment walk
    out.append("APPORTIONMENT WALK (anchor → evidence → doctrine → net):")
    for line in rat.net_apportionment_walk.split("\n"):
        out.append(f"  {line}")
    out.append("")

    # Confidence band (use first entry as representative)
    if apport:
        first = next(iter(apport.values()))
        out.append(
            f"CONFIDENCE BAND: {first.fault_pct_band_low}% — "
            f"{first.fault_pct_band_high}% "
            f"(confidence: {first.confidence:.2f})",
        )
        out.append("")

    # Variance flags
    out.append(f"VARIANCE FLAGS ({len(ctx.variance_flags)} active):")
    for f in ctx.variance_flags:
        out.append(f"  - {f}")
    if not ctx.variance_flags:
        out.append("  (none)")
    out.append("")

    # Prior posture delta
    if inputs.prior_posture_history:
        last = inputs.prior_posture_history[-1]
        prior_summary = ", ".join(
            f"{pid}={pct}%" for pid, pct in sorted(last.posture_by_party_id.items())
        )
        out.append(
            f"PRIOR POSTURE DELTA: {last.eval_date.isoformat()} → "
            f"current ({prior_summary} → "
            + ", ".join(f"{pid}={ap.fault_pct}%" for pid, ap in sorted(apport.items()))
            + ")",
        )
        out.append(f"  Basis: {last.basis_summary}")
        out.append("")

    # §316.066(4) evidence pack classification
    pack = ctx.evidence_pack
    out.append("§316.066(4) EVIDENCE PACK CLASSIFICATION:")
    out.append(
        f"  Trial-admissible: {len(pack.trial_admissible_evidence_idx)} items",
    )
    out.append(
        f"  Privileged statements (reserve-only): "
        f"{len(pack.privileged_316_066_excluded_idx)} items",
    )
    out.append(
        f"  Physical-evidence carveout: "
        f"{len(pack.physical_evidence_carveout_admissible_idx)} items",
    )
    out.append(
        f"  Chemical-test carveout: "
        f"{len(pack.chemical_test_carveout_admissible_idx)} items",
    )
    out.append("")

    # Diligence ledger (renders its own block)
    out.append(render_diligence_ledger(ledger))
    out.append("")

    # Authority
    auth = ctx.authority_routing
    out.append("AUTHORITY:")
    out.append(f"  Gross exposure: ${auth.gross_exposure}")
    out.append(f"  Net apportioned exposure: ${auth.net_apportioned_exposure}")
    out.append(f"  Required tier: {auth.required_tier}")
    out.append(f"  Committable at examiner: {auth.committable_at_examiner}")
    out.append(f"  Basis: {auth.basis_for_tier}")
    out.append("")

    # Downstream handoffs
    out.append("DOWNSTREAM HANDOFFS:")
    insured_id = next(
        (p.party_id for p in inputs.parties if p.role == "insured_driver"),
        None,
    )
    insured_pct = (
        apport[insured_id].fault_pct
        if insured_id and insured_id in apport
        else "n/a"
    )
    insured_band = (
        f"[{apport[insured_id].fault_pct_band_low}, {apport[insured_id].fault_pct_band_high}]"
        if insured_id and insured_id in apport
        else "n/a"
    )
    out.append(
        f"  Reserve: insured_liability_pct={insured_pct}, "
        f"band={insured_band}, regime={regime.statute}, "
        f"ceiling=vicarious_cap_applies={ceiling.vicarious_cap_applies}",
    )
    out.append(
        f"  Brief: rationale + diligence ledger + "
        f"{len(pack.trial_admissible_evidence_idx)} trial-admissible items",
    )
    out.append(
        f"  Authority/Tender: tier={auth.required_tier}, "
        f"committable_at_examiner={auth.committable_at_examiner}",
    )
    if ctx.subro_referral is not None:
        out.append(
            f"  Subro: recommended={ctx.subro_referral.recommended}, "
            f"third_party={ctx.subro_referral.recoverable_third_party_id}",
        )
    out.append(
        f"  Coverage: owner_type={inputs.owner_relationship.owner_type}, "
        f"permissive_use="
        + (
            "evidenced"
            if inputs.owner_relationship.permissive_use_evidence_cite
            else "not_evidenced"
        )
        + ", "
        f"line_of_business={inputs.line_of_business}",
    )

    return "\n".join(out)
