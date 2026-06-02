"""Eval harness for Liability workflow.

One `LiabilityEvalCase` per scenario. Runner builds the inputs, runs
the deterministic core (`compute_apportionment`), then asserts every
non-None expectation field against the produced `CalculationContext`.

Pass criteria documented in docs/evals/liability-thresholds.md.

Liability's output is NOT a dollar estimate — that lives in Reserve.
The fields graded here are: apportionment, applicable regime, bar
status, exposure ceiling, doctrines applied. See the threshold doc.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal

from argos.schemas.workflows.liability import (
    ApplicableRegimeStatute,
    LiabilityInputs,
    ProgramConfig,
    RecoveryBarBasis,
)
from argos.services.liability.apportionment_calculator import (
    CalculationContext,
    compute_apportionment,
)


DEFAULT_PROGRAM = ProgramConfig(
    program_id="EVAL_DEFAULT_FL_SPECIALTY_AUTO_BI",
    examiner_authority_dollars=Decimal("25000"),
    senior_examiner_authority_dollars=Decimal("75000"),
    supervisor_authority_dollars=Decimal("250000"),
    manager_authority_dollars=Decimal("1000000"),
    roundtable_threshold_dollars=Decimal("1000000"),
)


# Default tolerance for the apportionment central value. The calculator
# math is deterministic, so anything wider than this is a fixture-
# expectation drift, not an LLM-accuracy issue.
DEFAULT_FAULT_TOLERANCE_PP = Decimal("5")


@dataclass
class LiabilityEvalCase:
    """One eval scenario + the assertions it should satisfy."""

    case_id: str
    description: str
    inputs: LiabilityInputs

    # Regime expectations
    expected_regime: ApplicableRegimeStatute | None = None
    expected_bar_triggered: bool | None = None
    expected_bar_basis: RecoveryBarBasis | None = None

    # Apportionment central-value expectations (± tolerance_pp)
    expected_insured_fault_pct: Decimal | None = None
    expected_claimant_fault_pct: Decimal | None = None
    fault_tolerance_pp: Decimal = DEFAULT_FAULT_TOLERANCE_PP

    # Exposure ceiling expectations
    expected_vicarious_cap_applies: bool | None = None
    expected_vicarious_cap_value: Decimal | None = None
    expected_graves_lessor_removed: bool | None = None
    expected_neg_ent_path_available: bool | None = None
    expected_fabre_defendants_min_count: int | None = None

    # Doctrine membership expectations
    expected_doctrines_applied: list[str] = field(default_factory=list)
    expected_doctrines_not_applied: list[str] = field(default_factory=list)


def run_case(
    case: LiabilityEvalCase,
    *,
    request_id: str = "REQ-eval",
    reviewed_as_of: datetime | None = None,
) -> CalculationContext:
    """Run the deterministic core for one case. Returns the calc context."""
    return compute_apportionment(
        case.inputs,
        DEFAULT_PROGRAM,
        request_id=request_id,
        reviewed_as_of=reviewed_as_of or datetime(
            2026, 6, 2, 10, 0, 0, tzinfo=timezone.utc,
        ),
    )


def _resolve_insured_id(inputs: LiabilityInputs) -> str | None:
    for p in inputs.parties:
        if p.role == "insured_driver":
            return p.party_id
    return None


def _resolve_claimant_id(inputs: LiabilityInputs) -> str | None:
    for p in inputs.parties:
        if p.role in ("claimant_driver", "claimant_pedestrian"):
            return p.party_id
    return None


def assert_case(case: LiabilityEvalCase, ctx: CalculationContext) -> None:
    """Assert every non-None expectation against the calc context."""
    failures: list[str] = []

    regime = ctx.resolution.applicable_regime
    ceiling = ctx.resolution.exposure_ceiling

    if case.expected_regime is not None and regime.statute != case.expected_regime:
        failures.append(
            f"regime: expected {case.expected_regime!r}, got {regime.statute!r}",
        )
    if case.expected_bar_triggered is not None and (
        regime.recovery_bar_triggered != case.expected_bar_triggered
    ):
        failures.append(
            f"bar_triggered: expected {case.expected_bar_triggered}, "
            f"got {regime.recovery_bar_triggered}",
        )
    if case.expected_bar_basis is not None and regime.bar_basis != case.expected_bar_basis:
        failures.append(
            f"bar_basis: expected {case.expected_bar_basis!r}, got {regime.bar_basis!r}",
        )

    insured_id = _resolve_insured_id(case.inputs)
    claimant_id = _resolve_claimant_id(case.inputs)

    if case.expected_insured_fault_pct is not None:
        if insured_id is None:
            failures.append("expected insured_fault_pct but no insured_driver party")
        else:
            got = ctx.apportionment[insured_id].fault_pct
            if abs(got - case.expected_insured_fault_pct) > case.fault_tolerance_pp:
                failures.append(
                    f"insured_fault_pct: expected "
                    f"{case.expected_insured_fault_pct}±{case.fault_tolerance_pp}, "
                    f"got {got}",
                )

    if case.expected_claimant_fault_pct is not None:
        if claimant_id is None:
            failures.append("expected claimant_fault_pct but no claimant party")
        else:
            got = ctx.apportionment[claimant_id].fault_pct
            if abs(got - case.expected_claimant_fault_pct) > case.fault_tolerance_pp:
                failures.append(
                    f"claimant_fault_pct: expected "
                    f"{case.expected_claimant_fault_pct}±{case.fault_tolerance_pp}, "
                    f"got {got}",
                )

    # Pie sums to 100 (schema validator enforces but assert explicitly).
    total = sum(e.fault_pct for e in ctx.apportionment.values())
    if not (Decimal("99") <= total <= Decimal("101")):
        failures.append(f"apportionment pie sum: expected ≈100, got {total}")

    if case.expected_vicarious_cap_applies is not None and (
        ceiling.vicarious_cap_applies != case.expected_vicarious_cap_applies
    ):
        failures.append(
            f"vicarious_cap_applies: expected "
            f"{case.expected_vicarious_cap_applies}, "
            f"got {ceiling.vicarious_cap_applies}",
        )
    if case.expected_vicarious_cap_value is not None and (
        ceiling.vicarious_cap_value != case.expected_vicarious_cap_value
    ):
        failures.append(
            f"vicarious_cap_value: expected {case.expected_vicarious_cap_value}, "
            f"got {ceiling.vicarious_cap_value}",
        )
    if case.expected_graves_lessor_removed is not None and (
        ceiling.graves_lessor_removed != case.expected_graves_lessor_removed
    ):
        failures.append(
            f"graves_lessor_removed: expected "
            f"{case.expected_graves_lessor_removed}, "
            f"got {ceiling.graves_lessor_removed}",
        )
    if case.expected_neg_ent_path_available is not None and (
        ceiling.negligent_entrustment_uncapped_path_available
        != case.expected_neg_ent_path_available
    ):
        failures.append(
            f"negligent_entrustment_uncapped_path_available: expected "
            f"{case.expected_neg_ent_path_available}, "
            f"got {ceiling.negligent_entrustment_uncapped_path_available}",
        )
    if case.expected_fabre_defendants_min_count is not None and (
        len(ceiling.fabre_defendants) < case.expected_fabre_defendants_min_count
    ):
        failures.append(
            f"fabre_defendants count: expected ≥"
            f"{case.expected_fabre_defendants_min_count}, "
            f"got {len(ceiling.fabre_defendants)}",
        )

    applied = set(ctx.resolution.doctrines_applied)
    for d in case.expected_doctrines_applied:
        if d not in applied:
            failures.append(
                f"doctrines_applied missing {d!r}; got {sorted(applied)}",
            )
    for d in case.expected_doctrines_not_applied:
        if d in applied:
            failures.append(
                f"doctrines_applied should NOT include {d!r}; got {sorted(applied)}",
            )

    if failures:
        msg = (
            f"\nEVAL FAIL — case {case.case_id} ({case.description}):\n"
            + "\n".join(f"  - {f}" for f in failures)
        )
        raise AssertionError(msg)


__all__ = [
    "DEFAULT_FAULT_TOLERANCE_PP",
    "DEFAULT_PROGRAM",
    "LiabilityEvalCase",
    "assert_case",
    "run_case",
]


# ---------------------------------------------------------------------------
# Convenience: pull commonly-needed builders forward so cases stay short.
# ---------------------------------------------------------------------------


HB837_EFFECTIVE = date(2023, 3, 24)
POST_HB837 = date(2025, 6, 2)
PRE_HB837 = date(2022, 6, 2)
