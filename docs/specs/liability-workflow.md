---
tags:
  - project/argos
  - type/spec
  - status/design
created: 2026-06-01
updated: 2026-06-01
---

# Liability workflow — design spec

> **Status:** design. Schema and runtime not yet shipped. Runner is currently
> a stub (`_stub_workflow("liability")` in
> `src/argos/services/orchestrator/runner.py`). This doc defines what the
> real runtime does before we write it.

## The problem

The Reserve workflow we shipped takes `insured_liability_pct` as an input
field. Today, nothing in Argos produces that number. The demo fixture
provides it; in production, an adjuster has to compute it by hand from the
police report, recorded statements, scene photos, expert reports, and
their own application of Florida liability doctrines.

Liability does the cognitive labor between "new evidence landed" and
"defensible apportionment ready for Reserve."

But the headline insight from the research is sharper than that: in
real specialty-TPA practice, the **percentage is not the deliverable.**
The deliverable is a structured, evidence-anchored set of insights — the
fact-pattern classification, the evidence items with quoted source spans,
the FL doctrine gates that applied, the variance flags — that makes the
apportionment number *defensible against discovery*. Under
*Allstate v. Ruiz*, that record is itself a trial exhibit. Under
*Boston Old Colony / Berges / Harvey*, it's the bad-faith defense. The
percentage is what falls out of the structured record, not what gets
generated first.

So Liability does not "decide who's liable." Liability reads the file,
generates structured evidence aligned to FL doctrines, surfaces what the
evidence supports and what it doesn't, and produces a recommended
apportionment with a confidence band and the audit trail behind it. The
adjuster commits. Argos surfaces.

## Architecture: extractor + policy engine + apportionment calculator + diligence ledger

Same Software 1.0/3.0 split as Reserve (see [reserve-workflow.md](./reserve-workflow.md)
and `DECISIONS.md` 2026-06-01 entry), but the calculator decomposes into
two deterministic stages and there is a third co-equal artifact.

| Stage | Layer | Responsibility |
|---|---|---|
| **A. Extractor** | LLM (Software 3.0) | Reads docs + claim state, emits structured `LiabilityInputs` — fact pattern, parties + roles, evidence items with quoted spans, FL-specific facts (owner relationship, intoxication, rear-end rebuttal, Fabre candidates) |
| **B1. Policy engine** | Python (Software 1.0) | FL doctrine gates — step-function logic. Determines which apportionment regime applies (pre-/post-HB-837), vicarious cap ceiling, Graves preemption, negligent entrustment branch, §768.36 intoxication bar applicability |
| **B2. Apportionment calculator** | Python (Software 1.0) | Anchor + adjustment table. Per-pattern anchor (rear_end → 95% rear, left_turn → 90% turner). Evidence-weight table. Per-party-pair scalar with confidence band derived from evidence completeness + inter-evidence agreement |
| **C. Diligence ledger** | Python template | Contemporaneous record: posture by party, basis evidence with cite, change conditions, next review, open requests with age, evidence-not-obtained-with-reason, prior-posture deltas, supervisor disagreement record. Discoverable under *Ruiz*; defensible under *Harvey* |

> **Why not extractor-only with LLM-judged apportionment.** The FL doctrine
> gates (51% bar, Graves preemption, §768.36 intoxication, Fabre,
> dangerous-instrumentality cap) are step-functions with binary effects on
> recovery. Putting them in an LLM judgment call is the same trap that
> killed the v2 triage hybrid: the model infers its own policy instead of
> executing the documented one. Per [[karpathy-principles]] Software 1.0,
> these are specifiable rules. Per the Argos rule
> ([[policy-engine-first-then-llm-extraction]]): deterministic gates +
> LLM for extraction only.
>
> **Why not pure calculator.** Fact-pattern classification, evidence
> extraction with quoted spans, and consistency-checking (ER mechanism vs
> claimant statement vs police-report point-of-impact) genuinely require
> LLM-level reading. The split keeps each tier at the right altitude.
>
> **Why the diligence ledger is co-equal, not a side effect.** Under
> *Allstate v. Ruiz* (901 So. 2d 802, Fla. 2005) the claim file diligence
> trail is discoverable in bad-faith litigation. *Harvey v. GEICO* lost on
> procedural-diligence gaps, not on substantive fault calls. The ledger
> IS the artifact plaintiff's counsel reads to the jury. If we produce a
> defensible percentage with no trail, we have built the wrong product.

**Cost of the split (same as Reserve):** the rationale narrative is
templated, not LLM-voice. We gain byte-reproducibility, model-swap
survivability, and discovery-defensibility. For legally-bearing outputs
in FL bad-faith country, that's the right trade.

## Components

| Component | Layer | Responsibility |
|---|---|---|
| `LiabilityInputs` | data | Pydantic model the extractor emits; calculator + policy engine consume |
| `LiabilityAssessment` | data | Output: per-party apportionment band + applicable regime + exposure ceiling + rationale + ledger + variance flags + authority tier + evidence pack classification |
| `extract_liability_inputs` | LLM workflow | Document + claim state → LiabilityInputs via structured tool_use |
| `apply_fl_doctrines` | Python | Inputs + ProgramConfig → DoctrineResolution (regime, ceiling, bar flags, branch path) |
| `compute_apportionment` | Python | Inputs + DoctrineResolution → per-party-pair scalars with bands |
| `FACT_PATTERN_ANCHORS_V1` | Python const | Per-pattern anchor (rear_end 95% rear; left_turn 90% turner; etc.) |
| `EVIDENCE_WEIGHTS_V1` | Python const | Five-tier weight class → ±point adjustments |
| `FL_DOCTRINE_REGISTRY_V1` | Python const | Versioned catalog of named FL doctrines, statutes, controlling cases |
| `render_diligence_ledger` | Python template | Templated contemporaneous record; byte-reproducible |
| `render_liability_rationale` | Python template | Anchor → evidence walk → doctrine gates → net apportionment walk |

## Triggers — when the workflow runs

Same event-driven pattern as Reserve. Calendar diary is fallback safety net.

| Trigger | Fires when | Rationale |
|---|---|---|
| `FNOL_INITIAL` | FNOL or first notice extracted; police report not yet on file | §627.70131-adjacent investigation-begun expectation. Emits **preliminary posture only** (narrative + investigation plan, NO quantified apportionment) — Reserve runs on placeholder band, not point estimate |
| `INITIAL_APPORTIONMENT` | Police report on file AND (insured statement OR scene photos) on file | Earliest moment a quantified apportionment is defensible. Hands off first real `insured_liability_pct` to Reserve. Matches industry day 21-30 norm |
| `EVIDENCE_LANDED_RE_EVAL` | New recorded statement / EDR / surveillance video / expert report / supplemental police report / ER mechanism extracted | Event-driven re-eval. Apportionment recomputes with new evidence in the table; emits delta-from-prior. Delta > examiner band → roundtable trigger |
| `DEMAND_RECEIVED` | Time-limit or policy-limits demand arrives | Snapshot freeze. §624.155(4) "sufficient evidence" assessment fires; *DeLaune* set-up-defense framework requires contemporaneous record of what was known when demand landed |
| `DEPOSITION_TAKEN` | Deposition transcript (insured / claimant / treating MD / expert) lands | Apportionment can shift materially on sworn testimony vs prior recorded statement. Variance flag if depo contradicts prior statement |
| `CRN_FILED` | Civil Remedy Notice filed (§624.155(3)) | Parses alleged violations; cross-references diligence ledger for cited gaps; surfaces what must close inside 60 days |
| `NEAR_BAR_VARIANCE` | Apportionment lands within ±5 of 50% on post-2023-03-24 accrual | Step-function value swing. Roundtable escalation regardless of dollars — step-function risk dominates dollar risk |
| `POWELL_CLARITY_CHECK` | Insured fault >70% + excess-judgment indicators (severe injury, multi-claimant, low limits) | *Powell* duty to initiate settlement triggers. Flag for tender decision; don't let file sit without documented *Powell* evaluation |
| `CALENDAR_DIARY_90_DAY` | 90 days since last evaluation, no intervening event | Fallback adequacy review. Parallel with event-driven |

## `LiabilityInputs` schema (extractor output)

LLM extractor produces this Pydantic model. Each field anchors to source
documents for per-field anchor-pair eval.

```python
class LiabilityInputs(BaseModel):
    # HB 837 regime gating
    accrual_date: date              # gates pre/post 2023-03-24 regime
    line_of_business: Literal[
        "auto_bi", "med_mal", "commercial_auto", "trucking", "rideshare", "other",
    ]

    # Parties (N from day one; FL is several-only)
    parties: list[Party]            # role, identity_evidence_cite

    # Fact-pattern classification (drives anchor selection)
    fact_pattern: Literal[
        "rear_end", "left_turn_across_traffic", "lane_change",
        "uncontrolled_intersection", "controlled_intersection",
        "parked_pullout", "sideswipe", "chain_reaction",
        "pedestrian_in_crosswalk", "pedestrian_mid_block",
        "cyclist", "parking_lot", "other",
    ]

    # FL-specific facts
    owner_relationship: OwnerRelationship      # dangerous instrumentality + Graves + caps
    negligent_entrustment_indicators: NegligentEntrustment
    intoxication_evidence: IntoxicationEvidence  # §768.36 dual-prong
    rear_end_rebuttal_evidence: RearEndRebuttal  # Birge four categories

    # Evidence items (the load-bearing field)
    evidence_items: list[EvidenceItem]

    # Police report structured fields (FL HSMV 90010S)
    police_report_structured_fields: PoliceReportFields | None = None

    # Consistency checks
    consistency_checks: ConsistencyChecks

    # Demand state (for §624.155(4) sufficient-evidence assessment)
    demand_received: DemandState | None = None

    # ROR + CRN state (§627.426(2) cooperation defense windows; §624.155(3) cure)
    ror_and_crn_state: RorCrnState | None = None

    # Prior posture history (for delta detection)
    prior_posture_history: list[PostureSnapshot] = []
```

### `EvidenceItem` — the load-bearing inner type

Every percentage point in the final apportionment walks from an anchor
through evidence items to the final number. Every evidence item must be
quotable and source-cited.

```python
class EvidenceItem(BaseModel):
    kind: Literal[
        "police_report_field", "police_report_narrative",
        "recorded_statement_insured", "recorded_statement_claimant",
        "recorded_statement_witness",
        "scene_photo", "edr_download", "surveillance_video",
        "expert_report_recon", "expert_report_biomech",
        "expert_report_medical_causation",
        "er_record_mechanism", "damage_appraisal", "citation_issued",
        "mvr_record", "deposition_transcript", "party_admission",
    ]
    source_doc_id: str
    quoted_span: str              # verbatim from source — Ruiz discoverability
    contemporaneity_hours_from_loss: int | None
    fl_admissibility: Literal[
        "admissible",
        "privileged_316_066",          # accident-report privilege (statements)
        "physical_evidence_carveout",   # skid marks, debris, measurements
        "chemical_test_carveout",       # §316.1934 BAC results
    ]
    represented_by_counsel_at_capture: bool | None  # coercion-risk metadata
    fault_direction: Literal[
        "insured_more_fault", "claimant_more_fault", "neutral",
    ]
    weight_class: Literal[
        "hard_data",          # EDR, video, physical evidence — ±20-25
        "independent",        # witness statement, citation — ±10-15
        "party_admission",    # ±15
        "rebuttable_signal",  # police-report contributing factor — ±5
        "credibility_only",   # demeanor, prior crashes — ±0-5
    ]
```

## Policy engine constants

Versioned in Python. v1 anchors below — calibrated against the 2026-06-01
research workflow's named-source-grounded findings.

### Fact-pattern anchors (FL auto BI, post-HB 837)

Closest published proxy is MA 211 CMR 74 (codified presumptive fault for
rear-end / opposite-side / left-turn). FL has no equivalent codified
rule — these are industry-aligned anchors derived from controlling cases
(*Birge / Pierce / Eppler / Douglas-Seibert* for rear-end; FL Std. Jury
Instr. 401 for left-turn).

| Fact pattern | Anchor — rear/turning/striking party at fault | Controlling authority |
|---|---|---|
| `rear_end` | ~95% rear driver | *Birge v. Charron*, *Pierce v. Progressive*, *Eppler v. Tarmac* |
| `left_turn_across_traffic` | ~90% turning driver | FL Std. Jury Instr. 401, §316.122 |
| `uncontrolled_intersection` | ~50/50 baseline; evidence shifts ±20 | §316.121 (right-of-way) |
| `controlled_intersection` | ~85% violator (citation evidence) | §316.075 / §316.123 |
| `lane_change` | ~80% changing driver | §316.085 |
| `parked_pullout` | ~80% pulling-out driver | §316.195 |
| `sideswipe` | ~60/40 to lane-departing driver | §316.089 |
| `pedestrian_in_crosswalk` | ~80% striking driver | §316.130 |
| `pedestrian_mid_block` | ~60% pedestrian | §316.130(10) |
| `chain_reaction` | per-event single pie, FL several-only | Fabre |
| `parking_lot` | case-by-case | (forces human review) |
| `other` | (no anchor — escalate) | (forces human review) |

### Evidence weight table

Five-tier weight class. Adjustments are point-shifts off the anchor.

| Weight class | Examples | Adjustment |
|---|---|---|
| `hard_data` | EDR speed/brake, surveillance video, scene measurements | ±20–25 |
| `independent` | Independent witness statement; citation issued by officer | ±10–15 |
| `party_admission` | Insured/claimant admission against interest | ±15 |
| `rebuttable_signal` | Police-report contributing-factor code | ±5–10 |
| `credibility_only` | Demeanor in statement; prior crash history pattern | ±0–5 |

Consistency-check failures (ER mechanism vs claimant statement
contradiction; damage pattern vs claimed mechanism contradiction) **do
not auto-shift fault**. They widen the band and route to SIU if pattern
is strong — never silently feed contradiction into the calculator as a
fault-adjustment. (Per research finding 47: that's the "opening posture
as real call" bad-faith trap.)

### FL doctrine registry

15 named doctrines. v1 implements all of them. Each is a Python module
with `applies_when(inputs) -> bool` + `effect(state) -> state`.

| Doctrine | Statute / Case | Effect |
|---|---|---|
| HB 837 51% bar | §768.81(6) | Step-function — claimant >50% fault recovers zero (post-2023-03-24 non-medical-negligence) |
| Pure comparative (pre-HB-837 / med-mal carve-out) | §768.81 pre-amend | No bar — recovery proportional |
| Fabre apportionment | *Fabre v. Marin*; *Nash v. Wells Fargo* | Non-party fault apportioned if factually-supported AND pled per Rule 1.110(d) |
| Joint-and-several abolished for negligence | §768.81(3) | Per-defendant exposure = apportioned % × damages |
| Dangerous Instrumentality | *Aurbach v. Gallina*; *Hertz v. Jackson* | Vehicle owner vicariously liable; theft breaks chain |
| Natural-person owner cap | §324.021(9)(b)3 | Vicarious exposure capped $100K/$300K BI + $50K PD + conditional $500K econ |
| Negligent entrustment | §324.021(9)(b)3 closing | Uncapped direct theory if owner-knowledge evidence |
| Graves Amendment preemption | 49 USC §30106; *Vargas v. Enterprise* | Commercial lessor removed; exception: negligent maintenance / negligent rental |
| §768.36 Intoxication bar | §768.36 | Recovery bar if BAC≥0.08 OR impairment AND >50% fault-from-impairment (causation prong) |
| Rear-end rebuttable presumption | *Birge*; *Pierce*; *Eppler*; *Douglas-Seibert* | ~95% rear driver anchor unless 4 named rebuttals evidenced |
| Sudden Emergency eliminated | *Birge v. Charron* | Zero weight; folds into reasonableness. Medical emergency / loss of consciousness survives as distinct theory |
| Last Clear Chance abolished | *Hoffman v. Jones* (1973) | Zero weight |
| §316.066(4) accident-report privilege | §316.066(4) | Per-datum classification — privileged statements vs physical-evidence carveout vs chemical-test carveout |
| *Boston Old Colony / Berges / Harvey* good-faith duty | §624.155 + common law | Doesn't change apportionment — sets diligence ledger requirements |
| *Powell* duty to initiate settlement | *Powell v. Prudential* | Doesn't change apportionment — flags tender obligation when liability "clear" + excess-judgment likely |

### Variance zones (route around the calculator)

10 zones. The calculator does NOT silently commit through any of these.

| Zone | Condition | Action |
|---|---|---|
| `near_51_pct_bar` | Post-2023-03-24, any party within ±5 of 50% | Force roundtable regardless of dollars; widen band; Reserve runs dual scenarios (recovery vs zero) |
| `fabre_non_party_evidenced_but_unpled` | Factual basis exists, defense counsel hasn't pled | Calculator runs Fabre-granted AND Fabre-waived scenarios; Reserve gets conservative path with alt in band |
| `powell_clarity_ambiguity` | Insured >70% fault + excess-judgment indicators AND any contesting evidence | Surface "*Powell* duty contested — liability not free from doubt" with contesting-evidence ledger explicitly populated. *Welford* defense |
| `sufficient_evidence_borderline` | Demand received AND §624.155(4) assessment is borderline | Do NOT auto-start safe-harbor clock. Surface Y/N + reasoning to claims leadership |
| `multi_party_apportionment` | Party count >2 OR Fabre non-parties identified OR multiple claimants with divisible injuries | Switch to matrix view; per-event single pie totaling 100% across all parties |
| `intoxication_bar_candidate` | BAC≥0.08 OR impairment AND plaintiff-fault candidate >50% | Run §768.36 dual-prong check: admissibility + causation. Missing causation = flag as investigation gap |
| `siu_referral` | Damage-vs-mechanism contradiction OR ER-mechanism contradiction OR claimant prior-crash + similar-injury pattern | Route to SIU. Pause apportionment commit. Do NOT feed contradiction silently into calculator |
| `evidence_gap_blocks_initial_call` | Neither police report nor (insured statement + scene photos) on file by FNOL+21 | Refuse to emit quantified apportionment. Preliminary posture only |
| `apportionment_delta_exceeds_band` | New apportionment moves >15 points from prior posture in single re-eval | Roundtable trigger. Calculator emits delta with the specific new evidence that justified it |
| `graves_vs_negligent_entrustment_branch` | Commercial lessor in chain + any evidence of lessor's own negligence | Run Graves-preempts AND Graves-exception paths; Reserve gets conservative with alt scenario |

## `LiabilityAssessment` output

```python
class LiabilityAssessment(BaseModel):
    request_id: str
    reviewed_as_of: datetime

    # The number Reserve actually consumes
    apportionment: dict[str, ApportionmentEntry]  # party_id → {fault_pct, band, confidence}

    # Doctrine resolution
    applicable_regime: ApplicableRegime           # pre/post HB-837, bar_triggered, bar_basis
    exposure_ceiling: ExposureCeiling             # vicarious cap, econ layer, neg-entrust path

    # The audit trail (co-equal with apportionment)
    rationale: LiabilityRationale                 # anchor + evidence walk + doctrine gates
    diligence_ledger: DiligenceLedger             # the Ruiz discoverable artifact

    # Surfaces for downstream routing
    variance_flags: list[VarianceFlag]
    authority_tier_required: AuthorityRouting
    evidence_pack_classification: EvidencePack    # trial-admissible vs reserve-only vs privileged

    # Side handoffs
    subro_referral: SubroReferral | None
```

## Diligence ledger (the Ruiz/Harvey discoverable artifact)

This is the part that's not in Reserve. It's not optional. It is itself
the work product.

```python
class DiligenceLedger(BaseModel):
    posture_percent_by_party: dict[str, int]
    basis_evidence: list[BasisEvidenceEntry]    # source_doc_id, quoted_span, weight_class
    change_conditions: list[str]                # "if EDR shows pre-impact braking < 0.5s, apportionment shifts +10 insured"
    next_review_date: date
    next_review_trigger: str                    # event-driven default; calendar fallback
    prior_posture_delta: PriorPostureDelta | None  # prior_pct, prior_date, what_changed_evidence_id

    open_requests: list[OpenRequest]            # request_type, requested_date, age_days, target_party
    evidence_not_obtained: list[EvidenceNotObtained]  # evidence_kind, reason_declined, date

    supervisor_disagreement_record: list[Disagreement] | None  # date, dissent_pct, dissent_basis
```

**Anti-pattern this prevents (Harvey trap):** silent omission of evidence
the claim file lacked. *Harvey* lost on "completely dropped the ball"
gaps — the carrier didn't make the calls that would have surfaced
adverse facts. The ledger field `evidence_not_obtained` makes
non-collection a positive record (with reason), not a silent absence
plaintiff's counsel paints as cover-up.

## Authority bands (defaults; CHA overrides)

Same shape as Reserve: seeds loaded from `PROGRAM_CONFIG`; every TPA
customer overrides.

| Apportionment + exposure range | Required approver | Rationale |
|---|---|---|
| `committable_at_examiner` AND apportionment >70% insured/claimant AND no variance flags | Examiner unilateral | Clear cases |
| Standard auto BI, no variance flags, within examiner authority dollars | Examiner unilateral | Routine |
| Any variance flag active | Senior examiner + supervisor notice | Variance is the contract for non-silent escalation |
| `near_51_pct_bar` OR `powell_clarity_ambiguity` OR `sufficient_evidence_borderline` | Supervisor + roundtable | Step-function risk dominates dollar risk |
| Catastrophic injury + contested liability OR limits-exposed + Powell ambiguity | Manager + Large Loss Committee + coverage counsel | Bad-faith perimeter |
| Bad-faith risk markers active (CRN filed, safe-harbor expired without tender) | Claims VP / CCO + coverage counsel + executive committee | Same as Reserve top tier |

> **Critical:** authority is keyed off GROSS exposure (damages × full
> liability) at most TPAs, NOT net (damages × apportioned %). The
> calculator surfaces both. The `committable_at_examiner` flag is the
> load-bearing UX bit — Argos never silently commits beyond authority.

## Templated rationale

Same approach as Reserve: byte-reproducible interpolation, not LLM voice.

```
LIABILITY EVALUATION — Claim {claim_id} | Eval #{eval_seq} | {eval_date} | Examiner: {examiner_id} | constants {VERSION}
TRIGGER: {trigger_name} ({trigger_event_date})

PARTIES (N={party_count}):
{for each party — party_id, role, identity_evidence_cite}

FACT PATTERN: {fact_pattern} (anchor: {anchor_pct}% {anchor_party_role}; controlling: {controlling_authority})

APPLICABLE REGIME:
  Statute: {regime — pure_comparative_pre_hb837 | modified_51_bar_hb837 | med_mal_pure_comparative}
  Accrual date {accrual_date} → {regime_explanation}
  Recovery bar triggered: {bar_status — none | hb837_51_pct | 768_36_intoxication}

EXPOSURE CEILING:
  Vicarious cap: {cap_status — none | natural_person_cap_$100K/$300K + conditional_econ_$500K | graves_preempted}
  Negligent entrustment path: {neg_entrust_status — uncapped_path_available_with_evidence | not_evidenced}
  Fabre defendants: {fabre_list or "none pled"}

APPORTIONMENT WALK (anchor → evidence → doctrine → net):
  Start: {fact_pattern} anchor = {anchor_pct}% {anchor_party_role}
  Evidence adjustments:
{for each evidence_item — direction, magnitude, basis, source_doc_cite, quoted_span}
  Doctrine gates applied:
{for each doctrine — name, effect, statute_cite}
  Net: {final_pct} per party

CONFIDENCE BAND: {pct_low}% — {pct_high}% (basis: {band_basis — evidence_completeness, inter_evidence_agreement})

VARIANCE FLAGS ({flag_count} active):
{flag_list — each routes to a downstream action}

PRIOR POSTURE DELTA: {delta_pct} ({delta_direction}) — basis: {what_changed_evidence}

§316.066(4) EVIDENCE PACK CLASSIFICATION:
  Trial-admissible: {trial_admissible_count} items
  Privileged statements (reserve-only): {privileged_count} items
  Physical-evidence carveout: {physical_count} items
  Chemical-test carveout: {chemical_count} items

DILIGENCE LEDGER:
{full ledger render — posture by party, basis evidence with cites, change conditions, next review, open requests with age, evidence not obtained with reason, supervisor disagreements}

AUTHORITY:
  Gross exposure: {money}
  Net apportioned exposure: {money}
  Required tier: {tier}
  Committable at examiner: {bool}
  Basis: {tier_basis}

DOWNSTREAM HANDOFFS:
  Reserve: insured_liability_pct={point}, band=[{low},{high}], regime={regime}, ceiling={ceiling}
  Brief: {what Brief gets — rationale + ledger + admissible subset}
  Authority/Tender: {what Tender gets — variance flags + sufficient-evidence assessment}
  Subro: {recommended? recoverable_third_party}
  Coverage: {orthogonal facts handed off — owner_type, permissive_use, intentional_vs_negligent}
```

## Re-evaluation actions per trigger

| Event | Action |
|---|---|
| FNOL extracted | Emit preliminary posture (narrative + investigation plan, NO quantified apportionment) |
| Police report on file | Run extractor; if insured statement OR scene photos also present → initial apportionment; else stay preliminary |
| Recorded statement received | Re-extract; re-run consistency checks against prior statements + police report |
| Scene photos / EDR / surveillance video | Re-extract; bump weight class on existing evidence items if hard-data corroboration; emit delta with new evidence ID |
| Expert report (recon / biomech / medical-causation) | Re-extract; if recon contradicts claimant POI or biomech contradicts mechanism, flag SIU + widen band |
| Supplemental police report / FHP report | Re-extract; reconcile with prior police-report fields |
| Demand received | Snapshot freeze of current posture; run §624.155(4) sufficient-evidence assessment; do NOT auto-start safe-harbor clock; surface to claims leadership |
| Deposition transcript | Re-extract; if sworn testimony contradicts prior recorded statement, flag variance + add to diligence ledger |
| CRN filed | Hard escalation; parse alleged violations against diligence ledger; identify which open_requests close gaps; cure_deadline countdown |
| Apportionment delta > examiner band | Roundtable trigger. Emit delta with the specific evidence item that justified it |
| 90-day calendar diary | Lightweight re-eval; "no change — facts stable" if so, ledger updated, next_review_date refreshed |

## Anti-patterns (explicit)

| Anti-pattern | Argos response |
|---|---|
| **LLM emits final fault %** | Architectural rejection. Calculator owns apportionment math; doctrine engine owns regime gating |
| **Auto-start §624.155(4) safe-harbor clock on borderline sufficient-evidence** | Surface Y/N + reasoning to claims leadership; never auto-start. *Berges* "totality" trap |
| **Silent omission of evidence we didn't collect** | `evidence_not_obtained` ledger field with reason. Positive record beats silent absence. *Harvey* defense |
| **Feed consistency-check contradictions silently into fault adjustment** | Contradictions widen band + route to SIU. Per research: opening-posture-as-real-call is the bad-faith trap |
| **Commit through a variance flag** | `committable_at_examiner=false` if any variance flag active. Roundtable required |
| **Bad-faith risk overlay scoring** | Argos surfaces markers + ledger + variance flags. Does NOT output "bad-faith exposure score." Faking that judgment invites the AI-excuse-generator-becomes-bad-faith-exhibit failure mode |
| **Fabre non-party scored without pleading check** | Calculator runs dual scenarios (granted vs waived); Reserve gets conservative with alt in band; named defendant carries the share until pled per Rule 1.110(d) |
| **Single-pie totals != 100%** | Calculator validates pie totals 100% across named + Fabre slots per FL several-only regime; raises if violated |

## Open questions (v1 cannot resolve without carrier data)

- **Specialty TPA evidence weight tables** are not public. v1 ships industry-aligned anchors (MA 211 CMR 74 proxy + controlling-case anchors). Calibration loop against settled outcomes per program is roadmap, not v1.
- **Authority dollar bands** are illustrative — actual CHAs are confidential. Loaded as ProgramConfig.
- **§624.155(4) "sufficient evidence"** is undefined and being litigated post-HB-837 (*Doe v. Allstate* DCA split). Argos outputs Y/N + reasoning; never pretends to know what courts will hold.
- **HB 837 "mere negligence insufficient for bad faith"** — whether this meaningfully softens *Harvey* procedural-diligence trail expectation, or plaintiff bar still wins on *Berges* totality, is litigated. Posture: maintain *Harvey*-grade ledger anyway. Cost low, downside asymmetric.
- **EDR data**: 2024 NHTSA rule expanded pre-crash capture to 20s @ 10Hz (compliance 2027-09-01). v1 supports both legacy 5s and new 20s schemas. Installed-base mix in 2026 is mostly legacy.
- **Whether real TPAs will accept LLM-generated apportionment at all** without human-final-sign-off is a market question, not a technical one. v1 positions Liability as **validated draft work product** — never auto-commits, always surfaces authority tier needed.

## Realism caveats (what v1 explicitly does not model)

- **v1 anchor table covers ~12 fact patterns** plus an `other` bucket that forces human review. Real specialty book has more edge cases (parking-lot lane disputes, lot-to-lot transitions, gravity-fed chain reactions on icy roads); v1 routes them to `other`
- **Evidence weights are documented best-guess ProgramConfig values**, not empirically calibrated against settled outcomes. Honest framing in the demo: "the moat is the structured evidence trace + diligence ledger, not the specific numbers — which we calibrate per TPA against their settled-claim corpus"
- **v1 assumes single-event per claim.** Chain-reaction crashes with sequential separable impacts and divisible injuries get matrix view, but the calculator runs per-event single pies. Single claimant with two impacts contributing different injuries to different damage categories is roadmap
- **v1 is FL-only.** ~15 doctrine gates. Porting to TX/NY/GA/CA each requires its own gate set. Frame: depth-in-FL beats breadth-thin-everywhere
- **v1 does not model first-party UM/UIM claims**, only third-party BI. UM has different bad-faith contours (*Ruiz* arose in UM) and different apportionment downstream
- **v1 does not model coverage-questions liability interactions** (late notice + non-cooperation + Fabre stacking). §627.426(2) cooperation defense captured at intake; full bifurcation lives in Coverage workflow
- **Diligence ledger captures what Argos was given**, not what should have been investigated by a human off-system. v1 surfaces gaps; collection workflow is human-driven
- **v1 takes a single apportionment commit at each trigger event.** Does not model defense-counsel-vs-examiner-vs-supervisor disagreement dynamics. `supervisor_disagreement_record` is metadata, not parallel outputs
- **Authority-tier output assumes the TPA's CHA is loaded as ProgramConfig.** v1 demos with a representative CHA structure; production onboarding requires per-carrier CHA encoding
- **Bad-faith risk scoring is not in v1.** Argos surfaces the diligence ledger + variance flags that map to bad-faith triggers (*Powell*, *Harvey* gaps, sufficient-evidence borderlines). Does NOT output "bad-faith exposure score" — that's a judgment call left to coverage counsel, and faking it invites the exact failure mode the workflow is designed to prevent

## Evaluation plan

Same shape as Reserve: per-component eval.

| Layer | Method | Pass bar |
|---|---|---|
| Extractor | Per-field anchor-pair eval | >90% on `fact_pattern`, `applicable_regime`, `owner_type`, `intoxication_evidence.bac`; >85% on `evidence_items` quoted_span exactness; >95% on temporal fields |
| Policy engine | Unit tests per doctrine, golden inputs | 100% golden match (these are pure rules) |
| Apportionment calculator | Unit tests on hand-built inputs | 100% golden match |
| Rationale + ledger | Byte-exact golden-file diff | 100% match |
| End-to-end | Recorded claim files with examiner-validated apportionments | Apportionment within ±10 points of examiner-set on >75% of files; variance flags match examiner-noted markers on >80% |

## Runner interactions

| Downstream workflow | Data passed | Rationale |
|---|---|---|
| **Reserve** | `insured_liability_pct`, `fault_pct_band`, `applicable_regime` (with `recovery_bar_triggered`), `exposure_ceiling`, `prior_posture_delta` | Reserve takes the point estimate, the bar flag (step-function recovery zeroing), the ceiling (don't model above the cap on vicarious theory), the delta (examiner-band move vs roundtable-required) |
| **Brief** | `rationale` (anchor + evidence walk), `diligence_ledger` (basis evidence with quoted spans), `evidence_pack_classification` (trial-admissible subset) | Brief writes captioned report / status report / roundtable memo. Quoted spans matter — *Ruiz* makes them discoverable, Brief renders them as evidence-cited, not LLM paraphrase. Privileged classification keeps Brief from including §316.066(4) content in trial-facing artifacts |
| **Authority/Tender** | `authority_tier_required`, `gross_exposure`, `net_apportioned_exposure`, `variance_flags`, §624.155(4) sufficient-evidence assessment | Tender is where humans commit money. Liability never commits — surfaces what tier needed, both gross and net (CHAs typically gate on gross), and variance flags that argue against silent commitment |
| **Subro** | `subro_referral` (recommended bool, recoverable third party, basis apportionment, supporting evidence) | Subro is parallel workflow surface. Argos models the handoff, not the merge. FL post-HB-837 BI subro pathways are real but PIP-complicated; v1 flags + hands off, doesn't pursue |
| **Coverage** | `owner_relationship.owner_type`, permissive_use evidence, `theft_evidence_cite`, `negligent_entrustment_indicators`, `line_of_business` | Coverage answers "does the policy respond." Liability extracts overlapping facts; both surfaces must agree on underlying facts and reach independent conclusions. Schema bifurcation principle — keep them structurally separate so coverage analysis doesn't contaminate liability and vice versa |
| **Roundtable** | Full output + prior posture history + variance flags + divergent-scenario calculations (Fabre-granted-vs-waived, intoxication-bar-applied-vs-not) | Roundtable is the human decision surface. Argos produces blind-reviewable artifact: evidence and anchors shown first, recommended apportionment shown last. Divergent scenarios let roundtable converge inside or outside Argos's band without recomputing from scratch |

## Why this earns the demo

Three things an insurance interviewer will probe — same questions as Reserve, different answers:

1. **Where does the LLM stop and Python start, and why there?**
   At `LiabilityInputs`. LLM owns extraction with quoted spans (Software 3.0 — bounded, gradable, model-swappable). Policy engine owns FL doctrine gates (Software 1.0 — step-functions). Apportionment calculator owns the anchor + evidence-weight math (Software 1.0 — versioned, unit-testable). Rationale and diligence ledger are templated — no LLM voice in legally-bearing artifacts.

2. **How do you defend the apportionment against discovery and bad-faith litigation?**
   The diligence ledger IS the defense. Every evidence item is source-cited with a quoted span. Every percentage point walks from a published-controlling-authority anchor through evidence items to the final number. Evidence we didn't collect is positive record with reason, not silent absence. *Ruiz* discoverability = ledger reads as adjuster claim notes, not LLM paraphrase. *Harvey* procedural-diligence trail = open-request log with ages. *Berges* totality = full prior-posture-delta history with what-changed-evidence.

3. **What do you NOT model, and how do you know it matters?**
   The realism-caveats list above. Each one names the abstraction, why, and what carrier-specific signal would unlock it. Most important: we do not auto-commit. We do not score bad-faith risk. We do not pretend to know "sufficient evidence" doctrine when courts don't. We surface the structured record; the human commits.
