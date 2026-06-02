---
tags:
  - project/argos
  - type/spec
  - status/design
created: 2026-06-02
updated: 2026-06-02
---

# Recovery workflow — design spec

> **Status:** design. Schema, runtime, and runner integration not yet
> shipped. Builds on the Liability workflow (committed 2026-06-01) and
> the Reserve workflow (committed 2026-06-01).

## The problem

FL specialty-TPA auto BI books leak recovery dollars at the **front of
the funnel, not the back**. By the time a file is closed and an examiner
thinks about subrogation, three things have already happened: evidence
has degraded, SOL is months away, and the doctrinal gates (PIP /
anti-subrogation / made-whole) have not been screened. The recoverable
money is gone before recovery work begins.

Four post-HB-837 (effective 2023-03-24) regime changes amplify this and
have not been re-baselined into legacy LMM specialty-TPA workflows:

1. **Negligence SOL collapsed 4 years → 2 years** (§95.11(4)(a)).
   Adjusters trained on the old clock routinely miss the new one.
2. **>50% comparative-fault is now a binary cliff** (§768.81(6)). A
   5-point fault swing flips a file from full-value to zero. Recovery
   inherits this cliff from Liability's apportionment.
3. **§768.0427 caps recoverable past medicals at paid-not-billed.**
   Billed-amount basis overstates recoverable by 2-3×.
4. **§624.155 third-party safe harbor does NOT extend to Recovery
   conduct** — only to liability-insurer tender. Bad-faith exposure on
   subro work is unchanged.

The structural reason for the leak: **handler-owned subro is the LMM
specialty pattern.** A single examiner carries 90+ indemnity files,
comped on closure speed not net recovery, and lets subro slide.
Off-the-shelf vendor scoring (CCC Safekeep, Shift, Athenium) commoditizes
identification scores but does not run the FL doctrinal gates and is
trained on personal-auto patterns that underperform on specialty BI's
low-volume, high-severity files.

Recovery does not need another opportunity-score. It needs a
**deterministic FL-aware pursue/route decision with a calibrated
recoverable basis, hard SOL/AF clocks, and a cross-stream conflict
check against Coverage and Liability before any demand goes out.**

## Why Recovery is distinct from Liability and Reserve

| Workflow | Question |
|---|---|
| Liability | Whose fault, and how much? |
| Reserve | How much do we owe and have paid? |
| Brief | What's the current state of the file? |
| **Recovery** | **Is there a viable third-party we can put dollars back from, on which doctrinal lane, against what clock, net of what fee drag and conflict risk?** |

Recovery is the only specialist that:

- Operates against **external counterparty state** — AF signatory status
  of the OTHER carrier, NHTSA recall posture of the VIN, §324.021
  vicarious-cap layer of the owner, omnibus-roster overlap. Liability /
  Reserve / Coverage all operate on the carrier's own file. Recovery
  looks outward.
- Has **three binary cliffs** with zero-dollar outcomes: HB 837 >50%
  bar, SOL expiration, anti-subrogation rule.
- Carries **four hard external clocks** that fire on counterparty events,
  not file age: 2-year SOL, AF 60-day post-dismissal refile, §768.76
  30-day collateral-source notice, §627.727(6) 30-day UM preservation.
- Crosses Coverage's surface via the **deny+subrogate interlock**
  (§624.155 + *Harvey v. GEICO*) — a bad-faith vector if denied
  first-party coverage AND pursued third-party recovery on the same loss.

## Architecture: extractor + policy engine + calculator + renderer

Same Software 1.0/3.0 split as Liability and Reserve, with a co-equal
diligence ledger. See [reserve-workflow.md](./reserve-workflow.md) and
[liability-workflow.md](./liability-workflow.md).

| Stage | Layer | Responsibility |
|---|---|---|
| **A. Extractor** | LLM (Software 3.0) | Reads FNOL packet, policy declarations, police/crash report (with §316.066 admissibility flag), repair/medical bill registers, EOBs, and any rental/fleet/loaner agreement. Classifies tortfeasor vehicle per §627.732(3) body-type + primary-use test. Extracts VIN, owner/operator split, omnibus-insured candidates, resident-relative roster, recall signal, EDR-availability signal, and any release/settlement language. Emits structured `RecoveryInputs` only — no pursue/abstain judgment |
| **B1. Policy engine** | Python (Software 1.0) | Applies 15 FL doctrines as step-function gates. Each gate emits pass/fail + cite + variance flag |
| **B2. Calculator** | Python (Software 1.0) | Deterministic math: recoverable basis = §768.0427-capped damages − PIP collateral source − made-whole shortfall, apportioned per Liability's fault percentages across layered targets. Net economics = gross recoverable × P(recovery) − fee drag − fee-shifting exposure. SOL + AF + §768.76 + §627.727(6) countdowns |
| **C. Diligence ledger** | Python template | Contemporaneous record: doctrinal gates evaluated, AF signatory check timestamp, anti-subrogation roster cross-reference, made-whole computation, decision rationale, sources cited. Discoverable under *Boecher/Ruiz*; doubles as defense exhibit |

> **Why not LLM-ranked target lists.** Vendor scoring tools (CCC
> Safekeep, Shift, Athenium) already commoditize identification scores.
> The Argos wedge is the layer above: deterministic policy gates +
> calibrated probability per layer + sourced evidence + Boecher-
> discoverable diligence trail. LLM-ranked targets repeat the false-
> positive vendor failure mode and bury the doctrinal gates inside
> opaque model judgment. Per [[policy-engine-first-then-llm-extraction]].
>
> **Why not extractor-only with LLM pursue/abstain.** The FL gates are
> step-functions with binary effects on recovery (>50% bar, SOL
> expiration, anti-subrogation, made-whole). Putting them in an LLM
> judgment call is the same trap that killed the v2 triage hybrid. Per
> [[karpathy-principles]] Software 1.0 — these are specifiable rules.
>
> **Why the diligence ledger is co-equal.** Same reasoning as Liability:
> *Allstate v. Ruiz* makes the claim file discoverable in bad-faith
> litigation; *Boecher* extends that to subro file work product. The
> ledger IS the defense exhibit.

## Components

| Component | Layer | Responsibility |
|---|---|---|
| `RecoveryInputs` | data | Pydantic model the extractor emits; policy engine + calculator consume |
| `RecoveryAssessment` | data | Output: recommendation, subrogation lane, layered targets, doctrinal gates, recoverable basis, net economics, forum routing, deadline calendar, preservation hold, diligence ledger, variance flags, cross-stream conflicts |
| `extract_recovery_inputs` | LLM workflow | Document + claim state → RecoveryInputs via structured tool_use |
| `apply_fl_recovery_doctrines` | Python | Inputs + ProgramConfig + upstream Liability + Reserve + Coverage → DoctrineResolution (regime, gates fired, variance flags) |
| `compute_recoverable_basis` | Python | Inputs + DoctrineResolution → recoverable basis + layered targets + net economics + deadline countdowns |
| `FL_DOCTRINE_REGISTRY_V1` | Python const | Versioned catalog of 15 named FL recovery doctrines |
| `AF_SIGNATORY_ROSTER_V1` | Python const | NAIC → AF signatory status (seed; updated per AF publication) |
| `RECOVERY_PROB_BANDS_V1` | Python const | Calibrated P(recovery) translation from Liability calibration per layer |
| `render_recovery_diligence_ledger` | Python template | Templated Ruiz/Boecher-discoverable ledger; byte-reproducible |
| `render_recovery_rationale` | Python template | Doctrine walk → recoverable basis math → layered targets → forum routing → deadlines |

## Triggers — when the workflow runs

Same event-driven pattern as Liability and Reserve. Calendar diary is
fallback safety net; the load-bearing triggers are counterparty events.

| Trigger | Fires when | Rationale |
|---|---|---|
| `FNOL_THIRD_PARTY_SIGNAL` | Reader extracts third-party indicators (other-vehicle involved, identified driver/owner, commercial-vehicle signal, product-defect/recall language) BEFORE Liability completes | Spoliation duty attaches at reasonable foreseeability. Emits **preservation hold + evidence checklist only** — does NOT produce pursue/abstain until Liability completes. Industry data: FNOL-stage subro identification is the single largest leverage point |
| `LIABILITY_SUBRO_REFERRAL_HINT` | Upstream Liability emits `subro_referral` hint (claimant ≥30% fault on claimant side, no recovery bar tripped, identifiable third-party tortfeasor) | Primary trigger. Liability has done the fault-apportionment work Recovery needs; Recovery never re-derives fault |
| `RESERVE_INDEMNITY_PAID` | Reserve transitions any indemnity component from outstanding to paid | Made-whole status is computable only once paid amounts are known. Re-evaluate Recovery on any paid-indemnity update |
| `EXTERNAL_COUNTERPARTY_EVENT` | Tortfeasor's liability carrier tenders settlement offer to insured (triggers §627.727(6) 30-day UM window); OR claimant serves §768.76 notice of tort action (triggers 30-day collateral-source clock); OR AF complaint dismissed (triggers 60-day refile window) | Three of the four hardest deadlines are triggered by external events, not file age. Missing any is silent dollar loss |
| `SOL_THRESHOLD_CROSSED` | SOL countdown crosses T-90, T-60, or T-30 against loss date per HB 837 statute version | Post-HB-837 2-year clock means examiners trained on 4 years routinely miss. Deterministic countdown, no LLM judgment |
| `SALVAGE_RELEASE_REQUEST` | Loss file flags salvage / total-loss release on a file with non-zero subro potential | *Valcin* / *Martino* spoliation exposure attaches if vehicle / EDR is released before preservation. Recovery blocks release until preservation steps documented |
| `CALENDAR_DIARY_90_DAY` | 90 days since last evaluation, no intervening event | Fallback adequacy review |

## `RecoveryInputs` schema (extractor output)

20 fields. Each anchors to source documents for per-field anchor-pair eval.

```python
class RecoveryInputs(BaseModel):
    # Statute-version gating
    loss_date: date                              # selects HB 837 SOL + §768.0427 version
    loss_state: Literal["FL", "other"]           # v1 is FL-only; other → abstain
    claim_filing_date: date | None               # §768.0427 paid-not-billed trigger (filing-based)

    # Tortfeasor counterparty state (external)
    tortfeasor_vehicle_classification: Literal[
        "private_passenger", "commercial", "taxicab", "unknown",
    ]
    tortfeasor_vehicle_vin: str | None           # NHTSA recall cross-reference
    tortfeasor_carrier_naic: str | None          # AF signatory check
    tortfeasor_policy_limits: PolicyLimits | None

    # Owner / operator structure
    owner_operator_split: OwnerOperatorSplit     # triggers §324.021 cap layer + neg-entrust
    owner_knowledge_indicators: list[OwnerKnowledgeIndicator]

    # Insured-side rosters (for anti-subrogation gate)
    named_insured_and_omnibus_roster: list[OmnibusPartyEntry]
    policy_subrogation_language: PolicySubrogationLanguage  # made-whole waiver text

    # Doctrinal lane classification
    subrogation_lane: Literal[
        "legal", "equitable", "contractual",
        "627_7405_pip_commercial", "768_76_collateral_source",
    ]

    # Recovery-extinguishing signals
    release_or_settlement_signals: list[ReleaseSettlementSignal]
    collateral_source_payments: list[CollateralSourcePayment]

    # Verbal-threshold evidence (§627.737)
    verbal_threshold_evidence: VerbalThresholdEvidence | None

    # Evidence preservation
    evidence_artifacts: EvidenceArtifacts         # vehicle status, EDR pulled, dashcam, etc.

    # External-event triggers (deadline anchors)
    external_event_triggers: ExternalEventTriggers | None

    # Apportionment context
    fabre_candidate_nonparties: list[FabreCandidate]

    # Contractual lanes
    rental_fleet_loaner_agreement: RentalFleetLoanerAgreement | None

    # Cross-stream
    coverage_denial_status: CoverageDenialStatus | None
```

### `OwnerOperatorSplit` — drives §324.021 cap layer

```python
class OwnerOperatorSplit(BaseModel):
    owner_id: str
    operator_id: str
    are_same: bool
    owner_type: Literal[
        "natural_person", "commercial_lessor_graves",
        "business_not_in_leasing", "self_insured_fleet",
    ]
```

### `OmnibusPartyEntry` — drives anti-subrogation gate (per-coverage-section)

```python
class OmnibusPartyEntry(BaseModel):
    name: str
    role: Literal["named", "permissive", "resident_relative", "additional"]
    coverage_section_paid_under: Literal[
        "liability", "collision", "comprehensive", "um", "pip", "medpay",
    ]
```

### `CollateralSourcePayment` — §768.76 + PIP basis stripping

```python
class CollateralSourcePayment(BaseModel):
    payer: str
    amount: Decimal
    type: Literal["pip", "medpay", "health", "employer", "workers_comp"]
    has_subro_right: bool
    notice_sent_date: date | None  # §768.76(7) 30-day clock anchor
```

## Policy engine — 15 FL doctrines

Each is a Python module with `applies_when(inputs, upstream) -> bool` +
`effect(state) -> state`. Mirrors the Liability policy engine pattern.

| Doctrine | Statute / Case | Effect |
|---|---|---|
| `hb837_modified_comparative_bar` | §768.81(6) HB 837 | Hard cliff: claimant >50% fault → abstain regardless of damages (post-3/24/2023 auto BI) |
| `hb837_negligence_sol` | §95.11(4)(a) HB 837 | Selector: pre-3/24/2023 loss = 4yr; on/after = 2yr. Clock from date of loss in legal subrogation (insured's shoes) |
| `anti_subrogation_rule` | FL common law; policy omnibus construction | Blocking gate, per coverage section. If tortfeasor target overlaps with named / omnibus / resident-relative roster under SAME coverage section as paid loss, abstain and route to Coverage |
| `made_whole_doctrine` | *Schonau v. GEICO*, 903 So. 2d 285 (Fla. 4th DCA 2005) | Conditional: limited-fund + insured not made whole + no contractual waiver → cannot subrogate OUT of insured's recovery. Freestanding direct claim against tortfeasor NOT blocked |
| `pip_subrogability_627_7405` | §627.7405; §627.732(3); *Amerisure v. State Farm*, 897 So. 2d 1287 (Fla. 2005) | PIP subro barred EXCEPT against commercial-motor-vehicle owners (taxicabs excluded). Classification per §627.732(3) body-type + primary-use, NOT weight |
| `um_preservation_627_727_6` | §627.727(6) | Hard 30-day gate: when tortfeasor's liability carrier offers settlement, UM carrier must consent OR advance the offer within 30 days. Miss = extinguished |
| `collateral_source_768_76` | §768.76(7) | Hard 30-day gate: on claimant's notice of tort action, collateral-source provider asserts reimbursement right in writing within 30 days or waives. Medicare / Medicaid / WC statutorily excluded from "collateral source" |
| `vicarious_cap_324_021` | §324.021(9)(b)3 | Cap: natural-person owner vicarious BI capped $100K/$300K + $50K PD, plus $500K econ-only if operator <$500K combined. Cap does NOT apply to direct-negligence (negligent entrustment) — uncapped separate layer |
| `joint_several_abolition_768_81_3` | §768.81(3) (2006); *Fabre v. Marin*, 623 So. 2d 1182 (Fla. 1993) | Apportionment: recovery from each defendant capped at that defendant's percentage of fault; non-party Fabre defendants on verdict form. Forces layered-target math, no deepest-pocket |
| `verbal_threshold_627_737` | §627.737 | BI tort right for non-economic damages: permanent injury / scarring / significant function loss. Economic damages above $10K PIP cap recoverable without threshold. Threshold does NOT apply if tortfeasor lacks PIP-compliant coverage |
| `paid_not_billed_768_0427` | §768.0427 (HB 837) | Damages-basis: past medicals capped at amounts actually paid (or LOP contracted, or 120% Medicare for uninsured). Strips billed-amount basis |
| `af_compulsory_jurisdiction` | AF Reference Guide; AF Rule 1-2; AF Article Second | Routing: both carriers signatory AND company-paid damages ≤$100K → compulsory arbitration. Non-signatory or over-cap → litigation or Special Forum. 60-day post-dismissal refile window |
| `spoliation_valcin_martino` | *Public Health Trust v. Valcin*, 507 So. 2d 596 (Fla. 1987); *Martino v. Wal-Mart*, 908 So. 2d 342 (Fla. 2005) | Preservation duty: subrogating carrier owes *Valcin* duty on vehicle / EDR / parts / photos. First-party spoliation tort abolished (*Martino*) but *Valcin* presumption + sanctions apply. Block salvage release until preservation documented |
| `deny_subrogate_interlock` | §624.155 HB 837; *Harvey v. GEICO*, 259 So. 3d 1 (Fla. 2018) | Cross-stream: Coverage denied AND Recovery pursuing same loss → senior review with mandatory made-whole accounting + denial rationale. HB 837 safe harbor (§624.155(4)) covers third-party tender only — does NOT extend to Recovery conduct |
| `step_into_shoes_defenses` | *Dade County School Bd. v. Radio Station WQBA*, 731 So. 2d 638 (Fla. 1999) | Subrogated carrier acquires no greater rights than insured. Pre-tender release / settlement / extinguishing act by insured against tortfeasor (with knowledge of perfected subro) defeats recovery |

## Calculator logic

**Recoverable basis** (deterministic):

```
recoverable_basis = (
    §768.0427_capped_economic_damages
    − sum(collateral_source_payments where type ∈ {pip, medicare, medicaid, wc})
    − made_whole_shortfall
)
```

**Layered apportionment** (per Liability's fault percentages):

| Layer | Anchor | Apportioned share |
|---|---|---|
| 1 | Operator policy | Operator fault % × recoverable_basis |
| 2 | §324.021(9)(b)3 owner vicarious cap layer | Owner-vicarious fault % × recoverable_basis, capped at $100K/$300K + $50K PD (+ conditional $500K econ) |
| 3 | Owner direct-negligence (negligent entrustment) | Owner-direct fault % × recoverable_basis, uncapped |
| 4 | Fabre non-parties | Per-party Fabre share × recoverable_basis |
| 5 | Product-defect / NHTSA recall | Per VIN cross-reference; routes to products evaluator |

**Net economics** (per layer):

```
net = gross_layer × P(recovery_per_layer)
      − fee_drag
      − expected_fee_shifting_exposure
```

Where:
- `P(recovery_per_layer)` = Liability calibration confidence × layer-specific
  scalar (operator policy: 0.85 baseline; §324.021 vicarious: 0.70;
  negligent-entrustment uncapped: 0.55; Fabre: 0.40; products: 0.30 —
  v1 seeds, tunable per ProgramConfig)
- `fee_drag` = AF $42 flat (if arbitration) | 25% vendor contingency (if
  outsourced) | $60-100/hr × 4-15 hrs internal blended cost (if in-house)
- `expected_fee_shifting_exposure` = §627.428 fee risk for pre-3/24/2023
  policies only; substantially repealed post-HB-837

## Variance zones (route around the calculator)

Nine zones. Calculator does NOT silently commit through any of these.

| Zone | Condition | Action |
|---|---|---|
| `comparative_fault_cliff_buffer` | Liability apportions claimant fault in [45%, 55%] band on post-3/24/2023 accrual | Surface band + evidence quality + probability of crossing. Senior review. A 5-point swing flips full-value → zero |
| `commercial_vehicle_classification_ambiguity` | Tortfeasor vehicle is pickup / van / utility with mixed personal+occupational use, OR rideshare / delivery, OR §627.732(3) test does not return clean classification | Calculator must NOT silently classify. Surface ambiguity with use evidence; require human classification before §627.7405 gate fires |
| `anti_subrogation_per_coverage_section` | Tortfeasor target appears on omnibus / permissive roster but identity of coverage section that paid is ambiguous | Do NOT auto-abstain. Collision-section subro against permissive driver is routinely allowed (permissive driver not "insured" under collision-section named-insured-only definition). Surface for per-section analysis |
| `sol_accrual_vs_filing_split` | Loss date within 30 days of 3/24/2023 OR retroactivity-litigation-affected category | Compute both statute versions, surface both clocks, route to legal review. Do NOT silently pick |
| `made_whole_with_partial_settlement` | Insured received partial recovery from another source AND policy lacks clean made-whole waiver | Surface made-whole shortfall computation; do NOT silently commit to pursuit-out-of-insured-recovery. Freestanding direct claim against tortfeasor remains a separate path |
| `deny_plus_subrogate` | Coverage status = denied AND Recovery would otherwise recommend pursue | Mandatory senior review with made-whole accounting + denial rationale. Calculator does NOT autonomously issue pursue |
| `af_signatory_unverifiable` | Tortfeasor carrier NAIC missing OR signatory roster lookup fails | Do NOT default to litigation or AF. Surface signatory-check failure; block forum routing until resolved |
| `products_liability_repose_boundary` | Loss vehicle in NHTSA recall AND manufacture-delivery date within 24 months of §95.031(2)(b) 12-year repose | Surface repose boundary explicitly; route to products evaluator before pursuing recall recovery layer |
| `release_or_pre_tender_settlement_detected` | Extractor flags release / settlement language between insured and tortfeasor | Pause pursuit; surface for legal review of *WQBA* step-into-shoes defenses + tortfeasor-knowledge-of-subrogation exception. Do NOT issue demand |

## `RecoveryAssessment` output

```python
class RecoveryAssessment(BaseModel):
    request_id: str
    reviewed_as_of: datetime

    # The recommendation
    recommendation: Literal[
        "pursue", "route_to_af", "route_to_litigation",
        "route_to_negotiated_demand", "abstain", "senior_review_required",
    ]
    subrogation_lane: SubrogationLane           # cite + defense-checklist anchor

    # Doctrinal gates evaluated
    doctrinal_gates: list[DoctrineGateResult]   # ordered; pass/fail + cite + evidence ref

    # Layered targets (ranked recovery layers)
    layered_targets: list[LayeredTarget]        # per-layer apportioned share, expected value, P(recovery), evidence completeness

    # Calculator outputs
    recoverable_basis: RecoverableBasis         # §768.0427-capped damages − PIP collateral − made-whole shortfall
    net_economics: NetEconomics                 # per-layer net after fee drag + fee-shifting exposure
    forum_routing: ForumRouting                 # AF / litigation / negotiated demand, with signatory check evidence

    # Hard external clocks
    deadline_calendar: DeadlineCalendar         # SOL drop-dead, AF refile, §768.76, §627.727(6), products repose

    # Evidence preservation
    preservation_hold: PreservationHold         # templated litigation-hold + storage-yard letter; blocks salvage release

    # Audit trail (co-equal with recommendation)
    diligence_ledger: RecoveryDiligenceLedger   # Boecher/Ruiz-discoverable
    rationale_text: str                         # byte-reproducible templated rationale

    # Routing surfaces
    variance_flags: list[VarianceFlag]
    cross_stream_conflicts: CrossStreamConflicts  # Coverage denial + Recovery pursuit interlock state
```

## Templated rationale

Same approach as Liability and Reserve: byte-reproducible interpolation,
not LLM voice.

```
RECOVERY EVALUATION — Claim {claim_id} | Eval #{eval_seq} | {eval_date} | Examiner: {examiner_id} | constants {VERSION}
TRIGGER: {trigger_name} ({trigger_event_date})

LOSS POSTURE:
  loss_date: {loss_date}  → SOL version: {sol_version} (pre/post 3/24/2023)
  loss_state: {loss_state}
  filing_date: {filing_date or "(not filed)"}  → §768.0427 trigger: {filing_trigger_status}
  subrogation_lane: {subrogation_lane}

UPSTREAM CONSUMPTION:
  Liability: insured_fault={pct}%, claimant_fault={pct}%, regime={regime}, bar_basis={bar_basis}
  Reserve: paid_indemnity=${paid}, outstanding=${outstanding} (per component)
  Coverage: status={coverage_status}, omnibus_roster=[{roster}]

DOCTRINAL GATES (evaluated in order):
{for each doctrine — name, pass/fail, cite, evidence_ref, variance_flag_if_any}

LAYERED TARGETS:
  Layer 1 — Operator policy: apportioned share = {pct}% × ${basis} = ${gross}; P(recovery) = {p}; net = ${net}
  Layer 2 — §324.021 vicarious cap: apportioned share = {pct}% × ${basis}, capped at ${cap}; net = ${net}
  Layer 3 — Negligent entrustment (uncapped): apportioned share = {pct}% × ${basis}; net = ${net}
  Layer 4 — Fabre non-parties: {per-party breakdown}
  Layer 5 — Product-defect / recall: {VIN cross-reference status}

RECOVERABLE BASIS:
  §768.0427 economic damages: ${capped}
  − PIP collateral source: ${pip}
  − Made-whole shortfall: ${shortfall}
  = Recoverable basis: ${basis}

NET ECONOMICS:
  Gross recoverable (sum of layers): ${gross}
  − Fee drag ({fee_model}): ${fee_drag}
  − Fee-shifting exposure: ${fee_shift}
  = Net: ${net}

FORUM ROUTING:
  AF signatory check: {tortfeasor_carrier_naic} → {signatory_status}
  Company-paid damages: ${paid} vs AF $100K cap: {within/over}
  Recommendation: {AF | litigation | negotiated_demand} (basis: {tier_basis})

DEADLINE CALENDAR:
  SOL drop-dead: {date} (T-{days})
  AF 60-day refile (if applicable): {date}
  §768.76 30-day collateral source: {date} (T-{days})
  §627.727(6) 30-day UM preservation: {date} (T-{days})
  Products repose (if applicable): {date}

PRESERVATION HOLD:
{templated litigation-hold + storage-yard preservation letter; vehicle / EDR / scene photos / witness statements / dashcam}

VARIANCE FLAGS ({flag_count} active):
{flag_list — each routes to a downstream action}

CROSS-STREAM CONFLICTS:
  Coverage denial + Recovery pursuit interlock: {status}
  Anti-subrogation overlap with omnibus class: {status}
  §627.426(2) cooperation-defense window: {status}

DILIGENCE LEDGER:
{full ledger render — gates evaluated with timestamps, signatory check, anti-subro cross-reference, made-whole computation, decision rationale}

RECOMMENDATION: {pursue | route_to_af | route_to_litigation | route_to_negotiated_demand | abstain | senior_review_required}
  Basis: {recommendation_basis}

DOWNSTREAM HANDOFFS:
  Brief: full RecoveryAssessment + diligence ledger
  Claim system: preservation_hold (blocks salvage release until ack)
  Runner: deadline_calendar with T-90/T-60/T-30 trigger thresholds
```

## Diligence ledger (the Boecher/Ruiz discoverable artifact)

Same role as Liability's ledger — co-equal output, not a side effect.
Plaintiff's bad-faith counsel reads this verbatim. *Allstate v. Boecher*
extends *Ruiz* discoverability to subro work product.

```python
class RecoveryDiligenceLedger(BaseModel):
    gates_evaluated: list[GateEvaluation]
        # for each doctrine: gate_id, result, cite, evidence_ref, timestamp
    af_signatory_check: AfSignatoryCheckRecord
        # naic, source, lookup_timestamp, result, fallback_action
    anti_subrogation_cross_reference: AntiSubroCrossReference
        # omnibus_roster_snapshot, per-coverage-section overlap analysis
    made_whole_computation: MadeWholeComputation
        # paid_to_insured, total_economic_loss, shortfall, waiver_status
    decision_rationale: str
    preservation_hold_status: PreservationHoldStatus
        # vehicle / EDR / scene / dashcam — each: requested_date, ack_date, status
    sources_cited: list[SourceCitation]
        # statute or case → claim_doc_id → quoted_span
    open_requests: list[OpenRequest]
    evidence_not_obtained: list[EvidenceNotObtained]
        # positive record of declined-or-blocked; reason documented
    supervisor_disagreement_record: list[Disagreement] | None
```

## Authority bands (defaults; CHA overrides)

Mirrors Liability/Reserve pattern.

| Range | Required approver | Rationale |
|---|---|---|
| `recommendation=pursue` AND net economics within examiner authority AND no variance flags | Examiner unilateral | Clear cases |
| `recommendation=route_to_af` AND signatory check passes | Examiner unilateral | Routine AF filing |
| Any variance flag active | Senior examiner + supervisor notice | Variance is the contract for non-silent escalation |
| `comparative_fault_cliff_buffer` OR `deny_plus_subrogate` OR `release_or_pre_tender_settlement_detected` | Supervisor + roundtable | Binary-outcome zones; step-function risk dominates dollar risk |
| `route_to_litigation` AND net > $100K | Manager + Large Loss Committee + coverage counsel | Litigation commit, bad-faith perimeter |

> **Critical:** authority is keyed off **net apportioned recoverable**
> (not gross damages, unlike Liability/Reserve). Recovery is the
> money-back surface; the ceiling is what we can actually get back, not
> what we're exposed to.

## Runner interactions

| Upstream / downstream | Data passed | Rationale |
|---|---|---|
| **← Liability** | Fault apportionment per party (operator, owner, claimant, Fabre non-parties), calibration confidence, `subro_referral` hint, identified tortfeasor roster | Recovery never re-derives fault |
| **← Reserve** | Paid + outstanding indemnity per component (BI / PD / PIP / MedPay / UM), insured's total economic loss | Made-whole status + recoverable basis require Reserve's paid figures |
| **← Coverage** | Status (granted / denied / under-investigation), denial rationale, omnibus + resident-relative rosters, made-whole policy-language extract, §627.426(2) cooperation-defense window | Anti-subrogation gate + deny+subrogate interlock require Coverage's roster + denial state |
| **→ Brief** | Full RecoveryAssessment including diligence ledger, gates with cites, deadline calendar, preservation hold | Brief renders the file-level narrative. Recovery's ledger doubles as defense exhibit and should be byte-reproducible inside Brief |
| **→ Claim system** | Preservation hold (litigation hold + storage-yard letter) blocking salvage release until ack | *Valcin* presumption attaches if carrier destroys evidence. Hold must propagate to the loss-side salvage workflow |
| **→ Runner (re-fire)** | Deadline calendar with T-90 / T-60 / T-30 trigger thresholds | Runner re-fires Recovery on threshold crossings. Deadlines are deterministic; no LLM judgment |

## Anti-patterns (explicit)

| Anti-pattern | Argos response |
|---|---|
| **Free-form LLM ranking of subro targets** | Architectural rejection. Calculator owns layered apportionment; doctrine engine owns gates. LLM is bounded to extraction only |
| **Treating Recovery as a Reserve sub-component** | Distinct workflow. Reserve answers "owe and paid"; Recovery answers "is there a viable third-party against what clock with what fee drag." Conflating buries SOL / AF / anti-subro gates inside Reserve math |
| **Pre-HB-837 fee-shifting heuristics in net economics** | §627.428 substantially repealed for post-3/24/2023 policies. Statute-version selector required |
| **Billed-amount recoverable basis** | §768.0427 caps presentable past medicals at paid (or LOP contracted, or 120% Medicare). Strip to paid before computation |
| **Demand letter before omnibus-insured cross-reference** | Anti-subrogation gate runs BEFORE any external communication. Hard gate |
| **Salvage release before preservation documented** | Recovery emits preservation hold; blocks release until ack. *Valcin* presumption defense |
| **AF as default forum without signatory check** | AF compels only signatories. Specialty TPA counterparty mix skews non-signatory. Mis-routing wastes filing window and burns SOL |
| **Treating §95.11(2)(b) 5-year contract SOL as a tort-claim lifeline** | Rental / fleet / loaner agreement does NOT convert BI carrier's tort subro into 5-year contract claim — carrier isn't a party. Only narrow cases (carrier-held reimbursement contracts, mortgagee subro) get 5yr clock |
| **Equitable-subrogation accrual-on-payment against the tortfeasor** | Legal subrogation against third-party tortfeasor inherits insured's tort SOL from date of loss. Single most common fatal-SOL error in carrier recovery workflows |
| **Auto-pursue on PIP files outside §627.7405 commercial-vehicle exception** | FL is a no-PIP-subro state outside the carve-out. Hard gate, abstain by default |
| **Inheriting third-party safe harbor (§624.155(4)) into Recovery conduct** | HB 837 safe harbor textually limited to liability-insurer tender. Recovery retains full §624.155 exposure including deny+subrogate, made-whole, anti-subrogation breach paths |
| **Single-target deepest-pocket demand** | §768.81(3) abolished J&S; recovery from each defendant capped at apportioned share. Layered apportionment is mathematically correct posture |

## Open questions (v1 cannot resolve without carrier data)

- **AF signatory roster maintenance** — v1 assumes maintained signatory list keyed by NAIC; mechanism for keeping it current as AF publishes updates is not specified
- **Calibrated probability of recovery per layer** — v1 inherits Liability's calibration but the translation into recovery probability (accounting for fee drag + counterparty solvency) is open. v1 ships seeded scalars; per-program tuning is roadmap
- **Owner-knowledge evidence pipeline for negligent entrustment** — DL status, prior crashes, prior comms, social context — categories are identified but source-of-truth mechanism for FL DL history is not specified
- **Specialty-TPA-scale empirical benchmarks** — public 16% / 27% / $15B / 200-day cycle-time numbers are industry-wide and personal-auto-weighted. What the comparable specialty-TPA-BI numbers are post-HB-837 is genuinely open; v1 should not assume they transfer
- **Pre-3/24/2023 loss handling** — v1 supports statute-version selector but does not model the active retroactivity-litigation split for §768.0427 procedural-vs-substantive application; route to legal review
- **Boecher discovery ledger format** — v1 specifies a diligence ledger but does not pin a schema that survives *Ruiz* work-product discovery in a downstream bad-faith action; needs counsel review before production use
- **Vendor / outside-counsel handoff packet shape** — at-intake screen and file packet handed to ISG / Eckert / Rathbone is the leverage point; v1 does not specify handoff schema; Brief may absorb this
- **Fee-drag model precision** — internal-handler blended cost is practitioner consensus, not sourced; v1 exposes this as ProgramConfig parameter, not hardcoded

## Realism caveats (what v1 explicitly does NOT model)

- **Workers' comp / GL / commercial property subro lines.** Multi-line specialty TPAs will request these; doctrine is line-specific and warrants its own specialist
- **Non-FL losses (cross-state).** v1 is FL-only. Cross-state (FL insured + OOS tortfeasor; OOS loss + FL policy) needs lane-and-SOL selection logic this spec does not cover; routes to abstain with rationale
- **UM subrogation outside §627.727(6).** Boecher does NOT bar FL UM subro, but the §627.727(6) 30-day window is the load-bearing gate; v1 models the gate, not other UM-subro nuances
- **Real-time AF signatory roster sync.** v1 ships seeded roster; production needs a refresh mechanism
- **Calibrated P(recovery) translation from Liability calibration.** v1 ships seed scalars per layer; per-program calibration against settled-outcome data is roadmap
- **Cross-stream Coverage roster real-time sync.** Anti-subrogation gate consumes Coverage's roster snapshot at evaluation time; concurrency between Coverage roster updates and Recovery gate-firing is not modeled. v1 ships snapshot semantics; race conditions are roadmap

## Evaluation plan

Per-component eval, same shape as Liability and Reserve.

| Layer | Method | Pass bar |
|---|---|---|
| Extractor | Per-field anchor-pair eval | >90% on `loss_date`, `tortfeasor_vehicle_classification`, `owner_operator_split`, `coverage_denial_status`; >85% on `evidence_artifacts` and `release_or_settlement_signals`; >95% on temporal fields and NAIC |
| Policy engine | Unit tests per doctrine, golden inputs | 100% golden match (pure rules) |
| Calculator | Unit tests on hand-built inputs | 100% golden match on recoverable basis + layered apportionment + net economics |
| Rationale + ledger | Byte-exact golden-file diff | 100% match |
| End-to-end | Recorded claim files with examiner-validated recoveries | Recommendation matches examiner-final on >75% of files; variance flags match examiner-noted markers on >80% |

## Why this earns the demo

Three things an insurance interviewer will probe — same three as Reserve
and Liability, distinct answers:

1. **Where does the LLM stop and Python start, and why there?** At
   `RecoveryInputs`. LLM owns extraction with quoted spans + tortfeasor-
   vehicle classification + release-language detection (Software 3.0 —
   bounded, gradable). Policy engine owns 15 FL doctrine gates as
   step-functions (Software 1.0). Calculator owns layered apportionment +
   recoverable basis math + deadline countdowns (Software 1.0). Rationale
   and ledger are templated — no LLM voice in legally-bearing artifacts.

2. **How do you defend the recovery decision against discovery and
   bad-faith litigation?** The diligence ledger IS the defense. Every
   gate evaluated has a cite + evidence ref + timestamp. AF signatory
   check is timestamped with source. Anti-subrogation cross-reference is
   per-coverage-section. Made-whole computation is shown. Evidence we
   didn't collect is positive record with reason. *Boecher / Ruiz*
   discoverability = ledger reads as adjuster notes, not LLM paraphrase.

3. **What do you NOT model, and how do you know it matters?** The
   realism-caveats list above. Each names the abstraction, why, and
   what carrier-specific signal would unlock it. Most important: we do
   not auto-commit. We do not score bad-faith risk on subro lapse. We
   do not pretend to know AF signatory status when the roster lookup
   fails. We surface the structured record; the human commits.
