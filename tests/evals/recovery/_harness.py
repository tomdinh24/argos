"""Eval harness for Recovery workflow.

One `RecoveryEvalCase` per scenario. Runner runs the policy engine + the
apportionment calculator, then asserts every non-None expectation against
the produced `DoctrineResolution` + `CalculationContext`.

Pass criteria: `docs/evals/recovery-thresholds.md`. Per the 2026-06-02
eval-design policy: every emitted field is GRADED or DEFERRED; default
tolerance is 0.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal

from argos.schemas.workflows.recovery import (
    AuthorityTier,
    DoctrineResolution,
    ForumRecommendation,
    GateResult,
    Recommendation,
    RecoveryInputs,
    RecoveryUpstreamContext,
    VarianceFlag,
)
from argos.services.recovery.apportionment_calculator import (
    CalculationContext,
    compute_recovery,
)
from argos.services.recovery.constants import DEFAULT_PROGRAM
from argos.services.recovery.policy_engine import apply_fl_recovery_doctrines


HB837_EFFECTIVE = date(2023, 3, 24)
POST_HB837 = date(2025, 6, 2)
PRE_HB837 = date(2022, 6, 2)
REVIEW_AS_OF = datetime(2026, 6, 2, 10, 0, 0, tzinfo=timezone.utc)
REVIEW_AS_OF_DATE = REVIEW_AS_OF.date()


@dataclass
class RecoveryEvalCase:
    """One eval scenario + the assertions it should satisfy.

    All expectations are exact-match. Set only the fields a case
    targets; unset ones aren't asserted.
    """

    case_id: str
    description: str
    inputs: RecoveryInputs
    upstream: RecoveryUpstreamContext

    # Top-level decision
    expected_recommendation: Recommendation | None = None
    expected_recovery_barred: bool | None = None
    expected_bar_basis: str | None = None

    # SOL regime
    expected_statute_version: str | None = None
    expected_sol_deadline: date | None = None
    expected_sol_days_remaining: int | None = None

    # Variance flags — exact set
    expected_variance_flags_exact: set[VarianceFlag] | None = None
    expected_variance_flags_include: set[VarianceFlag] = field(default_factory=set)
    expected_variance_flags_exclude: set[VarianceFlag] = field(default_factory=set)

    # Per-gate results (gate_id → expected result)
    expected_gate_results: dict[str, GateResult] = field(default_factory=dict)

    # Subrogation lane cite (substring)
    expected_subrogation_lane_id: str | None = None
    expected_subrogation_lane_cite_substr: str | None = None

    # Recoverable basis
    expected_basis: Decimal | None = None
    expected_capped_damages: Decimal | None = None
    expected_stripped: Decimal | None = None

    # Layered targets — by layer_id membership + per-layer assertions
    expected_layer_ids_present: set[str] = field(default_factory=set)
    expected_layer_ids_absent: set[str] = field(default_factory=set)
    expected_layer_assertions: dict[str, dict] = field(default_factory=dict)

    # Net economics
    expected_net_total: Decimal | None = None
    expected_fee_model: str | None = None
    expected_fee_drag: Decimal | None = None
    expected_fee_shifting: Decimal | None = None

    # Forum
    expected_forum_recommendation: ForumRecommendation | None = None
    expected_within_af_cap: bool | None = None
    expected_af_signatory_check: str | None = None

    # Authority routing
    expected_authority_tier: AuthorityTier | None = None
    expected_committable_at_examiner: bool | None = None

    # Preservation hold
    expected_preservation_issued: bool | None = None
    expected_preservation_scope_includes: set[str] = field(default_factory=set)

    # Cross-stream
    expected_interlock: str | None = None
    expected_omnibus_overlap_min_count: int | None = None

    # Deadline calendar — per-deadline assertions
    expected_deadline_ids_present: set[str] = field(default_factory=set)


def run_case(case: RecoveryEvalCase) -> tuple[DoctrineResolution, CalculationContext]:
    """Run policy engine + calculator. Returns (resolution, context)."""
    resolution = apply_fl_recovery_doctrines(
        case.inputs, case.upstream, today=REVIEW_AS_OF_DATE,
    )
    ctx = compute_recovery(
        case.inputs, case.upstream, resolution, DEFAULT_PROGRAM,
        reviewed_as_of=REVIEW_AS_OF,
    )
    return resolution, ctx


def _check(failures: list[str], label: str, expected, got) -> None:
    if expected != got:
        failures.append(f"{label}: expected {expected!r}, got {got!r}")


def assert_case(
    case: RecoveryEvalCase,
    resolution: DoctrineResolution,
    ctx: CalculationContext,
) -> None:
    failures: list[str] = []

    # Top-level decision
    if case.expected_recommendation is not None:
        _check(failures, "recommendation",
               case.expected_recommendation, ctx.recommendation)
    if case.expected_recovery_barred is not None:
        _check(failures, "recovery_barred",
               case.expected_recovery_barred, resolution.recovery_barred)
    if case.expected_bar_basis is not None:
        _check(failures, "bar_basis",
               case.expected_bar_basis, resolution.bar_basis)

    # SOL regime
    if case.expected_statute_version is not None:
        _check(failures, "sol.statute_version",
               case.expected_statute_version,
               resolution.sol_regime.statute_version)
    if case.expected_sol_deadline is not None:
        _check(failures, "sol.deadline",
               case.expected_sol_deadline, resolution.sol_regime.sol_deadline)
    if case.expected_sol_days_remaining is not None:
        _check(failures, "sol.days_remaining",
               case.expected_sol_days_remaining,
               resolution.sol_regime.days_remaining)

    # Variance flags
    got_variance = set(resolution.variance_flags)
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
                f"variance_flags: expected to include {f!r}; "
                f"got {sorted(got_variance)}",
            )
    for f in case.expected_variance_flags_exclude:
        if f in got_variance:
            failures.append(
                f"variance_flags: expected NOT to include {f!r}; "
                f"got {sorted(got_variance)}",
            )

    # Gate results
    gate_by_id = {g.gate_id: g for g in resolution.gates}
    for gid, expected_result in case.expected_gate_results.items():
        if gid not in gate_by_id:
            failures.append(f"gate[{gid}]: not present in resolution.gates")
            continue
        if gate_by_id[gid].result != expected_result:
            failures.append(
                f"gate[{gid}].result: expected {expected_result!r}, "
                f"got {gate_by_id[gid].result!r}",
            )

    # Subrogation lane
    if case.expected_subrogation_lane_id is not None:
        _check(failures, "subrogation_lane.lane_id",
               case.expected_subrogation_lane_id,
               ctx.subrogation_lane.lane_id)
    if case.expected_subrogation_lane_cite_substr is not None:
        if case.expected_subrogation_lane_cite_substr not in ctx.subrogation_lane.cite:
            failures.append(
                f"subrogation_lane.cite: expected substring "
                f"{case.expected_subrogation_lane_cite_substr!r}, "
                f"got {ctx.subrogation_lane.cite!r}",
            )

    # Recoverable basis
    if case.expected_basis is not None:
        _check(failures, "recoverable_basis.basis",
               case.expected_basis, ctx.recoverable_basis.basis)
    if case.expected_capped_damages is not None:
        _check(failures, "recoverable_basis.capped_damages",
               case.expected_capped_damages,
               ctx.recoverable_basis.section_768_0427_capped_damages)
    if case.expected_stripped is not None:
        _check(failures, "recoverable_basis.stripped",
               case.expected_stripped,
               ctx.recoverable_basis.pip_collateral_source_stripped)

    # Layered targets
    got_layer_ids = {t.layer_id for t in ctx.layered_targets}
    for layer_id in case.expected_layer_ids_present:
        if layer_id not in got_layer_ids:
            failures.append(
                f"layered_targets: expected layer {layer_id!r} present; "
                f"got {sorted(got_layer_ids)}",
            )
    for layer_id in case.expected_layer_ids_absent:
        if layer_id in got_layer_ids:
            failures.append(
                f"layered_targets: expected layer {layer_id!r} absent; "
                f"got {sorted(got_layer_ids)}",
            )

    layer_by_id = {t.layer_id: t for t in ctx.layered_targets}
    for layer_id, asserts in case.expected_layer_assertions.items():
        if layer_id not in layer_by_id:
            failures.append(
                f"layer_assertion[{layer_id}]: layer not present",
            )
            continue
        layer = layer_by_id[layer_id]
        for attr, expected in asserts.items():
            got = getattr(layer, attr)
            if got != expected:
                failures.append(
                    f"layer[{layer_id}].{attr}: expected {expected!r}, got {got!r}",
                )

    # Net economics
    if case.expected_net_total is not None:
        _check(failures, "net_economics.net_total",
               case.expected_net_total, ctx.net_economics.net_total)
    if case.expected_fee_model is not None:
        _check(failures, "net_economics.fee_model",
               case.expected_fee_model, ctx.net_economics.fee_model)
    if case.expected_fee_drag is not None:
        _check(failures, "net_economics.fee_drag",
               case.expected_fee_drag, ctx.net_economics.fee_drag)
    if case.expected_fee_shifting is not None:
        _check(failures, "net_economics.fee_shifting",
               case.expected_fee_shifting, ctx.net_economics.fee_shifting_exposure)

    # Forum
    if case.expected_forum_recommendation is not None:
        _check(failures, "forum_routing.recommendation",
               case.expected_forum_recommendation,
               ctx.forum_routing.recommendation)
    if case.expected_within_af_cap is not None:
        _check(failures, "forum_routing.within_af_cap",
               case.expected_within_af_cap, ctx.forum_routing.within_af_cap)
    if case.expected_af_signatory_check is not None:
        _check(failures, "forum_routing.af_signatory_check",
               case.expected_af_signatory_check,
               ctx.forum_routing.af_signatory_check)

    # Authority routing
    if case.expected_authority_tier is not None:
        _check(failures, "authority_routing.required_tier",
               case.expected_authority_tier,
               ctx.authority_routing.required_tier)
    if case.expected_committable_at_examiner is not None:
        _check(failures, "authority_routing.committable_at_examiner",
               case.expected_committable_at_examiner,
               ctx.authority_routing.committable_at_examiner)

    # Preservation hold
    if case.expected_preservation_issued is not None:
        _check(failures, "preservation_hold.issued",
               case.expected_preservation_issued,
               ctx.preservation_hold.issued)
    if case.expected_preservation_scope_includes:
        got_scope = set(ctx.preservation_hold.hold_scope)
        for s in case.expected_preservation_scope_includes:
            if s not in got_scope:
                failures.append(
                    f"preservation_hold.hold_scope: expected {s!r}; "
                    f"got {sorted(got_scope)}",
                )

    # Cross-stream
    if case.expected_interlock is not None:
        _check(failures, "cross_stream.interlock",
               case.expected_interlock,
               ctx.cross_stream_conflicts.coverage_denial_recovery_pursuit_interlock)
    if case.expected_omnibus_overlap_min_count is not None:
        got_n = len(ctx.cross_stream_conflicts.anti_subrogation_omnibus_overlap)
        if got_n < case.expected_omnibus_overlap_min_count:
            failures.append(
                f"cross_stream.omnibus_overlap count: expected ≥"
                f"{case.expected_omnibus_overlap_min_count}, got {got_n}",
            )

    # Deadlines
    got_deadline_ids = {e.deadline_id for e in ctx.deadline_calendar.entries}
    for did in case.expected_deadline_ids_present:
        if did not in got_deadline_ids:
            failures.append(
                f"deadline_calendar: expected {did!r}; "
                f"got {sorted(got_deadline_ids)}",
            )

    # Smoke: gates with non-n_a result carry a cite
    for g in resolution.gates:
        if g.result != "n_a" and not g.statute_or_case_cite:
            failures.append(
                f"gate[{g.gate_id}] result={g.result!r} but cite is empty",
            )

    if failures:
        msg = (
            f"\nEVAL FAIL — case {case.case_id} ({case.description}):\n"
            + "\n".join(f"  - {f}" for f in failures)
        )
        raise AssertionError(msg)


__all__ = [
    "HB837_EFFECTIVE",
    "POST_HB837",
    "PRE_HB837",
    "REVIEW_AS_OF",
    "REVIEW_AS_OF_DATE",
    "RecoveryEvalCase",
    "assert_case",
    "run_case",
]
