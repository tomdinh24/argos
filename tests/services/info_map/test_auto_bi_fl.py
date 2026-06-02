"""Tests for the auto BI / FL info map.

The map itself is a static data structure; tests verify:
- Count matches the spec (15+11+13=39)
- All IDs unique
- All dependencies resolve to known IDs
- Conditional gating has triggers; non-conditional doesn't
- Critical-path ordering correctly surfaces perishable + long-cycle first
- Spec-doc invariants (highest-leverage HIPAA release gates 8 damages
  questions; EDR is the only perishable atom; MSPRP is the slowest)
"""
from __future__ import annotations

import pytest

from argos.services.info_map import INFO_MAP_AUTO_BI_FL as M
from argos.services.info_map.types import OpenQuestion, Source


# ---------------------------------------------------------------------------
# Shape and counts
# ---------------------------------------------------------------------------


class TestMapShape:
    def test_total_question_count(self):
        assert len(M.questions) == 39

    def test_split_by_end_state(self):
        assert len(M.for_end_state("coverage")) == 15
        assert len(M.for_end_state("liability")) == 11
        assert len(M.for_end_state("damages")) == 13

    def test_ids_unique(self):
        ids = [q.id for q in M.questions]
        assert len(ids) == len(set(ids))

    def test_ids_follow_naming_convention(self):
        for q in M.questions:
            assert q.id.startswith(("Q-COV-", "Q-LIA-", "Q-DAM-"))

    def test_revision_tag_present(self):
        assert M.revision.startswith("r")
        assert "2026" in M.revision


# ---------------------------------------------------------------------------
# Dependency integrity
# ---------------------------------------------------------------------------


class TestDependencies:
    def test_all_dependencies_resolve(self):
        ids = {q.id for q in M.questions}
        for q in M.questions:
            for dep in q.depends_on:
                assert dep in ids, f"{q.id} depends on unknown {dep}"

    def test_no_question_depends_on_itself(self):
        for q in M.questions:
            assert q.id not in q.depends_on

    def test_no_cycles_in_dependency_graph(self):
        """Topological-sort sanity — if questions cycle, this loops forever."""
        deps = {q.id: set(q.depends_on) for q in M.questions}
        resolved: set[str] = set()
        max_iterations = len(M.questions) + 1
        for _ in range(max_iterations):
            newly_resolved = {
                qid for qid, ds in deps.items()
                if qid not in resolved and ds.issubset(resolved)
            }
            if not newly_resolved:
                break
            resolved |= newly_resolved
        unresolved = set(deps) - resolved
        assert not unresolved, f"Cyclic or unresolvable dependencies: {unresolved}"


# ---------------------------------------------------------------------------
# Gating + conditional triggers
# ---------------------------------------------------------------------------


class TestGating:
    def test_conditional_questions_have_triggers(self):
        for q in M.questions:
            if q.gating == "conditional":
                assert q.conditional_trigger, f"{q.id} conditional missing trigger"

    def test_non_conditional_questions_have_no_trigger(self):
        for q in M.questions:
            if q.gating != "conditional":
                assert q.conditional_trigger is None, (
                    f"{q.id} has conditional_trigger but gating={q.gating}"
                )

    def test_validator_rejects_conditional_without_trigger(self):
        with pytest.raises(Exception):
            OpenQuestion(
                id="Q-TEST-001", description="x", blocks_end_state="coverage",
                gating="conditional", sources=[
                    Source(party="x", channel="email",
                           cycle_time_days_min=1, cycle_time_days_max=1,
                           fidelity="primary"),
                ],
                best_case_cycle_time_days_min=1,
                best_case_cycle_time_days_max=1,
                requirement_citation="x",
                cycle_time_citation="x",
            )

    def test_validator_rejects_trigger_without_conditional(self):
        with pytest.raises(Exception):
            OpenQuestion(
                id="Q-TEST-002", description="x", blocks_end_state="coverage",
                gating="required",
                conditional_trigger="oops",
                sources=[
                    Source(party="x", channel="email",
                           cycle_time_days_min=1, cycle_time_days_max=1,
                           fidelity="primary"),
                ],
                best_case_cycle_time_days_min=1,
                best_case_cycle_time_days_max=1,
                requirement_citation="x",
                cycle_time_citation="x",
            )


# ---------------------------------------------------------------------------
# Critical path
# ---------------------------------------------------------------------------


class TestCriticalPath:
    def test_perishable_questions_sort_first(self):
        order = M.critical_path_order()
        perishables = [q for q in order if q.is_perishable]
        non_perishables = [q for q in order if not q.is_perishable]
        if perishables:
            # All perishables come before any non-perishable
            last_perishable_idx = max(order.index(q) for q in perishables)
            first_non_perishable_idx = min(order.index(q) for q in non_perishables)
            assert last_perishable_idx < first_non_perishable_idx

    def test_within_non_perishable_longer_cycle_sorts_first(self):
        order = M.critical_path_order()
        non_perishables = [q for q in order if not q.is_perishable]
        for i in range(len(non_perishables) - 1):
            a, b = non_perishables[i], non_perishables[i + 1]
            # a's max cycle >= b's max cycle (sorted descending)
            assert a.best_case_cycle_time_days_max >= b.best_case_cycle_time_days_max

    def test_only_known_perishable_is_edr(self):
        perishables = M.perishable_questions()
        assert [q.id for q in perishables] == ["Q-LIA-011"]

    def test_long_pole_threshold_filters(self):
        seven_day = M.long_pole(threshold_days=7)
        # Every long-pole question must be ≥7d max OR perishable
        for q in seven_day:
            assert q.best_case_cycle_time_days_max >= 7 or q.is_perishable

    def test_msprp_is_slowest_non_demand_atom(self):
        """Q-DAM-011 (Medicare MSPRP) should be the slowest atom whose
        cycle is adjuster-controlled (i.e., excluding demand-letter
        questions like Q-DAM-012/Q-LIA-010 which are claimant-driven).
        """
        adjuster_controlled = [
            q for q in M.questions
            if q.id not in ("Q-DAM-012", "Q-LIA-010")
        ]
        slowest = max(
            adjuster_controlled,
            key=lambda q: q.best_case_cycle_time_days_max,
        )
        assert slowest.id == "Q-DAM-011"


# ---------------------------------------------------------------------------
# Spec-doc invariants
# ---------------------------------------------------------------------------


class TestSpecInvariants:
    def test_hipaa_release_transitively_gates_medical_damages_questions(self):
        """Per the spec: Q-DAM-013 (HIPAA release) is the highest-leverage
        day-1 action because it gates Q-DAM-001…008 (directly OR
        transitively through Q-DAM-002).
        """
        # Build transitive closure of "depends on Q-DAM-013"
        deps_index = {q.id: set(q.depends_on) for q in M.questions}
        transitively_gated: set[str] = set()
        changed = True
        while changed:
            changed = False
            for qid, ds in deps_index.items():
                if qid in transitively_gated:
                    continue
                if "Q-DAM-013" in ds or any(d in transitively_gated for d in ds):
                    transitively_gated.add(qid)
                    changed = True

        for needed in ("Q-DAM-001", "Q-DAM-002", "Q-DAM-004", "Q-DAM-007", "Q-DAM-008"):
            assert needed in transitively_gated, (
                f"Spec invariant: {needed} should transitively depend on Q-DAM-013"
            )

    def test_every_question_has_requirement_citation(self):
        for q in M.questions:
            assert q.requirement_citation, f"{q.id} missing requirement_citation"

    def test_every_question_has_cycle_time_citation(self):
        for q in M.questions:
            assert q.cycle_time_citation, f"{q.id} missing cycle_time_citation"

    def test_q_dam_013_has_structural_routing_note(self):
        """Q-DAM-013 must mention the rep_flag routing constraint, since
        Outreach Drafter relies on it."""
        q = M.get("Q-DAM-013")
        sources_text = " ".join(s.notes or "" for s in q.sources)
        assert "rep_flag" in sources_text


# ---------------------------------------------------------------------------
# Source helpers
# ---------------------------------------------------------------------------


class TestByParty:
    def test_by_party_returns_questions_with_that_party(self):
        cl_counsel = M.by_party("claimant_counsel")
        # Q-DAM-013 routes through counsel when represented
        ids = {q.id for q in cl_counsel}
        assert "Q-DAM-013" in ids
        assert "Q-LIA-010" in ids  # demand letter from counsel

    def test_by_party_no_match_returns_empty(self):
        assert M.by_party("nonexistent_party") == []


# ---------------------------------------------------------------------------
# Required vs nice-to-have split
# ---------------------------------------------------------------------------


class TestRequired:
    def test_required_questions_present(self):
        required = M.required_questions()
        # Critical required ones must be there
        required_ids = {q.id for q in required}
        for must_have in ("Q-COV-001", "Q-COV-006", "Q-DAM-013", "Q-LIA-001"):
            assert must_have in required_ids
