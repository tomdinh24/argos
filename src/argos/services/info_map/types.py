"""Info map types — the open-question schema.

Spec source: docs/specs/info-map-auto-bi-fl.md (r2).

An OpenQuestion is one fact a competent adjuster must know to make a
coverage / liability / damages decision. The InfoMap is the catalog
of those questions for a (LOB, jurisdiction) slice.

Status grain in v1 is binary (`open` / `answered`); partial-fill is
deferred to v2 per the spec.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


EndState = Literal["coverage", "liability", "damages"]
"""Which adjuster decision a question gates."""

Gating = Literal["required", "nice_to_have", "conditional"]
"""How load-bearing a question is for its end-state."""

FactStableAt = Literal[
    "immediate", "request_response", "MMI", "demand_received", "settlement"
]
"""When the answer stops changing. `immediate` = structured field, locked at
intake. `request_response` = stable once a source responds. `MMI` = stable at
maximum medical improvement (damages-side). `demand_received` = stable when
plaintiff counsel sends the demand. `settlement` = stable at settlement (liens,
final wage loss)."""

Fidelity = Literal["authoritative", "primary", "secondary", "tertiary"]
"""How reliable a source is for this question. `authoritative` = the source
of truth (e.g., DMV for license status). `primary`/`secondary`/`tertiary` =
ranked alternatives when authoritative is unreachable or absent."""

Channel = Literal[
    "internal_lookup",
    "email",
    "phone",
    "portal",
    "fax",
    "mail",
    "in_person",
    "api",
    "court_record",
    "subpoena",
]
"""How the request is sent. Different channels carry different compliance,
cycle-time, and provability profiles."""


class Source(BaseModel):
    """One way to answer an open question.

    A question typically has 1–3 sources ranked by fidelity. The
    Outreach Drafter routes to the highest-fidelity source available;
    when that's unreachable (e.g., insured ghosting), falls back to
    the next.
    """

    party: str = Field(
        description=(
            "Who supplies this answer. Free-form for v1 — typical values: "
            "'carrier_uw', 'insured', 'broker', 'claimant', 'claimant_counsel', "
            "'police_records_office', 'dmv', 'medical_provider', 'pip_carrier', "
            "'iso_claim_search', 'body_shop', 'employer', 'cms_msprp', 'witness', "
            "'court_records', 'fnol_system'."
        )
    )
    channel: Channel
    cycle_time_days_min: int = Field(ge=0)
    cycle_time_days_max: int = Field(ge=0)
    fidelity: Fidelity
    notes: str | None = None

    @model_validator(mode="after")
    def max_gte_min(self) -> Source:
        if self.cycle_time_days_max < self.cycle_time_days_min:
            raise ValueError(
                f"cycle_time_days_max ({self.cycle_time_days_max}) must be "
                f">= cycle_time_days_min ({self.cycle_time_days_min})"
            )
        return self


class OpenQuestion(BaseModel):
    """One fact required to advance the claim to a decision."""

    id: str = Field(
        description="Stable ID matching docs/specs/info-map-auto-bi-fl.md "
        "(e.g., 'Q-COV-001', 'Q-DAM-013')."
    )
    description: str
    blocks_end_state: EndState
    gating: Gating
    conditional_trigger: str | None = Field(
        default=None,
        description=(
            "Required when gating='conditional'. Free-form condition string "
            "(e.g., 'insured ≠ driver of record'). Outreach Drafter and Brief "
            "consult this to decide whether to surface the question on a "
            "given claim."
        ),
    )
    sources: list[Source] = Field(min_length=1)
    best_case_cycle_time_days_min: int = Field(ge=0)
    best_case_cycle_time_days_max: int = Field(ge=0)
    depends_on: list[str] = Field(
        default_factory=list,
        description="List of question IDs that must be answered first.",
    )
    fact_stable_at: FactStableAt = "request_response"
    is_perishable: bool = Field(
        default=False,
        description=(
            "True when the window to obtain the answer closes irreversibly "
            "(e.g., Q-LIA-011 EDR data lost on vehicle salvage). Perishable "
            "atoms get surfaced specially in the critical-path view."
        ),
    )
    requirement_citation: str
    cycle_time_citation: str
    notes: str | None = None

    @model_validator(mode="after")
    def conditional_has_trigger(self) -> OpenQuestion:
        if self.gating == "conditional" and not self.conditional_trigger:
            raise ValueError(
                f"{self.id}: gating='conditional' requires conditional_trigger"
            )
        if self.gating != "conditional" and self.conditional_trigger:
            raise ValueError(
                f"{self.id}: conditional_trigger set but gating is "
                f"{self.gating!r}; trigger only valid when gating='conditional'"
            )
        return self

    @model_validator(mode="after")
    def best_case_max_gte_min(self) -> OpenQuestion:
        if self.best_case_cycle_time_days_max < self.best_case_cycle_time_days_min:
            raise ValueError(
                f"{self.id}: best_case_cycle_time_days_max "
                f"({self.best_case_cycle_time_days_max}) must be >= min "
                f"({self.best_case_cycle_time_days_min})"
            )
        return self


class InfoMap(BaseModel):
    """The catalog of open questions for a (LOB, jurisdiction) slice."""

    lob: str = Field(description="Line of business (e.g., 'auto_BI').")
    jurisdiction: str = Field(description="State or country code (e.g., 'FL').")
    phase: str = Field(
        description="Workflow phase covered (e.g., 'post_FNOL_pre_coverage_decision')."
    )
    revision: str = Field(
        description=(
            "Revision tag matching the spec doc (e.g., 'r2 2026-05-31'). "
            "Bump when the underlying spec is revised."
        )
    )
    questions: list[OpenQuestion] = Field(min_length=1)

    @model_validator(mode="after")
    def ids_unique(self) -> InfoMap:
        ids = [q.id for q in self.questions]
        if len(ids) != len(set(ids)):
            seen: set[str] = set()
            dupes: set[str] = set()
            for qid in ids:
                if qid in seen:
                    dupes.add(qid)
                seen.add(qid)
            raise ValueError(f"Duplicate question IDs: {sorted(dupes)}")
        return self

    @model_validator(mode="after")
    def dependencies_resolve(self) -> InfoMap:
        ids = {q.id for q in self.questions}
        for q in self.questions:
            unknown = [d for d in q.depends_on if d not in ids]
            if unknown:
                raise ValueError(
                    f"{q.id}: depends_on references unknown question(s): "
                    f"{unknown}"
                )
        return self

    # ----- accessor helpers -----

    def get(self, question_id: str) -> OpenQuestion:
        for q in self.questions:
            if q.id == question_id:
                return q
        raise KeyError(f"No question with id={question_id!r}")

    def for_end_state(self, end_state: EndState) -> list[OpenQuestion]:
        return [q for q in self.questions if q.blocks_end_state == end_state]

    def required_questions(self) -> list[OpenQuestion]:
        return [q for q in self.questions if q.gating == "required"]

    def perishable_questions(self) -> list[OpenQuestion]:
        return [q for q in self.questions if q.is_perishable]

    def by_party(self, party: str) -> list[OpenQuestion]:
        """Questions that have at least one source from the given party."""
        return [
            q for q in self.questions
            if any(s.party == party for s in q.sources)
        ]

    # ----- critical-path computation -----

    def critical_path_order(self) -> list[OpenQuestion]:
        """Questions ordered by long-pole-first.

        Sort key: (perishable first) → (longest max cycle time descending)
        → (longest min cycle time descending) → (id ascending for
        deterministic ties).

        Perishable atoms sort first regardless of cycle time because
        their window-to-act is the binding constraint, not their cycle.
        """
        return sorted(
            self.questions,
            key=lambda q: (
                not q.is_perishable,                       # perishable first
                -q.best_case_cycle_time_days_max,          # longest max desc
                -q.best_case_cycle_time_days_min,          # longest min desc
                q.id,                                      # deterministic tiebreak
            ),
        )

    def long_pole(
        self, threshold_days: int = 7
    ) -> list[OpenQuestion]:
        """Questions whose best-case max cycle time meets or exceeds
        `threshold_days`. These are the day-1-request candidates."""
        return [
            q for q in self.questions
            if q.best_case_cycle_time_days_max >= threshold_days
            or q.is_perishable
        ]
