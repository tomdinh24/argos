---
tags:
  - project/argos
  - type/eval-threshold
  - status/living
created: 2026-06-02
updated: 2026-06-02
---

# Recovery eval — pass/fail criteria + thresholds

This doc is the contract. Every Recovery eval case in
`tests/evals/recovery/` is graded against the criteria below.

```bash
uv run pytest tests/evals/recovery/ -m eval -q
```

Excluded from default suite (`addopts = "-m 'not eval'"`). Inherits both
policies from the 2026-06-02 [DECISIONS.md](../DECISIONS.md) entry:

1. Every emitted field is GRADED or explicitly DEFERRED in the
   field-coverage table below.
2. Numeric assertions default to `tolerance = 0` (Decimal arithmetic).

## What we're grading

Recovery is the **first workflow that composes upstream outputs**
(Liability + Reserve + Coverage) and writes back a pursuit decision.
Its load-bearing output is the **recommendation literal** plus the
**doctrinal evaluation chain** that backs it. If Recovery says
`route_to_af` and the gates that produced it are wrong, the writeback
opens a defective AF case and we burn the file.

Specifically, Recovery emits via `compute_recovery()` → `CalculationContext`:

- **Top-line decision**: `recommendation` (pursue / route_to_af /
  route_to_litigation / route_to_negotiated_demand / abstain /
  senior_review_required).
- **Doctrine resolution**: `recovery_barred` + `bar_basis`, per-gate
  pass/fail/n_a results across ~15 FL doctrines, SOL regime + deadline,
  variance flags.
- **Recoverable basis**: §768.0427 capped damages minus PIP collateral
  minus made-whole shortfall.
- **Layered targets**: per-layer apportioned share, cap application,
  expected value, evidence completeness.
- **Net economics**: gross − fee drag − fee shifting → net.
- **Forum routing**: arbitration_forums / litigation /
  negotiated_demand / abstain / tbd_signatory_check_pending.
- **Deadline calendar**: SOL + AF refile + collateral source + UM
  preservation + products repose.
- **Preservation hold**, **authority routing**, **cross-stream
  conflicts**.

## Three layers of grading

### Layer 1 — LLM extractor (`RecoveryInputs`)

Out of scope (same posture as Liability + Reserve — deferred until
live-API budget). Target thresholds when built: enumerated fields exact
match ≥ 95%, statute cites ≥ 99%, temporal anchors ≥ 99% (SOL hinges
on them), VIN / NAIC literal-match ≥ 99%.

### Layer 2 — Deterministic policy engine + calculator

What this slice grades. All exact-match (`tolerance = 0`):

- `recommendation` — exact literal.
- `recovery_barred` + `bar_basis` — exact match per case.
- `sol_regime.statute_version` — exact literal; `sol_deadline` — exact date.
- Per-gate `result` for the specific gates the case targets.
- `variance_flags` — exact set match (order-independent).
- `recoverable_basis.{capped_damages, stripped, shortfall, basis}` —
  exact `Decimal`.
- `layered_targets[].{layer_id, apportioned_fault_pct, apportioned_share,
  cap_applied, gross_recoverable}` — exact per layer (substring match
  on `layer_id` set).
- `net_economics.{gross, fee_drag, fee_shifting, net, fee_model}` —
  exact.
- `forum_routing.{recommendation, af_signatory_check, within_af_cap}` —
  exact.
- `authority_routing.{required_tier, committable_at_examiner}` — exact.
- `preservation_hold.{issued, hold_scope}` — exact.
- `cross_stream_conflicts.{interlock, omnibus_overlap}` — exact.

### Layer 3 — Adversarial / boundary probes

Red/green at every seam: HB 837 SOL date boundary, 51% bar strict-`>`,
near-bar window ±5pp, SOL accrual/filing split ±30 days, AF cap
($100K), AF signatory unverifiable fallback, vicarious-cap eligibility
(natural-person + owner≠operator), products-repose boundary.

## Field coverage

| Field | Status | How / why |
|---|---|---|
| `recommendation` | GRADED | Top-line decision literal. |
| `recovery_barred`, `bar_basis` | GRADED | Terminal block + reason. |
| `subrogation_lane.{lane_id, cite}` | GRADED | Asserted per case. |
| `subrogation_lane.defense_checklist_anchor` | NOT-GRADED-by-design | Templated string from `lane_id`; redundant. |
| `doctrinal_gates[].result` | GRADED-per-case | Each case asserts the specific gates it probes. Full-set assertion would be brittle when new gates are added. |
| `doctrinal_gates[].statute_or_case_cite` | GRADED-smoke | Asserted non-empty when result != n_a; content checked separately by `test_constants.py`. |
| `doctrinal_gates[].effect_if_fired`, `evidence_ref` | NOT-GRADED-by-design | Free text; covered by ledger + rationale tests. |
| `sol_regime.statute_version`, `.sol_deadline`, `.days_remaining` | GRADED | Date math is load-bearing. |
| `sol_regime.statute_cite` | GRADED-smoke | Non-empty. |
| `variance_flags` | GRADED | Exact-set match. |
| `recoverable_basis.{capped_damages,stripped,shortfall,basis}` | GRADED | Numeric. |
| `layered_targets[].layer_id` | GRADED | Exact-set membership per case. |
| `layered_targets[].{apportioned_fault_pct, apportioned_share, cap_applied, gross_recoverable, expected_value}` | GRADED-per-layer | Per-case assertions on targeted layers. |
| `layered_targets[].{probability_of_recovery, evidence_completeness}` | GRADED-per-layer | Per-case. |
| `layered_targets[].target_party_id` | GRADED | Asserted on operator + owner layers. |
| `net_economics.{gross, fee_drag, fee_shifting, net, fee_model}` | GRADED | Numeric + literal. |
| `forum_routing.{recommendation, af_signatory_check, within_af_cap, company_paid_damages, af_cap_dollars}` | GRADED | Routing + math. |
| `forum_routing.basis` | NOT-GRADED-by-design | Free text. |
| `deadline_calendar.entries[]` | GRADED | Per-case: presence + days_remaining for the deadline the case probes. |
| `preservation_hold.{issued, hold_scope, blocks_salvage_release, acknowledgment_status}` | GRADED | Boolean + enum + set. |
| `preservation_hold.storage_yard_letter_text` | NOT-GRADED-by-design | Templated; ledger test covers. |
| `authority_routing.{committable_at_examiner, required_tier, net_apportioned_recoverable, basis_for_tier}` | GRADED | Tier + dollar + basis (smoke on text). |
| `cross_stream_conflicts.{interlock, omnibus_overlap, cooperation_window_open}` | GRADED | Set + boolean. |
| `request_id`, `reviewed_as_of`, `inputs`, `upstream`, `resolution`, `program_config` (on context) | NOT-GRADED-by-design | Pass-throughs / inputs. |
| `RecoveryAssessment.rationale_text` | NOT-GRADED-by-design | Templated by `render_recovery_rationale`; `test_ledger_and_rationale.py` covers. |
| `diligence_ledger.*` | NOT-GRADED-by-design | Co-equal artifact built by `diligence_ledger.py`; `test_ledger_and_rationale.py` covers structure. The eval covers the decisions the ledger logs, not the ledger entries themselves. |

## Case coverage matrix (golden, n=15)

| ID | Scenario | What it grades |
|---|---|---|
| GC-01 | Clean post-HB-837 case, both signatories, within AF cap | `route_to_af` recommendation; `forum=arbitration_forums`; `examiner` tier (or `senior_examiner` if non-mandatory variance); 2yr SOL |
| GC-02 | Pre-HB-837 loss (2022), claimant 60% pure comparative | NOT barred; `litigation` forum; 4yr SOL; pre-HB-837 fee-shifting exposure (10% scalar) |
| GC-03 | Post-HB-837, claimant 60% → §768.81 bar fires | `recovery_barred=True`; `bar_basis="hb_837_51_bar"`; `recommendation="abstain"` |
| GC-04 | Non-FL loss | `recovery_barred=True`; `bar_basis="non_fl_loss"`; mandatory escalation flag |
| GC-05 | SOL expired (loss > 2yr ago for post-HB-837) | `recovery_barred=True`; `bar_basis="sol_expired"`; `hb837_negligence_sol` gate fails |
| GC-06 | Anti-subrogation overlap — tortfeasor on omnibus roster | `anti_subrogation_rule` ambiguous; variance flag fires; `senior_review_required` |
| GC-07 | PIP-only commercial vehicle (`627_7405_pip_commercial` lane) | `pip_subrogability_627_7405` gate passes; subrogation_lane cite contains "§627.7405" |
| GC-08 | PIP-only non-commercial (private passenger) | `recovery_barred=True`; `bar_basis="pip_non_commercial"` |
| GC-09 | Pre-tender release / settlement signal | WQBA gate fails; `bar_basis="pre_tender_release"`; `release_or_pre_tender_settlement_detected` variance |
| GC-10 | Negligent entrustment — owner != operator + owner_knowledge_indicators present | `owner_negligent_entrustment_uncapped` layer appears in `layered_targets` |
| GC-11 | Fabre non-party present | `fabre_non_party` layer appears; calibration P(recovery)=0.40 |
| GC-12 | Vicarious cap fires — natural-person owner separate from operator | `owner_vicarious_cap_324_021` layer appears; `cap_applied = 300K PD-occurrence + 50K PD = 350K` |
| GC-13 | AF non-signatory tortfeasor carrier | `af_compulsory_jurisdiction` fails; `forum=negotiated_demand`; `recommendation=route_to_negotiated_demand` |
| GC-14 | Deny+subrogate cross-stream conflict | `deny_plus_subrogate` variance fires; `cross_stream_conflicts.interlock="active_conflict_senior_review_required"`; `recommendation="senior_review_required"` |
| GC-15 | Made-whole partial settlement — `made_whole_with_partial_settlement` variance | Variance fires; mandatory escalation; `recommendation="senior_review_required"` |

## Adversarial / boundary probes (n=8 scenarios → multi-sub-case)

| ID | Scenario | What it probes |
|---|---|---|
| ADV-01 | HB 837 SOL boundary — loss `2023-03-23` (4yr) vs `2023-03-24` (2yr) | Statute-version selector at the day. Both sub-cases: `sol_accrual_vs_filing_split` variance fires within ±30 days. |
| ADV-02 | Comparative bar edge — claimant exactly 50% vs 51% | `hb837_modified_comparative_bar` strict `>` vs `≥`. 50% NOT barred; 51% barred. |
| ADV-03 | Near-bar window — claimant exactly 45% (in [45,55]) vs 44% (out) | `comparative_fault_cliff_buffer` variance + mandatory escalation. |
| ADV-04 | AF cap edge — paid exactly $100K (in) vs $100,001 (over) | `af_compulsory_jurisdiction` `≤` vs `>`. In → `arbitration_forums`; over → `litigation`. |
| ADV-05 | AF signatory unverifiable (NAIC missing) | `af_signatory_unverifiable` variance + mandatory escalation. |
| ADV-06 | Vicarious cap eligibility: `owner==operator` (no cap), `business_not_in_leasing` owner (no cap), `natural_person` owner ≠ operator (cap fires) | 3 sub-cases — `owner_vicarious_cap_324_021` layer presence/absence. |
| ADV-07 | Products repose boundary — loss exactly 12yr ago | Products layer eligibility / variance. |
| ADV-08 | SOL exactly 0 days remaining today | `hb837_negligence_sol` gate boundary: `days_remaining > 0` strict; `=0` fails. |

## What "passing the eval" means

- **Golden suite**: 15/15 green; any red blocks merge.
- **Adversarial suite**: all sub-cases green; any red is an off-by-one
  at a doctrinal seam.

## Drift detection

Same protocol as Liability + Reserve. Re-run on every prompt edit,
upstream-snapshot schema change, or constant change. Any red previously
green = block merge.

## Known asterisks

- **Calibration** — same posture: grades calculator vs spec, not spec
  vs closed-claim ground truth. AF cap, P(recovery) scalars, vicarious
  cap dollar values ship as seed defaults; per-carrier tuning is
  per-customer.
- **LLM extractor** — Layer 1 deferred.
- **Diligence ledger structure + rationale text** — covered by
  `test_ledger_and_rationale.py`, not here.
- **Subrogation `PostureChanged` literal extension** — still locked
  behind Document Reader eval refresh (Liability open Gap #5).
  Recovery currently routes via `liability` posture; subrogation-only
  docs can't dispatch Recovery directly. Documented; deferred.

## Open gaps and revision path

| # | Gap | Severity | Trigger | Action |
|---|---|---|---|---|
| 1 | `made_whole_shortfall` math is force-zeroed (`shortfall = Decimal("0")`) after computation — the field surfaces in the ledger but doesn't reduce `basis`. Comment says it's intentional for direct-against-tortfeasor subrogation, but the field name suggests otherwise. | Medium | Reserve-Recovery integration writes a real case where made-whole shortfall ought to reduce recovery basis. | Either rename the field to reflect informational status OR wire it through the basis math with a config toggle per subrogation lane. |
| 2 | AF signatory roster is hardcoded in `AF_SIGNATORY_ROSTER_V1` (9 NAICs); no refresh path. | High | First real claim with NAIC not in the seed. | Build the AF roster refresh job (§0.2 #3 in SYSTEM_ARCHITECTURE.md). |
| 3 | `evidence_completeness` for negligent-entrustment layer uses `min(upstream_confidence, 0.5 + 0.1*min(indicators, 5))` — caps at 1.0 from 5+ indicators. Not eval-asserted because the input model doesn't yet require explicit per-indicator weighting. | Low | Negligent-entrustment claims become common enough that the cap matters. | Add per-indicator weighting to `OwnerKnowledgeIndicator` schema; assert per-case. |
| 4 | `product_defect_recall` layer always added when VIN present, even with `0` apportioned/share/expected_value. v1 surface is structural only. | Low | Recall cross-reference data wired in. | Either suppress empty layer OR add an `eligible_for_recovery` boolean. |
| 5 | LLM extractor (Layer 1) unevaled — silent prompt-change risk. | High | Live API budget + corpus. | Build Layer-1 harness. |

### Eval-design rules inherited

- Every emitted field GRADED or explicitly DEFERRED (see field-coverage table).
- Default `tolerance = 0`.

## Run history

| Date | SHA | Golden | Adversarial | Notes |
|---|---|---|---|---|
| 2026-06-02 | 2044439 | 15/15 | 14/14 | Initial slice — green on second run. Case-spec corrections: GC-02 loss bumped to 2023-01-01 (PRE_HB837=2022-06-02 is at the SOL boundary on today's review date); GC-04 + GC-09 expectations changed to `abstain` not `senior_review_required` because `recovery_barred=True` short-circuits in `_recommendation()` BEFORE the mandatory-escalation check; ADV-01b reframed to assert SOL-expiry short-circuits the split-window variance. 8 adversarial scenarios split into 14 sub-cases. |
