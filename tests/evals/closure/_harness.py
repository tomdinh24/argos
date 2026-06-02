"""Eval harness for Closure workflow.

One `ClosureEvalCase` per scenario. Runs `apply_fl_closure_gates` +
`build_closure_assessment`; asserts every non-None expectation.

Pass criteria: `docs/evals/closure-thresholds.md`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal

from argos.schemas.workflows.closure import (
    AuthorityTier,
    ClosureAssessment,
    ClosureInputs,
    ClosureUpstreamContext,
    DefectTier,
    DefenseStatus,
    GateResult,
    IndemnityStatus,
    OirClassification,
    Recommendation,
    VarianceFlag,
)
from argos.services.closure.closure_calculator import build_closure_assessment
from argos.services.closure.constants import DEFAULT_PROGRAM
from argos.services.closure.policy_engine import apply_fl_closure_gates


HB837_EFFECTIVE = date(2023, 3, 24)
EVAL_TODAY = date(2026, 6, 2)
DEFAULT_LOSS = date(2025, 6, 2)
REVIEW_AS_OF = datetime(2026, 6, 2, 10, 0, 0, tzinfo=timezone.utc)


@dataclass
class ClosureEvalCase:
    case_id: str
    description: str
    inputs: ClosureInputs
    upstream: ClosureUpstreamContext

    # Top-line
    expected_recommendation: Recommendation | None = None
    expected_ready_probability: float | None = None
    expected_indemnity_status: IndemnityStatus | None = None
    expected_defense_status: DefenseStatus | None = None
    expected_oir_classification: OirClassification | None = None

    # Blocking defects
    expected_defect_gate_ids: set[str] | None = None  # exact set match
    expected_defect_gate_ids_include: set[str] = field(default_factory=set)
    expected_defect_tiers_include: set[DefectTier] = field(default_factory=set)

    # Gates (gate_id → expected result)
    expected_gate_results: dict[str, GateResult] = field(default_factory=dict)

    # Variance flags
    expected_variance_flags_exact: set[VarianceFlag] | None = None
    expected_variance_flags_include: set[VarianceFlag] = field(default_factory=set)
    expected_variance_flags_exclude: set[VarianceFlag] = field(default_factory=set)

    # Authority
    expected_authority_tier: AuthorityTier | None = None
    expected_committable_at_examiner: bool | None = None
    expected_settlement_amount: Decimal | None = None

    # Preservation
    expected_preservation_until_date: date | None = None


def run_case(case: ClosureEvalCase) -> ClosureAssessment:
    """Run policy engine + calculator. Returns the assessment."""
    doctrine = apply_fl_closure_gates(
        case.inputs, case.upstream, DEFAULT_PROGRAM, today=EVAL_TODAY,
    )
    return build_closure_assessment(
        case.inputs, case.upstream, DEFAULT_PROGRAM, doctrine,
        request_id=f"REQ-{case.case_id}",
        today=EVAL_TODAY,
        reviewed_as_of=REVIEW_AS_OF,
    )


def _check(failures: list[str], label: str, expected, got) -> None:
    if expected != got:
        failures.append(f"{label}: expected {expected!r}, got {got!r}")


def assert_case(case: ClosureEvalCase, a: ClosureAssessment) -> None:
    failures: list[str] = []

    if case.expected_recommendation is not None:
        _check(failures, "recommendation", case.expected_recommendation, a.recommendation)
    if case.expected_ready_probability is not None:
        _check(failures, "ready_probability",
               case.expected_ready_probability, a.ready_probability)
    if case.expected_indemnity_status is not None:
        _check(failures, "indemnity_status",
               case.expected_indemnity_status, a.indemnity_status)
    if case.expected_defense_status is not None:
        _check(failures, "defense_status",
               case.expected_defense_status, a.defense_status)
    if case.expected_oir_classification is not None:
        _check(failures, "oir_classification",
               case.expected_oir_classification, a.oir_classification)

    got_defect_ids = {d.gate_id for d in a.blocking_defects}
    if case.expected_defect_gate_ids is not None:
        if got_defect_ids != case.expected_defect_gate_ids:
            failures.append(
                f"blocking_defects gate_ids: expected exactly "
                f"{sorted(case.expected_defect_gate_ids)}, "
                f"got {sorted(got_defect_ids)}",
            )
    for gid in case.expected_defect_gate_ids_include:
        if gid not in got_defect_ids:
            failures.append(
                f"blocking_defects: expected to include {gid!r}; "
                f"got {sorted(got_defect_ids)}",
            )
    got_defect_tiers = {d.tier for d in a.blocking_defects}
    for tier in case.expected_defect_tiers_include:
        if tier not in got_defect_tiers:
            failures.append(
                f"blocking_defects tiers: expected to include {tier!r}; "
                f"got {sorted(got_defect_tiers)}",
            )

    # Gates
    gate_by_id = {g.gate_id: g for g in a.doctrinal_gates}
    for gid, expected_result in case.expected_gate_results.items():
        if gid not in gate_by_id:
            failures.append(f"gate[{gid}]: not present")
            continue
        if gate_by_id[gid].result != expected_result:
            failures.append(
                f"gate[{gid}].result: expected {expected_result!r}, "
                f"got {gate_by_id[gid].result!r}",
            )

    # Variance flags
    got_variance = set(a.variance_flags)
    if case.expected_variance_flags_exact is not None:
        if got_variance != case.expected_variance_flags_exact:
            failures.append(
                f"variance_flags: expected exactly "
                f"{sorted(case.expected_variance_flags_exact)}, "
                f"got {sorted(got_variance)}",
            )
    for f in case.expected_variance_flags_include:
        if f not in got_variance:
            failures.append(
                f"variance_flags: expected {f!r}; got {sorted(got_variance)}",
            )
    for f in case.expected_variance_flags_exclude:
        if f in got_variance:
            failures.append(
                f"variance_flags: expected NOT to include {f!r}; "
                f"got {sorted(got_variance)}",
            )

    # Authority
    if case.expected_authority_tier is not None:
        _check(failures, "authority.required_tier",
               case.expected_authority_tier,
               a.authority_tier_required.required_tier)
    if case.expected_committable_at_examiner is not None:
        _check(failures, "authority.committable_at_examiner",
               case.expected_committable_at_examiner,
               a.authority_tier_required.committable_at_examiner)
    if case.expected_settlement_amount is not None:
        _check(failures, "authority.settlement_amount",
               case.expected_settlement_amount,
               a.authority_tier_required.settlement_amount)

    # Preservation
    if case.expected_preservation_until_date is not None:
        _check(failures, "preservation_plan.preservation_until_date",
               case.expected_preservation_until_date,
               a.preservation_plan.preservation_until_date)

    # Smoke: every failed gate has cite + remediation
    for g in a.doctrinal_gates:
        if g.result == "fail":
            if not g.statute_or_case_cite:
                failures.append(f"gate[{g.gate_id}] failed without cite")
            if not g.remediation_action:
                failures.append(f"gate[{g.gate_id}] failed without remediation")
            if not g.defect_emitted:
                failures.append(f"gate[{g.gate_id}] failed but defect_emitted=False")

    if failures:
        msg = (
            f"\nEVAL FAIL — case {case.case_id} ({case.description}):\n"
            + "\n".join(f"  - {f}" for f in failures)
        )
        raise AssertionError(msg)


__all__ = [
    "DEFAULT_LOSS",
    "EVAL_TODAY",
    "HB837_EFFECTIVE",
    "REVIEW_AS_OF",
    "ClosureEvalCase",
    "assert_case",
    "run_case",
]
