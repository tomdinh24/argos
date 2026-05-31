---
tags:
  - project/argos
  - type/eval-thresholds
  - status/revised
created: 2026-05-30
locked_before_run: true
revised: 2026-05-30
---

# Triage ranker — benchmark thresholds

**Locked before any benchmark run, then revised after a Codex challenge
pass found two math errors in the original.** This document defines what
counts as "deterministic features alone match a senior adjuster's
prioritization" vs "the ranker is closer to random than to the adjuster."
Locked first, measured second, per the eval methodology in
`docs/evals/methodology.md`.

The spec lives at `docs/specs/triage-ranker.md`. The fixture is the N=20
corner-covering caseload at `src/argos/ontology/synthetic_caseload.py`.
The gold ranking (originally planned as hand-ranked, sourced from Opus
4.8 in execution; see "Errata" below for the methodology consequence)
lives at `data/eval-runs/triage-ranker/gold.csv`.

## Errata — what changed and why

A Codex adversarial review found that the original tier interpretations
were arithmetically impossible for N=20, size-7 subsets. For two such
sets, the only attainable top-7 Jaccard values are the discrete set
`{0, 1/13, 2/12, 3/11, 4/10, 5/9, 6/8, 7/7}` =
`{0.000, 0.077, 0.167, 0.273, 0.400, 0.556, 0.750, 1.000}`. So:

- The original "≥0.80 = at minimum 5/7 overlap" was wrong (5/7 = 0.556).
  The 0.80 threshold actually collapses to k=7 only (Jaccard 1.000) —
  exact match — because 0.750 is the largest sub-1.0 attainable value.
- The original "0.60 ≈ 4/7" was wrong (4/7 = 0.400 is below 0.60). The
  0.60 threshold actually requires k≥6 (Jaccard 0.750).
- The high tier as originally written was therefore a "perfect-match-
  only" tier, which is exactly what tuning trains for and what
  same-family-model bias inflates. That made the original "DETERMINISTIC
  IS ENOUGH" verdict an artifact of the broken tier definition.

The tiers below are restated in terms of attainable k-bucket overlap.
The verdict structure is the same (deterministic-enough / hybrid-lifts /
hybrid-structural), but the boundaries now correspond to outcomes the
ranker can actually achieve. The Codex challenge transcript is preserved
in the project history for audit.

## Metrics

Two metrics, both computed against the hand gold:

- **Top-7 Jaccard.** Overlap of ranker's top-7 with gold's top-7. Range
  0–1. This is the "today's work" slice for a 20-claim caseload.
- **Kendall's tau.** Rank correlation on the full N=20 ordering. Range
  -1 to 1.

Top-7 Jaccard is the primary metric (it's what the adjuster actually
experiences: the morning queue). Tau is the secondary read on whether
the *ordering* matches, not just the *set*.

## Noise floor

Thresholds are interpretable only relative to what a random ranker would
score on the same N=20. Both noise figures below are computed
analytically; we don't need a Monte Carlo for N this small.

**Random top-7 Jaccard.** For two independently-drawn size-7 subsets of
N=20, the expected intersection size is `7 × 7 / 20 = 2.45`. By the
inclusion–exclusion identity for Jaccard,
`|A ∪ B| = |A| + |B| − |A ∩ B| = 14 − 2.45 = 11.55`, so
`E[Jaccard] = 2.45 / 11.55 ≈ 0.21`.

**Random Kendall tau.** Mean 0 under the null (uniform random
permutation). Stddev for n=20 is
`σ = √(2(2n+5) / (9n(n−1))) = √(90/3420) ≈ 0.16`. The spec's "≈ 0.22"
is a rougher `1/√n` approximation; the analytic figure is what we
quote below.

## Tiers, restated in attainable k-buckets

| k overlap | Top-7 Jaccard | × noise (0.21) | Kendall tau | σ above noise (σ=0.16) | Verdict |
|---|---|---|---|---|---|
| **k = 7** (exact) | 1.000 | 4.8× | ≥ 0.60 | ≥ 3.7σ | **Deterministic is enough** — but **only credible against an independent gold**, not the gold the ranker was tuned against. Same-family-tuning bias makes this tier reachable by memorization; see below. |
| **k = 6** | 0.750 | 3.6× | 0.40 – 0.60 | 2.5σ – 3.7σ | **Hybrid lifts.** Deterministic ranker gets 6/7 of the today's-work set right; the 7th-slot disagreement is real adjuster-judgment ambiguity. LLM materiality re-rank can help on the contested top slice. |
| **k ≤ 5** | ≤ 0.556 | ≤ 2.6× | < 0.40 | < 2.5σ | **Hybrid is structural.** Deterministic misses the heart of what makes a claim priority. Weight tuning won't close a 2+ claim gap on a 7-claim slice. |

The two metric columns are read as a pair: both must land in the same
tier for the verdict to be unambiguous. Splits (e.g. k=7 on training
gold but k=6 on independent gold) are themselves the diagnostic —
exactly what we observed in the v1 run.

## Same-family-bias caveat (load-bearing)

The k=7 / "deterministic is enough" tier reduces to "exact top-7 match
with the gold." When the gold is produced by an LLM in the same family
as any system involved in feature/prompt design (Opus 4.8 ranking, with
the prompt exposing the scorer's feature glossary), achieving k=7 may
reflect "tuned to reproduce same-family ranking conventions" rather
than "captures real priority structure."

**Operational consequence:** a k=7 result is only credible as
"deterministic is enough" if it holds against a gold produced by an
**independent** model family AND on a prompt that does **not** expose
the ranker's internal feature names. The v1 run hit k=7 against Opus
gold (which it was tuned against) but dropped to k=6 against both GPT-5
and GPT-5.5-pro golds. That cross-model gap is the honest read.

## Why these tier boundaries

- **k = 7 (Jaccard 1.000).** Perfect overlap — the ranker and the gold
  pick the same seven claims for today. Only one attainable value above
  the original 0.80 threshold, so this tier is necessarily exact-match.
- **k = 6 (Jaccard 0.750).** 6 of 7 top picks agree; one claim is
  contested. Real signal, but the contested claim is exactly where
  adjuster judgment (or LLM materiality assessment) earns its keep.
- **k ≤ 5 (Jaccard ≤ 0.556).** Two or more disagreements on a 7-slot
  cut. Structural gap that simple weight tuning won't close.

The tau tiers are calibrated so the marginal cell (0.4) is ~2.5σ above
noise, which is the conventional "interesting, not conclusive" line.
0.6 is 3.7σ — solid signal in a way that wouldn't be explained by
favorable shuffling of an N=20 sample.

## Failure modes that flip the eval to FAIL regardless of metric values

- Ranker output not a total order over the 20 request_ids (duplicates,
  missing IDs, ties without a deterministic tiebreak).
- Score function not deterministic (two runs on the same caseload
  produce different orderings).
- Any feature extractor crashes on the fixture (missing-field handling
  must return a sentinel or zero, never raise).
- Gold ranking changed between threshold-lock and benchmark run (the
  gold CSV must be committed before the benchmark script is invoked).
- "Deterministic is enough" verdict claimed on a gold the ranker was
  tuned against, without a cross-model independent-gold check that
  reproduces the k=7 result.

## How a passing eval reads (k=7 against independent gold)

> Top-7 Jaccard = 1.000 (k=7) against a gold produced by an independent
> model family on a feature-name-neutralized prompt. Kendall tau = +0.74.
> **PASS — deterministic is enough.** Defer hybrid; ship S1.

## How a hybrid-lifts eval reads (k=6)

> Top-7 Jaccard = 0.750 (k=6). Kendall tau = +0.81.
> **HYBRID LIFTS.** S1 is the base; the contested 7th-slot claim is
> exactly where LLM materiality re-rank earns its keep. Build hybrid v2.

## How a hybrid-structural eval reads (k ≤ 5)

> Top-7 Jaccard = 0.400 (k=4). Kendall tau = +0.31.
> **HYBRID IS STRUCTURAL.** Features alone do not capture priority;
> the deterministic ranker is not a viable v1 on its own.

## Scope

Defines thresholds for the S1 deterministic ranker on the v1 N=20
caseload only. Hybrid v2 (deterministic + LLM materiality layer) will
have its own thresholds doc when that work starts. Do not back-fit
hybrid results into this file.
