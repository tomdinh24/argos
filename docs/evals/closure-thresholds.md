---
tags:
  - project/argos
  - type/eval-threshold
  - status/living
created: 2026-06-02
updated: 2026-06-02
---

# Closure eval — pass/fail criteria + thresholds

Contract for `tests/evals/closure/`.

```bash
uv run pytest tests/evals/closure/ -m eval -q
```

Excluded from default suite. Inherits both 2026-06-02 eval-design
policies ([DECISIONS.md](../DECISIONS.md)): every emitted field is
GRADED or DEFERRED; tolerance defaults to 0.

## What we're grading

Closure is the **terminating analytical workflow** — its recommendation
shuts the file. If it says ready_to_close and a Tier A gate actually
failed, the file shuts with a defect recoverable only by reopen. The
most load-bearing math is the **tier-failure probability cap**: a
single Tier A failure caps `ready_probability` at 0.05, B at 0.25,
C at 0.50.

Outputs graded:

- **Top-line decision**: `recommendation` (11 literals — ready/soft_close/
  blocked/requires_*/recommend_reopen) + `ready_probability`.
- **Blocking defects**: ranked A→F, derived from failed gates.
- **Bifurcated status**: `indemnity_status` × `defense_status` per
  §624.155(6)(a) (interpleader case especially).
- **OIR classification**: closed_with_payment / without / reopened /
  not_yet_classifiable.
- **Per-gate results** for ~25 gates across 6 tiers.
- **Variance flags**, **authority tier**, **preservation plan**.

## Three layers of grading

### Layer 1 — LLM extractor (`ClosureInputs`)

Out of scope (same posture as the other three slices). Closure's
extractor reads claim record + upstream JSON + uploaded docs and emits
~40 nested fields covering coverage audit, Powell/Harvey/Boston Old
Colony signals, CRN state, multi-claimant tracking, PIP drain, lien
ledger, §111 log, settlement/release timeline. Anchor-pair eval
deferred until live-API budget.

### Layer 2 — Deterministic policy engine + calculator

What this slice grades. All exact-match (`tolerance = 0`):

- `recommendation` — exact literal.
- `ready_probability` — exact float per tier cap.
- `blocking_defects` — exact ordered set of `(gate_id, tier)` pairs.
- `oir_classification` — exact literal.
- `indemnity_status`, `defense_status` — exact literals.
- `authority_tier_required.{required_tier, committable_at_examiner,
  settlement_amount}` — exact.
- `variance_flags` — exact set.
- `preservation_plan.preservation_until_date` — exact date.
- Per-gate `result` for the gates each case probes.

### Layer 3 — Adversarial / boundary probes

Tier-rank arithmetic seams (A+B+C → A wins), CRN cure-window day
boundary, authority dollar boundaries, soft-close membership tests,
Powell/Macola routing precedence.

## Field coverage (ClosureAssessment)

| Field | Status | How / why |
|---|---|---|
| `recommendation` | GRADED | Top-line literal. |
| `ready_probability` | GRADED | Exact-match per case; tier-cap math is load-bearing. |
| `blocking_defects[].{gate_id, tier}` | GRADED | Exact-set per case. |
| `blocking_defects[].{description, statute_or_case_cite, evidence_ref, remediation_action}` | NOT-GRADED-by-design | Sourced from the gate registry; covered by `test_constants.py`. |
| `indemnity_status`, `defense_status` | GRADED | Bifurcation per case. |
| `oir_classification` | GRADED | Regulatory bucket. |
| `doctrinal_gates[].result` | GRADED-per-case | Each case targets specific gates. |
| `doctrinal_gates[].{statute_or_case_cite, evidence_ref, remediation_action}` | GRADED-smoke | Non-empty when result != n_a. |
| `doctrinal_gates[].defect_emitted` | GRADED-smoke | True iff result == fail. |
| `preservation_plan.preservation_until_date` | GRADED | Exact date per case. |
| `preservation_plan.{floor_components, data_sources_held}` | GRADED-smoke | Non-empty when applicable. |
| `variance_flags` | GRADED | Exact-set per case. |
| `authority_tier_required.{committable_at_examiner, required_tier, settlement_amount}` | GRADED | Tier + dollar. |
| `authority_tier_required.basis_for_tier` | NOT-GRADED-by-design | Free-text breakdown. |
| `diligence_ledger.*` | NOT-GRADED-by-design | Co-equal artifact; `test_ledger_and_rationale.py` covers structure. The eval grades the decisions the ledger logs. |
| `rationale_text` | NOT-GRADED-by-design | Templated; covered separately. |
| `request_id`, `reviewed_as_of` | NOT-GRADED-by-design | Pass-throughs. |

## Case coverage matrix (golden, n=15)

| ID | Scenario | What it grades |
|---|---|---|
| GC-01 | Clean ready_to_close_with_payment — all gates pass, settlement paid | `recommendation=ready_to_close_with_payment`, `ready_probability=0.95`, indemnity=ready/defense=n_a, examiner tier |
| GC-02 | Clean ready_to_close_without_payment — denial letter complete, intent=without_payment | `recommendation=ready_to_close_without_payment` |
| GC-03 | closed_with_open_recovery — Recovery decision committed + pursue | Indemnity ledger closes; recovery stays open |
| GC-04 | soft_close_pending_medicare_final_demand — only Medicare gate fails | Soft-close literal; tier-B cap 0.25 |
| GC-05 | soft_close_pending_section_111_confirmation — only §111 gate fails | Soft-close §111 literal |
| GC-06 | soft_close_pending_lien_release_letter — only lien gates (Medicaid + ERISA) fail | Soft-close lien literal |
| GC-07 | soft_close_pending_release_execution — only `missing_signed_release` fails | Soft-close release literal |
| GC-08 | blocked_by_defects — multiple Tier A + Tier B fails | `recommendation=blocked_by_defects`, `ready_probability=0.05` (worst-tier wins) |
| GC-09 | requires_legal_review — `macola_settlement_after_excess_trajectory` fails | Legal-review literal regardless of other state |
| GC-10 | requires_senior_review — mandatory-escalation variance flag set | Senior review |
| GC-11 | requires_senior_review — above-examiner authority, no defects | Senior review on dollar tier alone |
| GC-12 | A1 fail — coverage uncommitted | Tier A cap 0.05; defect with tier="A" |
| GC-13 | A2 fail — liability not committed | Tier A cap; defect ranked first |
| GC-14 | D1 fail — agent_action_ledger_incomplete | The gate promoted to blocker on 2026-06-02; tier D cap 0.70 |
| GC-15 | Interpleader bifurcation — indemnity deposited + tort actions unresolved | `indemnity_status=closed`, `defense_status=open` |

## Adversarial / boundary probes (n=8)

| ID | Scenario | What it probes |
|---|---|---|
| ADV-01 | Tier A fail → ready_probability = 0.05 (not 0.06) | Tier cap exact value. |
| ADV-02 | Tier B fail (no Tier A) → 0.25 | Tier-rank ordering when A clean. |
| ADV-03 | Tier C fail (no A/B) → 0.50 | Tier-rank ordering. |
| ADV-04 | Tier A + Tier C fail → A wins (0.05) | Worst-tier ordering. |
| ADV-05 | CRN cure window day-edge — day 59 (in window → fail) vs day 60 (`<` strict) | Strict `<` on cure-window threshold. |
| ADV-06 | Authority tier edges — settlement = exactly examiner authority ($25K) | `≤` boundary. |
| ADV-07 | Powell-unfulfilled gate fail trumps everything → requires_legal_review | Decision lattice precedence (item 2 in `_pick_recommendation`). |
| ADV-08 | Medicare + §111 fail (both Tier B) — does NOT route to medicare-only soft-close | `medicare_only` is a strict-subset test. |

## What "passing the eval" means

- 15/15 golden green. Any red blocks merge.
- All 8 adversarial green.

## Drift detection

Same protocol. Re-run on prompt/calc changes. Versioned-constant
changes (e.g. `FL_CLOSURE_GATE_REGISTRY_V1 → V2`) need new
golden cases pinned to the new registry.

## Known asterisks

- **Calibration** — same posture: spec vs reality is per-customer.
- **LLM extractor** — Layer 1 deferred.
- **Ledger / rationale text** — covered by `test_ledger_and_rationale.py`.

## Open gaps and revision path

| # | Gap | Severity | Trigger | Action |
|---|---|---|---|---|
| 1 | `_pick_recommendation` returns `blocked_by_defects` in the default fall-through (line 247), even when no gates fail and OIR classification is `not_yet_classifiable`. This is a defensive default; reachable only if doctrine resolution emits `not_yet_classifiable` AND no gates failed AND no soft-close path matched. | Low | A real claim hits this branch on production. | Either rename default to `requires_senior_review` (safer default) or document the unreachable-by-design status. |
| 2 | `_route_authority` keys solely off `inputs.settlement.agreement_amount`; never reads upstream Reserve `total_paid`. | Medium | A high-paid claim with low/missing `agreement_amount` mis-routes to examiner. | Add a `max(agreement_amount, reserve.total_paid)` floor OR wire upstream Reserve through the routing call. |
| 3 | `_build_preservation_plan` re-runs in the calculator even though `apply_fl_closure_gates` also computes `preservation_until_date`. Calculator overwrites unless doctrine resolution sets it. | Low | Plans drift between policy engine and calculator. | Pick one — recommend policy engine — and make the other read it. |
| 4 | LLM extractor (Layer 1) unevaled. | High | Live API budget + corpus. | Build Layer-1 harness. |
| 5 | `settlement_authority_exceeded` (D2) ALWAYS fires when `settlement > examiner_authority`. No `documented_escalation_evidence` input exists, so "above-examiner authority, properly escalated" is unrepresentable in v1. Effect: any settlement above $25K routes to `blocked_by_defects` with Tier D cap 0.70, NOT `requires_senior_review`. Confirmed by GC-11. | Medium | First real claim where senior examiner has authority and the file should close cleanly. | Add an `escalation_log` field to `ClosureInputs` (or a `documented_escalation` flag on `SettlementInfo`); gate passes if escalation evidence is on file for the relevant tier. |

### Eval-design rules inherited

- Every emitted field GRADED or DEFERRED (see field-coverage table).
- Default `tolerance = 0`.

## Run history

| Date | SHA | Golden | Adversarial | Notes |
|---|---|---|---|---|
| 2026-06-02 | 15a1b43 | 15/15 | 9/9 | Initial slice — green on second run. Two case-spec corrections: (1) GC-04 expectation widened from `{medicare_msp_unresolved}` to `{medicare_msp_unresolved, section_111_tpoc_unreported}` — both Tier B gates share the same trigger (beneficiary + settlement ≥ $750), so they always fire together; recommendation still routes correctly to `soft_close_pending_medicare_final_demand` because `medicare_only` is strict-subset of {medicare gates}. (2) GC-11 reframed from `requires_senior_review` (with `expected_defect_gate_ids=set()`) to `blocked_by_defects` (with `settlement_authority_exceeded` Tier D fail) — v1 policy engine has no `documented_escalation_evidence` input, so D2 always fires when settlement > examiner cap. Logged as new Gap #5; promoted to §0.2 item 2 of SYSTEM_ARCHITECTURE. 8 adversarial scenarios split into 9 sub-cases. ADV-08 reframed from "Medicare+§111 doesn't route to medicare-only" (false — both ARE in medicare_gates) to "Medicare + lien (mixed) → blocked_by_defects" (true boundary). |
