"""Reserve rationale renderer — deterministic string interpolation.

Produces the audit-trail rationale string from CalculationContext. NOT
LLM-generated. Same context → same string, byte-for-byte. Tested via
golden-file diff.

Template structure: docs/specs/reserve-workflow.md §Rationale template.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from argos.services.reserve.calculator import CalculationContext
from argos.services.reserve.constants import (
    CRN_CURE_DAYS,
    HB_837_EFFECTIVE_DATE,
    SAFE_HARBOR_DAYS,
    VERSION,
)


def _money(x: Decimal) -> str:
    return f"${x:,.2f}"


def _money_int(x: Decimal) -> str:
    return f"${x:,.0f}"


def _hb_837_filing_branch(ctx: CalculationContext) -> str:
    filing = ctx.inputs.filing_date
    if filing is None:
        return "(no suit filed; pre-suit posture)"
    if filing >= HB_837_EFFECTIVE_DATE:
        return f"filing {filing} ≥ {HB_837_EFFECTIVE_DATE} → HB 837 applies"
    return f"filing {filing} < {HB_837_EFFECTIVE_DATE} → pre-HB-837"


def render_reserve_rationale(
    ctx: CalculationContext,
    *,
    claim_id: str,
    eval_seq: int,
    trigger_name: str,
    trigger_event_date: datetime,
    examiner_id: str = "system",
) -> str:
    """Interpolate the audit-trail rationale.

    Pure function: identical (ctx, kwargs) → identical string output. Tests
    diff this byte-for-byte against checked-in golden files.
    """
    inputs = ctx.inputs
    perm = inputs.permanency_status
    pip = inputs.pip_status
    rep = inputs.representation_status
    indem = ctx.indemnity
    spec = ctx.specials
    gen = ctx.generals
    bf = ctx.bad_faith_markers

    # ----- PIP / threshold line -----
    pip_emc = (
        "EMC determined" if pip.emc_determination is True
        else "no EMC" if pip.emc_determination is False
        else "EMC undetermined"
    )
    pip_exhaustion = (
        "EXHAUSTED" if pip.exhausted
        else f"${pip.paid_to_date:,.2f} paid of ${pip.cap_applicable:,.0f} cap"
    )

    if not inputs.tortfeasor_pip_compliant:
        threshold_line = (
            "N/A — tortfeasor non-PIP-compliant per §627.737(1) "
            "(threshold immunity lost)"
        )
    elif perm.fatality:
        threshold_line = "satisfied via fatality"
    elif perm.scarring_disfigurement:
        threshold_line = "satisfied via scarring/disfigurement"
    elif perm.opinion_present:
        rating = (
            f" ({perm.rating_pct}% impairment)" if perm.rating_pct is not None else ""
        )
        threshold_line = f"satisfied via permanency opinion{rating}"
    elif perm.mmi_date is not None:
        threshold_line = (
            f"barred — MMI reached {perm.mmi_date} without permanency; "
            "non-econ at $0"
        )
    else:
        threshold_line = (
            f"not yet established — non-econ priced at "
            f"{gen.threshold_discount_pct}% probability"
        )

    # ----- Generals line -----
    if inputs.injury_bucket == "catastrophic":
        generals_block = (
            "GENERALS:\n"
            "  Severity tier: catastrophic — life-care-plan estimator (multiplier method not applied)\n"
            f"  Catastrophic indicators: {', '.join(sorted(inputs.catastrophic_indicators))}"
        )
    else:
        from argos.services.reserve.constants import MULTIPLIER_TABLE_V1
        tier_criteria = MULTIPLIER_TABLE_V1[inputs.injury_bucket].criteria_summary
        generals_block = (
            "GENERALS:\n"
            f"  Severity tier: {inputs.injury_bucket} ({tier_criteria})\n"
            f"  Multiplier band: {gen.multiplier_low}× — {gen.multiplier_high}× specials\n"
            f"  Venue calibrator: {inputs.venue_county} ({gen.venue_factor}×)\n"
            f"  Threshold discount: {gen.threshold_discount_pct}%\n"
            f"  GENERALS LOW: {_money(gen.low)} | CENTRAL: {_money(gen.central)} | "
            f"HIGH: {_money(gen.high)}"
        )

    # ----- ALAE / ULAE -----
    if inputs.litigation_status.phase == "pre_suit":
        alae_line = "ALAE: not opened (pre-suit)"
    else:
        alae_line = (
            f"ALAE: opened at suit served, phase={inputs.litigation_status.phase}, "
            f"cumulative budget {_money(Decimal(str(ctx.alae_band.p10)))} — "
            f"{_money(Decimal(str(ctx.alae_band.p90)))} "
            f"(central {_money(Decimal(str(ctx.alae_band.p50)))})"
        )

    # ----- Delta + stair-step -----
    if ctx.delta_amount == 0 and ctx.prior_basis == "no prior reserve":
        delta_block = "DELTA FROM PRIOR: initial reserve — no prior basis"
    else:
        delta_block = (
            f"DELTA FROM PRIOR: {_money(ctx.delta_amount)} ({ctx.delta_pct}%). "
            f"Prior basis: {ctx.prior_basis}.\n"
            f"Stair-step check: "
            + (f"FLAG — {ctx.stair_step.reason}" if ctx.stair_step.flagged
               else f"OK — {ctx.stair_step.reason}")
        )

    # ----- Authority -----
    recommended_total = indem.recommended + Decimal(str(ctx.alae_band.p50))
    authority_block = (
        f"AUTHORITY:\n"
        f"  Reserve {_money(recommended_total)} (indemnity {_money(indem.recommended)} "
        f"+ ALAE p50 {_money(Decimal(str(ctx.alae_band.p50)))})\n"
        f"  vs examiner authority {_money(ctx.program_config.examiner_reserve_authority)}: "
        f"{ctx.authority_level}\n"
        f"  Required approver: {ctx.required_approver}"
    )

    # ----- Notice obligations -----
    if not ctx.notice_obligations:
        notice_block = "  Reinsurance/excess notice: not triggered"
    else:
        notice_lines = []
        for n in ctx.notice_obligations:
            notice_lines.append(
                f"  TRIGGERED [{n.notice_type}] — {n.reasoning}; due by "
                f"{n.required_by_date.date()}"
            )
        notice_block = "\n".join(notice_lines)

    # ----- Bad-faith markers -----
    if not bf.active:
        bf_block = "BAD-FAITH RISK MARKERS (0 active): none"
    else:
        bf_block = (
            f"BAD-FAITH RISK MARKERS ({len(bf.active)} active):\n  "
            + "\n  ".join(bf.active)
        )
    bf_block += f"\n  §624.155(4) {SAFE_HARBOR_DAYS}-day safe harbor: {bf.safe_harbor_status}"
    bf_block += f"\n  §624.155(3) {CRN_CURE_DAYS}-day CRN cure: {bf.crn_status}"

    # ----- Final assembly -----
    return f"""RESERVE EVALUATION — Claim {claim_id} | Eval #{eval_seq} | {ctx.reviewed_as_of.date()} | Examiner: {examiner_id} | constants {VERSION}
TRIGGER: {trigger_name} ({trigger_event_date.date()})

LIABILITY: Insured {inputs.insured_liability_pct}% at fault. FL §768.81 modified comparative: {indem.comparative_status}. {_hb_837_filing_branch(ctx)}.

PIP/THRESHOLD: PIP cap ${pip.cap_applicable:,.0f} ({pip_emc}), {pip_exhaustion}. §627.737 verbal threshold: {threshold_line}.

SPECIALS (indemnity build):
  Medical paid-satisfied bills: {_money(spec.paid_satisfied)}
  LOP/unsatisfied at insurance-equivalent: {_money(spec.lop_equivalent)}
  Wage loss documented: {_money(spec.wage_loss)}
  SPECIALS SUBTOTAL: {_money(spec.total)}

{generals_block}

INDEMNITY RESERVE (gross × liability%):
  Low: {_money(indem.low)} | Central: {_money(indem.central)} | High: {_money(indem.high)}
  Recommended posting: {_money(indem.recommended)}

{alae_line}
ULAE: not allocated per-claim per industry practice; portfolio-level overhead.

{delta_block}

{authority_block}
{notice_block}

{bf_block}
"""
