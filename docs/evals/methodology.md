---
tags:
  - project/argos
  - type/eval-methodology
created: 2026-05-30
last_updated: 2026-05-30
title: Coverage specialist eval methodology — anchor pair, variance baseline, cross-model
summary: How we test whether the Coverage specialist actually reads the evidence — paired-delta on anchor variants, locked thresholds, variance baseline, Sonnet 4.6 vs Opus 4.8.
---

# Coverage specialist eval methodology

The Coverage specialist's contract is narrow: read the policy, the loss
facts, and the documentary evidence; emit per-question `Assessment`s with
calibrated probabilities; emit a `Synthesis` distribution over
`{clean_coverage, ROR, denial}`; draft the memo and the two letters. It does
**not** recommend a path. The adjuster owns the decision.

The test the eval has to answer is whether that contract is being honored
when we vary the evidence. Specifically: does adding one piece of evidence
that *should* shift the distribution actually shift it, and does the model
*cite* the new piece of evidence as the reason — or is it pattern-matching
priors and finding the citation post-hoc?

## Why an anchor pair, not a golden case

Single-fixture golden cases tell you whether a model produces output
matching one labeled answer. They do not isolate evidence-reading from prior
anchoring: a model that ignores the documents entirely and outputs a
plausible prior will pass a single-case test.

The anchor-pair design fixes this. We build two variants of the same claim,
byte-identical across every layer (policy, parties, dispatch log, recorded
statement, narrative) except for one sentence in one document. We measure
the *delta* between the two outputs. A model that anchors on priors produces
near-identical outputs on both. A model that reads the evidence moves.

The fixture lives at `src/argos/ontology/synthetic.py :: build_anchor_pair()`.
The two variants differ in exactly one place: the police report (DOC-002)
in `with_flag` contains the additional sentence

> When asked about the purpose of the trip, V-1 driver stated, "I was on my
> way home for the day."

That sentence raises a course-and-scope-of-employment question that should
move ROR mass up and clean-coverage mass down.

## Why the fixture facts are real

The accident facts (case number, location, date/time, vehicles, road
geometry, severity, traffic citation) come from NHTSA CRSS 2023 CASENUM
202304845216 — South region, urban, Monday 03/13/2023 16:42, T-intersection
on Causeway Blvd × Bermuda Ave, Tampa FL, 2019 Freightliner straight truck
front-impacted a 2022 Honda Civic. Synthesized layers: the carrier policy,
party identities, document text.

Synthesizing the *evidence layer* over real *accident facts* gives the
fixture two properties: the demo holds up under "is this realistic?"
scrutiny, and the synthesized parts are precisely the parts under test
(does the model read the policy and the documents and arrive at a
calibrated distribution?).

## Why thresholds are locked before runs

`docs/evals/coverage-anchor-pair-thresholds.md` is the contract:

1. **ROR delta** `≥ +0.05` (with_flag - clean)
2. **Clean-coverage delta (drop)** `≥ +0.05` (clean - with_flag)
3. **Course-and-scope Assessment delta** `≥ +0.05` (clean - with_flag)
4. **Citation directionality** — with_flag must cite the "home" quote;
   clean must not.

All four must hold. The thresholds were written before any model touched
the fixture. This is non-negotiable per past lesson — when thresholds are
set after measuring, marginal results get rationalized into wins. Lock the
target first, run second.

## Three post-runtime checks on top of the schema

The Pydantic schema rejects malformed outputs (missing citations,
probabilities not summing to 1.0, presence of any `recommended_*` field).
That is necessary but not sufficient. Three structural checks sit on top:

| Check | What it catches |
|---|---|
| `verify_citations` | `text_excerpt` on any citation must literally appear in the cited document body (whitespace / case / smart-quotes normalized). Catches citation hallucination. |
| `check_recommendation_prose` | Regex against memo + ROR letter + denial letter for "we recommend", "the carrier should", "our position is", etc. Catches recommendation-creep that bypasses the schema's absence of a `recommended_*` field. |
| `check_premise_grounding` | LLM judge extracts factual claims from each Assessment's `reasoning` and verifies each is supported by a cited document. Catches ungrounded reasoning that smuggles unsupported facts into the audit trail. |

These are independent of the paired-delta criteria. A run that passes the
deltas but fails any of these still fails.

## Variance baseline — the precondition for threshold-setting

The Sonnet 4.6 anchor-pair run produced these deltas:

| | clean | with_flag | Δ |
|---|---|---|---|
| ROR mass | 0.08 | 0.10 | **+0.02** |
| Clean mass | 0.90 | 0.88 | drop +0.02 |

Both deltas fall short of the locked +0.05 threshold. Eval fails.

But the eval fails uninformatively until we know how much of that +0.02 is
the model responding to the flag vs how much is run-to-run randomness on
the same input. So we ran the model 5× on the *identical* clean variant —
no evidence change, just resample.

```
       clean: mean=0.884  σ=0.0152  range=[0.870, 0.910]  Δ=0.040
         ROR: mean=0.560  σ=0.4338  range=[0.070, 0.880]  Δ=0.810
      denial: mean=0.020  σ=0.0000  range=[0.020, 0.020]
```

The clean-mass column is tight (σ ≈ 0.015). The ROR column is a coin flip
between roughly 0.08 and 0.88 — the model on the same input sometimes
emits a low-ROR distribution and sometimes a high-ROR distribution. The
distribution it picks is bimodal, not noisy-around-a-mean.

What that means: on Sonnet 4.6 with this fixture, the +0.02 inter-variant
ROR delta is well inside the σ on clean-mass and dwarfed by the σ on
ROR-mass. The eval cannot distinguish "Sonnet reads the flag and moves
+0.02" from "Sonnet would have moved ±0.02 by chance on either side." The
locked threshold (+0.05) is correctly calibrated to demand signal above
noise. The model did not produce signal above noise on this fixture.

This is the methodology insight: **σ is a precondition for setting any
threshold.** If σ is on the order of your threshold, the test is
uninformative. Codex's review of the methodology called this out
independently as the key gap.

## Cross-model — Sonnet 4.6 vs Opus 4.8

The natural next question: is the fixture too subtle, or is Sonnet 4.6 too
small for this judgment? Run the same anchor pair on Opus 4.8.

| | Sonnet 4.6 | Opus 4.8 | Threshold |
|---|---|---|---|
| ΔROR | +0.020 | **+0.040** | ≥ +0.05 |
| ΔClean drop | +0.020 | **+0.050** ✓ | ≥ +0.05 |
| Course-and-scope assessment | clean: yes / flag: **no** | clean: no / flag: **yes** | both, with Δ ≥ +0.05 |
| Citation directionality | ✓ | ✓ | ✓ |

Opus 4.8 doubles Sonnet's movement on both probability deltas, hits the
clean-drop threshold exactly, and falls 0.01 short on the ROR delta. More
significantly: Opus spawned an explicit course-and-scope assessment under
the with_flag variant that names the home-quote in its `claim_text`:

> "The vehicle was being used within the scope of business operations
> (in-scope use) at the time of loss, notwithstanding the driver's
> police-report remark about heading home." (p=0.880)

Sonnet did not produce a comparable assessment under with_flag. That is a
structural difference, not a probability difference: the locked threshold
asks not just for a probability shift but for the model to *reason about*
course-and-scope when the flag appears. Opus does; Sonnet doesn't.

Opus's variance baseline has not been measured. The +0.04 / +0.05 numbers
could still be inside Opus's own σ on this fixture. Until that's run, the
honest read on Opus is "the direction is correct on all three movement
metrics and the structural reasoning shows up, but the signal-to-noise
ratio is unconfirmed."

## Pricing — why we don't default to Opus

Opus 4.8 list price is $5/$25 per MTok input/output vs Sonnet 4.6 at
$3/$15 — ~1.7× base, and closer to 2.25× per request once the Opus
tokenizer's higher overhead is included on long-context inputs. A single
Coverage run costs ~$0.05 on Opus vs ~$0.02 on Sonnet at the current
fixture size. Variance baseline of 5 runs: ~$0.25 vs ~$0.10.

That's affordable for the eval suite, not affordable as the default
runtime if Coverage is invoked per-exposure at TPA scale. The decision
matrix:

- **Default runtime:** Sonnet 4.6 — fast, cheap, eval baseline.
- **Eval-only / hard cases:** Opus 4.8 — used to characterize the
  fixture's *upper bound* and to verify a delta is a model-capacity
  question vs a fixture-signal question.
- **Production escalation path:** if Coverage on Sonnet hits low confidence
  (`max(synthesis) < threshold`) or fails any post-runtime check, retry on
  Opus and surface both outputs to the adjuster with the disagreement
  flagged.

## What this round established

1. The paired-delta methodology works: it surfaces real differences
   between models that single-case scoring would have buried.
2. The Sonnet 4.6 baseline on this fixture is below threshold — and the
   variance baseline shows it would be below threshold regardless of how
   the flag was worded, because run-to-run noise dominates.
3. Opus 4.8 reads the fixture closer to the way a human adjuster would
   (explicit course-and-scope assessment naming the home quote) and moves
   the probability mass in the right direction by 2×.
4. The schema contract is necessary but not sufficient. Locked thresholds
   + post-runtime checks + variance baseline + cross-model comparison are
   the actual evidence that the contract is being honored.

## What this round did not establish

- Opus 4.8 variance baseline on this fixture. Until measured, the +0.04 /
  +0.05 Opus numbers are direction-correct but signal-strength-unknown.
- Whether a tuned prompt on Sonnet 4.6 closes the gap, or whether this
  fixture genuinely demands Opus-scale reasoning.
- Generalization across the full N=8 matrix (permissive-use anchor,
  exclusion anchor). That work has its own thresholds doc when it starts.

## Methodology gotchas surfaced and fixed

- **Substring matcher classified clean outcomes as ROR.** The model writes
  outcome labels in `label: explanation` form, and the explanation often
  contains the other labels' words ("Clean coverage: ... with no
  reservation needed"). The runner classified that as ROR. Fixed:
  `_classify_outcome` in `scripts/run_coverage_anchor.py` now splits on the
  label delimiter and matches only the prefix, with denial > ROR > clean
  precedence inside the prefix.
- **Course-and-scope matcher was too strict.** It required both "course"
  AND "scope" in `claim_text`. The model paraphrased ("within the scope of
  authorized use", "in furtherance of business operations") and the matcher
  reported "missing assessment." Broadened to match "scope" + any of a
  short list of operational-context words.
- **Fixture had an unintended CDL Class A vs B ambiguity.** Declarations
  required Class B; dispatch log and police report showed a license number
  starting with the letter A (`#A2241-FL`). Opus read that as a class flag
  and surfaced it as a coverage concern. Disambiguated both documents to
  state Class B explicitly with the license number separated, removing the
  fixture trap. A real CDL-class flag belongs in its own fixture, not
  smuggled in via document ambiguity.

## Files

| Path | Purpose |
|---|---|
| `docs/evals/coverage-anchor-pair-thresholds.md` | Locked thresholds. Pre-run contract. |
| `src/argos/ontology/synthetic.py :: build_anchor_pair()` | Fixture builder. |
| `scripts/run_coverage_anchor.py` | Runs both variants, prints paired-delta report. `--model` flag for cross-model. |
| `scripts/variance_baseline_coverage.py` | Runs N× on identical input, reports σ. |
| `src/argos/specialists/checks/` | Three post-runtime checks. |
| `data/eval-runs/coverage-anchor-pair/{clean,with_flag}.json` | Sonnet 4.6 results. |
| `data/eval-runs/coverage-anchor-pair-opus48/{clean,with_flag}.json` | Opus 4.8 results. |
| `data/eval-runs/coverage-anchor-variance/` | Sonnet 4.6 variance baseline (5 runs). |
