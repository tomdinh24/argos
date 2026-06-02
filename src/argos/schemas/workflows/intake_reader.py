"""Intake Reader specialist output schema.

The Intake Reader runs once per FNOL bundle at first-notice time.
It extracts the structured fields a downstream `Claim` and
`CoverageRequest` need from a free-text FNOL narrative plus any
attached documents. Output drives triage bucketing — without these
fields, the policy engine has nothing to read.

Spec: docs/specs/intake-reader.md (to be written)
Decision: docs/DECISIONS.md → "Intake reader is a distinct, unbuilt layer"
                            → "Step 2: Intake reader" (when shipped)
"""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, model_validator

from argos.ontology.types import SeverityTier


class IntakeExtraction(BaseModel):
    """Structured extraction from one FNOL bundle.

    Designed rich — every field that meaningfully changes a triage
    bucket or seeds a specialist. The runtime call is one LLM
    invocation per bundle, so adding fields here is cheap relative
    to the call's fixed cost. Downstream code combines this with
    intake metadata (claim_id, timestamp) to build the `Claim` and
    `CoverageRequest` records.

    Schema invariants enforced here:
      - severity_evidence non-empty (a verbatim quote supporting the tier)
      - loss_summary non-empty and within length cap
      - Each True flag has non-empty corresponding *_evidence
      - Each False flag has empty corresponding *_evidence (forces the
        model to be explicit about what it didn't find)
    """

    # ---- Loss facts ----

    loss_date: date = Field(
        description=(
            "ISO-format date the loss occurred. If the FNOL gives an "
            "ambiguous range, pick the earliest plausible date."
        )
    )
    loss_location: str = Field(
        min_length=1,
        description=(
            "Free-text location of the loss (e.g., 'I-95 northbound at "
            "exit 31, Boca Raton FL'). Use empty if unknown."
        ),
    )
    loss_summary: str = Field(
        max_length=600,
        description=(
            "1-3 sentence neutral narrative of what happened. Adjuster "
            "readable. No marketing language, no editorializing on "
            "fault."
        ),
    )

    # ---- Triage signals ----

    severity_tier: SeverityTier = Field(
        description=(
            "Triage tier: catastrophic (fatal or life-altering), "
            "serious (hospitalization or major surgery), standard "
            "(treatment but no major surgery), minor (cosmetic or no "
            "injury). Default to the lower tier when uncertain."
        ),
    )
    severity_evidence: str = Field(
        min_length=1,
        description=(
            "Verbatim quote from the FNOL bundle supporting the "
            "severity_tier assignment. Must non-empty."
        ),
    )

    # ---- Decision-load-bearing flags ----

    litigation_flag: bool = Field(
        description=(
            "True if a lawsuit has been filed or threatened. Mere "
            "attorney representation is rep_flag, not litigation_flag."
        ),
    )
    litigation_evidence: str = Field(
        default="",
        description=(
            "Verbatim quote supporting litigation_flag=True. Empty "
            "when litigation_flag=False."
        ),
    )

    rep_flag: bool = Field(
        description=(
            "True if the claimant is represented by counsel. Does not "
            "require a lawsuit; a letter of representation is enough."
        ),
    )
    rep_evidence: str = Field(
        default="",
        description=(
            "Verbatim quote supporting rep_flag=True. Empty when "
            "rep_flag=False."
        ),
    )

    complaint_flag: bool = Field(
        description=(
            "True if the FNOL bundle mentions a regulatory complaint "
            "(state DOI, AG office, BBB) about the claim."
        ),
    )
    complaint_evidence: str = Field(
        default="",
        description=(
            "Verbatim quote supporting complaint_flag=True. Empty "
            "when complaint_flag=False."
        ),
    )

    # ---- Optional identity / lookup fields ----

    policy_number: str | None = Field(
        default=None,
        description=(
            "Policy number stated in the FNOL. Null when the claimant "
            "couldn't provide it; downstream lookup falls back to "
            "name + DOB."
        ),
    )
    insured_name: str | None = Field(
        default=None,
        description="Named insured per the FNOL bundle.",
    )
    claimant_name: str | None = Field(
        default=None,
        description=(
            "Claimant (first-party or third-party). Null when the "
            "FNOL doesn't name them."
        ),
    )

    # ---- Validators ----

    @model_validator(mode="after")
    def flag_evidence_consistent(self) -> IntakeExtraction:
        """Each True flag must have non-empty evidence; each False flag
        must have empty evidence. Forces the LLM to be explicit."""
        for flag_name, evidence_name in (
            ("litigation_flag", "litigation_evidence"),
            ("rep_flag", "rep_evidence"),
            ("complaint_flag", "complaint_evidence"),
        ):
            flag = getattr(self, flag_name)
            evidence = getattr(self, evidence_name).strip()
            if flag and not evidence:
                raise ValueError(
                    f"IntakeExtraction.{evidence_name} must be non-empty "
                    f"when {flag_name}=True (verbatim FNOL quote)."
                )
            if not flag and evidence:
                raise ValueError(
                    f"IntakeExtraction.{evidence_name} must be empty "
                    f"when {flag_name}=False."
                )
        return self
