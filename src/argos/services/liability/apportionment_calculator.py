"""Apportionment calculator — anchor + evidence-weight math.

Pure-function deterministic stage. Takes LiabilityInputs + DoctrineResolution
+ optional gross-exposure dollars, emits per-party-pair apportionment
scalars with confidence bands, variance flags, authority routing, evidence
pack classification, and a structured rationale walk.

Calculation flow (per the spec):
  1. Pull fact-pattern anchor (e.g. rear_end → 95% rear_driver).
  2. Map anchor to actual party_ids by role.
  3. Walk evidence items in extraction order. Each item shifts fault toward
     a direction by a weight-class magnitude (signed; clamped to [0, 100]).
  4. Apply doctrine gates (regime bar, intoxication bar, vicarious cap
     surfacing — but vicarious cap is an exposure ceiling, not an
     apportionment shift, so it doesn't change %s).
  5. Detect variance zones (near-bar window, Powell clarity, evidence gap,
     delta-from-prior, etc.) and emit VarianceFlag list.
  6. Route authority based on net + gross exposure, dollar bands, and
     mandatory escalation flags.
  7. Classify evidence under §316.066(4).
  8. Build a structured rationale (anchor + evidence_adjustments +
     doctrine_gates + net_walk text). Templated rationale text is rendered
     separately by rationale.py.
"""
from __future__ import annotations

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import NamedTuple

from argos.schemas.workflows.liability import (
    ApportionmentEntry,
    AuthorityRouting,
    AuthorityTier,
    DoctrineGateApplied,
    DoctrineResolution,
    EvidenceAdjustment,
    EvidencePackClassification,
    FactPatternAnchor,
    LiabilityInputs,
    LiabilityRationale,
    PartyRole,
    ProgramConfig,
    SubroReferral,
    VarianceFlag,
)
from argos.services.liability.constants import (
    APPORTIONMENT_DELTA_BAND_PCT,
    EVIDENCE_GAP_FNOL_DAYS,
    EVIDENCE_WEIGHTS_V1,
    FACT_PATTERN_ANCHORS_V1,
    FL_DOCTRINE_REGISTRY_V1,
    MANDATORY_ESCALATION_VARIANCE_FLAGS,
    NEAR_BAR_WINDOW_PCT,
    POWELL_HIGH_FAULT_PCT_THRESHOLD,
)
from argos.services.liability.policy_engine import apply_fl_doctrines


# =============================================================================
# Intermediate types
# =============================================================================


class CalculationContext(NamedTuple):
    """Everything rationale.py + diligence_ledger.py need to render."""

    inputs: LiabilityInputs
    resolution: DoctrineResolution
    apportionment: dict[str, ApportionmentEntry]
    rationale: LiabilityRationale
    variance_flags: list[VarianceFlag]
    authority_routing: AuthorityRouting
    evidence_pack: EvidencePackClassification
    subro_referral: SubroReferral | None
    reviewed_as_of: datetime


# =============================================================================
# Helpers
# =============================================================================


def _round2(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _resolve_anchor_role_to_party(
    role: str, inputs: LiabilityInputs,
) -> str | None:
    """Map an anchor role (e.g. 'rear_driver') to an actual party_id.

    v1: role-name → party-role match. If the anchor uses 'rear_driver' /
    'turning_driver' etc., it's pattern-specific; we map to the structural
    inverse on the insured side. For typed PartyRoles we match directly.
    """
    pattern_to_party_role: dict[str, PartyRole] = {
        "rear_driver": "insured_driver",
        "turning_driver": "insured_driver",
        "lane_changing_driver": "insured_driver",
        "pulling_out_driver": "insured_driver",
        "striking_driver": "insured_driver",
        "violator": "insured_driver",
    }
    target_role: PartyRole | None = pattern_to_party_role.get(role)
    if target_role is None:
        # Already a PartyRole literal (e.g. claimant_pedestrian)
        for p in inputs.parties:
            if p.role == role:
                return p.party_id
        return None
    for p in inputs.parties:
        if p.role == target_role:
            return p.party_id
    return None


def _initial_pie(
    inputs: LiabilityInputs, anchor_pct: Decimal, anchor_party_id: str | None,
) -> dict[str, Decimal]:
    """Seed the pie with the anchor allocation; everyone else shares the rest."""
    party_ids = [p.party_id for p in inputs.parties]
    pie = {pid: Decimal("0") for pid in party_ids}
    if anchor_party_id is not None and anchor_party_id in pie:
        pie[anchor_party_id] = anchor_pct
        remainder = Decimal("100") - anchor_pct
        others = [pid for pid in party_ids if pid != anchor_party_id]
        if others:
            per_other = remainder / Decimal(len(others))
            for pid in others:
                pie[pid] = per_other
    else:
        per_party = Decimal("100") / Decimal(len(party_ids))
        for pid in party_ids:
            pie[pid] = per_party
    return pie


def _resolve_insured_and_claimant(
    inputs: LiabilityInputs,
) -> tuple[str | None, str | None]:
    insured = next(
        (
            p.party_id
            for p in inputs.parties
            if p.role in ("insured_driver", "insured_owner")
        ),
        None,
    )
    claimant = next(
        (
            p.party_id
            for p in inputs.parties
            if p.role
            in (
                "claimant_driver",
                "claimant_passenger",
                "claimant_pedestrian",
                "claimant_cyclist",
            )
        ),
        None,
    )
    return insured, claimant


def _shift_pie(
    pie: dict[str, Decimal],
    *,
    insured_id: str | None,
    claimant_id: str | None,
    direction: str,
    magnitude: Decimal,
) -> None:
    """Move `magnitude` points between insured and claimant based on direction.

    'neutral' shifts nothing. Other parties (Fabre non-parties) are not
    touched by evidence shifts in v1 — Fabre apportionment is a separate
    scenario fork.
    """
    if direction == "neutral" or insured_id is None or claimant_id is None:
        return
    if direction == "insured_more_fault":
        donor, recipient = claimant_id, insured_id
    elif direction == "claimant_more_fault":
        donor, recipient = insured_id, claimant_id
    else:
        return
    donor_avail = pie.get(donor, Decimal("0"))
    actual_shift = min(magnitude, donor_avail)
    pie[donor] = donor_avail - actual_shift
    pie[recipient] = pie.get(recipient, Decimal("0")) + actual_shift


def _normalize_pie(pie: dict[str, Decimal]) -> dict[str, Decimal]:
    total = sum(pie.values(), Decimal("0"))
    if total == 0:
        n = Decimal(len(pie))
        return {pid: Decimal("100") / n for pid in pie}
    scale = Decimal("100") / total
    return {pid: v * scale for pid, v in pie.items()}


def _confidence_from_evidence(inputs: LiabilityInputs) -> float:
    """Rough confidence proxy from evidence presence + tier mix.

    v1 heuristic: confidence baselines low, climbs with hard-data and
    independent-tier evidence count, and gets a small bump if the police
    report has structured fields. Not load-bearing for any gate — exposed
    to the user as a band-width hint.
    """
    hard = sum(1 for e in inputs.evidence_items if e.weight_class == "hard_data")
    indep = sum(1 for e in inputs.evidence_items if e.weight_class == "independent")
    party_adm = sum(1 for e in inputs.evidence_items if e.weight_class == "party_admission")
    base = 0.45
    score = base + 0.12 * hard + 0.06 * indep + 0.07 * party_adm
    if inputs.police_report_structured_fields is not None:
        score += 0.05
    return min(0.95, round(score, 2))


def _band_width_for_confidence(confidence: float) -> Decimal:
    """Confidence → half-band-width in points. Lower confidence → wider band."""
    if confidence >= 0.85:
        return Decimal("5")
    if confidence >= 0.7:
        return Decimal("10")
    if confidence >= 0.55:
        return Decimal("15")
    return Decimal("20")


def _classify_evidence_pack(
    inputs: LiabilityInputs,
) -> EvidencePackClassification:
    res = EvidencePackClassification()
    for idx, item in enumerate(inputs.evidence_items):
        if item.fl_admissibility == "admissible":
            res.trial_admissible_evidence_idx.append(idx)
            res.reserve_only_evidence_idx.append(idx)
        elif item.fl_admissibility == "privileged_316_066":
            res.privileged_316_066_excluded_idx.append(idx)
            res.reserve_only_evidence_idx.append(idx)
        elif item.fl_admissibility == "physical_evidence_carveout":
            res.physical_evidence_carveout_admissible_idx.append(idx)
            res.trial_admissible_evidence_idx.append(idx)
            res.reserve_only_evidence_idx.append(idx)
        elif item.fl_admissibility == "chemical_test_carveout":
            res.chemical_test_carveout_admissible_idx.append(idx)
            res.trial_admissible_evidence_idx.append(idx)
            res.reserve_only_evidence_idx.append(idx)
    return res


def _detect_variance_flags(
    inputs: LiabilityInputs,
    *,
    insured_pct: Decimal | None,
    claimant_pct: Decimal | None,
    resolution: DoctrineResolution,
    reviewed_as_of: datetime,
) -> list[VarianceFlag]:
    flags: list[VarianceFlag] = []

    # near_50_pct_bar (post-HB-837 only)
    if resolution.applicable_regime.statute == "modified_51_bar_hb837":
        for pct in (insured_pct, claimant_pct):
            if pct is None:
                continue
            if abs(pct - Decimal("50")) <= NEAR_BAR_WINDOW_PCT:
                flags.append("near_50_pct_bar")
                break

    # multi_party_matrix_required
    if len(inputs.parties) > 2 or resolution.exposure_ceiling.fabre_defendants:
        flags.append("multi_party_matrix_required")

    # fabre_non_party_unpled — v1: extractor flags via party role; pleading
    # check is downstream
    if resolution.exposure_ceiling.fabre_defendants:
        flags.append("fabre_non_party_unpled")

    # powell_duty_clarity
    if (
        insured_pct is not None
        and insured_pct >= POWELL_HIGH_FAULT_PCT_THRESHOLD
    ):
        flags.append("powell_duty_clarity")

    # safe_harbor_clock_decision_required
    if inputs.demand_received is not None and (
        inputs.demand_received.sufficient_evidence_assessment == "borderline"
    ):
        flags.append("safe_harbor_clock_decision_required")

    # intoxication_bar_candidate
    intox = inputs.intoxication_evidence
    intox_prong_one = (
        (intox.bac_value is not None and intox.bac_value >= Decimal("0.08"))
        or intox.impairment_observed
    )
    if intox_prong_one and (
        claimant_pct is not None and claimant_pct > Decimal("50")
    ):
        flags.append("intoxication_bar_candidate")

    # graves_vs_negligent_entrustment_branch
    ceiling = resolution.exposure_ceiling
    if ceiling.graves_lessor_removed and ceiling.negligent_entrustment_uncapped_path_available:
        flags.append("graves_vs_negligent_entrustment_branch")

    # consistency failures route to SIU
    cc = inputs.consistency_checks
    contradictions = (
        cc.er_mechanism_vs_claimant_statement == "contradiction"
        or cc.damage_pattern_vs_claimed_mechanism == "contradiction"
        or cc.police_poi_vs_claimant_statement == "contradiction"
    )
    if contradictions:
        flags.append("siu_referral_recommended")
        if cc.er_mechanism_vs_claimant_statement == "contradiction":
            flags.append("er_mechanism_contradicts_claimant")
        if cc.damage_pattern_vs_claimed_mechanism == "contradiction":
            flags.append("damage_vs_mechanism_contradiction")

    # evidence_gap_blocks_initial_call
    has_police = inputs.police_report_structured_fields is not None
    has_insured_stmt = any(
        e.kind == "recorded_statement_insured" for e in inputs.evidence_items
    )
    has_scene = any(e.kind == "scene_photo" for e in inputs.evidence_items)
    days_since_loss = (reviewed_as_of.date() - inputs.accrual_date).days
    if days_since_loss >= EVIDENCE_GAP_FNOL_DAYS and not (
        has_police or (has_insured_stmt and has_scene)
    ):
        flags.append("evidence_gap_blocks_initial_call")

    # apportionment_delta_exceeds_examiner_band
    if inputs.prior_posture_history and insured_pct is not None:
        last_posture = inputs.prior_posture_history[-1]
        insured_id, _ = _resolve_insured_and_claimant(inputs)
        if insured_id and insured_id in last_posture.posture_by_party_id:
            delta = abs(insured_pct - last_posture.posture_by_party_id[insured_id])
            if delta > APPORTIONMENT_DELTA_BAND_PCT:
                flags.append("apportionment_delta_exceeds_examiner_band")

    # roundtable_recommended — any mandatory-escalation flag also routes to roundtable
    if any(f in MANDATORY_ESCALATION_VARIANCE_FLAGS for f in flags):
        if "roundtable_recommended" not in flags:
            flags.append("roundtable_recommended")

    return flags


def _route_authority(
    *,
    insured_pct: Decimal | None,
    variance_flags: list[VarianceFlag],
    gross_exposure: Decimal,
    program_config: ProgramConfig,
) -> AuthorityRouting:
    """Authority tier from variance flags + gross-exposure bands.

    Authority is keyed on GROSS exposure at most TPAs (damages × full
    liability), NOT net — calculator surfaces both. committable_at_examiner
    is the load-bearing UX bit.
    """
    has_mandatory = any(f in MANDATORY_ESCALATION_VARIANCE_FLAGS for f in variance_flags)
    has_any_variance = bool(variance_flags) and any(
        f not in ("roundtable_recommended",) for f in variance_flags
    )

    net = (
        gross_exposure * (insured_pct / Decimal("100"))
        if insured_pct is not None
        else gross_exposure
    )

    if has_mandatory:
        tier: AuthorityTier = "roundtable"
        basis = (
            "Mandatory-escalation variance flag active "
            f"({', '.join(f for f in variance_flags if f in MANDATORY_ESCALATION_VARIANCE_FLAGS)})"
        )
        committable = False
    elif has_any_variance:
        tier = "senior_examiner"
        basis = f"Non-mandatory variance flag active: {', '.join(variance_flags)}"
        committable = False
    elif gross_exposure <= program_config.examiner_authority_dollars:
        tier = "examiner"
        basis = "Within examiner gross authority; no variance flags"
        committable = True
    elif gross_exposure <= program_config.senior_examiner_authority_dollars:
        tier = "senior_examiner"
        basis = "Within senior examiner authority"
        committable = False
    elif gross_exposure <= program_config.supervisor_authority_dollars:
        tier = "supervisor"
        basis = "Within supervisor authority"
        committable = False
    elif gross_exposure <= program_config.manager_authority_dollars:
        tier = "manager"
        basis = "Within manager authority"
        committable = False
    else:
        tier = "roundtable"
        basis = "Exposure exceeds manager authority"
        committable = False

    return AuthorityRouting(
        committable_at_examiner=committable,
        required_tier=tier,
        gross_exposure=_round2(gross_exposure),
        net_apportioned_exposure=_round2(net),
        basis_for_tier=basis,
    )


# =============================================================================
# Public entry point
# =============================================================================


def compute_apportionment(
    inputs: LiabilityInputs,
    program_config: ProgramConfig,
    *,
    request_id: str,
    reviewed_as_of: datetime,
    gross_exposure: Decimal = Decimal("0"),
) -> CalculationContext:
    """Run anchor + evidence-weight math; emit a CalculationContext.

    Runs the policy engine internally twice: once before apportionment to
    surface regime + ceiling, and once after to detect bar conditions that
    depend on the computed fault percentages (HB 837 51% bar; §768.36).
    Bundles everything rationale.py + diligence_ledger.py need to render.
    """
    del request_id  # consumed by workflow runner; surfaced via assessment

    anchor_seed = FACT_PATTERN_ANCHORS_V1[inputs.fact_pattern]
    anchor_party_id = _resolve_anchor_role_to_party(
        anchor_seed.anchor_party_role, inputs,
    )

    pie = _initial_pie(
        inputs, anchor_seed.anchor_pct, anchor_party_id,
    )
    insured_id, claimant_id = _resolve_insured_and_claimant(inputs)

    # Walk evidence items
    evidence_adjustments: list[EvidenceAdjustment] = []
    for idx, item in enumerate(inputs.evidence_items):
        weight_seed = EVIDENCE_WEIGHTS_V1[item.weight_class]
        magnitude = (weight_seed.min_points + weight_seed.max_points) / Decimal("2")

        # Rear-end rebuttable presumption — if the rebuttal evidence is present
        # and this item supports the rebuttal direction, magnify; otherwise the
        # rebuttal_evidence field works as informational. v1: rebuttal effect
        # rides on per-item fault_direction directly.
        _shift_pie(
            pie,
            insured_id=insured_id,
            claimant_id=claimant_id,
            direction=item.fault_direction,
            magnitude=magnitude,
        )
        evidence_adjustments.append(
            EvidenceAdjustment(
                evidence_item_idx=idx,
                direction=item.fault_direction,
                magnitude_points=magnitude,
                basis=f"{item.kind} ({item.weight_class}) — {item.source_doc_id}",
            ),
        )

    # Normalize and emit per-party apportionment with bands
    normalized = _normalize_pie(pie)
    confidence = _confidence_from_evidence(inputs)
    half_band = _band_width_for_confidence(confidence)

    apportionment: dict[str, ApportionmentEntry] = {}
    for pid, pct in normalized.items():
        pct_round = _round2(pct)
        low = max(Decimal("0"), pct_round - half_band)
        high = min(Decimal("100"), pct_round + half_band)
        apportionment[pid] = ApportionmentEntry(
            fault_pct=pct_round,
            fault_pct_band_low=_round2(low),
            fault_pct_band_high=_round2(high),
            confidence=confidence,
        )

    # Re-run policy engine with claimant_pct to detect HB 837 + intox bar
    insured_pct = apportionment[insured_id].fault_pct if insured_id else None
    claimant_pct = apportionment[claimant_id].fault_pct if claimant_id else None

    resolution_final = apply_fl_doctrines(
        inputs,
        program_config,
        insured_fault_pct=insured_pct,
        claimant_fault_pct=claimant_pct,
    )

    # Variance flags + authority routing (use final resolution)
    variance_flags = _detect_variance_flags(
        inputs,
        insured_pct=insured_pct,
        claimant_pct=claimant_pct,
        resolution=resolution_final,
        reviewed_as_of=reviewed_as_of,
    )

    authority = _route_authority(
        insured_pct=insured_pct,
        variance_flags=variance_flags,
        gross_exposure=gross_exposure,
        program_config=program_config,
    )

    evidence_pack = _classify_evidence_pack(inputs)

    # Doctrine gates applied — for rationale rendering
    doctrine_gates: list[DoctrineGateApplied] = []
    for doc_id in resolution_final.doctrines_applied:
        seed = FL_DOCTRINE_REGISTRY_V1.get(doc_id)
        if seed is None:
            continue
        doctrine_gates.append(
            DoctrineGateApplied(
                doctrine_id=doc_id,
                effect=seed.description,
                statute_or_case_cite=seed.statute_or_case_cite,
            ),
        )

    # Net walk text
    net_lines = [
        f"Start: {inputs.fact_pattern} anchor = {anchor_seed.anchor_pct}% "
        f"({anchor_seed.anchor_party_role} → {anchor_party_id or '(unresolved)'}).",
    ]
    for adj in evidence_adjustments:
        if adj.direction == "neutral":
            continue
        net_lines.append(
            f"  {adj.direction}: {adj.magnitude_points} pts ({adj.basis})",
        )
    for gate in doctrine_gates:
        net_lines.append(f"  doctrine: {gate.doctrine_id} — {gate.statute_or_case_cite}")
    net_lines.append(
        "Net per party: "
        + ", ".join(f"{pid}={ap.fault_pct}%" for pid, ap in apportionment.items()),
    )
    net_walk = "\n".join(net_lines)

    rationale = LiabilityRationale(
        fact_pattern_anchor=FactPatternAnchor(
            pattern=inputs.fact_pattern,
            anchor_pct=anchor_seed.anchor_pct,
            anchor_party_role=anchor_seed.anchor_party_role,  # type: ignore[arg-type]
            controlling_authority=anchor_seed.controlling_authority,
        ),
        evidence_adjustments=evidence_adjustments,
        doctrine_gates_applied=doctrine_gates,
        net_apportionment_walk=net_walk,
    )

    # Subro: if a claimant party has high fault and recovery isn't barred,
    # subro IS recommended toward that party. v1 surface, not pursuit.
    subro_referral: SubroReferral | None = None
    if (
        claimant_id
        and not resolution_final.applicable_regime.recovery_bar_triggered
        and claimant_pct is not None
        and claimant_pct >= Decimal("30")
    ):
        subro_referral = SubroReferral(
            recommended=True,
            recoverable_third_party_id=claimant_id,
            basis_apportionment_used={pid: ap.fault_pct for pid, ap in apportionment.items()},
            supporting_evidence_idxs=[
                idx
                for idx, item in enumerate(inputs.evidence_items)
                if item.fault_direction == "claimant_more_fault"
            ],
        )

    return CalculationContext(
        inputs=inputs,
        resolution=resolution_final,
        apportionment=apportionment,
        rationale=rationale,
        variance_flags=variance_flags,
        authority_routing=authority,
        evidence_pack=evidence_pack,
        subro_referral=subro_referral,
        reviewed_as_of=reviewed_as_of,
    )


# Re-exports so workflows/runner can pick what they need from one module.
__all__ = [
    "CalculationContext",
    "compute_apportionment",
]
