---
tags:
  - project/argos
  - type/spec
  - status/design
created: 2026-06-01
updated: 2026-06-01
---

# Reserve workflow — design spec

> **Status:** design. Architecture is split into LLM extractor + Python
> calculator. Existing schema at `src/argos/schemas/workflows/reserve.py`
> will be refactored. Runtime is currently a stub
> (`_stub_workflow("reserve")` in the orchestrator runner). This doc
> defines what the real runtime does before we write it.

## The problem

Reserve adequacy is the carrier's load-bearing financial discipline.
Every open claim carries a number — the current best estimate of
total future payout — which drives reported losses, reinsurance
recoveries, authority workflows, and notice obligations. Stale
reserves cause sudden adverse development on quarterly reports,
late reinsurance recoveries, missed notice deadlines (which the
excess carrier later cites as a coverage defense), and bad-faith
exposure when plaintiff counsel proves the carrier knew facts
implying higher payout and didn't reserve for them.

Adjusters carry 80–150 open claims. Resetting reserve on one claim
properly is roughly an hour of cognitive work: re-read every doc
since last touch, recompute per-component expected outflow, justify
the delta to a supervisor, post the number with audit-trail
language a future bad-faith plaintiff cannot turn against the
carrier. Most adjusters don't have an hour per claim per re-eval
cycle, so reserves drift — which is exactly the
"stair-stepping" anti-pattern IRMI defines as a deficiency:
incrementally bumping reserves to cover bills as they arrive
instead of reserving to ultimate cost up front.

Reserve is the workflow that does the cognitive labor between
"new evidence landed" and "supervisor-ready reserve recommendation
with audit-trail rationale."

## Architecture: extractor + calculator split

> **Why split, not bundled.** Reserve math is deterministic. The LLM
> belongs at the document → structured-facts boundary; the math
> belongs in Python with versioned constants. Bundling them as one
> tool_use call is the same trap that killed the v2 triage hybrid:
> the LLM infers its own multiplier policy instead of executing the
> documented one, and the output is unauditable. See `/consult`
> 2026-06-01 entry for the full framework citation —
> [[karpathy-principles]] Software 1.0/2.0/3.0 + Verifiability,
> [[2026-05-30-nick-nisi-skills-lessons]] enforce-don't-instruct
> + replace-trust-with-evidence,
> [[applied-llms]] architecture > model.

Two stages:

1. **Extractor (LLM — Software 3.0)** — reads `SyntheticClaim`
   documents + `coverage_posture` + `ClaimContext` and emits a
   structured `ReserveInputs` Pydantic model. Bounded scope:
   classify injury bucket, surface specials, anchor permanency
   status, pull demand history, flag bad-faith markers. Anchor-pair
   eval grades per-field accuracy on a curated test set.

2. **Calculator (Python — Software 1.0)** — pure function:
   `ReserveInputs + ClaimContext + ProgramConfig → ReserveAnalysis`.
   Multiplier tables, phase budgets, authority bands, notice
   thresholds, and rationale-template interpolation all live as
   versioned Python constants. Unit-tested with hand-built inputs.

3. **Rationale string** — templated. Interpolated from extractor
   outputs and calculator intermediates. NOT LLM-generated. Audit
   trail is reproducible byte-for-byte from inputs.

**Cost of the split:** fluent narrative reasoning per claim is
lost. The rationale reads as structured audit-trail prose, not
adjuster-voice paragraphs. For legally-bearing outputs in a
bad-faith-litigated state, this is the right trade — but it is a
real trade, called out here so we don't backslide.

## Components

| Component | Layer | Responsibility |
|---|---|---|
| `ReserveInputs` schema | data | Pydantic model the extractor emits and the calculator consumes |
| `ReserveAnalysis` schema | data | Output: indemnity bands + ALAE + authority + rationale + markers |
| `extract_reserve_inputs` | LLM workflow | Document → ReserveInputs via structured tool_use |
| `compute_reserve` | Python | ReserveInputs + ProgramConfig → ReserveAnalysis |
| `MULTIPLIER_TABLE_V1` | Python const | Severity-tier multiplier bands, versioned |
| `NOTICE_THRESHOLDS_V1` | Python const | Excess / reinsurance / bad-faith markers, versioned |
| `PROGRAM_CONFIG` | Runtime config | Per-CHA authority bands, phase budgets, escalation thresholds (NOT hardcoded — loaded from carrier program registry) |
| `render_reserve_rationale` | Python template | Interpolated audit-trail string |

## Triggers — when the workflow runs

Re-eval is event-driven, not calendar-driven. The 90-day diary is a
fallback safety net.

| Trigger | Fires when | Rationale |
|---|---|---|
| `FNOL_INITIAL_RESERVE` | Coverage workflow returns `accepted` or `accepted_with_ROR`; Reserve runs immediately with FNOL-only facts | First reserve set fast (per CHA, typically within 24–72 hours of FNOL — exact cadence is program config). Marked low-confidence placeholder, not evaluated reserve. |
| `PIP_EXHAUSTION_OR_THRESHOLD_CROSS` | PIP medicals paid reach 80% of applicable cap ($2,500 without EMC / $10,000 with EMC), OR EMC determination flips | FL §627.736 mechanic. PIP exhaustion is the structural event that converts a no-fault file into BI exposure. |
| `REPRESENTATION_LETTER_RECEIVED` | Letter of representation from claimant counsel logged | Per IRC data, FL PIP litigation rate runs ~22% vs ~8% nationally. Representation elevates LAE and cycle-time materially. |
| `PERMANENCY_OPINION_OR_MMI` | Treating physician issues permanency opinion / impairment rating / MMI declaration; or significant scarring/disfigurement documented; or death | FL §627.737(2) verbal threshold: non-economic damages barred without permanency, scarring, or death. Gating fact for the entire generals component. |
| `SURGERY_SCHEDULED_OR_PERFORMED` | Surgical recommendation in records; surgery performed; or major diagnostic (MRI showing herniation, fracture confirmation) added | Largest discrete jump in specials; shifts severity tier. |
| `DEMAND_LETTER_RECEIVED` | Pre-suit demand received with supporting docs | Crystallizes claimant valuation; starts negotiation. |
| `POLICY_LIMITS_DEMAND_OR_TIME_DEMAND` | Demand at/above limits OR demand with a stated deadline OR §624.155(4) trigger | Starts FL HB 837 90-day safe-harbor clock. Failure to tender within 90 days with sufficient evidence forfeits the statutory bad-faith defense. Load-bearing for FL post-3/24/23 files. |
| `CRN_FILED` | Civil Remedy Notice filed with FL DFS | §624.155(3) 60-day cure window starts at DFS e-submission. Most controllable bad-faith mitigation lever; auto-flag with cure deadline countdown. |
| `SUIT_SERVED` | Complaint served on insured/carrier | Triggers defense-counsel engagement, opens ALAE reserve, starts phase budgeting. |
| `VENUE_CONFIRMED_OR_CONTESTED` | County of filing established or motion to transfer filed | Venue calibrates non-economic damages. Tri-county (Miami-Dade/Broward/Palm Beach) historically higher than Jacksonville/Panhandle. |
| `RESERVE_CROSSES_AUTHORITY_OR_NOTICE_BAND` | Recommended reserve crosses examiner / supervisor / carrier-escalation / treaty-reinsurance threshold | Each band is a contractually distinct compliance event. |
| `CALENDAR_DIARY_90_DAY` | 90 days since last evaluation with no event-driven re-eval | Fallback adequacy review. Runs in parallel with event-driven triggers, not as replacement. |
| `CATASTROPHIC_INJURY_FLAG` | Fatality, TBI, SCI, amputation, severe burns, multiple fractures, permanent total disability | Bypasses dollar-ladder entirely; categorical large-loss-committee trigger. |

## `ReserveInputs` schema (extractor output)

LLM extractor produces this Pydantic model. Each field is anchored
to specific source documents so anchor-pair eval can grade
extraction independently per field.

```python
class ReserveInputs(BaseModel):
    # Temporal anchors (HB 837 branching)
    accrual_date: date              # gates SOL + paid-vs-billed pre/post-3/24/23
    filing_date: Optional[date]     # §768.0427, §768.81 key off filing date
    fnol_date: date
    actual_notice_date: Optional[date]  # starts §624.155(4) 90-day clock

    # Venue / coverage context
    venue_county: Literal["miami_dade", "broward", "palm_beach",
                          "hillsborough", "orange", "duval",
                          "other_fl", "other_state"]
    policy_limits: PolicyLimits
    self_insured_retention: Optional[Decimal]

    # Liability
    claimant_count: int
    insured_liability_pct: Decimal      # post-3/24/23: >50% bars recovery
    tortfeasor_pip_compliant: bool      # §627.737(1) carve-out

    # PIP / threshold
    pip_status: PipStatus               # cap, paid, exhausted, EMC, 14-day
    permanency_status: PermanencyStatus # opinion, rating, MMI, scarring, fatality

    # Specials
    medical_specials: list[MedicalBill] # billed/paid/payer/LOP/DOS per bill
    wage_loss: WageLoss

    # Severity
    injury_bucket: Literal["minor_soft_tissue",
                           "moderate_ortho_non_surgical",
                           "surgical_recovering",
                           "severe_permanent",
                           "catastrophic"]
    catastrophic_indicators: list[Literal[
        "fatality", "tbi", "sci", "amputation",
        "severe_burn", "multiple_fracture",
        "permanent_total_disability"]]

    # Representation / litigation
    representation_status: RepStatus    # represented, demand, time-demand, limits-demand
    litigation_status: LitStatus        # phase, suit-served-date, defense-counsel
    crn_status: Optional[CrnStatus]     # filed-date, cure-deadline, alleged-violation

    # Reserve history (stair-step detector)
    prior_reserve_history: list[ReserveSnapshot]
```

**Fields the calculator needs but does NOT come from the
extractor:** `carrier_program_config` (loaded from program registry
at runtime — per-CHA authority bands, phase budgets, escalation
thresholds).

## Calculator constants

Versioned in Python. v1 anchors below — must be tuned per program
from carrier closed-claim data before production. Treated as seed
defaults, not industry-canonical numbers.

### Severity tiers (FL auto BI, post-HB 837)

| Tier | Frequency | Specials | Multiplier | Generals | Typical indemnity | Criteria |
|---|---|---|---|---|---|---|
| `minor_soft_tissue` | ~50–60% of files surviving PIP/verbal-threshold gate | $2.5K–$15K | 1.0–1.8× | $3K–$15K | $8K–$35K gross / $5K–$25K typical settlement post-paid-not-billed | Strain/sprain/whiplash, conservative care only, no MRI findings, no permanency, full clinical resolution |
| `moderate_ortho_non_surgical` | ~25–30% | $10K–$40K | 1.5–2.5× | $15K–$70K | $25K–$110K | Confirmed disc bulge/herniation, fracture without surgery, sustained PT >12 weeks, possible permanency at MMI |
| `surgical_recovering` | ~8–12% | $40K–$200K | 2.0–3.5× | $50K–$300K | $100K–$500K (often hits 10/20 FL minimums) | Surgical fixation, fusion, ORIF; documented permanency rating; MMI achieved |
| `severe_permanent` | ~3–5% | $100K–$500K + future care | 3.0–5.0× | $200K–$1.5M | $400K–$2M+, frequently limits-exhausting | Permanent significant impairment, multi-level fusion, RSD/CRPS, significant scarring |
| `catastrophic` | <1% | Routes to life-care-plan estimator (no multiplier) | N/A | Per-jurisdiction; FL still sees >$10M nuclear verdicts | $800K–$15M+; assumes limits + bad-faith overlay | Fatality, TBI moderate-severe, SCI, amputation, severe burns >20% BSA, permanent total disability |

> **Why these bands.** Carrier-side anchors run lower than
> plaintiff-bar 1.5–3× wisdom because FL §627.737 threshold is
> often contested on soft-tissue. NSCISC SCI lifetime cost
> ($1.8M–$5.4M+) anchors the catastrophic tier upper bound. All
> bands flagged as v1 defaults; tune per program from closed-claim
> loss-development data before production.

### ALAE / defense phase budgets

Per-phase practitioner estimates for routine FL auto BI defense.
**Not citable as industry standard** — must be tuned per program
from actual TPA billing data.

| Phase | Defense budget (per phase) |
|---|---|
| Pre-answer | $1.5K–$4K |
| Written discovery | $3K–$8K |
| Depositions | $5K–$15K |
| Dispositive motions | $4K–$10K |
| Mediation | $2K–$5K |
| Trial-ready | $20K–$60K+ |

Aggregate FL auto BI litigated-file ALAE commonly 20–50% of
indemnity per CAS guidance.

### Expert fees (FL auto BI, defense-side)

Per-expert anchors. Configurable; carriers run actual rate cards.

| Expert | Range |
|---|---|
| Biomechanical | $8K–$20K |
| Accident reconstruction | $5K–$15K |
| IME orthopedic | $1.5K–$4K |
| IME neurology | $2K–$5K |
| Life-care planner (catastrophic) | $10K–$30K |
| Vocational | $5K–$12K |
| Economist | $5K–$15K |

### ULAE

**Not allocated per claim.** Industry practice (Kittel / Wendy
Johnson count-based methods) allocates ULAE portfolio-level as
overhead. Argos does not load ULAE onto case reserves. If carrier
CHA requires per-claim ULAE for TPA fee structure (Jeng 1996), expose
a configurable flat 5–8% applied at report-roll, never at
case-reserve level. Default off.

### Notice thresholds

Per-treaty / per-program — **not hardcoded**.

| Trigger | Anchor (defaults; CHA overrides) |
|---|---|
| Reinsurance / excess notice | Fixed-dollar (commonly $100K–$500K, IRMI examples cite $250K), OR categorical injury triggers (fatality, amputation, SCI, TBI, blindness, severe burns, multiple fractures) regardless of dollars |
| Carrier Large Loss Committee | $250K–$500K |
| Bad-faith risk overlay | Activates on (a) reserve >70% of limits + clear liability, OR (b) §624.155(4) 90-day clock expired without tender + sufficient-evidence demand on file, OR (c) ≥3 bad-faith risk markers per Boston Old Colony / Berges / Harvey trilogy |

## Authority bands (defaults; CHA overrides)

Seeds loaded from `PROGRAM_CONFIG`. v1 defaults below — every
carrier customer overrides.

| Reserve range | Required approver | Rationale |
|---|---|---|
| <$5K | Junior examiner — unilateral | Specialty TPAs under fronted programs run tighter than standard market |
| $5K–$25K | Mid-level examiner — unilateral | Merlin practitioner anchor |
| $25K–$75K | Senior examiner / litigation specialist — unilateral; supervisor notice | Litigation-specialist cap; FL files run lower than national norms given litigation severity |
| $75K–$250K | Claims supervisor + roundtable | 2–5× examiner cap is industry pattern; roundtable diligence per Boston Old Colony |
| $250K–$500K | Claims manager / director + Large Loss Committee | IRMI $250K reinsurance-notice anchor mirrors internal LLC. Categorical catastrophic triggers route here regardless of dollars. |
| >$500K, limits-exposed, or bad-faith-flagged | Claims VP / CCO + coverage counsel + executive committee; ceding carrier notice if fronted | Bad-faith files require coverage counsel; Harvey-style diligence-of-record. |

## Rationale template (deterministic, interpolated)

The rationale string is generated by Python interpolation, not by
LLM. Audit trail is reproducible byte-for-byte from
`ReserveInputs` + calculator intermediates.

```
RESERVE EVALUATION — Claim {claim_id} | Eval #{eval_seq} | {eval_date} | Examiner: {examiner_id}
TRIGGER: {trigger_name} ({trigger_event_date})

LIABILITY: Insured {insured_liability_pct}% at fault (basis: {liability_basis_summary}).
FL §768.81 modified comparative (filing post-3/24/23): {comparative_status —
  'within recovery' | 'bar zone 40-55% — HIGH VARIANCE' | 'barred >50%'}.

PIP/THRESHOLD: PIP cap {pip_cap_applicable} ({emc_status}), paid {pip_paid_to_date}, {pip_exhaustion_status}.
§627.737 verbal threshold: {permanency_status —
  'satisfied via {permanency_evidence}'
  | 'not yet established — non-econ priced at {threshold_risk_discount}% probability'
  | 'barred absent permanency, non-econ at $0'
  | 'N/A — tortfeasor non-PIP-compliant per §627.737(1)'}.

SPECIALS (indemnity build):
  Medical (post-HB 837 §768.0427 paid-anchor where applicable): ${medical_specials_anchored}
    — Paid satisfied bills: ${paid_satisfied}
    — LOP/unsatisfied at insurance-equivalent: ${lop_equivalent}
  Wage loss documented: ${wage_loss}
  Property damage (handled separate workflow): excluded
  SPECIALS SUBTOTAL: ${specials_subtotal}

GENERALS:
  Severity tier: {injury_bucket} (criteria: {tier_criteria_match})
  Multiplier band: {mult_low}× — {mult_high}× specials
  Venue calibrator: {venue_county} ({venue_band})
  GENERALS LOW: ${generals_low} | CENTRAL: ${generals_central} | HIGH: ${generals_high}

INDEMNITY RESERVE (gross × liability%):
  Low: ${indem_low} | Central: ${indem_central} | High: ${indem_high}
  Recommended posting: ${indem_recommended} (rationale: {posting_rationale})

ALAE: {alae_status —
  'not opened (pre-suit)'
  | 'opened at suit served, phase={current_phase}, budget=${phase_budget}'}
ULAE: not allocated per-claim per industry practice; portfolio-level overhead.

DELTA FROM PRIOR: {delta_amount} ({delta_pct}%). Prior basis: {prior_basis}.
Stair-step check: {stair_step_status —
  'OK — driven by new evidence: {new_evidence}'
  | 'FLAG — small revision without new facts'}.

AUTHORITY:
  Reserve ${reserve_amount} vs examiner authority ${examiner_authority}: {authority_status}
  Required approver: {required_approver}
  Reinsurance/excess notice: {reins_notice_status —
    'not triggered'
    | 'TRIGGERED at ${trigger_value} — notice due within {notice_window} days'}

BAD-FAITH RISK MARKERS ({marker_count} active):
  {marker_list with status per marker}
  §624.155(4) 90-day safe harbor clock: {days_since_actual_notice} / 90 days elapsed.
    Tender feasibility: {tender_status}.
  §624.155(3) CRN: {crn_status —
    'none filed'
    | 'filed {crn_filed_date}, cure deadline {cure_deadline}, days remaining: {days_to_cure}'}

NEXT RE-EVAL: {next_trigger_or_diary_date} ({next_trigger_reason})
EVIDENCE ATTACHED: {evidence_doc_list with citation ids}
```

## Re-evaluation actions per trigger

| Event | Action |
|---|---|
| PIP exhausted / EMC flipped | Re-extract `pip_status`; if exhausted with treatment ongoing, escalate severity-tier candidacy; reopen BI reserve if previously $0 |
| Representation letter received | Set `represented=true`; tier up LAE expectation; check FL bad-faith setup pattern (short window + limits proximity); diary tightened to 30-day |
| Demand letter received | Extract demand amount / deadline / supporting-evidence sufficiency; if policy-limits demand with sufficient evidence, start §624.155(4) 90-day clock; surface tender-feasibility analysis |
| Policy-limits / time-demand | Auto-escalate to supervisor + coverage counsel; document Boston Old Colony four-duty checklist; calculate `days_to_safe_harbor_expiry` |
| CRN filed | Hard escalation; compute `cure_deadline = filed_date + 60`; flag if <14 days remaining without tender plan; route to highest-priority workflow |
| Permanency / MMI declared | Re-extract `permanency_status`; unlock non-economic component (was discounted by threshold-risk probability); recompute generals at full multiplier |
| Surgery scheduled / performed | Bump `injury_bucket` candidacy to `surgical_recovering` or higher; re-extract `medical_specials`; surface updated multiplier band |
| Suit served | Open ALAE reserve; assign defense counsel; set `litigation_phase=answer`; load phase budget; recompute incurred (indemnity + ALAE) against authority bands |
| IME report received | Re-extract `permanency_status` if changed; document delta from treating-physician opinion in rationale |
| Deposition transcript added | Re-evaluate `liability_pct` if insured/claimant depo changes facts; re-evaluate damages if treating depo affects permanency/causation |
| Mediation scheduled / completed | Pre-mediation: refresh reserve to defense settlement-authority position. Post-mediation: capture demand/offer history and outcome for next-eval anchor |
| Large new medical bill (>20% of running specials or single >$15K) | Re-extract specials; check paid-vs-billed handling under §768.0427; flag if LOP relationship added |
| Venue confirmed / transferred | Apply venue calibrator to generals; document reserve swing if venue changed materially |
| 90-day calendar diary, no intervening event | Lightweight re-eval; PRISM-style adequacy check; document "no change — facts stable" if so, to preserve audit trail |
| Reserve crosses authority / escalation / reinsurance trigger | Generate escalation notice, supervisor referral, or reinsurance notice draft; reserve change held in pending until approver confirms |
| Prior reserves show 3+ small upward revisions in 90 days without new evidence | Auto-flag stair-step pattern; require supervisor sign-off on next revision; document defensibility risk in rationale |

## Anti-patterns (explicit)

| Anti-pattern | Argos response |
|---|---|
| **Stair-stepping** (incremental bumps as bills arrive) | `prior_reserve_history` field + stair-step detector. Flag 3+ small revisions in 90 days without new evidence. Per IRMI: "the ultimate cost is the amount that should be shown on the reserves at all times." |
| **LLM emits final dollar number** | Architectural rejection. Calculator owns all math. |
| **Reserve overlay for bad-faith without sign-off** | Markers are surfaced; no separate overlay reserve is auto-posted. Carrier instruction required. |
| **Single-multiplier across all soft-tissue claims** | Per-tier band; extractor assigns discrete bucket; calculator selects multiplier band. |
| **Skipping permanency threshold pricing** | Pre-MMI files discount non-econ by threshold-risk probability rather than zeroing or assuming full multiplier. |

## Open questions (v1 cannot resolve without carrier data)

- **Severity tier dollar bands** are practitioner-anchored estimates. Tom must validate v1 anchors against actual TPA closed-claim data before showing to any insurance interviewer with Colossus / ClaimIQ calibration access.
- **Initial reserve cadence** (24–72hr / 5–15 day) is CHA-specific. Default to a program config parameter.
- **Carrier-internal Large Loss Committee thresholds** are not publicly published. $250K/$500K anchors inferred from IRMI reinsurance examples, not from a named LLC SOP.
- **FL venue multipliers** on non-economic damages are not publicly quantified. Directional ranking (tri-county > I-4 > N. FL) is supported; no auditable multiplier exists publicly. Derive from carrier loss-development data per venue.
- **Phase-budget dollar ranges** are practitioner estimates, not citable.
- **HB 837 §768.0427 pre/post split:** whether paid-vs-billed applies to causes accruing pre-3/24/23 but filed post-3/24/23 is litigated in FL DCAs with mixed rulings. Calculator must support both `filing_date` and `accrual_date` and surface the ambiguity rather than picking one.
- **§624.155(4) "sufficient evidence to support the amount"** — gating phrase for starting the 90-day safe harbor — is being litigated. Flag the clock as "arguably running" when supporting evidence is partial; do not assert a definitive start.
- **Reinsurance notice triggers** vary widely per treaty. IRMI $250K + categorical-injury pattern is one example, not industry standard.
- **Separate bad-faith reserve overlay** practice varies by carrier. Argos v1 surfaces markers + exposure analysis; does not post a separate overlay reserve without carrier instruction.

## Realism caveats (what v1 explicitly does not model)

- Single-claimant only. Multi-claimant interpleader under §624.155 HB 837 safe harbor is flagged but not modeled.
- FL-only. SOL, comparative fault, paid-vs-billed, verbal threshold, and bad-faith mechanics hardcode FL law.
- At-fault BI only. UIM/UM, PIP (no-fault), property damage, and PD subrogation are out of scope.
- No subrogation recovery against indemnity. Reserve is gross, not net of expected subro.
- No coverage disputes. Assumes Coverage workflow has resolved `coverage_posture` before Reserve runs. ROR / declaratory-action candidates out of scope.
- Discrete severity tier, not continuous Colossus / ClaimIQ scoring. Argos trades depth for auditability — a stated product choice.
- Severity tier dollar bands are practitioner-anchored, not carrier-closed-claim-derived. Tune per program before production.
- No time-value-of-money on long-tail catastrophic. Lump-sum nominal posting; structured-settlement / PV math out of scope.
- ULAE intentionally not allocated per claim.
- Phase-based ALAE budgets are seed defaults; carrier-config overrideable.
- Authority bands ship with placeholders; per-carrier override expected.
- Bad-faith risk markers are a structured checklist derived from the FL trilogy + §624.155 + HB 837, not a published TPA SOP. They surface exposure; they do not auto-post overlay reserve.
- Stair-step detector is a defensibility check, not an actuarial control.
- No reinsurance treaty mechanics beyond single notice-trigger. Cession, treaty layers, reinstatement out of scope.

## Evaluation plan

Anchor-pair eval grades the extractor field-by-field on a curated
FL auto BI test set. Calculator is unit-tested on hand-built
`ReserveInputs` with expected `ReserveAnalysis` outputs. Rationale
template is golden-file tested. No LLM judge on the calculator —
the math either matches the golden file or it doesn't.

| Layer | Eval method | Pass bar |
|---|---|---|
| Extractor | Per-field accuracy on anchor pairs | >90% on `injury_bucket`, `permanency_status`, `pip_status`, `crn_status`; >80% on `medical_specials` (long-tail extraction); >95% on temporal fields (`accrual_date`, `filing_date`, `fnol_date`) |
| Calculator | Unit tests on hand-built inputs | 100% golden match |
| Rationale | Byte-exact golden-file diff | 100% match |
| End-to-end | Workflow over recorded claim files with examiner-validated reserves | Reserve recommendation within ±20% of examiner-set reserve on >70% of files; flagged exposure markers match examiner-noted markers on >80% |

## Why this earns the demo

Three things an insurance interviewer will probe:

1. **Where does the LLM stop and Python start, and why there?** Answer: at `ReserveInputs`. LLM owns extraction (Software 3.0 territory — bounded, gradable, model-swappable). Calculator owns math (Software 1.0 — versioned, unit-testable, byte-reproducible). Rationale is templated — no LLM voice in legally-bearing audit trail.

2. **How do you defend the numbers against a bad-faith plaintiff?** Answer: rationale interpolation is byte-reproducible from inputs. Multiplier band is in versioned Python. Authority bands fired correctly per CHA. CRN cure deadline tracked. Stair-step detector caught the pattern. Every number traces to a formula + a cited input.

3. **What do you NOT model, and how do you know it matters?** Answer: the realism caveats list above. Each one names the abstraction, why it's abstracted, and what carrier-specific signal would unlock modeling it.
