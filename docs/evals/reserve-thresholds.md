---
tags:
  - project/argos
  - type/eval-threshold
  - status/living
created: 2026-06-02
updated: 2026-06-02
---

# Reserve eval — pass/fail criteria + thresholds

This doc is the contract. Every Reserve eval case in
`tests/evals/reserve/` is graded against the criteria below.

```bash
uv run pytest tests/evals/reserve/ -m eval -q
```

Excluded from the default test run (`addopts = "-m 'not eval'"`).
Inherits both policies from the eval-design decisions log entry
([2026-06-02 in DECISIONS.md](../DECISIONS.md)):

1. **Every Pydantic field the workflow emits is either GRADED or
   explicitly listed as NOT-GRADED under "Field coverage" below.**
2. **Numeric assertions default to tolerance = 0.** All Reserve math
   is `Decimal` arithmetic; there is no stochastic source.

## What we're grading

Reserve's output is **the dollar number that downstream surfaces act on.**
That's load-bearing for the entire system — writebacks, authority tiers,
notice triggers, and the cockpit all key off Reserve's `ReserveAnalysis`.

Specifically, Reserve emits:

- **Per-component bands** (indemnity always; ALAE when litigated): each with
  `recommended_outstanding_band` (p10/p50/p90) and `current_outstanding`.
- **Notice obligations triggered**: `reinsurer`, `client`, `excess_carrier`,
  with required-by-date.
- **Authority required level**: `handler`, `supervisor`, `manager`, `client`.
- **No-change-warranted** flag.
- **Templated rationale** (graded separately — see "Field coverage" below).
- **Calculator intermediates** (`CalculationContext`): specials breakdown,
  generals band, indemnity band, ALAE band, bad-faith markers, stair-step
  result, delta vs prior. These are exposed because downstream consumers
  (rationale rendering, future writebacks) depend on them — so they're
  graded too.

## Three layers of grading

### Layer 1 — LLM extractor (`ReserveInputs`)

**Out of scope for this vertical slice.** Same posture as Liability:
requires live-API spend and a labeled corpus. Target thresholds when built:

- Enumerated fields (`injury_bucket`, `venue_county`, `litigation_phase`,
  `medical_payer`): exact match ≥ **95%**.
- Continuous fields (specials `billed`/`paid`, wage `documented_to_date`,
  `insured_liability_pct`): within **±5%** on ≥ **90%** of cases.
- Temporal anchors (`accrual_date`, `filing_date`, `fnol_date`,
  `actual_notice_date`): exact match ≥ **99%** (these gate HB 837 + safe
  harbor — off-by-one days flip outcomes).
- Categorical lists (`catastrophic_indicators`, `mandatory_referral_categories`):
  exact-set match ≥ **95%**.

### Layer 2 — Deterministic calculator

**This is what the vertical slice grades.** Pass criteria per case, all
**exact match** (tolerance = 0):

- **Specials breakdown**: `paid_satisfied`, `lop_equivalent`, `wage_loss`, `total`.
- **Generals band**: `low`, `central`, `high` + the multiplier/venue/threshold
  inputs that produced them (for transparency, not just the answer).
- **Indemnity band**: `low`, `central`, `high`, `recommended`,
  `comparative_status` substring match.
- **ALAE band**: `p10`, `p50`, `p90` (cumulative through current phase).
- **Notice obligations**: exact set of `notice_type` values + each
  `required_by_date` (computed as `reviewed_as_of + notice_days`).
- **Authority required level**: exact tier.
- **No-change warranted**: bool.
- **Bad-faith markers**: exact set of marker strings (order-independent).
- **Stair-step result**: `flagged` bool + `revisions_in_window` count.
- **Delta vs prior**: `delta_amount`, `delta_pct`, `prior_basis`.

### Layer 3 — Adversarial / boundary probes

Red/green at every doctrinal seam: HB 837 filing-date edge, comparative-bar
strict-vs-loose comparison, variance-zone in/out, safe-harbor 90/91-day
flip, excess-carrier proximity exactly 50%, authority tier edges
(`recommended_total = examiner_authority` exactly), stair-step revision
count 2 vs 3.

## Field coverage (ReserveAnalysis + CalculationContext)

Per the eval-design policy: every emitted field must be GRADED, DEFERRED,
or NOT-GRADED-by-design (with reason).

### `ReserveAnalysis` (workflow output)

| Field | Status | How / why |
|---|---|---|
| `request_id` | NOT-GRADED-by-design | Pass-through input, not a calc output. |
| `reviewed_as_of` | NOT-GRADED-by-design | Pass-through input. |
| `per_component[].component` | GRADED | Asserted to be `indemnity` (always) + `ALAE` (litigated). |
| `per_component[].current_outstanding` | GRADED | Equals `indemnity.recommended` for indemnity row; `alae_band.p50` for ALAE row. |
| `per_component[].recommended_outstanding_band.{p10,p50,p90}` | GRADED | Per-case numeric assertions. |
| `per_component[].rationale` | NOT-GRADED-by-design | Free-text comparative status; covered by `tests/services/reserve/test_rationale.py`. |
| `per_component[].triggers_fired` | NOT-GRADED-by-design | v1 calculator never populates — SpecialistConfig integration deferred. Asserted empty as a smoke. |
| `per_component[].evidence_citations` | NOT-GRADED-by-design | Calculator emits a procedural citation pointing at `constants.py`, not a document-level cite; that's the contract for now. Asserted non-empty as a smoke. |
| `notice_obligations_triggered[].notice_type` | GRADED | Exact set per case. |
| `notice_obligations_triggered[].required_by_date` | GRADED | Computed as `reviewed_as_of + notice_days`; exact-match. |
| `notice_obligations_triggered[].probability` | NOT-GRADED-by-design | Always `1.0` in v1 (calculator-emitted); asserted as smoke. |
| `notice_obligations_triggered[].reasoning` | NOT-GRADED-by-design | Free text; not load-bearing for routing. |
| `notice_obligations_triggered[].evidence_citations` | NOT-GRADED-by-design | Procedural; same as per-component. |
| `authority_required_level` | GRADED | Exact tier per case. |
| `no_change_warranted` | GRADED | Boolean; one golden case + one boundary case. |
| `rationale` (top-level) | NOT-GRADED-by-design | Templated by `rationale.render_reserve_rationale`; covered separately. |

### `CalculationContext` intermediates (load-bearing for downstream)

| Field | Status | Why grade it |
|---|---|---|
| `specials.{paid_satisfied,lop_equivalent,wage_loss,total}` | GRADED | §768.0427 paid-vs-billed is the most-flipped piece of FL auto BI math; must be exact. |
| `generals.{low,central,high}` | GRADED | Downstream of multiplier × venue × threshold; bugs here cascade silently. |
| `generals.{multiplier_*,venue_factor,threshold_discount_pct}` | GRADED | Transparency — assert the factors, not just the product, so a regression names which dial moved. |
| `indemnity.{low,central,high,recommended}` | GRADED | The dollar number. |
| `indemnity.comparative_status` | GRADED-substring | Substring match for `barred` / `within recovery` / `pre-HB-837` / `HIGH VARIANCE`. |
| `alae_band.{p10,p50,p90}` | GRADED | Phase cumulative sums must be exact. |
| `bad_faith_markers.active[]` | GRADED | Exact-set match per case. |
| `bad_faith_markers.safe_harbor_status` | NOT-GRADED-by-design | Free text; the marker list captures the actionable signal. |
| `bad_faith_markers.crn_status` | NOT-GRADED-by-design | Same. |
| `stair_step.flagged` | GRADED | Boolean. |
| `stair_step.revisions_in_window` | GRADED | Count. |
| `stair_step.reason` | NOT-GRADED-by-design | Free text. |
| `delta_amount`, `delta_pct`, `prior_basis` | GRADED | Exact-match. |
| `authority_level`, `required_approver` | GRADED | Authority tier + named approver string. |
| `notice_obligations[]` | GRADED | Mirror of `ReserveAnalysis.notice_obligations_triggered`. |
| `current_phase` | GRADED | Pass-through but asserted as a smoke. |
| `inputs`, `program_config`, `reviewed_as_of` | NOT-GRADED-by-design | Pass-throughs. |

## Case coverage matrix (golden, n=15)

| ID | Scenario | What it grades |
|---|---|---|
| GC-01 | Minor soft-tissue clean (pre-suit, insured 100%, permanency present) | Baseline arithmetic: specials → generals (1.4×) → indemnity central, no ALAE, no notices, handler authority |
| GC-02 | Surgical recovering, permanency present, post-HB-837, depositions phase | Mid-tier multiplier (2.75×), full threshold, ALAE cumulative through depositions, no comparative bar |
| GC-03 | Catastrophic — TBI single indicator, post-HB-837 | Catastrophic branch: `CATASTROPHIC_BANDS_V1["tbi"]`, posted at limits, reinsurance + LLC notices, manager authority |
| GC-04 | Catastrophic — fatality + SCI (multiple indicators) | Max-band wins per p10/p50/p90 |
| GC-05 | Pre-HB-837 (accrual 2022) at claimant 60% fault | Pure comparative — NOT barred despite > 50% |
| GC-06 | Post-HB-837 at claimant 60% fault | §768.81 modified-51 bar fires; all bands = $0; `comparative_status` contains "barred" |
| GC-07 | Variance zone (insured 50%, post-HB-837) | `recommended` bumped to `(central + high) / 2`, status contains "HIGH VARIANCE" |
| GC-08 | Venue calibrator — Miami-Dade (1.20×) vs Duval (0.90×), same facts | Same specials/multiplier; generals scaled by venue factor |
| GC-09 | ALAE cumulative through `trial_prep` phase | Sum of pre_suit + answer + discovery + depo + disp + mediation + trial_prep budgets |
| GC-10 | Excess-carrier notice fires (proximity ≥ 50%, insured 80%+) | `excess_carrier` in notices; `required_by_date = reviewed_as_of + 15` |
| GC-11 | Reinsurance notice on $250K dollar threshold | `reinsurer` in notices; `required_by_date = reviewed_as_of + 30` |
| GC-12 | Authority routing — `handler`/`supervisor`/`manager`/`client` boundaries (4 sub-cases) | One case per tier; recommended_total set to fall in each band |
| GC-13 | §768.0427 paid-vs-billed: filed 2024, health-ins paid + LOP self-pay | `paid_satisfied` = paid for health-ins; `lop_equivalent` = billed for LOP |
| GC-14 | Bad-faith markers stack: policy-limits demand + represented + reserve ≥ 70% limits + clear liability | Exact marker set asserted |
| GC-15 | Stair-step pattern detected (3 small upward revisions <20% in 90 days) | `stair_step.flagged=True`, `revisions_in_window=3` |

## Adversarial / boundary probes (n=8)

| ID | Scenario | What it probes |
|---|---|---|
| ADV-01 | HB 837 filing boundary: `filing_date=2023-03-23` vs `2023-03-24`, claimant 60% | Day before → pre-HB-837 (no bar). Day of → §768.81 bar fires. |
| ADV-02 | Comparative bar edge: claimant exactly 50.00% | `>` 50, not `≥`. NO bar at 50.00; bar at 50.01. |
| ADV-03 | Variance zone edges: insured 40% (in), insured 39% (out), insured 55% (in), insured 56% (out) | Recommended bumps only in [40, 55]; outside falls back to central. |
| ADV-04 | Safe harbor: actual_notice + 89 days / 90 days / 91 days / 91 days no demand | Marker fires only when (elapsed > 90) AND policy-limits demand present. |
| ADV-05 | Excess-carrier proximity: 49.99% (no fire), 50.00% (fire); + insured liability 79% (no fire), 80% (fire) | Both conditions must hold; `>=` on both. |
| ADV-06 | Authority tier edges: `recommended_total = examiner_authority` exactly (handler), $1 over (supervisor) | `<=` on each tier upper bound. |
| ADV-07 | Stair-step edges: 2 revisions (not flagged), 3 revisions (flagged); revision delta exactly 20% (not "small") | Strict `<` on small-revision pct; min revisions = 3. |
| ADV-08 | Catastrophic + post-HB-837 + claimant 60% | Bar still fires on catastrophic branch — all bands $0 despite life-care-plan path. |

## What "passing the eval" means

- **Golden suite**: 15/15 green. Any red is a regression in the dollar
  number or a doctrinal classification — both block merge.
- **Adversarial suite**: 8/8 green. Any red is an off-by-one at a
  doctrinal seam.

## Drift detection

Same protocol as Liability: re-run on every prompt edit, model swap, or
calculator constant change. Any red previously green = block merge.
Constant changes (e.g., `MULTIPLIER_TABLE_V1 → V2`) require a versioned
constant + new golden cases pinned to the new table, not edits to V1.

## Known asterisks

- **Calibration** — same posture as Liability. The eval grades the
  calculator against the spec; it does NOT grade the spec against
  closed-claim reality. `MULTIPLIER_TABLE_V1`, `VENUE_GENERALS_MULTIPLIER_V1`,
  `DEFENSE_PHASE_BUDGETS_V1`, and `CATASTROPHIC_BANDS_V1` ship as seed
  defaults — every TPA customer overrides via `ProgramConfig` or
  programmatic constant swap. Calibration is per-customer, not in this slice.
- **LLM-extractor accuracy** — Layer 1 deferred until live-API budget is set.
- **`rationale` strings** — covered by `tests/services/reserve/test_rationale.py`,
  not here.
- **Liability `vicarious_cap_value` Gap #1** — does NOT resolve here.
  Reserve's `policy_limits.per_person` is a separate input, not derived
  from `ExposureCeiling.vicarious_cap_value`. Fix path remains: surface
  both per-person and per-occurrence figures on `ExposureCeiling`, OR
  document the per-occurrence semantics on the field. Tracked in
  `liability-thresholds.md` Open gaps Gap #1.

## Open gaps and revision path

| # | Gap | Severity | Trigger to revise | Action when triggered |
|---|---|---|---|---|
| 1 | Specials anchoring for `payer="unknown"` falls into LOP-equivalent bucket — silent semantic merger. | Low | A real claim hits with `unknown` payer AND nonzero billed/paid. | Either split `unknown` into its own bucket OR document the LOP-equivalent merge in the schema field doc; add a case that asserts the chosen behavior. |
| 2 | Notice `required_by_date` uses `reviewed_as_of`, not `accrual_date` or any document date — could be wrong on backdated reviews. | Low | First backdated review (eval-as-of differs from today) flips a notice deadline. | Either parameterize `notice_clock_anchor` OR document `reviewed_as_of` as the canonical anchor + add an adversarial case. |
| 3 | `_default_evidence_for(...)` returns the same `EvidenceCitation` shape for every notice/component (procedural cite, not document cite). | Medium | Cockpit / writeback consumer requires document-level citations. | Wire extractor-supplied citations through the calculator (already in spec, not yet implemented). |
| 4 | `program_config.settlement_authority` is read nowhere in the calculator. | Low | A case requires settlement-authority routing. | Either implement settlement-authority routing OR remove the field from `ProgramConfig`. |
| 5 | LLM-extractor (Layer 1) unevaled — prompt change can silently break specials/comparative/notices. | High | Live-API budget + labeled corpus exist. | Build Layer-1 harness per the thresholds above. |

### Eval-design rules inherited from Liability slice

- **Every emitted field is GRADED or DEFERRED.** See "Field coverage" — every
  field on `ReserveAnalysis` + `CalculationContext` has a row.
- **Default tolerance = 0.** All numeric assertions use exact `Decimal` equality.

## Run history

| Date | SHA | Golden | Adversarial | Notes |
|---|---|---|---|---|
| 2026-06-02 | 54a49f8 | 15/15 | 15/15 | Initial slice — green on third run. Fixed: GC-11 (LLC $250K trigger maps to `client`, not `excess_carrier`); ADV-01a (pre-HB-837 filings skip §768.0427 paid-anchor, use billed); ADV-03 (variance-zone edge probes moved to insured 55/56, since insured 40 crosses claimant 60% bar before variance can apply). 8 adversarial scenarios split into 15 sub-cases for per-side assertion. |
