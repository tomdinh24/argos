"""Invariants on the versioned reserve constants.

These tests catch silent calibration drift — if anyone edits MULTIPLIER_TABLE_V1
in place instead of creating V2, ordering or range invariants will fail.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from argos.services.reserve.constants import (
    DEFAULT_PROGRAM,
    DEFENSE_PHASE_BUDGETS_V1,
    DEFENSE_PHASE_ORDER,
    MULTIPLIER_TABLE_V1,
    NOTICE_THRESHOLDS_V1,
    VENUE_GENERALS_MULTIPLIER_V1,
    VERSION,
)


def test_version_pinned():
    assert VERSION.startswith("v1.")


def test_multiplier_bands_ordered():
    for bucket, tier in MULTIPLIER_TABLE_V1.items():
        if bucket == "catastrophic":
            # Catastrophic uses life-care-plan, multipliers are zero.
            continue
        assert tier.multiplier_low <= tier.multiplier_central <= tier.multiplier_high, (
            f"{bucket}: multiplier band must be ordered low ≤ central ≤ high"
        )


def test_multiplier_bands_in_industry_range():
    """Multipliers should fall within plaintiff-bar/carrier-side anchor range.

    Lower bound: 1.0 (carrier-side never goes below specials for generals).
    Upper bound: 5.0 (catastrophic excepted; severe_permanent caps at 5.0).
    """
    for bucket, tier in MULTIPLIER_TABLE_V1.items():
        if bucket == "catastrophic":
            continue
        assert Decimal("1.0") <= tier.multiplier_low, f"{bucket} multiplier_low < 1.0"
        assert tier.multiplier_high <= Decimal("5.0"), f"{bucket} multiplier_high > 5.0"


def test_typical_indemnity_ordered():
    for bucket, tier in MULTIPLIER_TABLE_V1.items():
        assert tier.typical_indemnity_low <= tier.typical_indemnity_high


def test_severity_tier_progression():
    """Each successive tier should have higher typical-indemnity floor."""
    order = [
        "minor_soft_tissue", "moderate_ortho_non_surgical",
        "surgical_recovering", "severe_permanent", "catastrophic",
    ]
    prev_low = Decimal("0")
    for bucket in order:
        tier = MULTIPLIER_TABLE_V1[bucket]
        assert tier.typical_indemnity_low >= prev_low, (
            f"{bucket}: typical_indemnity_low ({tier.typical_indemnity_low}) "
            f"< prev tier ({prev_low})"
        )
        prev_low = tier.typical_indemnity_low


def test_phase_budgets_ordered():
    for phase, budget in DEFENSE_PHASE_BUDGETS_V1.items():
        assert budget.low <= budget.central <= budget.high, (
            f"phase {phase}: ordering violation"
        )


def test_phase_budget_pre_suit_is_zero():
    pre = DEFENSE_PHASE_BUDGETS_V1["pre_suit"]
    assert pre.low == pre.central == pre.high == Decimal("0")


def test_phase_order_covers_all_phases():
    assert set(DEFENSE_PHASE_ORDER) == set(DEFENSE_PHASE_BUDGETS_V1.keys())


def test_venue_multipliers_in_reasonable_range():
    for county, mult in VENUE_GENERALS_MULTIPLIER_V1.items():
        assert Decimal("0.5") <= mult <= Decimal("2.0"), (
            f"venue {county}: multiplier {mult} outside [0.5, 2.0]"
        )


def test_tri_county_higher_than_n_florida():
    """Established directional ranking: Miami-Dade > Duval."""
    assert (
        VENUE_GENERALS_MULTIPLIER_V1["miami_dade"]
        > VENUE_GENERALS_MULTIPLIER_V1["duval"]
    )


def test_default_program_authority_ladder():
    p = DEFAULT_PROGRAM
    assert p.examiner_reserve_authority < p.supervisor_reserve_authority
    assert p.supervisor_reserve_authority < p.manager_reserve_authority


def test_notice_thresholds_present():
    assert "reinsurance" in NOTICE_THRESHOLDS_V1
    assert "excess_carrier" in NOTICE_THRESHOLDS_V1
    assert "large_loss_committee" in NOTICE_THRESHOLDS_V1


def test_catastrophic_categorical_in_reinsurance_notice():
    """Catastrophic injuries must trigger reinsurance notice categorically."""
    rein = NOTICE_THRESHOLDS_V1["reinsurance"]
    for required in ("fatality", "tbi", "sci", "amputation"):
        assert required in rein.categorical_triggers, (
            f"{required} missing from reinsurance categorical triggers"
        )
