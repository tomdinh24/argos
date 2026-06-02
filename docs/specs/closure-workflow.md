---
created: 2026-06-02
status: design
tags:
  - project/argos
  - type/spec
  - workflow/closure
aliases:
  - Closure spec
---

# Closure workflow — design spec

> **Status:** design. Schema, runtime, and runner integration not yet
> committed. Companion to the Recovery / Liability / Reserve specs.
> Source of truth for what ships: SYSTEM_ARCHITECTURE.md §0.1.

## §1 — Purpose

Closure is the sixth analytical workflow and the **terminating step** of
the claim lifecycle. It does not re-decide coverage, fault, reserve, or
recovery — those workflows commit their own decisions through their own
writebacks. Closure consumes those committed decisions and asks one
question: **"Is there anything left that prevents safe close of this
file?"**

The exposure surface is dense. Florida law makes the close moment the
single highest-leverage bad-faith trap in the auto BI claim lifecycle
(Berges totality-of-circumstances pulls the entire handling history
forward to the close decision; Ruiz strips work-product privilege over
every artifact created up to resolution). Federal MSP law imposes
double-damages exposure for closing a Medicare beneficiary file with
unresolved conditional payments. NAIC Model 902 and FL §626.884 make the
close action itself a regulator-auditable event.

The TPA examiner doing this manually today scans ~25 separate gates
across coverage / liability / reserve / recovery / liens / notices /
preservation / authority / records. Closure surfaces the gate
evaluations + a ready_to_close probability + the ranked blocking
defects, and routes the close-execution decision to the human.

## §2 — Architecture

Same five-stage shape as Recovery:

```
┌──────────────────────────────────────────────────────────────────────┐
│  1. LLM extractor → ClosureInputs                                    │
│     (claim state + committed upstream assessments → structured facts)│
├──────────────────────────────────────────────────────────────────────┤
│  2. Python policy engine → DoctrineResolution                        │
│     (~25 deterministic gates, FL + federal + program-config)         │
├──────────────────────────────────────────────────────────────────────┤
│  3. Python calculator → CalculationContext                           │
│     (ready_probability + ranked defects + remediation hints +        │
│      indemnity_status / defense_status bifurcation + retention plan) │
├──────────────────────────────────────────────────────────────────────┤
│  4. Diligence ledger (Boecher/Ruiz-discoverable, co-equal artifact)  │
├──────────────────────────────────────────────────────────────────────┤
│  5. Templated rationale (byte-reproducible audit string)             │
└──────────────────────────────────────────────────────────────────────┘
```

Only step 1 talks to an LLM. Steps 2–5 are reproducible byte-for-byte.

The Liability / Recovery implementation pattern is the template
(commits `9c0c1ea` + `c68df11` for Liability, `057260d` + `40f662b` for
Recovery).

## §3 — What Closure consumes

Closure is the only workflow with full upstream dependency on every other
analytical workflow. The extractor receives small typed snapshots, not
full schemas:

```python
ClosureUpstreamContext:
  coverage:    UpstreamCoverageSnapshotForClosure | None
  liability:   UpstreamLiabilitySnapshotForClosure | None
  reserve:     UpstreamReserveSnapshotForClosure | None
  recovery:    UpstreamRecoverySnapshotForClosure | None
  brief:       UpstreamBriefSnapshotForClosure | None
```

Each snapshot carries:

- **Coverage:** `decision_committed: bool`, `decision: granted | ror | denied`, `denial_letter_on_file: bool`, `denial_letter_cites_policy_provision: bool`, `denial_letter_cites_facts: bool`, `denial_letter_cites_law: bool`, `omnibus_roster`.
- **Liability:** `apportionment_committed: bool`, `regime_statute`, `insured_fault_pct`, `claimant_fault_pct`, `multi_claimant_occurrence: bool`, `competing_demands_exceed_aggregate: bool`, `first_actual_notice_date`, `powell_duty_potentially_triggered: bool`, `tender_made: bool`.
- **Reserve:** `paid_indemnity_by_component`, `outstanding_indemnity_by_component`, `total_paid`, `reserve_balance`, `pip_bill_ledger: list[PipBillStatus]`.
- **Recovery:** `pursuit_decision_committed: bool`, `decision: pursue | route_to_af | abstain | senior_review_required`, `subro_only_file_state: bool`.
- **Brief:** `open_obrs_with_legal_weight: int`, `open_obrs_informational: int`, `agent_action_count`, `claim_first_notice_date`.

## §4 — Gate taxonomy (research-grounded)

All gates are deterministic Booleans applied in `apply_fl_closure_gates`
(see §6). Each emits a `ClosureGateResult` for the diligence ledger.
Gates that fire produce a `BlockingDefect` with a `remediation_action`
hint.

Citations below are research-confirmed (`docs/research/closure-research/`
or inline in the policy engine). The 2026-06-02 6-dimensional research
workflow produced 54 confirmed findings across 5 dimensions; refuted
findings (Mid-Continent v. Basdeo as multi-claimant authority — wrong
case) are explicitly excluded.

### §4.1 — Tier A — Hard statutory gates (FL)

| # | Gate ID | Cite | Fires when |
|---|---|---|---|
| A1 | `coverage_decision_uncommitted` | §626.9541(1)(i)3 | Coverage workflow ran but `decision_committed == False` |
| A2 | `liability_apportionment_uncommitted` | Berges totality | Liability ran but adjuster never picked from distribution |
| A3 | `denial_letter_deficient` | §626.9541(1)(i)3 | Closure-without-payment + missing letter OR letter doesn't cite policy provision + facts + applicable law |
| A4 | `open_crn_within_cure_window` | §624.155(3); Ruiz | Live CRN on file; days_since_DFS_filing < 60; specific alleged violation not documented as cured |
| A5 | `third_party_safe_harbor_window_expiring_unotendered` | §624.155(4) HB 837 | Third-party BI; days_since_actual_notice > 90; evidence supports demand; no policy-limits tender on file |
| A6 | `multi_claimant_safe_harbor_not_invoked` | §624.155(6) HB 837; Farinas; Shuster | Multi-claimant + competing demands ≥ aggregate + no Rule 1.240 interpleader filed OR no binding arbitration submission within 90 days of competing-claims notice |
| A7 | `section_627_4137_affidavit_missing_or_stale` | §627.4137 | Claimant written request on file; no affidavit delivered within 30 days; OR affidavit not amended for aggregate-limit erosion from sibling claimants |
| A8 | `pip_exposure_not_drained` | §627.736(4)(b) | Any PIP bill on file neither paid nor formally denied within its own 30-day window |
| A9 | `section_627_4265_tender_window_violated` | §627.4265 | Settlement signed; days_since_agreement > 20; no check tendered. OR release executed; days_since_release > 20; no check tendered. 12% interest accruing. |
| A10 | `open_exposure_at_any_coverage_section` | Guidewire ClaimCenter Cloud API | Any individual exposure (BI/PD/MP/PIP/UM) not closed/denied/paid |
| A11 | `boston_old_colony_diligence_incomplete` | Boston Old Colony 386 So.2d 783 | At least one of: insured-not-notified-of-settlement-opportunity / no-excess-exposure-warning / investigation-incomplete / settlement-offer-not-considered / not-reasonable-prudent-person-decision |
| A12 | `powell_duty_unfulfilled` | Powell 584 So.2d 12 | Liability clear + damages plausibly exceed limits + no affirmative policy-limits offer made + no documented why-Powell-doesn't-apply memo |
| A13 | `harvey_communication_delay` | Harvey 259 So.3d 1 | Claimant communication received pre-close not answered AND/OR not relayed to insured |
| A14 | `macola_settlement_after_excess_trajectory` | Macola 953 So.2d 451 | Powell duty arguably triggered earlier + tender came only after suit/demand pressure + close memo treats payment as resolution |

### §4.2 — Tier B — Federal recovery (lien) gates

| # | Gate ID | Cite | Fires when |
|---|---|---|---|
| B1 | `medicare_msp_unresolved` | 42 USC §1395y(b)(2)+(3); 42 CFR §411.24(g)+(i); Verisk 2025 | Settlement ≥ $750 + Medicare beneficiary identified + no CMS Final Demand satisfied or active dispute on file. **Soft-close eligible** as `pending_medicare_final_demand` (60–180d post-TPOC) |
| B2 | `section_111_tpoc_unreported` | 42 USC §1395y(b)(8); CMP $1,000/day/claim | Settlement ≥ $750 + no Section 111 TPOC transmit-success log within 135 days |
| B3 | `florida_medicaid_lien_unresolved` | §409.910(11)(f); Gallardo v. Marstiller (2022) | Medicaid beneficiary identified + no FAHCA satisfaction letter OR §409.910(17)(b) DOAH reduction order. Gallardo: applies to past AND future medicals |
| B4 | `workers_comp_lien_unsatisfied` | §440.39(3)(a); Aetna v. Norman | Claimant in scope of employment + no §440.39 lien statement + waiver. BI vs UM allocation must be documented (lien excludes UM) |
| B5 | `erisa_self_funded_lien_unresolved` | McCutchen 569 US 88; Sereboff 547 US 356; 29 USC §1132(a)(3); §1144(b)(2)(B) | Self-funded ERISA plan identified + no plan-status confirmation + no written reimbursement agreement OR release without hold-harmless. §768.76 waiver does NOT apply to ERISA |
| B6 | `hospital_lien_unresolved` | Shands v. Mercury 97 So.3d 204 (Fla. 2012) | County-specific hospital lien recorded + no recorded release. **Must run county-of-treatment search** (Miami-Dade §25A, Broward §11½, etc.), not state — §713.50 struck down |
| B7 | `va_tricare_recovery_pending` | 38 USC §1729; 10 USC §1095; 32 CFR §199.12 | Veteran or active-duty/dependent claimant + no VA Form 10-7959f-1 or TRICARE HHC zero-balance letter |

### §4.3 — Tier C — Settlement-evidence gates

| # | Gate ID | Cite | Fires when |
|---|---|---|---|
| C1 | `missing_signed_release` | WQBA; §627.4265 (tender clock) | Settlement agreed but no signed release on file. Releases are required as both (a) bar-against-reopen and (b) §627.4265 tender-clock starter |
| C2 | `release_does_not_address_known_liens` | Sereboff 547 US 356 | Settlement with identified lien holders + release lacks hold-harmless / indemnity for known liens. ERISA §502(a)(3) exposure |
| C3 | `section_768_76_window_open` | §768.76(6)+(7); Mercury v. Emergency Physicians 182 So.3d 661 | Notice sent + 30-day waiver window not expired + no responding lien resolved |
| C4 | `outstanding_obr_with_legal_weight` | §627.4137; §627.736 | Open OutboundRequest tagged `legally_required` (sworn statement, EUO, reasonable-proof request). Informational OBRs NOT blocking |

### §4.4 — Tier D — Audit + authority gates

| # | Gate ID | Cite | Fires when |
|---|---|---|---|
| D1 | `agent_action_ledger_incomplete` | Ruiz 899 So.2d 1121 | Any workflow run on this claim does not have a corresponding `AgentAction` row with input hash + output + reasoning |
| D2 | `settlement_authority_exceeded` | Wallace Pierce (authority tied to reserve) | Examiner authority dollars < settlement amount + no documented escalation to next tier |
| D3 | `record_classification_missing` | FL OIR market conduct exam frame | Closure verdict not classified into one of OIR's three regulatory buckets: `closed_with_payment` / `closed_without_payment` / `reopened` |

### §4.5 — Tier E — Defense-track gate (bifurcation)

| # | Gate ID | Cite | Fires when |
|---|---|---|---|
| E1 | `open_defense_track_post_interpleader` | §624.155(6)(a) | Interpleader filed + limits deposited (indemnity sub-file closeable) BUT underlying tort actions vs insured unresolved. Single CLOSED flag for both = structurally non-compliant |

### §4.6 — Tier F — Preservation + retention gates

| # | Gate ID | Cite | Fires when |
|---|---|---|---|
| F1 | `spoliation_preservation_hold_pre_sol_expiry` | Valcin 507 So.2d 596; Martino 908 So.2d 342; §626.884; HIPAA §164.530(j)(2) | Auto-purge attempted on file with SOL not expired. `preservation_until` = max(DOL + 2yr-SOL, last_CMS_CPN + 6yr, last_PHI_auth + 6yr, regulatory_floor_3yr, TPA_contract_termination + 5yr) |

### §4.7 — Decoupling rule (NOT a closure-blocker)

- **Recovery is decoupled from close.** Per industry practice (Crawford
  & Co., Amaxx), open subrogation does NOT block close of the main
  claim. Closure emits `closed_with_open_recovery` as a distinct
  recommendation state when Recovery has committed to pursuit but main
  claim is otherwise close-ready.

## §5 — RecommendationLiteral

```python
Recommendation = Literal[
    "ready_to_close_with_payment",
    "ready_to_close_without_payment",
    "closed_with_open_recovery",
    "soft_close_pending_medicare_final_demand",
    "soft_close_pending_section_111_confirmation",
    "soft_close_pending_lien_release_letter",
    "soft_close_pending_release_execution",
    "blocked_by_defects",
    "requires_senior_review",
    "requires_legal_review",
    "recommend_reopen",
]
```

- The three `ready_to_close_*` literals correspond to the OIR
  regulatory buckets (auditable).
- The four `soft_close_*` literals describe the industry-standard
  "pending" states where main work is done but a known external clock
  hasn't run.
- `recommend_reopen` is the inverse path — emitted on a closed file
  when new evidence materially shifts an upstream workflow's output.

## §6 — Policy engine

`apply_fl_closure_gates(inputs, upstream, program_config, *, today)` —
pure function, no side effects, deterministic.

Returns `DoctrineResolution { gates, defects, variance_flags,
preservation_until_date, oir_classification }`.

Each gate evaluation produces:

```python
ClosureGateResult:
  gate_id: str
  result: Literal["pass", "fail", "n_a"]
  statute_or_case_cite: str
  evidence_ref: str         # e.g., "Coverage decision: granted committed 2026-05-30"
  defect_emitted: BlockingDefect | None
```

Variance flags route the recommendation toward `requires_senior_review`
or `requires_legal_review` regardless of gate-pass count. Examples:
multi-claimant + competing-limits ambiguity; ERISA plan identified but
funding-type undetermined; Medicare-eligibility check skipped.

## §7 — Calculator

`compute_closure(inputs, upstream, resolution, program_config, *,
reviewed_as_of) -> CalculationContext`.

Builds:

- `ready_probability` — calibrated band based on gate-pass count + Tier
  weighting. A single Tier A failure caps probability at 0.05; Tier B
  failures cap at 0.25; Tier C at 0.50; Tier D/E at 0.70.
- `blocking_defects` — ranked by Tier (A > B > C > D > E > F) then by
  remediation-effort estimate.
- `indemnity_status` and `defense_status` — bifurcated when E1 fires.
- `preservation_until_date` — the computed F1 floor.
- `oir_classification` — `closed_with_payment | closed_without_payment
  | reopened` (D3 source).
- `recommendation` — derived per the priority order:
  1. Any Tier A failure → `blocked_by_defects`
  2. Mandatory variance flag → `requires_senior_review` or
     `requires_legal_review`
  3. Any Tier B failure with soft-close eligibility → corresponding
     `soft_close_*`
  4. Otherwise classify into `ready_to_close_*` per OIR bucket, or
     `closed_with_open_recovery` if Recovery is in pursuit state.
- `authority_routing` — keyed off settlement amount (not gross
  exposure). Recovery is the money-out surface; Closure is the
  decision-commit surface, and the authority floor is per the program
  config's `closure_authority_dollars` ladder.

## §8 — Diligence ledger (Boecher/Ruiz-discoverable)

Co-equal artifact with the recommendation. Includes:

- `gates_evaluated: list[ClosureGateEvaluationLedgerEntry]` — every
  gate with timestamp + evidence ref.
- `lien_resolution_records: dict[LienKind, LienResolutionRecord]` —
  per-lien per-payer: Medicare, Medicaid, WC, ERISA, hospital, VA,
  TRICARE. Each carries: identified, notice_sent, response_status,
  release_letter_on_file, satisfaction_amount.
- `multi_claimant_global_settlement_artifacts: list[ArtifactCheck]` —
  per-claimant: global-tender-letter-sent, response-logged,
  priority-memo, insured-notice. (Per Farinas / Shuster / practitioner
  consensus.)
- `crn_state: CrnStateRecord | None` — open CRN identifier, DFS filing
  date, alleged statutory violations, cure status.
- `notice_delivery_audit: list[NoticeDeliveryRecord]` — §627.4137,
  §768.76, §626.9541 denial letter, §627.4265 tender — each with
  delivery date + content audit.
- `preservation_plan: PreservationPlan` — `preservation_until_date` +
  data sources held + Valcin-anchor.
- `record_classification: OirClassification` — D3.
- `decision_rationale: str` — composed from `recommendation` + tier
  decisions.

`render_closure_diligence_ledger(ledger)` produces a byte-reproducible
string.

## §9 — Templated rationale

`render_closure_rationale(ctx, ledger, *, claim_id, eval_seq,
trigger_name, trigger_event_date, examiner_id="system") -> str`.

Standard section order:

1. Header (`CLOSURE EVALUATION — Claim {claim_id} | Eval #{eval_seq} |
   {eval_date} | Examiner: {examiner_id} | constants {VERSION}`)
2. Trigger + lifecycle posture
3. Upstream consumption summary
4. Tier A gates (statutory, FL bad-faith)
5. Tier B gates (federal lien)
6. Tier C gates (release-evidence)
7. Tier D/E/F gates (audit / defense-track / preservation)
8. Indemnity vs defense status bifurcation
9. Lien-resolution ledger
10. Multi-claimant artifacts ledger
11. CRN state
12. Notice delivery audit
13. Preservation plan
14. OIR classification
15. Variance flags
16. Recommendation + authority routing
17. Downstream handoffs

VERSION is stamped in the header; constants live in
`services/closure/constants.py`.

## §10 — Program config additions

```python
class ProgramConfig:
    # ... existing ...
    closure_examiner_authority_dollars: Decimal
    closure_senior_examiner_authority_dollars: Decimal
    closure_supervisor_authority_dollars: Decimal
    closure_manager_authority_dollars: Decimal
    soft_close_max_days_pending_final_demand: int = 180  # CMS max
    soft_close_max_days_pending_section_111: int = 135
    powell_clear_liability_threshold_pct: int = 80  # insured fault ≥ X → Powell duty
    auto_close_enabled: bool = False  # ship OFF — manual approval default
```

## §11 — Action wire — `apply_closure_decision`

Symmetric to `apply_coverage_decision`. Flips `claim.closure_status`
into one of the OIR buckets + appends an `AgentAction` with:

- `action_type = "apply_closure_decision"`
- `inputs_hash` (the upstream snapshots used)
- `outputs` (the recommendation + classification)
- `reasoning_trace` (the rationale_text)
- `escalation_outcome` (e.g., "senior approved" / "auto-applied
  under threshold" / "human override")

Auto-apply boundary: surfacing the recommendation is auto; **executing
the close write is always human**. (Auto-close stays off in v1 even for
trivially-closable cases until calibration data accumulates.)

## §12 — Reopen path

Closure does not own a separate "reopen workflow." Reopen is the
existing pipeline running on a closed file:

1. Document Reader classifies any new doc on a closed claim.
2. If posture is non-null, Dispatcher routes to the relevant analytical
   workflow.
3. If any workflow output materially shifts (e.g., new Coverage
   decision, new Reserve magnitude), Closure auto-reruns.
4. Closure emits `recommend_reopen` when the new gate evaluation
   contradicts the closed-state classification.
5. Action wire `apply_reopen_decision` flips `claim.closure_status →
   reopened` and appends `AgentAction`. The same Claim ID is reused
   (matches ClaimCenter precedent).

Common reopen triggers (per research): CMS Final Demand (60–180d
post-TPOC), late-served lawsuit, late-emerging medical bills, ERISA
post-settlement reimbursement claim under §502(a)(3), Recovery
recoupment dispute, SIU/fraud finding post-close.

## §13 — Eval suite (planned)

Per [feedback_thresholds_before_measuring], thresholds before measuring:

- **Anchor-pair golden set:** ≥30 hand-labeled FL auto BI claims at
  varying close-readiness states (clean ready-to-close, multi-defect
  blocked, soft-close pending Medicare, requires-senior-review,
  recommend-reopen).
- **Gate-level eval:** Each of the 25+ gates exercised at least once
  positive and once negative across the golden set.
- **Recommendation alignment threshold:** 90% match with hand-labeled
  recommendation on the golden set before declaring production-ready.
- **Rationale byte-reproducibility:** 100% (deterministic by
  construction).
- **Diligence ledger completeness:** 100% — every fired gate has a
  ledger entry; every claim has a `lien_resolution_record` per
  identified lien holder.

## §14 — Code touched (planned)

- `src/argos/schemas/workflows/closure.py` — full refactor (replaces
  current minimal scaffold).
- `src/argos/services/closure/` — new package: `__init__.py`,
  `constants.py`, `policy_engine.py`, `closure_calculator.py`,
  `diligence_ledger.py`, `rationale.py`.
- `src/argos/workflows/closure.py` — new: extractor (`SYSTEM_PROMPT`,
  `_render_for_extractor`, `_closure_inputs_tool_schema`,
  `extract_closure_inputs`, `run_closure`).
- `src/argos/services/orchestrator/runner.py` — register
  `_run_closure_via_adapter` + `_load_closure_upstream`.
- `src/argos/services/orchestrator/dispatcher.py` — add `closure` to
  `POSTURE_TO_WORKFLOWS` for closure-trigger postures
  (last_obr_replied, recovery_committed, coverage_decision_committed,
  daily_closable_scan).
- `src/argos/services/orchestrator/closure_actions.py` — new:
  `apply_closure_decision`, `apply_reopen_decision`.
- `tests/schemas/workflows/test_smoke.py` — Closure smoke tests.
- `tests/services/closure/` — new: `_fixtures.py`, `test_constants.py`,
  `test_policy_engine.py`, `test_closure_calculator.py`,
  `test_ledger_and_rationale.py`.
- `tests/workflows/test_closure.py` — extractor + integration tests.

The Liability / Recovery pattern is the template (Liability commits
`9c0c1ea` + `c68df11`; Recovery commits `057260d` + `40f662b`).

## §15 — Open architectural questions deferred to implementation

- **CMS Section 111 mock vs live integration.** For v1, Closure uses an
  `inputs.section_111_tpoc_log` extracted from claim docs (transmit
  receipts). Live RRE integration deferred.
- **County hospital-lien database integration.** FL has no statewide
  registry; per-county searches are manual. For v1, Closure surfaces
  `hospital_lien_county_search_status: pending | searched_clean |
  searched_lien_found | not_applicable` and treats `pending` as a
  variance flag.
- **AgentAction backfill.** D1 (`agent_action_ledger_incomplete`) will
  initially fire on most files because AgentAction writes are not yet
  wired (see SYSTEM_ARCHITECTURE §0.1). For v1, D1 is a warning, not a
  block. Promoted to block after AgentAction writes ship.
- **Powell `clear_liability_threshold_pct` calibration.** Default 80%
  insured fault → Powell duty. Subject to calibration after the
  golden-set eval lands.

---

> Refuted findings explicitly excluded from this spec:
> - **Mid-Continent Cas. Co. v. Basdeo, 742 F. Supp. 2d 1293** — case
>   exists but is a declaratory-judgment coverage action, not a
>   multi-claimant settlement bad-faith authority. Use Farinas,
>   Shuster, Boston Old Colony, §624.155(6) instead.
> - **§626.989(6) SIU confidentiality** — cited language misplaced; do
>   not rely on this section verbatim for post-close SIU finding
>   procedures.
