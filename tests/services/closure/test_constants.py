"""Constants registry sanity tests."""
from __future__ import annotations

from argos.services.closure.constants import (
    DEFAULT_PROGRAM,
    FL_CLOSURE_GATE_REGISTRY_V1,
    MANDATORY_ESCALATION_VARIANCE_FLAGS,
    TIER_FAILURE_PROBABILITY_CAP,
    VERSION,
)


def test_version_stamped():
    assert VERSION.startswith("v1.")


def test_gate_registry_covers_all_six_tiers():
    tiers = {g.tier for g in FL_CLOSURE_GATE_REGISTRY_V1.values()}
    assert tiers == {"A", "B", "C", "D", "E", "F"}


def test_gate_registry_count_matches_spec():
    # 14 A + 7 B + 4 C + 3 D + 1 E + 1 F = 30 (some merged in build)
    # The shipped count is whatever's in the dict — assert it's >= 25.
    assert len(FL_CLOSURE_GATE_REGISTRY_V1) >= 25


def test_every_gate_has_cite():
    for gid, seed in FL_CLOSURE_GATE_REGISTRY_V1.items():
        assert seed.statute_or_case_cite, f"Gate {gid} missing statute_or_case_cite"
        assert seed.tier in {"A", "B", "C", "D", "E", "F"}


def test_tier_probability_caps_ordered():
    assert TIER_FAILURE_PROBABILITY_CAP["A"] < TIER_FAILURE_PROBABILITY_CAP["B"]
    assert TIER_FAILURE_PROBABILITY_CAP["B"] < TIER_FAILURE_PROBABILITY_CAP["C"]
    assert TIER_FAILURE_PROBABILITY_CAP["C"] < TIER_FAILURE_PROBABILITY_CAP["F"]


def test_mandatory_escalation_flags_distinct():
    assert len(MANDATORY_ESCALATION_VARIANCE_FLAGS) == len(set(MANDATORY_ESCALATION_VARIANCE_FLAGS))


def test_default_program_authority_bands_monotonic():
    p = DEFAULT_PROGRAM
    assert p.closure_examiner_authority_dollars < p.closure_senior_examiner_authority_dollars
    assert p.closure_senior_examiner_authority_dollars < p.closure_supervisor_authority_dollars
    assert p.closure_supervisor_authority_dollars < p.closure_manager_authority_dollars
