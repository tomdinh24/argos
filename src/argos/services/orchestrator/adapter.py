"""Adapter: extract a Coverage-ready SyntheticClaim from a Caseload.

The cross-claim `Caseload` (used by triage and the Reader integration)
carries Claim + CoverageRequest + Documents but does NOT carry the
Policy contract, PolicyPeriod, PolicyCoverages, or loss_facts that the
Coverage specialist reads.

For the orchestrator demo, this adapter synthesizes minimal versions
of those missing fields from defaults that match what
`synthetic_caseload.py` assumes implicitly (auto BI, FL jurisdiction,
$1M/$300K standard limits). In production this adapter would pull from
the real ontology store.

The adapter is intentionally narrow — it doesn't try to be a general
Caseload→SyntheticClaim conversion. It's a bridge specifically for
making the integration runnable today.
"""
from __future__ import annotations

from datetime import date, timedelta

from argos.ontology.types import (
    Caseload,
    Policy,
    PolicyCoverage,
    PolicyPeriod,
    SyntheticClaim,
)


# Defaults that match the synthetic caseload's implicit assumptions.
# These are placeholder values, fine for the orchestrator demo;
# production would pull from real policy records.
_DEFAULT_POLICY_ID = "POL-PLACEHOLDER-2026"
_DEFAULT_POLICY_PERIOD_ID = "PP-FIXTURE-2026"  # matches synthetic_caseload
_DEFAULT_NAMED_INSURED = "PTY-NAMED-INSURED-PLACEHOLDER"
_DEFAULT_CLIENT_PROGRAM = "CLIENT-PLACEHOLDER"
_DEFAULT_JURISDICTION = "FL"
_DEFAULT_POLICY_FORM = "CA00"
_DEFAULT_POLICY_NUMBER = "PLACEHOLDER-001"


def _default_coverage(coverage_id: str) -> PolicyCoverage:
    """Synthesize a PolicyCoverage matching the coverage_id strings the
    synthetic fixture uses (CP-AUTO-BI-STANDARD, CP-AUTO-PD-STANDARD,
    CP-PROP-BUILDING)."""
    if "BI" in coverage_id:
        return PolicyCoverage(
            coverage_id=coverage_id,
            policy_period_id=_DEFAULT_POLICY_PERIOD_ID,
            coverage_type="auto_BI",
            limit_per_occurrence=1_000_000.0,
            limit_per_person=300_000.0,
            limit_aggregate=1_000_000.0,
            deductible=0.0,
        )
    if "PD" in coverage_id:
        return PolicyCoverage(
            coverage_id=coverage_id,
            policy_period_id=_DEFAULT_POLICY_PERIOD_ID,
            coverage_type="auto_PD",
            limit_per_occurrence=100_000.0,
            limit_aggregate=100_000.0,
            deductible=1_000.0,
        )
    # Fallback (property etc.) — generic shape.
    return PolicyCoverage(
        coverage_id=coverage_id,
        policy_period_id=_DEFAULT_POLICY_PERIOD_ID,
        coverage_type="property",
        limit_per_occurrence=500_000.0,
        limit_aggregate=500_000.0,
        deductible=2_500.0,
    )


def caseload_to_synthetic_claim(
    caseload: Caseload,
    claim_id: str,
) -> SyntheticClaim:
    """Adapt one claim out of a Caseload into a Coverage-ready
    SyntheticClaim.

    Raises ValueError if the claim or its CoverageRequest can't be found.
    """
    claim = next((c for c in caseload.claims if c.claim_id == claim_id), None)
    if claim is None:
        raise ValueError(f"Claim {claim_id!r} not in caseload")

    request = next(
        (r for r in caseload.requests if r.claim_id == claim_id), None
    )
    if request is None:
        raise ValueError(f"No CoverageRequest for claim {claim_id!r}")

    docs = [d for d in caseload.documents if d.claim_id == claim_id]

    # Synthesize policy + period
    policy = Policy(
        policy_id=_DEFAULT_POLICY_ID,
        client_program_id=_DEFAULT_CLIENT_PROGRAM,
        policy_number=_DEFAULT_POLICY_NUMBER,
        named_insured_party_id=_DEFAULT_NAMED_INSURED,
        policy_form=_DEFAULT_POLICY_FORM,
        jurisdiction_state=_DEFAULT_JURISDICTION,
    )
    period = PolicyPeriod(
        policy_period_id=_DEFAULT_POLICY_PERIOD_ID,
        policy_id=_DEFAULT_POLICY_ID,
        effective_from=date(claim.opened_date.year, 1, 1),
        effective_to=date(claim.opened_date.year, 12, 31),
        status="in_force",
    )

    # The CoverageRequest references one coverage_id — synthesize that
    # coverage. (For richer demos, include all relevant coverages.)
    coverages = [_default_coverage(request.coverage_id)]

    # Loss date defaults to claim.opened_date minus 1 day (claims usually
    # open after the loss). Loss facts is a one-sentence placeholder.
    loss_date = claim.opened_date - timedelta(days=1)
    loss_facts = (
        f"Auto bodily injury claim, severity tier "
        f"{claim.severity_tier_summary!r}. Claim opened "
        f"{claim.opened_date.isoformat()}. "
        f"Litigation flag: {claim.litigation_flag}; "
        f"represented: {claim.rep_flag}; complaint: {claim.complaint_flag}. "
        f"(Loss facts synthesized by the Caseload→SyntheticClaim adapter "
        f"for orchestrator demo purposes; production would pull from the "
        f"underlying intake record.)"
    )

    return SyntheticClaim(
        policy=policy,
        policy_period=period,
        coverages=coverages,
        request=request,
        documents=docs,
        loss_date=loss_date,
        loss_facts=loss_facts,
    )
