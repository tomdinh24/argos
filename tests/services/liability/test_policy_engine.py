"""FL doctrine policy engine — gate-by-gate behavior tests."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from argos.schemas.workflows.liability import (
    IntoxicationEvidence,
    NegligentEntrustment,
    OwnerRelationship,
)
from argos.services.liability.constants import DEFAULT_PROGRAM
from argos.services.liability.policy_engine import apply_fl_doctrines

from tests.services.liability._fixtures import (
    POST_HB837_LOSS,
    PRE_HB837_LOSS,
    make_inputs,
)


class TestRegimeDetection:
    def test_post_hb837_auto_bi_picks_modified_51(self) -> None:
        res = apply_fl_doctrines(make_inputs(), DEFAULT_PROGRAM)
        assert res.applicable_regime.statute == "modified_51_bar_hb837"
        assert "hb_837_51_bar" in res.doctrines_applied

    def test_pre_hb837_picks_pure_comparative(self) -> None:
        res = apply_fl_doctrines(
            make_inputs(accrual_date=PRE_HB837_LOSS), DEFAULT_PROGRAM,
        )
        assert res.applicable_regime.statute == "pure_comparative_pre_hb837"
        assert "pure_comparative_pre_hb837" in res.doctrines_applied

    def test_med_mal_keeps_pure_comparative_after_hb837(self) -> None:
        res = apply_fl_doctrines(
            make_inputs(line_of_business="med_mal"), DEFAULT_PROGRAM,
        )
        assert res.applicable_regime.statute == "med_mal_pure_comparative"

    def test_hb837_effective_date_is_inclusive(self) -> None:
        on_date = make_inputs(accrual_date=date(2023, 3, 24))
        res = apply_fl_doctrines(on_date, DEFAULT_PROGRAM)
        assert res.applicable_regime.statute == "modified_51_bar_hb837"


class TestRecoveryBarHb837:
    def test_claimant_under_50_no_bar(self) -> None:
        res = apply_fl_doctrines(
            make_inputs(),
            DEFAULT_PROGRAM,
            claimant_fault_pct=Decimal("45"),
        )
        assert not res.applicable_regime.recovery_bar_triggered

    def test_claimant_over_50_triggers_bar(self) -> None:
        res = apply_fl_doctrines(
            make_inputs(),
            DEFAULT_PROGRAM,
            claimant_fault_pct=Decimal("55"),
        )
        assert res.applicable_regime.recovery_bar_triggered
        assert res.applicable_regime.bar_basis == "hb837_51_pct"

    def test_pre_hb837_never_bars_on_high_claimant_pct(self) -> None:
        res = apply_fl_doctrines(
            make_inputs(accrual_date=PRE_HB837_LOSS),
            DEFAULT_PROGRAM,
            claimant_fault_pct=Decimal("80"),
        )
        assert not res.applicable_regime.recovery_bar_triggered


class TestIntoxicationBar768_36:
    def _intox(self, *, bac: str = "0.10", causation: bool = True) -> IntoxicationEvidence:
        return IntoxicationEvidence(
            bac_value=Decimal(bac),
            bac_source="blood",
            impairment_observed=True,
            causation_to_fault_evidence_cites=(
                ["recon-report-1"] if causation else []
            ),
            chemical_test_admissible=True,
        )

    def test_full_dual_prong_triggers_bar(self) -> None:
        inputs = make_inputs(intox=self._intox())
        res = apply_fl_doctrines(
            inputs, DEFAULT_PROGRAM, claimant_fault_pct=Decimal("60"),
        )
        assert res.applicable_regime.bar_basis == "768_36_intoxication"
        assert "intoxication_bar_768_36" in res.doctrines_applied

    def test_no_causation_evidence_does_not_bar(self) -> None:
        inputs = make_inputs(intox=self._intox(causation=False))
        res = apply_fl_doctrines(
            inputs, DEFAULT_PROGRAM, claimant_fault_pct=Decimal("80"),
        )
        assert res.applicable_regime.bar_basis != "768_36_intoxication"

    def test_under_50_pct_fault_does_not_bar_even_with_full_evidence(self) -> None:
        inputs = make_inputs(intox=self._intox())
        res = apply_fl_doctrines(
            inputs, DEFAULT_PROGRAM, claimant_fault_pct=Decimal("40"),
        )
        assert res.applicable_regime.bar_basis != "768_36_intoxication"


class TestExposureCeilingGraves:
    def test_commercial_lessor_graves_preempts(self) -> None:
        inputs = make_inputs(owner_type="commercial_lessor_graves", driver_is_owner=False)
        res = apply_fl_doctrines(inputs, DEFAULT_PROGRAM)
        assert res.exposure_ceiling.graves_lessor_removed
        assert "graves_preemption" in res.doctrines_applied
        assert not res.exposure_ceiling.vicarious_cap_applies

    def test_graves_exception_when_negligence_evidence_present(self) -> None:
        inputs = make_inputs(
            owner_type="commercial_lessor_graves",
            driver_is_owner=False,
            neg_ent=NegligentEntrustment(
                owner_knowledge_evidence_cites=["maintenance-log-1"],
            ),
        )
        res = apply_fl_doctrines(inputs, DEFAULT_PROGRAM)
        assert not res.exposure_ceiling.graves_lessor_removed


class TestExposureCeilingNaturalPerson:
    def test_natural_person_owner_non_driver_caps(self) -> None:
        inputs = make_inputs(driver_is_owner=False, owner_type="natural_person")
        res = apply_fl_doctrines(inputs, DEFAULT_PROGRAM)
        assert res.exposure_ceiling.vicarious_cap_applies
        assert res.exposure_ceiling.vicarious_cap_value == Decimal("300000")

    def test_driver_is_owner_no_vicarious_cap(self) -> None:
        # Driver-as-owner is direct exposure, not vicarious — no §324 cap
        inputs = make_inputs(driver_is_owner=True, owner_type="natural_person")
        res = apply_fl_doctrines(inputs, DEFAULT_PROGRAM)
        assert not res.exposure_ceiling.vicarious_cap_applies

    def test_negligent_entrustment_path_available_with_indicators(self) -> None:
        inputs = make_inputs(
            driver_is_owner=False,
            owner_type="natural_person",
            neg_ent=NegligentEntrustment(
                driver_unlicensed=True,
                owner_knowledge_evidence_cites=["recorded-statement-1"],
            ),
        )
        res = apply_fl_doctrines(inputs, DEFAULT_PROGRAM)
        assert res.exposure_ceiling.negligent_entrustment_uncapped_path_available
        assert "negligent_entrustment_uncapped" in res.doctrines_applied


def test_joint_several_abolished_always_emitted() -> None:
    res = apply_fl_doctrines(make_inputs(), DEFAULT_PROGRAM)
    assert "joint_several_abolished" in res.doctrines_applied


def test_rear_end_doctrine_emitted_for_rear_end_pattern() -> None:
    res = apply_fl_doctrines(make_inputs(fact_pattern="rear_end"), DEFAULT_PROGRAM)
    assert "rear_end_rebuttable_presumption" in res.doctrines_applied


def test_left_turn_pattern_does_not_emit_rear_end_doctrine() -> None:
    res = apply_fl_doctrines(
        make_inputs(fact_pattern="left_turn_across_traffic"), DEFAULT_PROGRAM,
    )
    assert "rear_end_rebuttable_presumption" not in res.doctrines_applied
