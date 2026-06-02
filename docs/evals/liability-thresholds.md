---
tags:
  - project/argos
  - type/eval-threshold
  - status/living
created: 2026-06-02
updated: 2026-06-02
---

# Liability eval — pass/fail criteria + thresholds

This doc is the contract. Every Liability eval case in
`tests/evals/liability/` is graded against the criteria below.
The eval suite runs on demand via:

```bash
uv run pytest tests/evals/liability/ -m eval -q
```

It is **excluded from the default test run** (`addopts = "-m 'not eval'"`
in `pyproject.toml`) because evals are quality-regression detection,
not per-commit gating.

## What we're grading

Liability's output is **not a dollar estimate** — that lives in Reserve.
Liability emits:

- **Apportionment**: per-party `fault_pct` (Decimal, sums to 100 across the pie).
- **Applicable regime**: one of `pure_comparative_pre_hb837`, `modified_51_bar_hb837`, `med_mal_pure_comparative`.
- **Bar status**: `recovery_bar_triggered` (bool) + `bar_basis` (`none`, `hb837_51_pct`, `768_36_intoxication`).
- **Exposure ceiling**: `vicarious_cap_applies`, `cap_value`, `graves_lessor_removed`, `negligent_entrustment_uncapped_path_available`, `fabre_defendants`.
- **Doctrines applied**: list of doctrine IDs (each carries its statute/case cite).
- **Variance flags**: routing signals (Powell, multi-party, intoxication candidate, etc.).
- **Authority tier**: required commit authority.

## Three layers of grading

### Layer 1 — LLM extractor (anchor pairs)

**Out of scope for this vertical slice.** Requires `ANTHROPIC_API_KEY` +
live API spend. Will be added once the deterministic-core eval is
stable and a budget is set for live runs. Target thresholds when built:

- Enumerated fields (`fact_pattern`, `line_of_business`, `owner_type`): exact match ≥ **95%**.
- Continuous fields (any extracted fault % when LLM is asked to estimate): within **±5pp** on ≥ **90%** of cases.
- Statute citations: exact match against registry ≥ **99%**.

### Layer 2 — Deterministic policy engine + calculator

**This is what the vertical slice grades.** Pass criteria per case:

- Regime classification — exact match: **100%**.
- Bar detection (`recovery_bar_triggered` + `bar_basis`) — exact match: **100%**.
- Exposure-ceiling booleans (`vicarious_cap_applies`, `graves_lessor_removed`, `negligent_entrustment_uncapped_path_available`) — exact match: **100%**.
- Doctrines-applied membership — every doctrine in `expected_doctrines_applied` must appear; every doctrine in `expected_doctrines_NOT_applied` must NOT appear.
- Apportionment central value — `insured_fault_pct` within **±5pp** of expectation (calculator math is deterministic, so this is really a sanity check on the test fixture, not on the LLM).
- Apportionment pie — sums to 100 (model-validator enforced, but asserted explicitly).

### Layer 3 — Adversarial / boundary probes

Red/green per case. **No tolerance** on boundary checks — they exist
to catch off-by-one errors at doctrinal seams.

## Case coverage matrix (golden, n=15)

| ID | Scenario | What it grades |
|---|---|---|
| GC-01 | Rear-end clean (no rebuttal) | Anchor pattern + clean apportionment |
| GC-02 | Rear-end + sudden-stop rebuttal | Evidence shifts pie toward claimant |
| GC-03 | Left turn across traffic | Anchor on turning driver (90%) |
| GC-04 | Controlled intersection — claimant ran light | Anchor + HB 837 bar fires |
| GC-05 | Pre-HB-837 loss (2022-06-02), same facts as GC-04 | Pure comparative, NO bar despite claimant >50% |
| GC-06 | Med-mal carve-out, claimant 60% | `med_mal_pure_comparative`, NO bar |
| GC-07 | §768.36 intoxication bar (BAC 0.12 + causation + >50%) | `768_36_intoxication` bar fires |
| GC-08 | Intoxication WITHOUT causation evidence | Bar does NOT fire (dual-prong) |
| GC-09 | Intoxication, BAC < 0.08, no impairment | Bar does NOT fire |
| GC-10 | Natural-person owner vicarious cap | `vicarious_cap_applies=True`, cap value set |
| GC-11 | Graves Act preemption (commercial lessor) | `graves_lessor_removed=True` |
| GC-12 | Graves Act exception (owner-knowledge evidence) | `graves_lessor_removed=False` |
| GC-13 | Negligent entrustment uncapped path | `negligent_entrustment_uncapped_path_available=True` |
| GC-14 | Fabre non-party | `fabre_defendants` non-empty, `fabre_apportionment` doctrine applied |
| GC-15 | Chain reaction (50/50 anchor) | Forces matrix view, low confidence |

## Adversarial / boundary probes (n=8)

| ID | Scenario | What it probes |
|---|---|---|
| ADV-01 | HB 837 boundary: loss 2023-03-23 | Day before → pre-HB-837, NO bar |
| ADV-02 | HB 837 boundary: loss 2023-03-24 | Effective day → modified-51 regime |
| ADV-03 | HB 837 boundary: loss 2023-03-25 + claimant 51% | Day after, bar fires |
| ADV-04 | Modified-51 edge: claimant exactly 50% | Strict `>` 50, NOT `≥`. NO bar at 50.00. |
| ADV-05 | Modified-51 edge: claimant exactly 51% | Bar fires at 51.00. |
| ADV-06 | Intoxication threshold: BAC exactly 0.08 + causation + >50% | `≥` threshold; bar fires. |
| ADV-07 | Intoxication threshold: BAC 0.07, no impairment | Bar does NOT fire. |
| ADV-08 | Driver-is-owner kills vicarious cap | Natural-person owner but driver==owner → cap does NOT apply (no vicarious theory). |

## What "passing the eval" means

- **Golden suite**: 15/15 green. Any red is a doctrinal regression and blocks the release.
- **Adversarial suite**: 8/8 green. Any red is an off-by-one at a doctrinal seam — these are the bugs that look fine until they ship.

## Drift detection

When a prompt edit or model swap lands, re-run the suite. Threshold:
**any red previously green = block merge**, investigate root cause,
add a new case if the regression exposed an untested seam.

## Known asterisks

- **Calibration** (does the apportionment reflect reality on closed-claim ground truth?) — out of scope for v1. Requires labeled closed claims, which we don't have for synthetic data. The eval grades correctness against the spec; it does not grade real-world calibration. This is the "garbage in, garbage out" boundary — if the spec's anchor table is wrong, the eval still passes.
- **LLM-extractor accuracy** — Layer 1 deferred until live API budget is set.
- **Reserve calibration** — Reserve eval is a separate vertical slice; this doc is Liability-only.

## Run history

Stamp each successful suite run here with date + git SHA. Update on
every full-green run.

| Date | SHA | Golden | Adversarial | Notes |
|---|---|---|---|---|
| 2026-06-02 | 86bc4f6 | 15/15 | 8/8 | Initial slice — green on first full run. GC-10 expectation pinned to per-occurrence ceiling (`$300K`), per `policy_engine.py` default. |
