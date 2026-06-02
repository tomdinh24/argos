"""Invariants on the recovery constants — golden values + structural sanity."""
from __future__ import annotations

from decimal import Decimal

from argos.services.recovery.constants import (
    AF_COMPULSORY_CAP_DOLLARS,
    AF_SIGNATORY_ROSTER_V1,
    DEFAULT_PROGRAM,
    FL_RECOVERY_DOCTRINE_REGISTRY_V1,
    HB_837_EFFECTIVE_DATE,
    MANDATORY_ESCALATION_VARIANCE_FLAGS,
    NATURAL_PERSON_OWNER_CAP_PER_OCCURRENCE,
    NATURAL_PERSON_OWNER_CAP_PER_PERSON,
    SOL_NEGLIGENCE_YEARS_POST_HB837,
    SOL_NEGLIGENCE_YEARS_PRE_HB837,
    VERSION,
)


def test_version_is_dated_v1() -> None:
    assert VERSION.startswith("v1.")


def test_doctrine_registry_has_15_doctrines() -> None:
    assert len(FL_RECOVERY_DOCTRINE_REGISTRY_V1) == 15
    required = (
        "hb837_modified_comparative_bar", "hb837_negligence_sol",
        "anti_subrogation_rule", "made_whole_doctrine",
        "pip_subrogability_627_7405", "um_preservation_627_727_6",
        "collateral_source_768_76", "vicarious_cap_324_021",
        "joint_several_abolition_768_81_3", "verbal_threshold_627_737",
        "paid_not_billed_768_0427", "af_compulsory_jurisdiction",
        "spoliation_valcin_martino", "deny_subrogate_interlock",
        "step_into_shoes_defenses",
    )
    for r in required:
        assert r in FL_RECOVERY_DOCTRINE_REGISTRY_V1


def test_hb_837_effective_date_is_2023_03_24() -> None:
    assert HB_837_EFFECTIVE_DATE.year == 2023
    assert HB_837_EFFECTIVE_DATE.month == 3
    assert HB_837_EFFECTIVE_DATE.day == 24


def test_sol_years_compressed_post_hb837() -> None:
    assert SOL_NEGLIGENCE_YEARS_POST_HB837 == 2
    assert SOL_NEGLIGENCE_YEARS_PRE_HB837 == 4


def test_natural_person_cap_values() -> None:
    assert NATURAL_PERSON_OWNER_CAP_PER_PERSON == Decimal("100000")
    assert NATURAL_PERSON_OWNER_CAP_PER_OCCURRENCE == Decimal("300000")


def test_af_cap_is_100k() -> None:
    assert AF_COMPULSORY_CAP_DOLLARS == Decimal("100000")


def test_af_signatory_roster_seeded() -> None:
    # Confirm major carrier seeds are present
    assert AF_SIGNATORY_ROSTER_V1.get("25178") is True   # State Farm
    assert AF_SIGNATORY_ROSTER_V1.get("10650") is True   # GEICO


def test_default_program_authority_ladder_monotone() -> None:
    p = DEFAULT_PROGRAM
    assert (
        p.examiner_authority_dollars
        < p.senior_examiner_authority_dollars
        < p.supervisor_authority_dollars
        < p.manager_authority_dollars
    )


def test_mandatory_escalation_includes_step_function_zones() -> None:
    """Step-function-risk zones must always escalate above examiner."""
    assert "comparative_fault_cliff_buffer" in MANDATORY_ESCALATION_VARIANCE_FLAGS
    assert "deny_plus_subrogate" in MANDATORY_ESCALATION_VARIANCE_FLAGS
    assert "release_or_pre_tender_settlement_detected" in MANDATORY_ESCALATION_VARIANCE_FLAGS


def test_recovery_probability_ladder_monotone() -> None:
    """Layer probabilities should descend operator > vicarious > neg-ent > Fabre > products."""
    p = DEFAULT_PROGRAM
    assert (
        p.p_recovery_operator_policy
        > p.p_recovery_vicarious_cap
        > p.p_recovery_negligent_entrustment
        > p.p_recovery_fabre_non_party
        > p.p_recovery_products_defect
    )
