---
tags:
  - project/argos
  - type/eval-tuning-procedure
  - status/locked
created: 2026-05-30
locked_before_run: true
---

# Triage ranker — weight-tuning procedure

**Locked before any tuning run.** This document defines exactly how the S1
weights will be tuned, with what budget, against what objective, before
the tuned ranker is benchmarked against the locked thresholds in
`docs/evals/triage-ranker-thresholds.md`.

## Why this doc exists

The first benchmark ran with uniform 1.0 weights (the spec's "starting
prior") and produced top-7 Jaccard = 0.273 (low tier) and Kendall tau =
+0.453 (mid tier) — a split verdict. The diagnosis was that uniform
weights are obviously underweighting hard service/legal clocks (SLA-
imminent claims dropped to ranks 7–13 because aged-and-incurred claims
have three features firing at once vs SLA's one).

A reasonable next step is to tune weights against gold and re-benchmark.
But "tune weights against gold" is exactly the move that, done without
discipline, turns into "tune until the verdict says what you want." This
doc locks the tuning shape *before* the run so the result is interpretable
either way:

- If tuned S1 clears the decision rule → deterministic was a calibration
  problem, not a structural one. Ship S1.
- If tuned S1 still fails → deterministic features alone genuinely don't
  capture priority. Hybrid v2 is justified.

Either outcome is honest. Without pre-registration, neither is.

## What is tunable

The 12 weights in `Weights` (`src/argos/services/triage/ranker.py`):
`w_sla`, `w_stat`, `w_aged`, `w_diary`, `w_sev`, `w_amt`, `w_reserve`,
`w_contact`, `w_unread`, `w_lit`, `w_rep`, `w_compl`.

Each weight is searched over the continuous interval **`[0.0, 8.0]`**.
Upper bound chosen at 8× the uniform prior to give legal-clock features
enough headroom to dominate without being unbounded.

## What is NOT tunable

- **No new features.** The feature set is frozen at the 12 in
  `src/argos/services/triage/features.py`. If a feature seems missing,
  that's the v2 question.
- **No removed features.** Setting a weight to 0.0 is allowed by the
  search; *deleting* a feature is not.
- **No per-claim hand-exceptions.** No "if litigation AND statute then
  rank = 1" rules. The whole point of S1 is the score is linear in
  normalized features.
- **No fixture changes.** The N=20 caseload in
  `src/argos/ontology/synthetic_caseload.py` is frozen at the corner mix
  it has now. Adding a corner mid-tuning would let us tune ourselves out
  of any failure.
- **No threshold changes.** The locked thresholds in
  `docs/evals/triage-ranker-thresholds.md` apply unchanged to the tuned
  result.
- **No gold ranking changes.** `data/eval-runs/triage-ranker/gold.csv`
  is the Opus 4.8 ranking locked at this point in time; do not regenerate
  to "improve" the gold.

## Search method

**Random search** over the 12-dim weight space with a fixed seed.

- Sample size: **N = 5000** random weight vectors.
- Each component drawn independently from `Uniform(0.0, 8.0)`.
- Seed: `42` (passed to `random.Random(42)` for reproducibility — no
  numpy required).
- Two **anchor vectors** added to the search set so the tuner sees the
  obvious priors alongside random draws:
  1. Uniform-1.0 (the baseline that produced the split verdict).
  2. Clock-biased: `w_sla = 4.0`, `w_stat = 4.0`, `w_lit = 2.0`,
     `w_compl = 2.0`, all others `1.0`. This is the prior I'd write by
     hand from the diagnosis; including it lets us see whether random
     search beats human intuition or vice versa.

Random search is chosen over gradient-based methods because the objective
(top-7 Jaccard) is discrete and non-differentiable. It's chosen over
exhaustive grid because 12 dimensions × any meaningful per-dim resolution
explodes; 5000 random draws covers the box adequately for an N=20
fixture and runs in seconds. Coordinate descent or differential
evolution would be reasonable alternatives but bring more knobs (step
size, mutation rate) that themselves invite post-hoc tuning.

## Objective

Maximize **top-7 Jaccard agreement with `gold.csv`**.

Tiebreak (when two weight vectors produce identical top-7 Jaccard):
maximize **Kendall tau** on the full N=20 ordering.

Second tiebreak: weight vector closest to the uniform-1.0 prior in L2
norm (prefer simpler weights when scores tie). Deterministic.

The optimizer reports the **single best weight vector** plus the top-5
runner-up vectors for diagnostic purposes only. The single winner is what
gets benchmarked.

## Budget and stopping

- Fixed budget: **5000 random samples + 2 anchor vectors = 5002 total
  evaluations.** No "if it doesn't converge, run more." If the budget is
  insufficient, the verdict is "deterministic doesn't cleanly beat
  random search at this budget," which is itself informative.
- Wall clock: expected < 30 seconds on the existing N=20 fixture (the
  ranker is pure Python; each evaluation is a sort + two metric
  computations).
- No early stopping based on the threshold values — searching only as
  far as needed to clear 0.80 is a textbook example of the
  rationalization spiral this doc exists to prevent.

## Single-run rule

After tuning, the benchmark script runs **once** with the winning
weights:

```
scripts/run_triage_benchmark.py --weights data/eval-runs/triage-ranker/tuned_weights.json
```

The output of that single run is final. The locked thresholds in
`docs/evals/triage-ranker-thresholds.md` apply unchanged:

- top-7 ≥ 0.80 AND tau ≥ 0.60 → **deterministic is enough**, defer hybrid.
- top-7 ∈ [0.60, 0.80) AND tau ∈ [0.40, 0.60) → **hybrid lifts**, build LLM
  materiality layer as the second stage.
- top-7 < 0.60 AND tau < 0.40 → **hybrid is structural**, deterministic
  S1 is not viable v1; LLM is required, not optional.
- Split tier verdicts read per the thresholds doc.

If the result lands in a split tier (e.g., top-7 high, tau mid) the
read is structural per the thresholds doc, not "let me re-tune."

## Reporting

After the tuning + benchmark run, append a results section to **this**
file (not a new file) with:

- Date of the run.
- Best weight vector (all 12 weights, 3 decimal places).
- Best top-7 Jaccard, best Kendall tau.
- Top-5 runner-up vectors and their scores.
- Verdict per the locked thresholds.
- One paragraph of plain-English reading: which feature weights moved
  most, which moved least, what that says about the structure of the
  caseload.

This file becomes the durable record of "we tuned, here's how, here's
what we got." Future readers of the repo can replicate by running the
same script with the same seed.

## Failure modes that flip the eval to FAIL regardless of metric values

- Tuning procedure deviates from this doc (different sample size,
  different seed, different bounds, different objective) and the
  deviation isn't documented in a subsequent locked revision.
- Anchor vectors omitted from the search.
- Tuning run done > 1 time with results cherry-picked.
- `gold.csv` regenerated between this doc lock and the benchmark run.
- Feature set or fixture changed between this doc lock and the benchmark
  run.

## Why not differential evolution / Bayesian opt / etc.

For 12 continuous dims with an N=20 cheap objective, the marginal
benefit of a smarter optimizer is small relative to the cost of locking
its hyperparameters here too. Random search at N=5000 is the simplest
honest baseline. If the result is borderline, the right follow-up is
"hybrid lifts" (per the thresholds doc), not "smarter optimizer."

## What this doc does NOT cover

- The hybrid v2 design. Separate spec when/if we get there.
- Tuning weights against a *different* caseload (e.g., a held-out v2
  fixture). For v1 the fixture and the gold are the same; this is
  acknowledged scope, not an oversight (see thresholds doc "Scope").
- Tuning the noise-floor calculation. Random ranker noise is analytic and
  independent of weights.

## Run results — 2026-05-30

Tuning ran exactly per the locked procedure: random search, 5000 samples
+ 2 anchor vectors, seed 42, bounds [0.0, 8.0]. Total ~3 seconds wall
clock. Output saved to `data/eval-runs/triage-ranker/tuned_weights.json`.

**Winner (random sample #4073):**

| weight | value | weight | value |
|---|---|---|---|
| `w_sla` | 7.809 | `w_contact` | 0.910 |
| `w_stat` | 7.484 | `w_unread` | 2.113 |
| `w_aged` | 3.274 | `w_lit` | 1.623 |
| `w_diary` | 1.845 | `w_rep` | 3.798 |
| `w_sev` | 1.064 | `w_compl` | 2.689 |
| `w_amt` | 5.951 | `w_reserve` | 5.972 |

**Tuned-S1 benchmark (single run, locked thresholds applied):**

- top-7 Jaccard = **1.000** (4.8× noise floor — high tier)
- Kendall tau = **+0.874** (+5.5σ above noise — high tier)

**Verdict against Opus gold (the gold tuned against): k=7 / high tier.**
But see "Cross-model validation" below — this verdict does *not* survive
an independent-gold check.

**Anchor vectors for context:**

- Uniform-1.0: top-7 = 0.273 (k=3). The result that triggered tuning.
- Clock-biased prior (hand-written w_sla=4, w_stat=4, w_lit=2, w_compl=2,
  rest=1): top-7 = **0.750 (k=6)**. The hand-written prior was already
  in mid tier per the corrected thresholds — better than I'd guessed.
  Random search lifted it from k=6 to k=7 by finding ratios that pick
  up the seventh (lit+rep+statute) claim Opus put at #3.

**Top-6 score sweep (diagnostic only — winner is the one above):**

| rank | top-7 | tau | L2 | origin |
|---|---|---|---|---|
| 1 | 1.000 | +0.874 | 12.48 | random #4073 |
| 2 | 1.000 | +0.821 | 9.11 | random #2809 |
| 3 | 1.000 | +0.821 | 10.88 | random #393 |
| 4 | 1.000 | +0.789 | 7.72 | random #489 |
| 5 | 1.000 | +0.758 | 14.14 | random #532 |
| 6 | 1.000 | +0.726 | 12.10 | random #716 |

Five different weight vectors recovered the same gold top-7 with different
tradeoffs in full-ordering tau and different distances from the uniform
prior. That breadth is the relevant signal: the gold's today's-work set
is reachable by the deterministic features through *many* weight
configurations, not just a single fragile maximum. The Codex consult's
prediction — that the uniform-weights failure was calibration, not
missing-information — checks out.

**Plain-English reading of the weights:**

- Hard clocks dominate: SLA (7.81) and statute (7.48) ended up at the
  top of the range, as the failure analysis predicted.
- Dollar amount lifted to ~6.0 — large incurred drives priority more
  than uniform weights allowed. (The tuner also raised w_reserve to
  5.97, but that weight is inert; see "Known inert feature" below.)
- Severity tier weight ended up near uniform (1.06) — it's not doing
  much work, probably because severity is correlated with incurred,
  so w_amt absorbs most of its variance.
- Days-since-claimant-contact ended up *below* uniform (0.91) — silent-
  claim staleness is a weaker priority signal in this gold than I'd
  have guessed. This matches Opus ranking the aged corners in the
  middle of the pack rather than the top, even though they have lots
  of staleness signal.
- Diary (1.85), unread (2.11), and litigation (1.62) all sit near
  uniform — present, contributing, but not dominant.
- Rep (3.80) and complaint (2.69) lifted moderately above uniform —
  representation and DOI flags do bump priority but don't dominate the
  clocks.

**Honest caveat — fit-on-the-fixture risk:**

top-7 = 1.000 is a perfect match on the same N=20 caseload the tuner
trained on, against a gold produced by Opus 4.8. There's no held-out
test set. The five-winners-with-different-shapes diagnostic mitigates
the "single fragile maximum" version of overfit, but the broader point
stands: this is calibration evidence, not generalization evidence.

## Cross-model validation (independent-gold check)

A Codex adversarial review flagged that the gold was Opus-produced and
the ranking prompt exposed the scorer's feature glossary, so the k=7
result could reflect same-family-LLM convention rather than real
adjuster priority structure. To test that, the same prompt was rewritten
with shuffled block order (kills the request_id clustering leakage:
`REQ-001..003` = SLA, `REQ-004..006` = statute, etc.) and a neutralized
preamble (no "ranker reads the same fields" hint, field names rephrased
to adjuster-shop language). Two independent OpenAI models then produced
their own gold rankings. The **same tuned weights** were benchmarked
against each new gold with **no re-tuning**.

| gold source | top-7 Jaccard | k overlap | Kendall tau | tier (per revised thresholds doc) |
|---|---|---|---|---|
| Opus 4.8 (trained against) | 1.000 | 7/7 | +0.874 | k=7 (training fit) |
| GPT-5 (codex CLI default) | 0.750 | 6/7 | +0.811 | **k=6 / hybrid-lifts** |
| GPT-5.5-pro (API direct) | 0.750 | 6/7 | +0.747 | **k=6 / hybrid-lifts** |

Same k-bucket result across two different OpenAI tiers. The
disagreement is on a single claim — the seventh slot:

- Opus → REQ-017 (litigation + rep + statute-45d + $350K)
- GPT-5 → REQ-006 (statute-14d)
- GPT-5.5-pro → REQ-018 (complaint + rep)
- Tuned ranker → REQ-017

Three different "marginal seventh" picks across the three LLMs. That's
genuine adjuster-judgment ambiguity in the contested top slice, not a
deterministic-vs-LLM gap. An LLM materiality re-rank layer won't
necessarily fix it because the LLMs themselves disagree on which claim
deserves the seventh slot.

## Revised verdict

**HYBRID LIFTS.** Tuned-S1 reaches k=6 against an independent gold,
clearing the mid tier on top-7 and the high tier on tau (+5σ above
noise). That's a credible base for the today's-work slice. The k=7
result against Opus was inflated by same-family-tuning bias. Building
hybrid v2 (LLM materiality re-rank on the top slice) is justified.

## Hybrid v2 run — 2026-05-30

Per the locked spec (`docs/specs/triage-ranker-hybrid-v2.md`) and locked
thresholds (`docs/evals/triage-ranker-hybrid-v2-thresholds.md`), v2 was
run once: tuned-S1 top-10 handed to GPT-5.5-pro as materiality judge,
re-ranked slice spliced back in front of S1's tail. Scored against the
same two independent golds used in v1 verification.

| gold | S1 k | v2 k | Δk | S1 tau | v2 tau | Δtau | tau in tolerance? |
|---|---|---|---|---|---|---|---|
| gpt5 | 6 | **5** | **−1** | +0.811 | +0.811 | +0.000 | yes |
| gpt55pro | 6 | 6 | 0 | +0.747 | +0.768 | +0.021 | yes |

**Verdict per locked thresholds: DO NOT SHIP V2.** v2 regressed below
the k=6 baseline on the GPT-5 gold and held flat on the GPT-5.5-pro
gold. Per the rule "k≤5 on either → do not ship," v2 fails on its first
run. Per the locked single-run rule, no re-run is permitted.

**What the judge did.** GPT-5.5-pro promoted REQ-017 (lit+rep+statute-45d)
and REQ-018 (complaint+rep) into its top-7 by applying explicit
"litigation+statute under 60 days = top-3" and "complaint+rep needs
same-day acknowledgment" rules — judgment the linear scorer cannot apply.
This matched GPT-5.5-pro-as-gold's instinct on REQ-018, but kicked out
REQ-005 and REQ-006 (statute-7d and statute-14d) that GPT-5-as-gold had
in its top-7. The v2 judge has its own priority interpretation; it
aligned with one gold and diverged from the other.

**Read in plain English.** Three different LLMs (Opus, GPT-5,
GPT-5.5-pro) produced three different gold rankings with three different
"marginal seventh" picks. The v2 judge (a fourth LLM call, also
GPT-5.5-pro but in re-rank mode with more context) picked yet another
ordering that disagreed with two of the three. This is the diagnostic:
the contested top-slice is **genuine adjuster judgment ambiguity**, not
a calibration problem the linear scorer can't reach. No single judge —
LLM or otherwise — closes the disagreement, because the disagreement
isn't about what the features say; it's about how a particular adjuster
weighs litigation-risk vs time-pressure vs escalation-flags vs incurred
exposure.

**Net of v1 + v2 verdicts:** ship deterministic S1 with the tuned
weights from `tuned_weights.json`. v2 is dead — the LLM materiality
re-rank as designed does not earn its keep on independent golds.

The architectural lesson from v2 is captured in
`docs/specs/triage-ranker-policy-engine.md`: triage should be a
deterministic policy engine (gates on absolute thresholds) + within-
bucket linear scoring + LLM only for extraction and materiality. Free-
form LLM ranking is an oracle problem with no canonical answer. The
next serious triage iteration should be built from that architecture,
not from another iteration of the linear-scorer-plus-LLM-judge pattern.

## Known inert feature in the tuned vector

`w_reserve = 5.972` is a dead weight. `reserve_adequacy_gap` is
hardcoded to `0.0` in `src/argos/services/triage/features.py` until a
Reserve specialist runs and populates a recommended-reserve value. With
all 20 requests at 0, per-caseload min-max normalization with epsilon
returns 0.0 for every request, so the weight multiplies zero
regardless of value. The tuner's 5.972 is a random draw with no effect
on the result. The Reserve specialist work is when this weight becomes
real.
