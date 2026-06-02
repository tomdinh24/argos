"""Invariants on the liability constants — golden values + structural sanity."""
from __future__ import annotations

from decimal import Decimal

import pytest

from argos.schemas.workflows.liability import FactPattern, EvidenceWeightClass
from argos.services.liability.constants import (
    DEFAULT_PROGRAM,
    EVIDENCE_WEIGHTS_V1,
    FACT_PATTERN_ANCHORS_V1,
    FL_DOCTRINE_REGISTRY_V1,
    HB_837_EFFECTIVE_DATE,
    MANDATORY_ESCALATION_VARIANCE_FLAGS,
    NATURAL_PERSON_OWNER_CAP_ECONOMIC_CONDITIONAL,
    NATURAL_PERSON_OWNER_CAP_PER_OCCURRENCE,
    NATURAL_PERSON_OWNER_CAP_PER_PERSON,
    VERSION,
)


def test_version_is_dated_v1() -> None:
    assert VERSION.startswith("v1.")


def test_fact_pattern_anchors_cover_every_literal() -> None:
    expected_patterns = set(FactPattern.__args__)  # type: ignore[attr-defined]
    assert set(FACT_PATTERN_ANCHORS_V1.keys()) == expected_patterns


@pytest.mark.parametrize(
    "pattern,expected_pct",
    [
        ("rear_end", Decimal("95")),
        ("left_turn_across_traffic", Decimal("90")),
        ("controlled_intersection", Decimal("85")),
        ("lane_change", Decimal("80")),
        ("uncontrolled_intersection", Decimal("50")),
        ("other", Decimal("50")),
    ],
)
def test_anchor_pct_golden_values(pattern: str, expected_pct: Decimal) -> None:
    assert FACT_PATTERN_ANCHORS_V1[pattern].anchor_pct == expected_pct  # type: ignore[index]


def test_evidence_weights_cover_every_class() -> None:
    expected = set(EvidenceWeightClass.__args__)  # type: ignore[attr-defined]
    assert set(EVIDENCE_WEIGHTS_V1.keys()) == expected


def test_evidence_weight_ordering() -> None:
    """Tier ordering: hard_data > party_admission/independent > rebuttable > credibility."""
    hd = EVIDENCE_WEIGHTS_V1["hard_data"]
    ind = EVIDENCE_WEIGHTS_V1["independent"]
    rb = EVIDENCE_WEIGHTS_V1["rebuttable_signal"]
    cr = EVIDENCE_WEIGHTS_V1["credibility_only"]
    assert hd.min_points >= ind.min_points
    assert ind.min_points >= rb.min_points
    assert rb.min_points >= cr.min_points


def test_doctrine_registry_has_15_doctrines() -> None:
    assert len(FL_DOCTRINE_REGISTRY_V1) >= 15
    # Named registry sanity
    for required_id in (
        "hb_837_51_bar",
        "fabre_apportionment",
        "graves_preemption",
        "intoxication_bar_768_36",
        "rear_end_rebuttable_presumption",
        "powell_duty_to_initiate",
        "good_faith_duty_harvey",
    ):
        assert required_id in FL_DOCTRINE_REGISTRY_V1


def test_hb_837_effective_date_is_2023_03_24() -> None:
    assert HB_837_EFFECTIVE_DATE.year == 2023
    assert HB_837_EFFECTIVE_DATE.month == 3
    assert HB_837_EFFECTIVE_DATE.day == 24


def test_natural_person_owner_cap_values() -> None:
    assert NATURAL_PERSON_OWNER_CAP_PER_PERSON == Decimal("100000")
    assert NATURAL_PERSON_OWNER_CAP_PER_OCCURRENCE == Decimal("300000")
    assert NATURAL_PERSON_OWNER_CAP_ECONOMIC_CONDITIONAL == Decimal("500000")


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
    assert "near_50_pct_bar" in MANDATORY_ESCALATION_VARIANCE_FLAGS
    assert "powell_duty_clarity" in MANDATORY_ESCALATION_VARIANCE_FLAGS
    assert "intoxication_bar_candidate" in MANDATORY_ESCALATION_VARIANCE_FLAGS
