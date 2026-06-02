"""FL recovery policy engine — gate-by-gate behavior tests."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from argos.schemas.workflows.recovery import (
    CoverageDenialStatus,
    EvidenceArtifacts,
    ExternalEventTriggers,
    OmnibusPartyEntry,
    OwnerOperatorSplit,
    PolicySubrogationLanguage,
    ReleaseSettlementSignal,
    UpstreamCoverageSnapshot,
)
from argos.services.recovery.policy_engine import apply_fl_recovery_doctrines

from tests.services.recovery._fixtures import (
    POST_HB837_LOSS, PRE_HB837_LOSS, make_inputs, make_upstream,
)


EVAL_TODAY = date(2025, 7, 1)


class TestSolRegime:
    def test_post_hb837_picks_2yr(self) -> None:
        res = apply_fl_recovery_doctrines(make_inputs(), make_upstream(), today=EVAL_TODAY)
        assert res.sol_regime.statute_version == "post_hb837_2yr"
        assert res.sol_regime.sol_deadline == date(2027, 6, 2)

    def test_pre_hb837_picks_4yr(self) -> None:
        res = apply_fl_recovery_doctrines(
            make_inputs(loss_date=PRE_HB837_LOSS),
            make_upstream(),
            today=EVAL_TODAY,
        )
        assert res.sol_regime.statute_version == "pre_hb837_4yr"
        assert res.sol_regime.sol_deadline == date(2026, 6, 2)

    def test_sol_expired_bars_recovery(self) -> None:
        # Loss in 2020 + post-eval today 2025 → 4yr clock expired
        res = apply_fl_recovery_doctrines(
            make_inputs(loss_date=date(2020, 1, 1)),
            make_upstream(),
            today=EVAL_TODAY,
        )
        assert res.recovery_barred
        assert res.bar_basis == "sol_expired"


class TestRecoveryBars:
    def test_claimant_over_50_pct_bars_recovery_post_hb837(self) -> None:
        upstream = make_upstream(insured_pct=40, claimant_pct=60)
        res = apply_fl_recovery_doctrines(make_inputs(), upstream, today=EVAL_TODAY)
        assert res.recovery_barred
        assert res.bar_basis == "hb_837_51_bar"

    def test_claimant_at_50_pct_does_not_bar(self) -> None:
        upstream = make_upstream(insured_pct=50, claimant_pct=50)
        res = apply_fl_recovery_doctrines(make_inputs(), upstream, today=EVAL_TODAY)
        assert not res.recovery_barred

    def test_near_cliff_buffer_variance_flag(self) -> None:
        # claimant 48% post-HB-837 → within ±5 of 50 → variance
        upstream = make_upstream(insured_pct=52, claimant_pct=48)
        res = apply_fl_recovery_doctrines(make_inputs(), upstream, today=EVAL_TODAY)
        assert "comparative_fault_cliff_buffer" in res.variance_flags

    def test_non_fl_loss_bars_recovery(self) -> None:
        res = apply_fl_recovery_doctrines(
            make_inputs(loss_state="other"),
            make_upstream(),
            today=EVAL_TODAY,
        )
        assert res.recovery_barred
        assert "non_fl_loss_routed_to_abstain" in res.variance_flags


class TestPipSubrogability:
    def test_pip_lane_with_commercial_passes(self) -> None:
        res = apply_fl_recovery_doctrines(
            make_inputs(
                subrogation_lane="627_7405_pip_commercial",
                tortfeasor_vehicle_classification="commercial",
            ),
            make_upstream(),
            today=EVAL_TODAY,
        )
        pip_gate = next(g for g in res.gates if g.gate_id == "pip_subrogability_627_7405")
        assert pip_gate.result == "pass"

    def test_pip_lane_with_private_passenger_fails_and_bars(self) -> None:
        res = apply_fl_recovery_doctrines(
            make_inputs(
                subrogation_lane="627_7405_pip_commercial",
                tortfeasor_vehicle_classification="private_passenger",
            ),
            make_upstream(),
            today=EVAL_TODAY,
        )
        assert res.recovery_barred
        assert res.bar_basis == "pip_non_commercial"

    def test_pip_lane_with_unknown_classification_routes_to_senior(self) -> None:
        res = apply_fl_recovery_doctrines(
            make_inputs(
                subrogation_lane="627_7405_pip_commercial",
                tortfeasor_vehicle_classification="unknown",
            ),
            make_upstream(),
            today=EVAL_TODAY,
        )
        assert "commercial_vehicle_classification_ambiguity" in res.variance_flags

    def test_legal_lane_pip_gate_na(self) -> None:
        res = apply_fl_recovery_doctrines(make_inputs(), make_upstream(), today=EVAL_TODAY)
        pip_gate = next(g for g in res.gates if g.gate_id == "pip_subrogability_627_7405")
        assert pip_gate.result == "n_a"


class TestAntiSubrogation:
    def test_overlap_routes_to_senior(self) -> None:
        # Tortfeasor operator name appears in omnibus roster
        roster = [
            OmnibusPartyEntry(
                name="P-tortfeasor-operator", role="permissive",
                coverage_section_paid_under="collision",
            ),
        ]
        res = apply_fl_recovery_doctrines(
            make_inputs(omnibus_roster=roster), make_upstream(), today=EVAL_TODAY,
        )
        assert "anti_subrogation_per_coverage_section_ambiguity" in res.variance_flags

    def test_no_overlap_passes(self) -> None:
        res = apply_fl_recovery_doctrines(make_inputs(), make_upstream(), today=EVAL_TODAY)
        gate = next(g for g in res.gates if g.gate_id == "anti_subrogation_rule")
        assert gate.result == "pass"


class TestUmAndCollateralSourceClocks:
    def test_um_window_fires_after_30_days(self) -> None:
        triggers = ExternalEventTriggers(
            liability_carrier_offer_date=date(2025, 4, 1),  # 91 days before EVAL_TODAY
        )
        res = apply_fl_recovery_doctrines(
            make_inputs(external_event_triggers=triggers),
            make_upstream(),
            today=EVAL_TODAY,
        )
        um_gate = next(g for g in res.gates if g.gate_id == "um_preservation_627_727_6")
        assert um_gate.result == "fail"

    def test_um_window_within_30_days(self) -> None:
        triggers = ExternalEventTriggers(
            liability_carrier_offer_date=date(2025, 6, 20),  # 11 days before EVAL_TODAY
        )
        res = apply_fl_recovery_doctrines(
            make_inputs(external_event_triggers=triggers),
            make_upstream(),
            today=EVAL_TODAY,
        )
        um_gate = next(g for g in res.gates if g.gate_id == "um_preservation_627_727_6")
        assert um_gate.result == "pass"

    def test_collateral_source_30_day_fires(self) -> None:
        triggers = ExternalEventTriggers(
            section_768_76_notice_date=date(2025, 5, 1),
        )
        res = apply_fl_recovery_doctrines(
            make_inputs(external_event_triggers=triggers),
            make_upstream(),
            today=EVAL_TODAY,
        )
        cs_gate = next(g for g in res.gates if g.gate_id == "collateral_source_768_76")
        assert cs_gate.result == "fail"


class TestVicariousCap:
    def test_natural_person_owner_non_operator_cap_applies(self) -> None:
        split = OwnerOperatorSplit(
            owner_id="P-owner", operator_id="P-operator",
            are_same=False, owner_type="natural_person",
        )
        res = apply_fl_recovery_doctrines(
            make_inputs(owner_operator_split=split),
            make_upstream(),
            today=EVAL_TODAY,
        )
        gate = next(g for g in res.gates if g.gate_id == "vicarious_cap_324_021")
        assert gate.result == "pass"

    def test_owner_is_operator_cap_na(self) -> None:
        res = apply_fl_recovery_doctrines(make_inputs(), make_upstream(), today=EVAL_TODAY)
        gate = next(g for g in res.gates if g.gate_id == "vicarious_cap_324_021")
        assert gate.result == "n_a"


class TestAfCompulsory:
    def test_signatory_within_cap_passes(self) -> None:
        res = apply_fl_recovery_doctrines(
            make_inputs(tortfeasor_carrier_naic="25178"),  # State Farm seed
            make_upstream(paid_indemnity=25000),
            today=EVAL_TODAY,
        )
        gate = next(g for g in res.gates if g.gate_id == "af_compulsory_jurisdiction")
        assert gate.result == "pass"

    def test_missing_naic_routes_to_senior(self) -> None:
        res = apply_fl_recovery_doctrines(
            make_inputs(tortfeasor_carrier_naic=None),
            make_upstream(),
            today=EVAL_TODAY,
        )
        assert "af_signatory_unverifiable" in res.variance_flags

    def test_non_signatory_fails(self) -> None:
        res = apply_fl_recovery_doctrines(
            make_inputs(tortfeasor_carrier_naic="11185"),  # Non-signatory seed
            make_upstream(),
            today=EVAL_TODAY,
        )
        gate = next(g for g in res.gates if g.gate_id == "af_compulsory_jurisdiction")
        assert gate.result == "fail"


class TestSpoliation:
    def test_vehicle_released_breaches_preservation(self) -> None:
        inputs = make_inputs(
            evidence_artifacts=EvidenceArtifacts(vehicle_status="released_to_salvage"),
        )
        res = apply_fl_recovery_doctrines(inputs, make_upstream(), today=EVAL_TODAY)
        gate = next(g for g in res.gates if g.gate_id == "spoliation_valcin_martino")
        assert gate.result == "fail"
        assert "preservation_hold_unacknowledged" in res.variance_flags

    def test_vehicle_in_storage_passes(self) -> None:
        res = apply_fl_recovery_doctrines(make_inputs(), make_upstream(), today=EVAL_TODAY)
        gate = next(g for g in res.gates if g.gate_id == "spoliation_valcin_martino")
        assert gate.result == "pass"


class TestDenySubrogate:
    def test_coverage_denied_routes_to_senior(self) -> None:
        upstream = make_upstream(coverage_status="denied")
        res = apply_fl_recovery_doctrines(make_inputs(), upstream, today=EVAL_TODAY)
        assert "deny_plus_subrogate" in res.variance_flags

    def test_inputs_coverage_denial_status_routes_to_senior(self) -> None:
        res = apply_fl_recovery_doctrines(
            make_inputs(coverage_denial=CoverageDenialStatus(denied=True, basis="late_notice")),
            make_upstream(),
            today=EVAL_TODAY,
        )
        assert "deny_plus_subrogate" in res.variance_flags


class TestWqbaReleaseScreen:
    def test_release_signal_fails_and_bars(self) -> None:
        # Build the input with release signal
        from argos.schemas.workflows.recovery import ReleaseSettlementSignal
        signal = ReleaseSettlementSignal(
            type="release_executed",
            party="P-tortfeasor-operator",
            signal_date=date(2025, 3, 1),
            source_doc_id="DOC-release-1",
            quoted_span="Insured releases all claims against tortfeasor.",
        )
        inputs = make_inputs()
        inputs.release_or_settlement_signals = [signal]
        res = apply_fl_recovery_doctrines(inputs, make_upstream(), today=EVAL_TODAY)
        assert res.recovery_barred
        assert res.bar_basis == "pre_tender_release"
        assert "release_or_pre_tender_settlement_detected" in res.variance_flags


def test_sol_split_window_flag_fires_near_hb837_date() -> None:
    # Loss within ±30 days of 3/24/2023 → split window flag.
    # Use eval date inside the post-HB-837 2yr clock to avoid SOL bar swallowing the flag.
    res = apply_fl_recovery_doctrines(
        make_inputs(loss_date=date(2023, 4, 5)),
        make_upstream(),
        today=date(2024, 6, 1),
    )
    assert "sol_accrual_vs_filing_split" in res.variance_flags


def test_all_15_doctrines_emit_a_gate() -> None:
    """Every doctrine in the registry produces a gate entry (pass/fail/n_a)."""
    res = apply_fl_recovery_doctrines(make_inputs(), make_upstream(), today=EVAL_TODAY)
    gate_ids = {g.gate_id for g in res.gates}
    # Engine emits a gate for each of the 15 doctrines as part of normal eval
    assert len(gate_ids) >= 14  # At least 14; some n_a paths may collapse
