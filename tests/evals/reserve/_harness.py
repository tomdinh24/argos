"""Eval harness for Reserve workflow.

One `ReserveEvalCase` per scenario. Runner builds the inputs, runs the
deterministic calculator (`compute_reserve`), then asserts every non-None
expectation against the produced `ReserveAnalysis` + `CalculationContext`.

Pass criteria documented in `docs/evals/reserve-thresholds.md`. Per the
2026-06-02 eval-design policy:

- Every emitted field is GRADED or DEFERRED (see threshold doc field-coverage).
- Default tolerance = 0 (exact equality). Calculator is `Decimal`
  arithmetic with no stochastic source.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal

from argos.schemas.workflows.reserve import (
    AuthorityLevel,
    NoticeType,
    ReserveAnalysis,
    ReserveInputs,
)
from argos.services.reserve.calculator import (
    CalculationContext,
    compute_reserve,
)
from argos.services.reserve.constants import DEFAULT_PROGRAM


HB837_EFFECTIVE = date(2023, 3, 24)
POST_HB837 = date(2025, 6, 2)
PRE_HB837 = date(2022, 6, 2)
REVIEW_AS_OF = datetime(2026, 6, 2, 10, 0, 0, tzinfo=timezone.utc)


@dataclass
class ReserveEvalCase:
    """One eval scenario + the assertions it should satisfy.

    Any field left as None is not asserted. Every assertion is exact-match
    (tolerance = 0) per the eval-design policy.
    """

    case_id: str
    description: str
    inputs: ReserveInputs

    # Specials breakdown
    expected_paid_satisfied: Decimal | None = None
    expected_lop_equivalent: Decimal | None = None
    expected_wage_loss: Decimal | None = None
    expected_specials_total: Decimal | None = None

    # Generals band + factors
    expected_generals_low: Decimal | None = None
    expected_generals_central: Decimal | None = None
    expected_generals_high: Decimal | None = None
    expected_multiplier_central: Decimal | None = None
    expected_venue_factor: Decimal | None = None
    expected_threshold_discount_pct: Decimal | None = None

    # Indemnity band
    expected_indemnity_low: Decimal | None = None
    expected_indemnity_central: Decimal | None = None
    expected_indemnity_high: Decimal | None = None
    expected_indemnity_recommended: Decimal | None = None
    expected_comparative_status_substr: str | None = None

    # ALAE band (Decimal for consistency; calculator stores as float)
    expected_alae_p10: Decimal | None = None
    expected_alae_p50: Decimal | None = None
    expected_alae_p90: Decimal | None = None

    # Notice obligations — exact set
    expected_notice_types: set[NoticeType] | None = None
    expected_notice_days_by_type: dict[NoticeType, int] | None = None

    # Authority + no-change
    expected_authority: AuthorityLevel | None = None
    expected_no_change_warranted: bool | None = None

    # Bad-faith markers — exact-set match (substring-match per marker if listed)
    expected_bad_faith_markers_exact: set[str] | None = None
    expected_bad_faith_marker_substrings: list[str] = field(default_factory=list)

    # Stair-step
    expected_stair_step_flagged: bool | None = None
    expected_stair_step_revisions: int | None = None

    # Delta vs prior
    expected_delta_amount: Decimal | None = None
    expected_delta_pct: Decimal | None = None


def run_case(case: ReserveEvalCase) -> tuple[ReserveAnalysis, CalculationContext]:
    """Run the calculator for one case. Returns (analysis, context)."""
    return compute_reserve(
        case.inputs,
        DEFAULT_PROGRAM,
        request_id=f"REQ-{case.case_id}",
        reviewed_as_of=REVIEW_AS_OF,
    )


def _check(failures: list[str], label: str, expected, got) -> None:
    if expected != got:
        failures.append(f"{label}: expected {expected!r}, got {got!r}")


def assert_case(
    case: ReserveEvalCase,
    analysis: ReserveAnalysis,
    ctx: CalculationContext,
) -> None:
    """Assert every non-None expectation. Exact-match throughout."""
    failures: list[str] = []

    # Specials
    if case.expected_paid_satisfied is not None:
        _check(failures, "specials.paid_satisfied",
               case.expected_paid_satisfied, ctx.specials.paid_satisfied)
    if case.expected_lop_equivalent is not None:
        _check(failures, "specials.lop_equivalent",
               case.expected_lop_equivalent, ctx.specials.lop_equivalent)
    if case.expected_wage_loss is not None:
        _check(failures, "specials.wage_loss",
               case.expected_wage_loss, ctx.specials.wage_loss)
    if case.expected_specials_total is not None:
        _check(failures, "specials.total",
               case.expected_specials_total, ctx.specials.total)

    # Generals
    if case.expected_generals_low is not None:
        _check(failures, "generals.low", case.expected_generals_low, ctx.generals.low)
    if case.expected_generals_central is not None:
        _check(failures, "generals.central",
               case.expected_generals_central, ctx.generals.central)
    if case.expected_generals_high is not None:
        _check(failures, "generals.high", case.expected_generals_high, ctx.generals.high)
    if case.expected_multiplier_central is not None:
        _check(failures, "generals.multiplier_central",
               case.expected_multiplier_central, ctx.generals.multiplier_central)
    if case.expected_venue_factor is not None:
        _check(failures, "generals.venue_factor",
               case.expected_venue_factor, ctx.generals.venue_factor)
    if case.expected_threshold_discount_pct is not None:
        _check(failures, "generals.threshold_discount_pct",
               case.expected_threshold_discount_pct,
               ctx.generals.threshold_discount_pct)

    # Indemnity
    if case.expected_indemnity_low is not None:
        _check(failures, "indemnity.low",
               case.expected_indemnity_low, ctx.indemnity.low)
    if case.expected_indemnity_central is not None:
        _check(failures, "indemnity.central",
               case.expected_indemnity_central, ctx.indemnity.central)
    if case.expected_indemnity_high is not None:
        _check(failures, "indemnity.high",
               case.expected_indemnity_high, ctx.indemnity.high)
    if case.expected_indemnity_recommended is not None:
        _check(failures, "indemnity.recommended",
               case.expected_indemnity_recommended, ctx.indemnity.recommended)
    if case.expected_comparative_status_substr is not None:
        if case.expected_comparative_status_substr not in ctx.indemnity.comparative_status:
            failures.append(
                f"comparative_status: expected substring "
                f"{case.expected_comparative_status_substr!r}, "
                f"got {ctx.indemnity.comparative_status!r}",
            )

    # ALAE
    if case.expected_alae_p10 is not None:
        _check(failures, "alae.p10",
               float(case.expected_alae_p10), ctx.alae_band.p10)
    if case.expected_alae_p50 is not None:
        _check(failures, "alae.p50",
               float(case.expected_alae_p50), ctx.alae_band.p50)
    if case.expected_alae_p90 is not None:
        _check(failures, "alae.p90",
               float(case.expected_alae_p90), ctx.alae_band.p90)

    # Notice obligations
    if case.expected_notice_types is not None:
        got_types = {n.notice_type for n in analysis.notice_obligations_triggered}
        if got_types != case.expected_notice_types:
            failures.append(
                f"notice_types: expected {sorted(case.expected_notice_types)}, "
                f"got {sorted(got_types)}",
            )
    if case.expected_notice_days_by_type is not None:
        for t, days in case.expected_notice_days_by_type.items():
            matches = [
                n for n in analysis.notice_obligations_triggered if n.notice_type == t
            ]
            if not matches:
                failures.append(f"notice_days[{t}]: expected {days}, no such notice fired")
                continue
            got_days = (matches[0].required_by_date - REVIEW_AS_OF).days
            if got_days != days:
                failures.append(
                    f"notice_days[{t}]: expected {days}, got {got_days}",
                )

    # Authority + no-change
    if case.expected_authority is not None:
        _check(failures, "authority_required_level",
               case.expected_authority, analysis.authority_required_level)
    if case.expected_no_change_warranted is not None:
        _check(failures, "no_change_warranted",
               case.expected_no_change_warranted, analysis.no_change_warranted)

    # Bad-faith markers
    if case.expected_bad_faith_markers_exact is not None:
        got = set(ctx.bad_faith_markers.active)
        if got != case.expected_bad_faith_markers_exact:
            failures.append(
                f"bad_faith_markers: expected {sorted(case.expected_bad_faith_markers_exact)}, "
                f"got {sorted(got)}",
            )
    for substr in case.expected_bad_faith_marker_substrings:
        if not any(substr in m for m in ctx.bad_faith_markers.active):
            failures.append(
                f"bad_faith_markers: expected marker containing {substr!r}, "
                f"got {sorted(ctx.bad_faith_markers.active)}",
            )

    # Stair-step
    if case.expected_stair_step_flagged is not None:
        _check(failures, "stair_step.flagged",
               case.expected_stair_step_flagged, ctx.stair_step.flagged)
    if case.expected_stair_step_revisions is not None:
        _check(failures, "stair_step.revisions_in_window",
               case.expected_stair_step_revisions, ctx.stair_step.revisions_in_window)

    # Delta vs prior
    if case.expected_delta_amount is not None:
        _check(failures, "delta_amount",
               case.expected_delta_amount, ctx.delta_amount)
    if case.expected_delta_pct is not None:
        _check(failures, "delta_pct",
               case.expected_delta_pct, ctx.delta_pct)

    # Smoke: every reserve component has a band that respects p10 ≤ p50 ≤ p90
    for comp in analysis.per_component:
        band = comp.recommended_outstanding_band
        if not (band.p10 <= band.p50 <= band.p90):
            failures.append(
                f"per_component[{comp.component}] band order violated: "
                f"p10={band.p10}, p50={band.p50}, p90={band.p90}",
            )
        if not comp.evidence_citations:
            failures.append(
                f"per_component[{comp.component}] evidence_citations empty",
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
    "ReserveEvalCase",
    "assert_case",
    "run_case",
]
