---
tags:
  - project/argos
  - type/eval-thresholds
  - status/locked
created: 2026-05-30
locked_before_run: true
---

# Triage ranker hybrid v2 — benchmark thresholds

**Locked before any v2 run.** Defines what counts as "the LLM
materiality re-rank earns its keep" vs "v1 was already at the ceiling."
Locked first, measured second, per the eval methodology in
`docs/evals/methodology.md`.

Spec: `docs/specs/triage-ranker-hybrid-v2.md`. The v1 thresholds doc
(`triage-ranker-thresholds.md`) carries over for the metric semantics
(top-7 Jaccard, Kendall tau, k-bucket framing).

## What v2 must beat to ship

Three concrete pre-conditions, all measured against the **same two
independent golds used in v1 verification** (`gold_gpt5.csv` and
`gold_gpt55pro.csv`). The Opus gold is excluded — it was tuned against
in v1 and using it would over-credit v2.

### Primary metric: top-7 k-bucket lift

| against gold_gpt5 | against gold_gpt55pro | v2 verdict |
|---|---|---|
| k=7 | k=7 | **SHIP V2.** LLM re-rank closes the 7th-slot disagreement on both independent judges. Hybrid earns its keep. |
| k=7 on one, k=6 on the other | mixed | **HOLD.** v2 helps one judge and not the other — investigate the disagreement before shipping. The "lifting" judge is likely the one whose 7th-claim pick matches the LLM judge's intuition; understand why before declaring success. |
| k=6 on both | flat | **DEFER V2, SHIP V1.** The k=6 ceiling is genuine adjuster ambiguity, not closeable by LLM judgment. Two LLMs (GPT-5 and GPT-5.5-pro) saw the same 12 features and a third LLM judge couldn't reconcile their disagreement. |
| k ≤ 5 on either | regression | **DO NOT SHIP.** v2 hurts; the LLM re-rank is introducing noise that didn't exist in S1. |

### Secondary metric: full-ordering tau preservation

The re-rank only touches ranks 1..10. Ranks 11..20 keep S1's ordering,
so tau on the full N=20 should be **within ±0.05** of the v1 tau on
each gold:

- v1 tau vs gold_gpt5 = +0.811. v2 tau must be in [+0.761, +0.861].
- v1 tau vs gold_gpt55pro = +0.747. v2 tau must be in [+0.697, +0.797].

A tau drop of more than 0.05 means the re-rank is shuffling the top
slice in ways that hurt overall ordering even if the set improves —
flag for investigation, do not ship as-is.

### Tertiary check: schema validity

The LLM judge must return a CSV that passes the schema check on the
first try (no retry loop in v2). Schema validity rate across the two
benchmark runs:

- 2/2 valid: pass.
- 1/2 valid: warn. v2 cannot ship until the judge prompt is stable
  enough to round-trip schema on every call.
- 0/2 valid: fail. The judge prompt is too loose; revisit before any
  numeric verdict.

## Why these thresholds

**Why k=7 and not "any improvement"?** The k-bucket structure of top-7
Jaccard means a "small" improvement (say k=6.3 averaged over many runs)
doesn't exist — every individual run is either k=5, k=6, k=7, or
worse/better in whole units. The honest test of "did the LLM layer
help" is whether it converts k=6 wins into k=7 wins on the same
independent gold. Anything weaker leaves the v1 verdict unchanged.

**Why both golds and not the average?** If v2 lifts one gold to k=7 and
the other stays at k=6, that's diagnostic: the LLM judge's intuition
aligns with one judge's marginal pick but not the other's. That's
useful signal, but it's not "deterministic + LLM beats deterministic."
Both must clear to ship.

**Why ±0.05 on tau and not exact?** The re-rank touches 10 of 20
positions. Even a perfect re-rank of the top-10 will produce small tau
drift relative to v1 (different intra-slice ordering than S1's score
order). ±0.05 is roughly one standard error on the analytic noise
stddev of 0.16 for N=20 — tight enough to catch scrambling, loose
enough to allow legitimate re-rank movement.

## Failure modes that flip v2 to FAIL regardless of metric values

- Judge model changed between spec lock and run (spec locks
  `gpt-5.5-pro`).
- Slice size N changed (spec locks N=10).
- Either independent gold CSV regenerated between v1 commit and v2 run.
- Judge prompt deviates from the locked template in
  `src/argos/services/triage/hybrid.py` after the benchmark commit.
- Re-rank applied to ranks outside the top-N slice (spec violation —
  v2 must not reorder the tail).
- Multiple runs averaged or cherry-picked (one run = one verdict, per
  the v1 single-run rule that carries over).

## Reporting

After the v2 run, append a results section to the **tuning procedure
doc** (`triage-ranker-tuning-procedure.md`) with:

- Date of the run.
- v2 k vs each gold + delta vs v1.
- v2 tau vs each gold + delta vs v1.
- Schema validity rate.
- The judge's reasoning for the 7th-slot pick on each gold (the
  qualitative read — even if k=6, is the LLM at least *picking the
  same 7th claim as the corresponding judge gold*?).
- Verdict per the table above.
- One paragraph on whether the 7th-claim ambiguity is now better
  understood (was it materiality? was it weighting? was it genuine
  judgment dispute?).

## Scope

Defines thresholds for hybrid v2 (S1 base + GPT-5.5-pro re-rank on
top-10) on the v1 N=20 caseload only. v3 (held-out fixture, alternate
judges, latency/cost budgets) gets its own thresholds doc.
