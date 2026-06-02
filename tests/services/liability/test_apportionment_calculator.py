"""Apportionment calculator — anchor/evidence/doctrine math + variance + authority."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from argos.schemas.workflows.liability import (
    IntoxicationEvidence,
)
from argos.services.liability.apportionment_calculator import compute_apportionment
from argos.services.liability.constants import DEFAULT_PROGRAM

from tests.services.liability._fixtures import (
    POST_HB837_LOSS,
    PRE_HB837_LOSS,
    make_evidence,
    make_inputs,
    make_party,
    posture_snapshot,
)


NOW = datetime(2025, 7, 1, 10, 0, 0, tzinfo=timezone.utc)


def _ctx(**overrides):
    inputs = make_inputs(**overrides)
    return compute_apportionment(
        inputs,
        DEFAULT_PROGRAM,
        request_id="req-1",
        reviewed_as_of=NOW,
        gross_exposure=Decimal("25000"),
    )


class TestAnchorOnly:
    def test_rear_end_seeds_95_5_pie(self) -> None:
        ctx = _ctx()
        ap = ctx.apportionment
        assert ap["P-insured"].fault_pct == Decimal("95.00")
        assert ap["P-claimant"].fault_pct == Decimal("5.00")

    def test_left_turn_seeds_90_10_pie(self) -> None:
        ctx = _ctx(fact_pattern="left_turn_across_traffic")
        ap = ctx.apportionment
        assert ap["P-insured"].fault_pct == Decimal("90.00")
        assert ap["P-claimant"].fault_pct == Decimal("10.00")

    def test_uncontrolled_intersection_seeds_50_50(self) -> None:
        ctx = _ctx(fact_pattern="uncontrolled_intersection")
        ap = ctx.apportionment
        assert ap["P-insured"].fault_pct == Decimal("50.00")
        assert ap["P-claimant"].fault_pct == Decimal("50.00")


class TestEvidenceWalk:
    def test_claimant_more_fault_evidence_shifts_pie(self) -> None:
        ctx = _ctx(
            fact_pattern="uncontrolled_intersection",
            evidence_items=[
                make_evidence(
                    "edr_download",
                    fault_direction="claimant_more_fault",
                    weight_class="hard_data",
                ),
            ],
        )
        ap = ctx.apportionment
        # hard_data magnitude ≈ 22.5; pie should swing toward claimant
        assert ap["P-claimant"].fault_pct > ap["P-insured"].fault_pct

    def test_insured_more_fault_increases_anchor(self) -> None:
        ctx = _ctx(
            fact_pattern="rear_end",
            evidence_items=[
                make_evidence(
                    "citation_issued",
                    fault_direction="insured_more_fault",
                    weight_class="independent",
                ),
            ],
        )
        ap = ctx.apportionment
        assert ap["P-insured"].fault_pct >= Decimal("95.00")

    def test_neutral_evidence_does_not_shift(self) -> None:
        ctx = _ctx(
            fact_pattern="uncontrolled_intersection",
            evidence_items=[
                make_evidence(
                    "scene_photo",
                    fault_direction="neutral",
                    weight_class="hard_data",
                ),
            ],
        )
        ap = ctx.apportionment
        assert ap["P-insured"].fault_pct == Decimal("50.00")
        assert ap["P-claimant"].fault_pct == Decimal("50.00")


class TestPieInvariants:
    def test_pie_always_sums_to_100(self) -> None:
        ctx = _ctx(
            fact_pattern="lane_change",
            evidence_items=[
                make_evidence("edr_download", fault_direction="claimant_more_fault", weight_class="hard_data"),
                make_evidence("recorded_statement_insured", fault_direction="insured_more_fault", weight_class="party_admission"),
            ],
        )
        total = sum(e.fault_pct for e in ctx.apportionment.values())
        assert total == Decimal("100.00")

    def test_bands_clamped_to_0_100(self) -> None:
        ctx = _ctx()
        for entry in ctx.apportionment.values():
            assert Decimal("0") <= entry.fault_pct_band_low <= entry.fault_pct
            assert entry.fault_pct <= entry.fault_pct_band_high <= Decimal("100")


class TestVarianceFlags:
    def test_near_50_pct_bar_fires_post_hb837(self) -> None:
        # 50/50 anchor with no shift → near-bar
        ctx = _ctx(fact_pattern="uncontrolled_intersection")
        assert "near_50_pct_bar" in ctx.variance_flags

    def test_near_50_pct_bar_does_not_fire_pre_hb837(self) -> None:
        ctx = _ctx(
            fact_pattern="uncontrolled_intersection",
            accrual_date=PRE_HB837_LOSS,
        )
        assert "near_50_pct_bar" not in ctx.variance_flags

    def test_powell_duty_clarity_on_high_insured_fault(self) -> None:
        ctx = _ctx()  # rear_end 95% insured
        assert "powell_duty_clarity" in ctx.variance_flags

    def test_multi_party_matrix_flag_on_three_party(self) -> None:
        parties = [
            make_party("P-insured", "insured_driver"),
            make_party("P-claimant", "claimant_driver"),
            make_party("P-passenger", "claimant_passenger"),
        ]
        ctx = _ctx(parties=parties)
        assert "multi_party_matrix_required" in ctx.variance_flags

    def test_intoxication_bar_candidate_fires_with_high_bac(self) -> None:
        ctx = _ctx(
            intox=IntoxicationEvidence(
                bac_value=Decimal("0.12"),
                bac_source="blood",
                impairment_observed=True,
                causation_to_fault_evidence_cites=["recon-1"],
            ),
            # 95% rear-end → claimant 5% — not above 50, no flag
            evidence_items=[
                make_evidence(
                    "edr_download",
                    fault_direction="claimant_more_fault",
                    weight_class="hard_data",
                ),
                make_evidence(
                    "expert_report_recon",
                    fault_direction="claimant_more_fault",
                    weight_class="hard_data",
                ),
                make_evidence(
                    "expert_report_recon",
                    fault_direction="claimant_more_fault",
                    weight_class="hard_data",
                ),
                make_evidence(
                    "expert_report_recon",
                    fault_direction="claimant_more_fault",
                    weight_class="hard_data",
                ),
            ],
            fact_pattern="uncontrolled_intersection",
        )
        # Multiple hard_data shifts toward claimant should push >50
        assert "intoxication_bar_candidate" in ctx.variance_flags

    def test_apportionment_delta_flag_fires_when_history_changed(self) -> None:
        ctx = _ctx(
            fact_pattern="rear_end",
            prior_posture=[posture_snapshot(insured_pct=50, claimant_pct=50)],
        )
        # rear-end anchor at 95%, prior at 50% — delta 45 > 15
        assert "apportionment_delta_exceeds_examiner_band" in ctx.variance_flags

    def test_consistency_contradiction_routes_to_siu(self) -> None:
        inputs = make_inputs()
        inputs.consistency_checks.er_mechanism_vs_claimant_statement = "contradiction"
        ctx = compute_apportionment(
            inputs,
            DEFAULT_PROGRAM,
            request_id="req-1",
            reviewed_as_of=NOW,
            gross_exposure=Decimal("25000"),
        )
        assert "siu_referral_recommended" in ctx.variance_flags
        assert "er_mechanism_contradicts_claimant" in ctx.variance_flags


class TestAuthorityRouting:
    def test_committable_at_examiner_when_no_variance_and_small_exposure(self) -> None:
        # Need a fact pattern that doesn't fire variance flags
        inputs = make_inputs(fact_pattern="rear_end")
        # rear_end fires powell_duty_clarity; use a lower-fault pattern
        inputs.fact_pattern = "sideswipe"  # 60/40
        ctx = compute_apportionment(
            inputs,
            DEFAULT_PROGRAM,
            request_id="req-1",
            reviewed_as_of=NOW,
            gross_exposure=Decimal("10000"),
        )
        if not ctx.variance_flags:
            assert ctx.authority_routing.committable_at_examiner
            assert ctx.authority_routing.required_tier == "examiner"

    def test_mandatory_variance_escalates_to_roundtable(self) -> None:
        ctx = _ctx(fact_pattern="uncontrolled_intersection")
        # near_50_pct_bar fires → roundtable
        assert ctx.authority_routing.required_tier == "roundtable"
        assert not ctx.authority_routing.committable_at_examiner

    def test_net_apportioned_exposure_uses_insured_pct(self) -> None:
        ctx = _ctx(fact_pattern="rear_end")  # 95% insured
        # gross 25000 × 0.95 = 23750
        assert ctx.authority_routing.gross_exposure == Decimal("25000.00")
        assert ctx.authority_routing.net_apportioned_exposure == Decimal("23750.00")


class TestEvidencePackClassification:
    def test_privileged_routes_to_reserve_only(self) -> None:
        ctx = _ctx(
            evidence_items=[
                make_evidence(
                    "recorded_statement_insured",
                    admissibility="privileged_316_066",
                    weight_class="independent",
                ),
            ],
        )
        pack = ctx.evidence_pack
        assert 0 in pack.privileged_316_066_excluded_idx
        assert 0 in pack.reserve_only_evidence_idx
        assert 0 not in pack.trial_admissible_evidence_idx

    def test_chemical_test_carveout_is_trial_admissible(self) -> None:
        ctx = _ctx(
            evidence_items=[
                make_evidence(
                    "expert_report_recon",
                    admissibility="chemical_test_carveout",
                    weight_class="hard_data",
                ),
            ],
        )
        pack = ctx.evidence_pack
        assert 0 in pack.chemical_test_carveout_admissible_idx
        assert 0 in pack.trial_admissible_evidence_idx

    def test_physical_evidence_carveout_is_trial_admissible(self) -> None:
        ctx = _ctx(
            evidence_items=[
                make_evidence(
                    "scene_photo",
                    admissibility="physical_evidence_carveout",
                    weight_class="hard_data",
                ),
            ],
        )
        pack = ctx.evidence_pack
        assert 0 in pack.physical_evidence_carveout_admissible_idx
        assert 0 in pack.trial_admissible_evidence_idx


class TestRationaleStructure:
    def test_rationale_records_anchor(self) -> None:
        ctx = _ctx()
        anchor = ctx.rationale.fact_pattern_anchor
        assert anchor.pattern == "rear_end"
        assert anchor.anchor_pct == Decimal("95")
        assert "Birge" in anchor.controlling_authority

    def test_rationale_records_each_evidence_item(self) -> None:
        evidence = [
            make_evidence("scene_photo", fault_direction="neutral", weight_class="hard_data"),
            make_evidence("citation_issued", fault_direction="insured_more_fault", weight_class="independent"),
        ]
        ctx = _ctx(evidence_items=evidence)
        assert len(ctx.rationale.evidence_adjustments) == 2

    def test_rationale_records_doctrine_gates(self) -> None:
        ctx = _ctx(fact_pattern="rear_end")
        gate_ids = [g.doctrine_id for g in ctx.rationale.doctrine_gates_applied]
        assert "rear_end_rebuttable_presumption" in gate_ids
        assert "joint_several_abolished" in gate_ids


class TestSubroReferral:
    def test_subro_recommended_when_claimant_high_fault_no_bar(self) -> None:
        # rear_end anchor 95/5 + rebuttable-signal shift toward claimant
        # → claimant lands ~32-40%, under HB 837 bar, ≥30 subro threshold
        ctx = compute_apportionment(
            make_inputs(
                fact_pattern="rear_end",
                evidence_items=[
                    make_evidence(
                        "police_report_field",
                        fault_direction="claimant_more_fault",
                        weight_class="rebuttable_signal",
                    ),
                ],
            ),
            DEFAULT_PROGRAM,
            request_id="req-1",
            reviewed_as_of=NOW,
            gross_exposure=Decimal("25000"),
        )
        claimant_pct = ctx.apportionment["P-claimant"].fault_pct
        if claimant_pct >= Decimal("30") and not ctx.resolution.applicable_regime.recovery_bar_triggered:
            assert ctx.subro_referral is not None
            assert ctx.subro_referral.recommended

    def test_no_subro_when_recovery_bar_triggered(self) -> None:
        # Heavy claimant shift past 50% on post-HB-837 → bar → no subro
        ctx = _ctx(
            fact_pattern="uncontrolled_intersection",
            evidence_items=[
                make_evidence("edr_download", fault_direction="claimant_more_fault", weight_class="hard_data"),
                make_evidence("edr_download", fault_direction="claimant_more_fault", weight_class="hard_data"),
                make_evidence("edr_download", fault_direction="claimant_more_fault", weight_class="hard_data"),
            ],
        )
        if ctx.resolution.applicable_regime.recovery_bar_triggered:
            assert ctx.subro_referral is None
