"""Info map — auto BI / FL / post-FNOL pre-coverage-decision.

Code form of docs/specs/info-map-auto-bi-fl.md (r2). 39 open questions
total: 15 coverage + 11 liability + 13 damages.

This file is hand-authored to match the spec doc 1:1. The spec is
human-readable; this is machine-readable. They are kept in sync by
review, not by code generation — the spec is short enough and the
schema is strict enough that drift gets caught fast.

When the spec is revised (e.g., new state, new LOB, atom changes),
bump `REVISION` and re-review.
"""
from __future__ import annotations

from argos.services.info_map.types import InfoMap, OpenQuestion, Source


REVISION = "r2 2026-05-31"


# ---------------------------------------------------------------------------
# Section A — Coverage decision open questions (15)
# ---------------------------------------------------------------------------


_Q_COV: list[OpenQuestion] = [
    OpenQuestion(
        id="Q-COV-001",
        description="Is the policy in force on the loss date?",
        blocks_end_state="coverage",
        gating="required",
        sources=[
            Source(
                party="carrier_uw",
                channel="internal_lookup",
                cycle_time_days_min=0, cycle_time_days_max=0,
                fidelity="authoritative",
            ),
            Source(
                party="broker", channel="email",
                cycle_time_days_min=1, cycle_time_days_max=2,
                fidelity="secondary",
            ),
        ],
        best_case_cycle_time_days_min=0,
        best_case_cycle_time_days_max=0,
        depends_on=[],
        fact_stable_at="immediate",
        requirement_citation="AIC §2.3 (coverage triggers); FL § 627.7407 (in-force requirement for PIP)",
        cycle_time_citation="ACORD policy lookup is canonically real-time within carrier systems.",
    ),
    OpenQuestion(
        id="Q-COV-002",
        description="Is the driver of record covered under the policy (named, listed permissive, or excluded)?",
        blocks_end_state="coverage",
        gating="required",
        sources=[
            Source(
                party="carrier_uw", channel="internal_lookup",
                cycle_time_days_min=0, cycle_time_days_max=0,
                fidelity="authoritative",
            ),
            Source(
                party="insured", channel="phone",
                cycle_time_days_min=1, cycle_time_days_max=3,
                fidelity="tertiary",
                notes="Self-report — claimants may misstate",
            ),
            Source(
                party="dmv", channel="portal",
                cycle_time_days_min=7, cycle_time_days_max=14,
                fidelity="authoritative",
                notes="Authoritative for license status only",
            ),
        ],
        best_case_cycle_time_days_min=0,
        best_case_cycle_time_days_max=0,
        depends_on=["Q-COV-001"],
        fact_stable_at="immediate",
        requirement_citation="AIC §2.4 (driver eligibility); standard auto policy 'Persons Insured' provision",
        cycle_time_citation="Internal lookup immediate",
    ),
    OpenQuestion(
        id="Q-COV-003",
        description="Was the vehicle being used in a covered manner (personal vs business; permissive vs unauthorized)?",
        blocks_end_state="coverage",
        gating="required",
        sources=[
            Source(
                party="insured", channel="phone",
                cycle_time_days_min=1, cycle_time_days_max=3,
                fidelity="primary",
            ),
            Source(
                party="police_records_office", channel="mail",
                cycle_time_days_min=14, cycle_time_days_max=30,
                fidelity="secondary",
            ),
        ],
        best_case_cycle_time_days_min=1,
        best_case_cycle_time_days_max=3,
        depends_on=["Q-COV-002"],
        requirement_citation="Standard auto policy 'Use' provision; AIC §2.4",
        cycle_time_citation="[ESTIMATE] — insured response within 1–3d typical when adjuster reaches them",
    ),
    OpenQuestion(
        id="Q-COV-004",
        description="Was timely notice of the loss given per the policy?",
        blocks_end_state="coverage",
        gating="required",
        sources=[
            Source(
                party="fnol_system", channel="internal_lookup",
                cycle_time_days_min=0, cycle_time_days_max=0,
                fidelity="authoritative",
            ),
        ],
        best_case_cycle_time_days_min=0,
        best_case_cycle_time_days_max=0,
        depends_on=[],
        fact_stable_at="immediate",
        requirement_citation="Standard auto policy 'Duties After an Accident' provision; FL § 627.736(4)(b) (PIP notice)",
        cycle_time_citation="Internal timestamp",
    ),
    OpenQuestion(
        id="Q-COV-005",
        description="Are there any policy exclusions triggered by the loss facts (intentional act, racing, criminal use, etc.)?",
        blocks_end_state="coverage",
        gating="required",
        sources=[
            Source(
                party="police_records_office", channel="mail",
                cycle_time_days_min=14, cycle_time_days_max=30,
                fidelity="primary",
            ),
            Source(
                party="insured", channel="phone",
                cycle_time_days_min=1, cycle_time_days_max=3,
                fidelity="secondary",
            ),
        ],
        best_case_cycle_time_days_min=14,
        best_case_cycle_time_days_max=30,
        depends_on=[],
        requirement_citation="Standard auto policy 'Exclusions' provision; AIC §2.5",
        cycle_time_citation="FL state records — Hillsborough County Sheriff published 30-day standard response. Many FL agencies similar.",
        notes="Coarse-grained on purpose — Coverage specialist decomposes by exclusion class downstream.",
    ),
    OpenQuestion(
        id="Q-COV-006",
        description="What are the per-person and per-occurrence BI limits, and any sublimits or SIR?",
        blocks_end_state="coverage",
        gating="required",
        sources=[
            Source(
                party="carrier_uw", channel="internal_lookup",
                cycle_time_days_min=0, cycle_time_days_max=0,
                fidelity="authoritative",
            ),
        ],
        best_case_cycle_time_days_min=0,
        best_case_cycle_time_days_max=0,
        depends_on=["Q-COV-001"],
        fact_stable_at="immediate",
        requirement_citation="ACORD Form 1 §3; AIC §2.6",
        cycle_time_citation="Internal",
    ),
    OpenQuestion(
        id="Q-COV-007",
        description="Is there a co-defendant carrier with primary coverage, contribution duty, or excess obligation?",
        blocks_end_state="coverage",
        gating="conditional",
        conditional_trigger="multi-vehicle loss OR commercial-use vehicle",
        sources=[
            Source(
                party="iso_claim_search", channel="api",
                cycle_time_days_min=0, cycle_time_days_max=0,
                fidelity="secondary",
                notes="Realtime API; finds matching claims by VIN/parties",
            ),
            Source(
                party="police_records_office", channel="mail",
                cycle_time_days_min=14, cycle_time_days_max=30,
                fidelity="primary",
                notes="Identifies other parties' carriers",
            ),
        ],
        best_case_cycle_time_days_min=0,
        best_case_cycle_time_days_max=0,
        depends_on=["Q-COV-005"],
        requirement_citation="AIC §6.2 (multi-carrier coordination); CPCU 552 §4",
        cycle_time_citation="ISO ClaimSearch is realtime API",
    ),
    OpenQuestion(
        id="Q-COV-008",
        description="Does the claimant qualify as an insured / non-owned / excluded party under policy definitions?",
        blocks_end_state="coverage",
        gating="required",
        sources=[
            Source(
                party="carrier_uw", channel="internal_lookup",
                cycle_time_days_min=0, cycle_time_days_max=0,
                fidelity="authoritative",
            ),
            Source(
                party="insured", channel="phone",
                cycle_time_days_min=1, cycle_time_days_max=3,
                fidelity="primary",
                notes="Needed when claimant relationship not in UW data (e.g., household member)",
            ),
        ],
        best_case_cycle_time_days_min=0,
        best_case_cycle_time_days_max=3,
        depends_on=["Q-COV-001"],
        requirement_citation="Standard auto policy 'Definitions' / 'Persons Insured'",
        cycle_time_citation="Internal",
    ),
    OpenQuestion(
        id="Q-COV-009",
        description="Was the loss reported to PIP within the FL statutory window, and is PIP coordination required?",
        blocks_end_state="coverage",
        gating="required",
        sources=[
            Source(
                party="insured", channel="phone",
                cycle_time_days_min=1, cycle_time_days_max=3,
                fidelity="primary",
            ),
        ],
        best_case_cycle_time_days_min=1,
        best_case_cycle_time_days_max=3,
        depends_on=["Q-COV-004"],
        requirement_citation="FL § 627.736 (PIP); AIC FL state supplement",
        cycle_time_citation="[ESTIMATE] — insured response 1–3d",
    ),
    OpenQuestion(
        id="Q-COV-010",
        description="Is there a valid certificate of insurance / additional-insured / waiver-of-subrogation endorsement in place per the underlying contract?",
        blocks_end_state="coverage",
        gating="conditional",
        conditional_trigger="loss involves a contractual additional-insured claim or third-party tender",
        sources=[
            Source(
                party="carrier_uw", channel="internal_lookup",
                cycle_time_days_min=0, cycle_time_days_max=0,
                fidelity="authoritative",
            ),
            Source(
                party="broker", channel="email",
                cycle_time_days_min=1, cycle_time_days_max=7,
                fidelity="primary",
            ),
        ],
        best_case_cycle_time_days_min=0,
        best_case_cycle_time_days_max=0,
        depends_on=["Q-COV-001"],
        requirement_citation="Standard commercial auto policy 'Additional Insureds' endorsement (CA 20 series); ISO CA 0001 declarations",
        cycle_time_citation="Internal lookup",
        notes="Wrong-named-insured and missing endorsement wording are common COI issues — frequent coverage-dispute root cause per Logrock FL commercial auto guide.",
    ),
    OpenQuestion(
        id="Q-COV-011",
        description="Has the named insured complied with the cooperation provision (recorded statement provided, EUO attended if requested)?",
        blocks_end_state="coverage",
        gating="required",
        sources=[
            Source(
                party="carrier_uw", channel="internal_lookup",
                cycle_time_days_min=0, cycle_time_days_max=0,
                fidelity="authoritative",
                notes="Adjuster file notes record statement requests + attendance",
            ),
            Source(
                party="insured", channel="phone",
                cycle_time_days_min=1, cycle_time_days_max=3,
                fidelity="primary",
            ),
        ],
        best_case_cycle_time_days_min=1,
        best_case_cycle_time_days_max=3,
        depends_on=["Q-COV-001"],
        requirement_citation="Standard auto policy 'Duties After an Accident' provision (Part E)",
        cycle_time_citation="Internal + insured response",
        notes="Material non-cooperation can void coverage. Structural question: have we asked, and was the response sufficient — not 'is the insured being friendly.'",
    ),
    OpenQuestion(
        id="Q-COV-012",
        description="Is UM/UIM coverage stacked or non-stacked, and is there a valid written waiver on file?",
        blocks_end_state="coverage",
        gating="required",
        sources=[
            Source(
                party="carrier_uw", channel="internal_lookup",
                cycle_time_days_min=0, cycle_time_days_max=0,
                fidelity="authoritative",
                notes="UM/UIM selection/rejection form on file",
            ),
        ],
        best_case_cycle_time_days_min=0,
        best_case_cycle_time_days_max=0,
        depends_on=["Q-COV-001"],
        fact_stable_at="immediate",
        requirement_citation="FL § 627.727(9). Specific form requirements (12-point bold heading, exact statutory language); absent a compliant waiver, stacking is the default.",
        cycle_time_citation="Internal",
        notes="High-leverage FL atom — non-compliant waivers routinely struck down, converting non-stacked policies into stacked ones mid-claim. Limits at stake can change 5×+ on multi-vehicle policies.",
    ),
    OpenQuestion(
        id="Q-COV-013",
        description="Is there excess / umbrella coverage on top of the primary, and what's its attachment point and exhaustion mechanic?",
        blocks_end_state="coverage",
        gating="conditional",
        conditional_trigger="high-severity / catastrophic exposure exceeding primary limits",
        sources=[
            Source(
                party="carrier_uw", channel="internal_lookup",
                cycle_time_days_min=0, cycle_time_days_max=0,
                fidelity="authoritative",
            ),
            Source(
                party="broker", channel="email",
                cycle_time_days_min=1, cycle_time_days_max=7,
                fidelity="primary",
            ),
        ],
        best_case_cycle_time_days_min=0,
        best_case_cycle_time_days_max=0,
        depends_on=["Q-COV-001"],
        fact_stable_at="immediate",
        requirement_citation="Standard excess/umbrella policy language; AIC §2.7 (multi-layer coordination)",
        cycle_time_citation="Internal",
    ),
    OpenQuestion(
        id="Q-COV-014",
        description="Does a self-insured retention or deductible apply, and what's the attachment point?",
        blocks_end_state="coverage",
        gating="conditional",
        conditional_trigger="SIR or deductible > $0",
        sources=[
            Source(
                party="carrier_uw", channel="internal_lookup",
                cycle_time_days_min=0, cycle_time_days_max=0,
                fidelity="authoritative",
            ),
        ],
        best_case_cycle_time_days_min=0,
        best_case_cycle_time_days_max=0,
        depends_on=["Q-COV-006"],
        fact_stable_at="immediate",
        requirement_citation="ACORD Form 1 §3; standard policy declarations",
        cycle_time_citation="Internal",
    ),
    OpenQuestion(
        id="Q-COV-015",
        description="Is the defense duty triggered (typically broader than indemnity duty)?",
        blocks_end_state="coverage",
        gating="required",
        sources=[
            Source(
                party="claimant_counsel", channel="email",
                cycle_time_days_min=1, cycle_time_days_max=14,
                fidelity="primary",
                notes="Complaint/claim allegations needed to evaluate",
            ),
            Source(
                party="carrier_uw", channel="internal_lookup",
                cycle_time_days_min=0, cycle_time_days_max=0,
                fidelity="authoritative",
                notes="Policy language analysis",
            ),
        ],
        best_case_cycle_time_days_min=0,
        best_case_cycle_time_days_max=0,
        depends_on=["Q-COV-001", "Q-COV-005"],
        fact_stable_at="demand_received",
        requirement_citation="FL 'duty to defend' jurisprudence (8 Corners rule; broader than indemnity duty). AIC §2.8.",
        cycle_time_citation="Internal once inputs known",
        notes="Defense duty often kicks in even on uncovered claims (FL 'potential coverage' / 8-Corners rule).",
    ),
]


# ---------------------------------------------------------------------------
# Section B — Liability decision open questions (11)
# ---------------------------------------------------------------------------


_Q_LIA: list[OpenQuestion] = [
    OpenQuestion(
        id="Q-LIA-001",
        description="What was the date, time, and exact location of the loss?",
        blocks_end_state="liability",
        gating="required",
        sources=[
            Source(
                party="fnol_system", channel="internal_lookup",
                cycle_time_days_min=0, cycle_time_days_max=0,
                fidelity="primary",
            ),
            Source(
                party="police_records_office", channel="mail",
                cycle_time_days_min=14, cycle_time_days_max=30,
                fidelity="authoritative",
            ),
            Source(
                party="insured", channel="phone",
                cycle_time_days_min=1, cycle_time_days_max=3,
                fidelity="secondary",
            ),
        ],
        best_case_cycle_time_days_min=0,
        best_case_cycle_time_days_max=0,
        depends_on=[],
        fact_stable_at="immediate",
        requirement_citation="ACORD Form 1 §4; AIC §3.1",
        cycle_time_citation="Internal",
    ),
    OpenQuestion(
        id="Q-LIA-002",
        description="What was the traffic control at the location (signal, sign, uncontrolled, marked lane)?",
        blocks_end_state="liability",
        gating="required",
        sources=[
            Source(
                party="police_records_office", channel="mail",
                cycle_time_days_min=14, cycle_time_days_max=30,
                fidelity="authoritative",
            ),
            Source(
                party="carrier_uw", channel="internal_lookup",
                cycle_time_days_min=0, cycle_time_days_max=0,
                fidelity="secondary",
                notes="Google Maps / street-view as supporting evidence",
            ),
            Source(
                party="insured", channel="phone",
                cycle_time_days_min=1, cycle_time_days_max=3,
                fidelity="tertiary",
            ),
        ],
        best_case_cycle_time_days_min=0,
        best_case_cycle_time_days_max=0,
        depends_on=["Q-LIA-001"],
        requirement_citation="AIC §3.2 (traffic-control analysis); FL § 316 (traffic code) cross-reference",
        cycle_time_citation="Internal",
    ),
    OpenQuestion(
        id="Q-LIA-003",
        description="What was each driver's path of travel and point of impact?",
        blocks_end_state="liability",
        gating="required",
        sources=[
            Source(
                party="police_records_office", channel="mail",
                cycle_time_days_min=14, cycle_time_days_max=30,
                fidelity="primary",
                notes="Police report diagram",
            ),
            Source(
                party="body_shop", channel="email",
                cycle_time_days_min=1, cycle_time_days_max=7,
                fidelity="secondary",
                notes="Vehicle damage photos",
            ),
            Source(
                party="insured", channel="phone",
                cycle_time_days_min=1, cycle_time_days_max=3,
                fidelity="tertiary",
            ),
        ],
        best_case_cycle_time_days_min=1,
        best_case_cycle_time_days_max=7,
        depends_on=["Q-LIA-001"],
        requirement_citation="AIC §3.3 (accident reconstruction basics)",
        cycle_time_citation="[ESTIMATE] — photos when responsive; police 14–30d",
    ),
    OpenQuestion(
        id="Q-LIA-004",
        description="Was either driver issued a citation, and for what code section?",
        blocks_end_state="liability",
        gating="required",
        sources=[
            Source(
                party="police_records_office", channel="mail",
                cycle_time_days_min=14, cycle_time_days_max=30,
                fidelity="authoritative",
                notes="HSMV-90010 captures FL statute # + charge explicitly",
            ),
            Source(
                party="court_records", channel="court_record",
                cycle_time_days_min=1, cycle_time_days_max=7,
                fidelity="primary",
            ),
            Source(
                party="insured", channel="phone",
                cycle_time_days_min=1, cycle_time_days_max=3,
                fidelity="tertiary",
                notes="Self-report unreliable for own citation",
            ),
        ],
        best_case_cycle_time_days_min=1,
        best_case_cycle_time_days_max=7,
        depends_on=["Q-LIA-001"],
        requirement_citation="AIC §3.4; FL § 316.123 (failure to yield example)",
        cycle_time_citation="Citation info populated field on HSMV-90010; FL court portal real-time when known cited",
    ),
    OpenQuestion(
        id="Q-LIA-005",
        description="Was the insured driver legally licensed, not impaired, and otherwise compliant with traffic law?",
        blocks_end_state="liability",
        gating="required",
        sources=[
            Source(
                party="dmv", channel="portal",
                cycle_time_days_min=7, cycle_time_days_max=14,
                fidelity="authoritative",
            ),
            Source(
                party="police_records_office", channel="mail",
                cycle_time_days_min=14, cycle_time_days_max=30,
                fidelity="primary",
                notes="Toxicology mention in narrative if applicable",
            ),
            Source(
                party="insured", channel="phone",
                cycle_time_days_min=1, cycle_time_days_max=3,
                fidelity="tertiary",
                notes="Low fidelity for impairment self-report",
            ),
        ],
        best_case_cycle_time_days_min=7,
        best_case_cycle_time_days_max=14,
        depends_on=["Q-COV-002"],
        requirement_citation="AIC §3.5; FL § 316.193 (DUI)",
        cycle_time_citation="FL DHSMV published 7–14d for record requests",
    ),
    OpenQuestion(
        id="Q-LIA-006",
        description="Did the police officer make an explicit fault determination at the scene?",
        blocks_end_state="liability",
        gating="nice_to_have",
        sources=[
            Source(
                party="police_records_office", channel="mail",
                cycle_time_days_min=14, cycle_time_days_max=30,
                fidelity="primary",
                notes="Often absent — FL officers frequently decline to assign fault",
            ),
        ],
        best_case_cycle_time_days_min=14,
        best_case_cycle_time_days_max=30,
        depends_on=["Q-LIA-001"],
        requirement_citation="AIC §3.4",
        cycle_time_citation="Police records 30d standard",
    ),
    OpenQuestion(
        id="Q-LIA-007",
        description="Are there witnesses, and what are their statements?",
        blocks_end_state="liability",
        gating="nice_to_have",
        sources=[
            Source(
                party="police_records_office", channel="mail",
                cycle_time_days_min=14, cycle_time_days_max=30,
                fidelity="secondary",
                notes="Identifies witnesses",
            ),
            Source(
                party="witness", channel="phone",
                cycle_time_days_min=1, cycle_time_days_max=14,
                fidelity="primary",
                notes="Reachable in 1–14d when responsive; never otherwise",
            ),
        ],
        best_case_cycle_time_days_min=7,
        best_case_cycle_time_days_max=30,
        depends_on=["Q-LIA-001"],
        requirement_citation="AIC §3.6",
        cycle_time_citation="Tom's TPA estimate; CPCU 552 §3 (witnesses are notoriously hard to reach)",
    ),
    OpenQuestion(
        id="Q-LIA-008",
        description="Did either driver admit fault at the scene or in post-loss communications?",
        blocks_end_state="liability",
        gating="required",
        sources=[
            Source(
                party="insured", channel="phone",
                cycle_time_days_min=1, cycle_time_days_max=3,
                fidelity="primary",
            ),
            Source(
                party="police_records_office", channel="mail",
                cycle_time_days_min=14, cycle_time_days_max=30,
                fidelity="primary",
            ),
            Source(
                party="claimant_counsel", channel="email",
                cycle_time_days_min=14, cycle_time_days_max=30,
                fidelity="secondary",
                notes="Recorded statement of opposing party (rare; via counsel if represented)",
            ),
        ],
        best_case_cycle_time_days_min=1,
        best_case_cycle_time_days_max=3,
        depends_on=["Q-LIA-001"],
        requirement_citation="AIC §3.4",
        cycle_time_citation="[ESTIMATE] — insured 1–3d when responsive",
    ),
    OpenQuestion(
        id="Q-LIA-009",
        description="Does the loss involve any FL-specific liability doctrines (joint-and-several, dangerous instrumentality, vicarious liability)?",
        blocks_end_state="liability",
        gating="conditional",
        conditional_trigger="insured ≠ driver of record OR loss involves multiple at-fault parties",
        sources=[
            Source(
                party="dmv", channel="portal",
                cycle_time_days_min=7, cycle_time_days_max=14,
                fidelity="authoritative",
                notes="Vehicle ownership records",
            ),
        ],
        best_case_cycle_time_days_min=7,
        best_case_cycle_time_days_max=14,
        depends_on=["Q-LIA-001", "Q-COV-002"],
        requirement_citation="FL dangerous-instrumentality doctrine (Florida common law); AIC FL supplement",
        cycle_time_citation="DMV 7–14d",
        notes="FL dangerous-instrumentality holds vehicle owners vicariously liable for permissive-user negligence — only matters when ownership ≠ operation.",
    ),
    OpenQuestion(
        id="Q-LIA-010",
        description="Is the claimant alleging the insured's comparative fault (and what percentage)?",
        blocks_end_state="liability",
        gating="required",
        sources=[
            Source(
                party="claimant_counsel", channel="email",
                cycle_time_days_min=60, cycle_time_days_max=365,
                fidelity="primary",
                notes="Demand letter typically months post-loss; counsel waits for medicals to stabilize. Soft-tissue pre-suit timeline 6–12 months.",
            ),
        ],
        best_case_cycle_time_days_min=60,
        best_case_cycle_time_days_max=365,
        depends_on=["Q-LIA-001"],
        fact_stable_at="demand_received",
        requirement_citation="FL § 768.81",
        cycle_time_citation="Florida PI case timeline (DeLoach, Hofstra & Cavonis) — soft-tissue pre-suit 6–12 months",
    ),
    OpenQuestion(
        id="Q-LIA-011",
        description="Is there event-data-recorder (EDR / 'black box') data, and what does it show about speed, braking, and impact dynamics?",
        blocks_end_state="liability",
        gating="nice_to_have",
        sources=[
            Source(
                party="body_shop", channel="in_person",
                cycle_time_days_min=7, cycle_time_days_max=21,
                fidelity="authoritative",
                notes="Bosch CDR tool readout; requires physical vehicle access before salvage",
            ),
            Source(
                party="insured", channel="email",
                cycle_time_days_min=7, cycle_time_days_max=30,
                fidelity="primary",
                notes="OEM telematics (GM OnStar, Tesla, fleet) via insured-consent",
            ),
        ],
        best_case_cycle_time_days_min=7,
        best_case_cycle_time_days_max=21,
        depends_on=["Q-LIA-001"],
        is_perishable=True,
        requirement_citation="NHTSA EDR rule (49 CFR Part 563); FL practice treats EDR as standard exhibit in disputed-causation cases",
        cycle_time_citation="[ESTIMATE] — based on Bosch CDR extraction workflow + typical scheduling delay",
        notes="PERISHABLE: if vehicle is salvaged before extraction, data is gone. Short cycle but short window-to-act.",
    ),
]


# ---------------------------------------------------------------------------
# Section C — Damages estimate open questions (13)
# ---------------------------------------------------------------------------


_Q_DAM: list[OpenQuestion] = [
    OpenQuestion(
        id="Q-DAM-001",
        description="What injuries did the claimant sustain (initial diagnosis)?",
        blocks_end_state="damages",
        gating="required",
        sources=[
            Source(
                party="medical_provider", channel="fax",
                cycle_time_days_min=5, cycle_time_days_max=30,
                fidelity="authoritative",
                notes="HIPAA release to provider; AHIMA typical 5-10d, statutory max 30d",
            ),
            Source(
                party="pip_carrier", channel="email",
                cycle_time_days_min=1, cycle_time_days_max=7,
                fidelity="primary",
                notes="PIP carrier records when PIP applied",
            ),
            Source(
                party="claimant", channel="phone",
                cycle_time_days_min=1, cycle_time_days_max=3,
                fidelity="tertiary",
                notes="Low fidelity self-report",
            ),
        ],
        best_case_cycle_time_days_min=1,
        best_case_cycle_time_days_max=7,
        depends_on=["Q-DAM-013"],
        fact_stable_at="MMI",
        requirement_citation="AIC §4.1; FL § 627.736 (PIP records access for related carriers)",
        cycle_time_citation="HIPAA Privacy Rule 30-day max (45 CFR 164.524(b)(2)); AHIMA: typical 5-10d",
    ),
    OpenQuestion(
        id="Q-DAM-002",
        description="What treatment to date (providers, dates, modalities)?",
        blocks_end_state="damages",
        gating="required",
        sources=[
            Source(
                party="medical_provider", channel="fax",
                cycle_time_days_min=5, cycle_time_days_max=30,
                fidelity="authoritative",
                notes="HIPAA release per provider; statutory max 30d + possible 30d extension",
            ),
            Source(
                party="claimant_counsel", channel="email",
                cycle_time_days_min=7, cycle_time_days_max=14,
                fidelity="secondary",
                notes="Counsel summary letter — lower detail",
            ),
        ],
        best_case_cycle_time_days_min=5,
        best_case_cycle_time_days_max=14,
        depends_on=["Q-DAM-013"],
        fact_stable_at="MMI",
        requirement_citation="AIC §4.2",
        cycle_time_citation="HIPAA Privacy Rule 30d max (45 CFR 164.524(b)(2)); AHIMA: typical 5-10d",
    ),
    OpenQuestion(
        id="Q-DAM-003",
        description="What is the projected future treatment plan?",
        blocks_end_state="damages",
        gating="required",
        sources=[
            Source(
                party="medical_provider", channel="fax",
                cycle_time_days_min=14, cycle_time_days_max=30,
                fidelity="primary",
                notes="Treating provider's plan",
            ),
            Source(
                party="medical_provider", channel="in_person",
                cycle_time_days_min=21, cycle_time_days_max=60,
                fidelity="authoritative",
                notes="IME — schedule + report",
            ),
        ],
        best_case_cycle_time_days_min=14,
        best_case_cycle_time_days_max=30,
        depends_on=["Q-DAM-002"],
        fact_stable_at="MMI",
        requirement_citation="AIC §4.3",
        cycle_time_citation="[ESTIMATE] — IME scheduling typically 21-45d in FL metros",
    ),
    OpenQuestion(
        id="Q-DAM-004",
        description="What are the medical bills incurred to date?",
        blocks_end_state="damages",
        gating="required",
        sources=[
            Source(
                party="medical_provider", channel="fax",
                cycle_time_days_min=5, cycle_time_days_max=30,
                fidelity="authoritative",
                notes="Provider billing offices via HIPAA release",
            ),
            Source(
                party="claimant_counsel", channel="email",
                cycle_time_days_min=7, cycle_time_days_max=14,
                fidelity="secondary",
                notes="Counsel bill summary — less granular",
            ),
            Source(
                party="pip_carrier", channel="email",
                cycle_time_days_min=1, cycle_time_days_max=7,
                fidelity="primary",
                notes="PIP ledger when PIP applied",
            ),
        ],
        best_case_cycle_time_days_min=1,
        best_case_cycle_time_days_max=7,
        depends_on=["Q-DAM-013"],
        fact_stable_at="MMI",
        requirement_citation="AIC §4.4; FL § 627.736 (PIP coordination)",
        cycle_time_citation="HIPAA 30d max, AHIMA 5-10d typical; PIP coordination per FL § 627.736(6)",
    ),
    OpenQuestion(
        id="Q-DAM-005",
        description="What are the projected future medical costs?",
        blocks_end_state="damages",
        gating="nice_to_have",
        sources=[
            Source(
                party="medical_provider", channel="fax",
                cycle_time_days_min=14, cycle_time_days_max=30,
                fidelity="primary",
                notes="Treating provider estimate",
            ),
            Source(
                party="medical_provider", channel="in_person",
                cycle_time_days_min=30, cycle_time_days_max=90,
                fidelity="authoritative",
                notes="Life-care planner report (if catastrophic)",
            ),
        ],
        best_case_cycle_time_days_min=14,
        best_case_cycle_time_days_max=30,
        depends_on=["Q-DAM-003"],
        fact_stable_at="demand_received",
        requirement_citation="AIC §4.5",
        cycle_time_citation="[ESTIMATE]",
    ),
    OpenQuestion(
        id="Q-DAM-006",
        description="Has the claimant lost wages, and have they been employer-verified?",
        blocks_end_state="damages",
        gating="conditional",
        conditional_trigger="claimant alleges lost wages",
        sources=[
            Source(
                party="claimant_counsel", channel="email",
                cycle_time_days_min=7, cycle_time_days_max=14,
                fidelity="primary",
                notes="Wage submission from counsel",
            ),
            Source(
                party="employer", channel="email",
                cycle_time_days_min=7, cycle_time_days_max=30,
                fidelity="authoritative",
                notes="Large employers can take the full 30d (Tom's TPA estimate)",
            ),
            Source(
                party="claimant", channel="mail",
                cycle_time_days_min=14, cycle_time_days_max=30,
                fidelity="secondary",
                notes="Tax returns via release",
            ),
        ],
        best_case_cycle_time_days_min=7,
        best_case_cycle_time_days_max=14,
        depends_on=[],
        fact_stable_at="demand_received",
        requirement_citation="AIC §4.6",
        cycle_time_citation="Tom's TPA estimate — employer HR response varies significantly by org size",
    ),
    OpenQuestion(
        id="Q-DAM-007",
        description="Has the claimant sustained permanent impairment, and to what degree?",
        blocks_end_state="damages",
        gating="conditional",
        conditional_trigger="claimant alleges permanent impairment",
        sources=[
            Source(
                party="medical_provider", channel="fax",
                cycle_time_days_min=5, cycle_time_days_max=30,
                fidelity="primary",
                notes="Treating provider impairment rating",
            ),
            Source(
                party="medical_provider", channel="in_person",
                cycle_time_days_min=21, cycle_time_days_max=60,
                fidelity="authoritative",
                notes="IME — see Q-DAM-003",
            ),
        ],
        best_case_cycle_time_days_min=5,
        best_case_cycle_time_days_max=14,
        depends_on=["Q-DAM-002"],
        fact_stable_at="MMI",
        requirement_citation="AIC §4.7; AMA Guides to the Evaluation of Permanent Impairment (referenced by FL practice)",
        cycle_time_citation="HIPAA + AHIMA per Q-DAM-002. IME scheduling: [ESTIMATE]",
    ),
    OpenQuestion(
        id="Q-DAM-008",
        description="What is the claimant's pre-accident medical history relevant to the injuries claimed?",
        blocks_end_state="damages",
        gating="required",
        sources=[
            Source(
                party="medical_provider", channel="fax",
                cycle_time_days_min=5, cycle_time_days_max=30,
                fidelity="primary",
                notes="Pre-accident records via HIPAA release (per provider)",
            ),
            Source(
                party="medical_provider", channel="portal",
                cycle_time_days_min=21, cycle_time_days_max=45,
                fidelity="authoritative",
                notes="Health-insurer claims history — Tom: 'they're very inefficient'",
            ),
        ],
        best_case_cycle_time_days_min=5,
        best_case_cycle_time_days_max=14,
        depends_on=["Q-DAM-013"],
        fact_stable_at="MMI",
        requirement_citation="AIC §4.8; FL causation defense practice",
        cycle_time_citation="HIPAA + AHIMA per Q-DAM-002; health-insurer historic 21-45d per Tom's TPA estimate",
    ),
    OpenQuestion(
        id="Q-DAM-009",
        description="What property damage (vehicle, contents) is claimed, and what is the repair estimate?",
        blocks_end_state="damages",
        gating="conditional",
        conditional_trigger="property damage claimed",
        sources=[
            Source(
                party="body_shop", channel="email",
                cycle_time_days_min=1, cycle_time_days_max=7,
                fidelity="primary",
            ),
            Source(
                party="body_shop", channel="in_person",
                cycle_time_days_min=3, cycle_time_days_max=10,
                fidelity="authoritative",
                notes="Independent appraiser",
            ),
            Source(
                party="carrier_uw", channel="api",
                cycle_time_days_min=0, cycle_time_days_max=0,
                fidelity="secondary",
                notes="NADA / Mitchell valuation for total loss",
            ),
        ],
        best_case_cycle_time_days_min=0,
        best_case_cycle_time_days_max=7,
        depends_on=[],
        requirement_citation="AIC §4.9",
        cycle_time_citation="Tom confirmed body shop 1-7d turnaround",
    ),
    OpenQuestion(
        id="Q-DAM-010",
        description="Is there a diminution-of-value claim, and on what basis?",
        blocks_end_state="damages",
        gating="nice_to_have",
        sources=[
            Source(
                party="body_shop", channel="email",
                cycle_time_days_min=7, cycle_time_days_max=21,
                fidelity="primary",
                notes="DV appraisal (independent)",
            ),
            Source(
                party="claimant_counsel", channel="email",
                cycle_time_days_min=14, cycle_time_days_max=30,
                fidelity="secondary",
                notes="Demand letter — includes basis",
            ),
        ],
        best_case_cycle_time_days_min=7,
        best_case_cycle_time_days_max=21,
        depends_on=["Q-DAM-009"],
        requirement_citation="FL DV claim practice (variable by case law)",
        cycle_time_citation="[ESTIMATE]",
    ),
    OpenQuestion(
        id="Q-DAM-011",
        description="Are there liens (medical provider, ERISA, Medicare/Medicaid, workers comp)?",
        blocks_end_state="damages",
        gating="required",
        sources=[
            Source(
                party="cms_msprp", channel="portal",
                cycle_time_days_min=30, cycle_time_days_max=90,
                fidelity="authoritative",
                notes="CMS published MSPRP turnaround 65 business days standard",
            ),
            Source(
                party="claimant_counsel", channel="email",
                cycle_time_days_min=7, cycle_time_days_max=14,
                fidelity="primary",
                notes="ERISA plan lien notice via counsel after demand",
            ),
            Source(
                party="medical_provider", channel="mail",
                cycle_time_days_min=1, cycle_time_days_max=30,
                fidelity="primary",
                notes="Provider lien notices arrive as filed",
            ),
        ],
        best_case_cycle_time_days_min=30,
        best_case_cycle_time_days_max=90,
        depends_on=["Q-DAM-001"],
        fact_stable_at="settlement",
        requirement_citation="Medicare Secondary Payer Act; AIC §4.10",
        cycle_time_citation="CMS published MSPRP turnaround 65 business days standard — known long pole",
        notes="Slowest known atom in the map. If claimant is Medicare-eligible, MUST be queried day 1.",
    ),
    OpenQuestion(
        id="Q-DAM-012",
        description="Has a demand been made, and for what amount on what basis?",
        blocks_end_state="damages",
        gating="required",
        sources=[
            Source(
                party="claimant_counsel", channel="email",
                cycle_time_days_min=60, cycle_time_days_max=365,
                fidelity="primary",
                notes="Demand letter when counsel sends; not on a request cycle",
            ),
        ],
        best_case_cycle_time_days_min=60,
        best_case_cycle_time_days_max=365,
        depends_on=["Q-DAM-002", "Q-DAM-006"],
        fact_stable_at="demand_received",
        requirement_citation="Standard pre-suit practice; AIC §5",
        cycle_time_citation="Not adjuster-controlled. Industry: most demands give 20-60d (commonly 30d) to respond.",
    ),
    OpenQuestion(
        id="Q-DAM-013",
        description="Has the claimant executed HIPAA medical-records releases for the providers we need?",
        blocks_end_state="damages",
        gating="required",
        sources=[
            Source(
                party="claimant_counsel", channel="email",
                cycle_time_days_min=1, cycle_time_days_max=7,
                fidelity="primary",
                notes="STRUCTURAL CONSTRAINT: when rep_flag=True, counsel ONLY — FL § 626.9541(1)(i) prohibits direct contact with represented claimants",
            ),
            Source(
                party="claimant", channel="email",
                cycle_time_days_min=1, cycle_time_days_max=7,
                fidelity="primary",
                notes="ONLY when unrepresented (rep_flag=False)",
            ),
        ],
        best_case_cycle_time_days_min=1,
        best_case_cycle_time_days_max=7,
        depends_on=[],
        requirement_citation="HIPAA Privacy Rule (45 CFR 164); FL § 626.9541(1)(i) (no direct contact with represented claimants)",
        cycle_time_citation="[ESTIMATE] — counsel response per Tom's TPA experience",
        notes="HIGHEST-LEVERAGE DAY-1 ACTION: gates Q-DAM-001 through Q-DAM-008. Outreach Drafter MUST enforce rep_flag routing.",
    ),
]


# ---------------------------------------------------------------------------
# Public map
# ---------------------------------------------------------------------------


INFO_MAP_AUTO_BI_FL = InfoMap(
    lob="auto_BI",
    jurisdiction="FL",
    phase="post_FNOL_pre_coverage_decision",
    revision=REVISION,
    questions=[*_Q_COV, *_Q_LIA, *_Q_DAM],
)
"""The locked v1 info map. 39 questions: 15 coverage, 11 liability, 13
damages. Synced 1:1 with `docs/specs/info-map-auto-bi-fl.md` (r2)."""
