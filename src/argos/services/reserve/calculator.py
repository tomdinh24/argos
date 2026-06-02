"""Reserve calculator — pure-Python deterministic math.

Signature: compute_reserve(inputs, program_config, *, request_id, reviewed_as_of)
           -> ReserveAnalysis

No LLM calls, no I/O, no randomness, no time-of-day side effects. Same inputs
→ same outputs, byte-for-byte. All math anchors to constants in constants.py.

Spec: docs/specs/reserve-workflow.md §Architecture.
Rationale interpolation: rationale.py (called separately and attached).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import NamedTuple

from argos.schemas.contract import EvidenceCitation
from argos.schemas.workflows.reserve import (
    AuthorityLevel,
    NoticeObligationTriggered,
    ProgramConfig,
    ReserveAnalysis,
    ReserveBand,
    ReserveComponentAnalysis,
    ReserveInputs,
)
from argos.services.reserve.constants import (
    BAD_FAITH_LIMIT_PROXIMITY_PCT,
    BAD_FAITH_MARKER_THRESHOLD,
    CATASTROPHIC_BANDS_V1,
    COMPARATIVE_BAR_PCT,
    COMPARATIVE_VARIANCE_HIGH,
    COMPARATIVE_VARIANCE_LOW,
    CRN_CURE_DAYS,
    DEFENSE_PHASE_BUDGETS_V1,
    DEFENSE_PHASE_ORDER,
    EXCESS_NOTICE_LIMIT_PCT,
    HB_837_EFFECTIVE_DATE,
    MULTIPLIER_TABLE_V1,
    NOTICE_THRESHOLDS_V1,
    SAFE_HARBOR_DAYS,
    STAIR_STEP_MIN_REVISIONS,
    STAIR_STEP_SMALL_REVISION_PCT,
    STAIR_STEP_WINDOW_DAYS,
    VENUE_GENERALS_MULTIPLIER_V1,
)


CENT = Decimal("0.01")


def _round_cents(x: Decimal) -> Decimal:
    return x.quantize(CENT, rounding=ROUND_HALF_UP)


# =============================================================================
# Intermediate result containers — exposed to rationale.py
# =============================================================================


class SpecialsBreakdown(NamedTuple):
    paid_satisfied: Decimal
    lop_equivalent: Decimal
    wage_loss: Decimal
    total: Decimal


class GeneralsBand(NamedTuple):
    low: Decimal
    central: Decimal
    high: Decimal
    multiplier_low: Decimal
    multiplier_central: Decimal
    multiplier_high: Decimal
    venue_factor: Decimal
    threshold_discount_pct: Decimal


class IndemnityBand(NamedTuple):
    low: Decimal
    central: Decimal
    high: Decimal
    recommended: Decimal
    comparative_status: str


class BadFaithMarkers(NamedTuple):
    active: list[str]
    safe_harbor_days_elapsed: int | None
    safe_harbor_status: str
    crn_days_remaining: int | None
    crn_status: str


class StairStepResult(NamedTuple):
    flagged: bool
    revisions_in_window: int
    reason: str


class CalculationContext(NamedTuple):
    """Everything rationale.py needs to interpolate the audit-trail string.

    Returned alongside ReserveAnalysis so the rationale stays in lockstep with
    the numbers it describes.
    """

    inputs: ReserveInputs
    program_config: ProgramConfig
    reviewed_as_of: datetime
    specials: SpecialsBreakdown
    generals: GeneralsBand
    indemnity: IndemnityBand
    alae_band: ReserveBand
    current_phase: str
    bad_faith_markers: BadFaithMarkers
    stair_step: StairStepResult
    delta_amount: Decimal
    delta_pct: Decimal
    prior_basis: str
    authority_level: AuthorityLevel
    required_approver: str
    notice_obligations: list[NoticeObligationTriggered]


# =============================================================================
# Specials anchoring (§768.0427 paid-vs-billed)
# =============================================================================


def _hb_837_paid_anchor_applies(inputs: ReserveInputs) -> bool:
    """§768.0427 keys to filing_date; only applies if filed post-HB-837."""
    if inputs.filing_date is None:
        # Pre-suit file: rule will apply if suit is filed post-HB-837. For
        # reserve purposes, anchor conservatively (use paid where available).
        return True
    return inputs.filing_date >= HB_837_EFFECTIVE_DATE


def _anchor_specials(inputs: ReserveInputs) -> SpecialsBreakdown:
    """Apply post-HB-837 paid-vs-billed where appropriate.

    Bills paid by health_ins / medicare / medicaid / pip → anchor at paid.
    LOP / self_pay / unknown → anchor at insurance-equivalent (use paid if
    nonzero, else billed). LOP markups are real but the v1 anchor is the
    billed amount when no paid figure exists — a conservative reserve choice
    that matches what defense counsel would argue at trial.
    """
    paid_anchor = _hb_837_paid_anchor_applies(inputs)
    paid_satisfied = Decimal("0")
    lop_equivalent = Decimal("0")

    for bill in inputs.medical_specials:
        if bill.payer in ("health_ins", "medicare", "medicaid", "pip"):
            if paid_anchor and bill.paid > 0:
                paid_satisfied += bill.paid
            else:
                paid_satisfied += bill.billed
        else:  # lop, self_pay, unknown
            if bill.paid > 0:
                lop_equivalent += bill.paid
            else:
                lop_equivalent += bill.billed

    wage = inputs.wage_loss.documented_to_date if inputs.wage_loss else Decimal("0")
    total = paid_satisfied + lop_equivalent + wage

    return SpecialsBreakdown(
        paid_satisfied=_round_cents(paid_satisfied),
        lop_equivalent=_round_cents(lop_equivalent),
        wage_loss=_round_cents(wage),
        total=_round_cents(total),
    )


# =============================================================================
# Generals (specials × multiplier × venue, with threshold gating)
# =============================================================================


def _threshold_discount(inputs: ReserveInputs) -> Decimal:
    """FL §627.737 verbal threshold — non-economic damages gating.

    Returns the fraction of full generals that survives the threshold gate:
      - 1.0 = full generals (permanency satisfied, or non-PIP-compliant)
      - 0.0 = no non-econ recoverable (threshold barred, MMI reached, no
              permanency)
      - 0.0..1.0 = probability-weighted estimate when permanency is
                   not-yet-established (pre-MMI, opinion-pending)
    """
    # §627.737(1) carve-out: non-PIP-compliant tortfeasor loses threshold immunity
    if not inputs.tortfeasor_pip_compliant:
        return Decimal("1.0")

    perm = inputs.permanency_status
    if perm.fatality or perm.scarring_disfigurement or perm.opinion_present:
        return Decimal("1.0")

    # MMI reached without permanency → threshold barred
    if perm.mmi_date is not None:
        return Decimal("0.0")

    # Pre-MMI / opinion pending — probability-weighted. Default 50% threshold
    # risk discount; tighter buckets refine: minor_soft_tissue weights down,
    # surgical/severe weights up.
    bucket_weights: dict[str, Decimal] = {
        "minor_soft_tissue": Decimal("0.25"),
        "moderate_ortho_non_surgical": Decimal("0.50"),
        "surgical_recovering": Decimal("0.80"),
        "severe_permanent": Decimal("0.90"),
        "catastrophic": Decimal("1.0"),
    }
    return bucket_weights.get(inputs.injury_bucket, Decimal("0.50"))


def _compute_generals(
    inputs: ReserveInputs, specials: SpecialsBreakdown,
) -> GeneralsBand:
    """generals_band = specials × multiplier_band × venue_factor × threshold."""
    tier = MULTIPLIER_TABLE_V1[inputs.injury_bucket]
    venue_factor = VENUE_GENERALS_MULTIPLIER_V1[inputs.venue_county]
    threshold = _threshold_discount(inputs)

    base = specials.total

    low = base * tier.multiplier_low * venue_factor * threshold
    central = base * tier.multiplier_central * venue_factor * threshold
    high = base * tier.multiplier_high * venue_factor * threshold

    return GeneralsBand(
        low=_round_cents(low),
        central=_round_cents(central),
        high=_round_cents(high),
        multiplier_low=tier.multiplier_low,
        multiplier_central=tier.multiplier_central,
        multiplier_high=tier.multiplier_high,
        venue_factor=venue_factor,
        threshold_discount_pct=(threshold * Decimal("100")).quantize(Decimal("1")),
    )


# =============================================================================
# Indemnity (gross × liability%, with FL §768.81 modified comparative bar)
# =============================================================================


def _hb_837_comparative_applies(inputs: ReserveInputs) -> bool:
    """§768.81 modified-comparative 51% bar applies to filings post-HB-837."""
    if inputs.filing_date is not None:
        return inputs.filing_date >= HB_837_EFFECTIVE_DATE
    return inputs.accrual_date >= HB_837_EFFECTIVE_DATE


def _compute_indemnity(
    inputs: ReserveInputs, specials: SpecialsBreakdown, generals: GeneralsBand,
) -> IndemnityBand:
    """Gross value × (insured_liability_pct / 100), with §768.81 bar applied."""
    insured_pct = inputs.insured_liability_pct
    claimant_pct = Decimal("100") - insured_pct

    hb_837 = _hb_837_comparative_applies(inputs)
    barred = hb_837 and claimant_pct > COMPARATIVE_BAR_PCT
    in_variance_zone = COMPARATIVE_VARIANCE_LOW <= insured_pct <= COMPARATIVE_VARIANCE_HIGH

    if barred:
        comparative_status = (
            f"barred — claimant {claimant_pct}% at fault > 50% bar (HB 837 §768.81)"
        )
        zero = Decimal("0")
        return IndemnityBand(
            low=zero, central=zero, high=zero, recommended=zero,
            comparative_status=comparative_status,
        )

    gross_low = specials.total + generals.low
    gross_central = specials.total + generals.central
    gross_high = specials.total + generals.high

    pct_factor = insured_pct / Decimal("100")
    low = _round_cents(gross_low * pct_factor)
    central = _round_cents(gross_central * pct_factor)
    high = _round_cents(gross_high * pct_factor)

    # Recommended posting: p50 by default; bump toward p90 when in variance zone
    # (high-uncertainty liability call deserves a conservative reserve).
    if in_variance_zone and hb_837:
        recommended = _round_cents((central + high) / Decimal("2"))
        comparative_status = (
            f"within recovery — insured {insured_pct}% at fault — HIGH VARIANCE "
            f"(40-55% zone, close to §768.81 bar)"
        )
    else:
        recommended = central
        if hb_837:
            comparative_status = f"within recovery — insured {insured_pct}% at fault"
        else:
            comparative_status = (
                f"pre-HB-837 pure-comparative — insured {insured_pct}% at fault"
            )

    return IndemnityBand(
        low=low, central=central, high=high, recommended=recommended,
        comparative_status=comparative_status,
    )


# =============================================================================
# Catastrophic branch (life-care-plan estimator instead of multiplier)
# =============================================================================


def _compute_catastrophic_indemnity(
    inputs: ReserveInputs, specials: SpecialsBreakdown,
) -> IndemnityBand:
    """Catastrophic claims reserve at policy limits with overlay flag, OR at
    NSCISC-anchored band if limits exceed band."""
    if not inputs.catastrophic_indicators:
        # Schema validator should have caught this; safety belt.
        return _compute_indemnity(
            inputs, specials, _compute_generals(inputs, specials),
        )

    # Take the worst-case indicator band (max p90).
    p10 = max(
        CATASTROPHIC_BANDS_V1[ind][0] for ind in inputs.catastrophic_indicators
    )
    p50 = max(
        CATASTROPHIC_BANDS_V1[ind][1] for ind in inputs.catastrophic_indicators
    )
    p90 = max(
        CATASTROPHIC_BANDS_V1[ind][2] for ind in inputs.catastrophic_indicators
    )

    # Cap at per-person policy limits (reserve never exceeds limits without
    # excess-overlay flag — that's a notice obligation, not a higher reserve).
    limit = inputs.policy_limits.per_person
    p10 = min(p10, limit)
    p50 = min(p50, limit)
    p90 = min(p90, limit)

    # Apply comparative as usual.
    insured_pct = inputs.insured_liability_pct
    hb_837 = _hb_837_comparative_applies(inputs)
    claimant_pct = Decimal("100") - insured_pct
    if hb_837 and claimant_pct > COMPARATIVE_BAR_PCT:
        zero = Decimal("0")
        return IndemnityBand(
            low=zero, central=zero, high=zero, recommended=zero,
            comparative_status=(
                f"barred — catastrophic claimant {claimant_pct}% at fault "
                f"> 50% bar (HB 837 §768.81)"
            ),
        )

    pct_factor = insured_pct / Decimal("100")
    low = _round_cents(p10 * pct_factor)
    central = _round_cents(p50 * pct_factor)
    high = _round_cents(p90 * pct_factor)
    # Catastrophic posts to limits-exhausting recommended; reserve at p90.
    recommended = high

    return IndemnityBand(
        low=low, central=central, high=high, recommended=recommended,
        comparative_status=(
            f"catastrophic — life-care-plan band; insured {insured_pct}% at fault; "
            f"capped at per-person limits ${limit:,}"
        ),
    )


# =============================================================================
# ALAE phase budget
# =============================================================================


def _compute_alae(inputs: ReserveInputs) -> ReserveBand:
    """Cumulative defense phase budget through current phase."""
    current_phase = inputs.litigation_status.phase
    if current_phase == "pre_suit":
        zero = Decimal("0")
        return ReserveBand(p10=float(zero), p50=float(zero), p90=float(zero))

    low = Decimal("0")
    central = Decimal("0")
    high = Decimal("0")
    for phase in DEFENSE_PHASE_ORDER:
        budget = DEFENSE_PHASE_BUDGETS_V1[phase]
        low += budget.low
        central += budget.central
        high += budget.high
        if phase == current_phase:
            break

    return ReserveBand(
        p10=float(_round_cents(low)),
        p50=float(_round_cents(central)),
        p90=float(_round_cents(high)),
    )


# =============================================================================
# Notice obligations
# =============================================================================


def _compute_notice_obligations(
    inputs: ReserveInputs, recommended_total: Decimal, reviewed_as_of: datetime,
) -> list[NoticeObligationTriggered]:
    triggered: list[NoticeObligationTriggered] = []

    # Reserve-anchored notice (reinsurance, LLC) — uses recommended_total.
    for name, threshold in NOTICE_THRESHOLDS_V1.items():
        if name == "excess_carrier":
            continue  # handled separately, limit-anchored
        fired_dollar = (
            threshold.dollar_trigger is not None
            and recommended_total >= threshold.dollar_trigger
        )
        fired_categorical = any(
            ind in threshold.categorical_triggers
            for ind in inputs.catastrophic_indicators
        )
        if fired_dollar or fired_categorical:
            reason_parts: list[str] = []
            if fired_dollar:
                reason_parts.append(
                    f"reserve ${recommended_total:,.2f} ≥ ${threshold.dollar_trigger:,.2f} "
                    f"threshold"
                )
            if fired_categorical:
                cats = sorted(
                    set(inputs.catastrophic_indicators)
                    & set(threshold.categorical_triggers)
                )
                reason_parts.append(f"categorical injury: {', '.join(cats)}")
            triggered.append(NoticeObligationTriggered(
                notice_type="reinsurer" if name == "reinsurance" else "client",
                probability=1.0,
                reasoning=" + ".join(reason_parts),
                required_by_date=reviewed_as_of + timedelta(days=threshold.notice_days),
                evidence_citations=[_default_evidence_for("notice")],
            ))

    # Excess-carrier notice: anchored to per-person limit proximity + clear liability.
    limit = inputs.policy_limits.per_person
    proximity = recommended_total / limit if limit > 0 else Decimal("0")
    clear_liability = inputs.insured_liability_pct >= Decimal("80")
    if proximity >= EXCESS_NOTICE_LIMIT_PCT and clear_liability:
        excess_threshold = NOTICE_THRESHOLDS_V1["excess_carrier"]
        triggered.append(NoticeObligationTriggered(
            notice_type="excess_carrier",
            probability=1.0,
            reasoning=(
                f"reserve ${recommended_total:,.2f} = "
                f"{(proximity * Decimal('100')).quantize(Decimal('1'))}% of per-person "
                f"limit ${limit:,.2f}; insured liability "
                f"{inputs.insured_liability_pct}% (clear)"
            ),
            required_by_date=reviewed_as_of + timedelta(days=excess_threshold.notice_days),
            evidence_citations=[_default_evidence_for("notice")],
        ))

    return triggered


def _default_evidence_for(_kind: str) -> EvidenceCitation:
    """Calculator-emitted citation pointing at the program-config rule.

    Real evidence (document_id) is attached by the extractor; this is the
    procedural-rule citation that proves a notice fired because the
    threshold rule said so. The sourced_rule_id resolves to constants.py.
    """
    return EvidenceCitation(
        sourced_rule_id=f"reserve.constants.{_kind}",
        locator="constants.py",
        text_excerpt=(
            "Notice threshold rule from constants.NOTICE_THRESHOLDS_V1 "
            "fired deterministically on calculator inputs."
        ),
        relation="supports",
    )


# =============================================================================
# Bad-faith risk markers (FL trilogy + §624.155 + HB 837)
# =============================================================================


def _compute_bad_faith_markers(
    inputs: ReserveInputs,
    indemnity: IndemnityBand,
    reviewed_as_of: datetime,
) -> BadFaithMarkers:
    """Surface markers; do NOT post a separate overlay reserve.

    Reserve overlay requires carrier instruction per the spec; this function
    flags the exposure for supervisor + coverage-counsel review.
    """
    active: list[str] = []

    # Marker 1: reserve > limits proximity threshold + clear liability
    limit = inputs.policy_limits.per_person
    if limit > 0:
        proximity = indemnity.recommended / limit
        if proximity >= BAD_FAITH_LIMIT_PROXIMITY_PCT and (
            inputs.insured_liability_pct >= Decimal("80")
        ):
            active.append(
                f"reserve_at_{(proximity * Decimal('100')).quantize(Decimal('1'))}pct_of_limits_with_clear_liability"
            )

    # Marker 2: policy-limits demand or time-demand on file
    rep = inputs.representation_status
    if rep.policy_limits_demand:
        active.append("policy_limits_demand_received")
    if rep.time_demand_deadline is not None:
        active.append("time_demand_with_deadline")

    # Marker 3: representation by counsel
    if rep.represented:
        active.append("represented_by_counsel")

    # Marker 4: catastrophic injury present
    if inputs.catastrophic_indicators:
        active.append(f"catastrophic_injury:{','.join(sorted(inputs.catastrophic_indicators))}")

    # Marker 5: §624.155(4) 90-day clock — running or expired
    safe_harbor_days_elapsed: int | None = None
    safe_harbor_status = "no_actual_notice_logged"
    if inputs.actual_notice_date is not None and rep.policy_limits_demand:
        elapsed = (reviewed_as_of.date() - inputs.actual_notice_date).days
        safe_harbor_days_elapsed = elapsed
        if elapsed > SAFE_HARBOR_DAYS:
            active.append("safe_harbor_clock_expired_without_tender")
            safe_harbor_status = (
                f"EXPIRED — {elapsed} days since actual notice (limit: {SAFE_HARBOR_DAYS})"
            )
        elif elapsed > SAFE_HARBOR_DAYS - 14:
            active.append("safe_harbor_clock_under_14_days_remaining")
            safe_harbor_status = (
                f"URGENT — {SAFE_HARBOR_DAYS - elapsed} days remaining of "
                f"{SAFE_HARBOR_DAYS}-day safe harbor"
            )
        else:
            safe_harbor_status = (
                f"running — {elapsed}/{SAFE_HARBOR_DAYS} days elapsed"
            )

    # Marker 6: CRN filed
    crn_days_remaining: int | None = None
    crn_status = "none filed"
    if inputs.crn_status is not None:
        active.append("crn_filed")
        remaining = (inputs.crn_status.cure_deadline - reviewed_as_of.date()).days
        crn_days_remaining = remaining
        if remaining < 0:
            active.append("crn_cure_window_expired")
            crn_status = (
                f"EXPIRED {-remaining} days ago — cure deadline "
                f"{inputs.crn_status.cure_deadline}"
            )
        elif remaining < 14:
            active.append("crn_cure_window_under_14_days")
            crn_status = (
                f"URGENT — {remaining} days remaining of {CRN_CURE_DAYS}-day cure "
                f"window (deadline {inputs.crn_status.cure_deadline})"
            )
        else:
            crn_status = (
                f"filed {inputs.crn_status.filed_date}, "
                f"{remaining} days remaining (deadline {inputs.crn_status.cure_deadline})"
            )

    return BadFaithMarkers(
        active=active,
        safe_harbor_days_elapsed=safe_harbor_days_elapsed,
        safe_harbor_status=safe_harbor_status,
        crn_days_remaining=crn_days_remaining,
        crn_status=crn_status,
    )


# =============================================================================
# Stair-step detector
# =============================================================================


def _detect_stair_step(
    inputs: ReserveInputs, reviewed_as_of: datetime,
) -> StairStepResult:
    if not inputs.prior_reserve_history:
        return StairStepResult(
            flagged=False, revisions_in_window=0, reason="no prior history",
        )

    window_start = reviewed_as_of.date() - timedelta(days=STAIR_STEP_WINDOW_DAYS)
    recent = [
        s for s in inputs.prior_reserve_history if s.eval_date >= window_start
    ]
    if len(recent) < STAIR_STEP_MIN_REVISIONS:
        return StairStepResult(
            flagged=False,
            revisions_in_window=len(recent),
            reason=f"only {len(recent)} revisions in {STAIR_STEP_WINDOW_DAYS}-day window",
        )

    recent_sorted = sorted(recent, key=lambda s: s.eval_date)
    small_upward = 0
    for prev, curr in zip(recent_sorted, recent_sorted[1:]):
        if prev.indemnity == 0:
            continue
        delta = curr.indemnity - prev.indemnity
        if delta <= 0:
            continue
        delta_pct = delta / prev.indemnity
        if delta_pct < STAIR_STEP_SMALL_REVISION_PCT:
            small_upward += 1

    if small_upward >= STAIR_STEP_MIN_REVISIONS - 1:
        return StairStepResult(
            flagged=True,
            revisions_in_window=len(recent),
            reason=(
                f"{small_upward} small upward revisions (<"
                f"{(STAIR_STEP_SMALL_REVISION_PCT * Decimal('100')).quantize(Decimal('1'))}% each) "
                f"in {STAIR_STEP_WINDOW_DAYS}-day window — supervisor review required"
            ),
        )
    return StairStepResult(
        flagged=False,
        revisions_in_window=len(recent),
        reason=f"{len(recent)} revisions but pattern not stair-step",
    )


# =============================================================================
# Authority routing
# =============================================================================


def _route_authority(
    inputs: ReserveInputs,
    recommended_total: Decimal,
    program_config: ProgramConfig,
) -> tuple[AuthorityLevel, str]:
    """Map reserve total → required approver per program_config bands."""
    # Categorical triggers route to manager+ regardless of dollars.
    if set(inputs.catastrophic_indicators) & set(program_config.mandatory_referral_categories):
        return "manager", "Claims manager / director + Large Loss Committee"

    if recommended_total <= program_config.examiner_reserve_authority:
        return "handler", "Examiner — unilateral"
    if recommended_total <= program_config.supervisor_reserve_authority:
        return "supervisor", "Senior examiner / supervisor notice"
    if recommended_total <= program_config.manager_reserve_authority:
        return "manager", "Claims supervisor + roundtable"
    if recommended_total <= program_config.carrier_escalation_threshold:
        return "manager", "Claims manager / director + Large Loss Committee"
    return "client", "Claims VP / CCO + coverage counsel + executive committee"


# =============================================================================
# Delta vs prior
# =============================================================================


def _compute_delta(
    inputs: ReserveInputs, recommended_total: Decimal,
) -> tuple[Decimal, Decimal, str]:
    if not inputs.prior_reserve_history:
        return Decimal("0"), Decimal("0"), "no prior reserve"

    latest = max(inputs.prior_reserve_history, key=lambda s: s.eval_date)
    prior_total = latest.indemnity + latest.alae
    delta = recommended_total - prior_total
    delta_pct = (delta / prior_total * Decimal("100")) if prior_total > 0 else Decimal("0")
    return _round_cents(delta), delta_pct.quantize(Decimal("0.1")), latest.basis


# =============================================================================
# Top-level entry point
# =============================================================================


def compute_reserve(
    inputs: ReserveInputs,
    program_config: ProgramConfig,
    *,
    request_id: str,
    reviewed_as_of: datetime,
) -> tuple[ReserveAnalysis, CalculationContext]:
    """Pure-Python reserve calculation.

    Returns (analysis, context). The context carries intermediate values that
    rationale.render_reserve_rationale needs to produce the audit-trail
    string; attach it via ReserveAnalysis.rationale after rendering.
    """
    # 1. Specials
    specials = _anchor_specials(inputs)

    # 2. Generals (or catastrophic branch)
    if inputs.injury_bucket == "catastrophic":
        # Catastrophic skips multiplier-method generals; indemnity comes
        # directly from life-care-plan bands. We still build a generals shape
        # for the rationale to print zeros.
        zero = Decimal("0")
        generals = GeneralsBand(
            low=zero, central=zero, high=zero,
            multiplier_low=zero, multiplier_central=zero, multiplier_high=zero,
            venue_factor=VENUE_GENERALS_MULTIPLIER_V1[inputs.venue_county],
            threshold_discount_pct=Decimal("0"),
        )
        indemnity = _compute_catastrophic_indemnity(inputs, specials)
    else:
        generals = _compute_generals(inputs, specials)
        indemnity = _compute_indemnity(inputs, specials, generals)

    # 3. ALAE
    alae_band = _compute_alae(inputs)
    alae_p50 = Decimal(str(alae_band.p50))

    # 4. Recommended total reserve (indemnity recommended + ALAE p50)
    recommended_total = indemnity.recommended + alae_p50

    # 5. Notice obligations
    notices = _compute_notice_obligations(inputs, recommended_total, reviewed_as_of)

    # 6. Bad-faith markers
    bf_markers = _compute_bad_faith_markers(inputs, indemnity, reviewed_as_of)

    # 7. Stair-step
    stair_step = _detect_stair_step(inputs, reviewed_as_of)

    # 8. Authority
    authority_level, required_approver = _route_authority(
        inputs, recommended_total, program_config,
    )

    # 9. Delta vs prior
    delta_amount, delta_pct, prior_basis = _compute_delta(inputs, recommended_total)

    # 10. Build per_component output
    components: list[ReserveComponentAnalysis] = []

    indem_evidence = [_default_evidence_for("indemnity")]
    components.append(ReserveComponentAnalysis(
        component="indemnity",
        current_outstanding=float(indemnity.recommended),
        recommended_outstanding_band=ReserveBand(
            p10=float(indemnity.low),
            p50=float(indemnity.central),
            p90=float(indemnity.high),
        ),
        rationale=indemnity.comparative_status,
        triggers_fired=[],
        evidence_citations=indem_evidence,
    ))

    if inputs.litigation_status.phase != "pre_suit":
        components.append(ReserveComponentAnalysis(
            component="ALAE",
            current_outstanding=alae_band.p50,
            recommended_outstanding_band=alae_band,
            rationale=(
                f"defense phase budget cumulative through "
                f"{inputs.litigation_status.phase}"
            ),
            triggers_fired=[],
            evidence_citations=[_default_evidence_for("alae")],
        ))

    # 11. no_change detection: <5% delta + no new triggers + not stair-step
    no_change = (
        abs(delta_pct) < Decimal("5.0")
        and not stair_step.flagged
        and not notices
        and len(bf_markers.active) == 0
        and len(inputs.prior_reserve_history) > 0
    )

    analysis = ReserveAnalysis(
        request_id=request_id,
        reviewed_as_of=reviewed_as_of,
        per_component=components,
        notice_obligations_triggered=notices,
        authority_required_level=authority_level,
        no_change_warranted=no_change,
        rationale="",  # filled in by render_reserve_rationale
    )

    context = CalculationContext(
        inputs=inputs,
        program_config=program_config,
        reviewed_as_of=reviewed_as_of,
        specials=specials,
        generals=generals,
        indemnity=indemnity,
        alae_band=alae_band,
        current_phase=inputs.litigation_status.phase,
        bad_faith_markers=bf_markers,
        stair_step=stair_step,
        delta_amount=delta_amount,
        delta_pct=delta_pct,
        prior_basis=prior_basis,
        authority_level=authority_level,
        required_approver=required_approver,
        notice_obligations=notices,
    )

    return analysis, context
