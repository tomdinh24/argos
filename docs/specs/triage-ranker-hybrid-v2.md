---
tags:
  - project/argos
  - type/spec
  - status/draft
created: 2026-05-30
---

# Triage ranker — hybrid v2 (LLM materiality re-rank)

## Why v2 exists

The deterministic S1 ranker (v1, shipped as `services/triage/ranker.py`)
reaches **k=6** top-7 overlap against independent OpenAI golds (GPT-5
and GPT-5.5-pro). Both LLMs agreed on 6 of 7 today's-work claims but
contested the 7th slot — three different rankers picked three different
"marginal seventh" claims:

- Opus 4.8 → REQ-017 (litigation + rep + statute-45d + $350K)
- GPT-5 → REQ-006 (statute-14d, otherwise clean)
- GPT-5.5-pro → REQ-018 (complaint + rep)
- Tuned S1 → REQ-017

The disagreement is on materiality, not data: every ranker has the same
12 features visible. The deterministic linear scorer cannot apply
adjuster judgment like "litigation + statute under 60d auto-promotes to
top-3 regardless of other features." That class of reasoning is what v2
adds.

Per the locked thresholds doc, this is "hybrid lifts" territory: S1
stays the base; v2 is a thin LLM re-rank layer on the contested top
slice.

## What v2 is NOT

- Not a replacement for S1. S1 still ranks all 20.
- Not a per-claim specialist. It does not generate analysis, drafts,
  reserves, or anything else — just a re-ranking of N claims.
- Not stateful. One call, one re-ranked top slice.
- Not interactive. No human-in-the-loop in v2; that's a v3 concern.

## Architecture

```
Caseload  ─►  S1.rank()  ─►  full ordering (20)
                              │
                              ▼
                         top-N slice ──►  LLM materiality judge
                                                │
                                                ▼
                                         re-ranked top-N
                              │
                              ▼
                    final output: re-ranked top-N + S1's tail (N+1..20)
```

The re-rank only touches the top-N slice. Claims below position N keep
their S1 ordering — there's no signal that LLM judgment helps the
bottom-13 (k≤5 on independent gold is structural-not-calibration
territory per the thresholds doc).

## Locked design choices

### N — the size of the re-ranked slice

**N = 10.** Justification: v1 evidence shows the disagreement is
concentrated in the top ~7-9 (the contested 7th claim moves between
rank 7 and rank 9 across the three LLM golds). N=10 covers the
contested band with one slot of headroom. Larger N (say 15) would dilute
the LLM's attention across less-contested mid-pack claims; smaller N
(say 7) would miss boundary cases where S1 puts a real top-7 claim at
rank 8.

### Materiality judge model

**GPT-5.5-pro** (OpenAI Responses API). Reasoning:

- Independent family from Opus 4.8 (which produced one of the golds).
  Using Opus as judge against Opus gold re-introduces the same-family
  bias that v1 just measured (k=7 inflated to k=6 when family changed).
- Stronger than Sonnet 4.6 on judgment-heavy tasks per recent
  benchmarks; closer to Opus 4.8 in capability tier.
- Already validated end-to-end in the v1 cross-model gold generation.

The judge model is locked in this spec. Swapping the judge invalidates
the v2 eval (different judge = different experiment).

### What the judge sees per claim

The same 12-feature block the gold-ranking prompts showed Opus and
GPT-5.5-pro, plus three additions only available at re-rank time:

1. **S1's rank for the claim** (1..N). So the judge knows what the
   deterministic ranker thought.
2. **The S1 score components per feature.** So the judge can see "this
   claim has SLA firing AND high incurred AND lit/rep all stacked," not
   just the final score.
3. **Recent communications summary.** First two `Communication` rows
   per claim (most recent first). Adds materiality context without
   adding the full document corpus.

Documents themselves are NOT shown in v2. Materiality of documents is
a v3 concern (requires a per-claim Document Reader step that does not
exist yet).

### Output contract

The judge returns a re-ranked list of N request_ids, ranks 1..N, with
a one-line reason per claim. Same CSV schema as the gold:

```csv
rank,request_id,reason_short
1,REQ-XXX,one-line reason
...
N,REQ-XXX,one-line reason
```

Schema enforced by post-parse validation:
- Exactly N rows, ranks 1..N, no gaps, no duplicates.
- Every request_id appears exactly once.
- request_ids are a subset of the input top-N slice (judge cannot
  introduce claims from the tail).

Any validation failure = LLM call fails the eval (no retry logic in v2;
the failure rate IS data).

### Determinism

LLM calls are not deterministic. v2 runs the judge **once** per
benchmark; reproducibility of the *result* is not claimed. Reproducibility
of the *procedure* (same spec, same fixture, same prompt template) is.
For the benchmark, the judge is called with `temperature=0` (or the
GPT-5.5-pro equivalent) to minimize per-call variance, but variance is
expected.

## Eval methodology

### Pre-registered thresholds

Locked in `docs/evals/triage-ranker-hybrid-v2-thresholds.md` (this
spec + thresholds get committed together before any v2 run).

### Comparison structure

v2 is benchmarked against the SAME two independent golds used in v1
verification: `gold_gpt5.csv` and `gold_gpt55pro.csv`. **The Opus gold
is NOT used for v2** — it's contaminated by being the gold the v1
weights were tuned against, and reusing it would make v2 look better
than it is by exact-match-fitting Opus.

| metric | benchmark slice | what it measures |
|---|---|---|
| v1 k against gold_gpt5 | top-7 | S1 baseline (k=6) |
| v2 k against gold_gpt5 | top-7 | does LLM re-rank lift S1 by one bucket? |
| v1 k against gold_gpt55pro | top-7 | S1 baseline (k=6) |
| v2 k against gold_gpt55pro | top-7 | same question, second gold |
| v1 tau against both | full N=20 | S1 baseline (tail unchanged → tau holds) |
| v2 tau against both | full N=20 | does re-rank degrade ordering? |

### Verdict structure (locked in the thresholds doc)

- **v2 lifts both golds to k=7** → ship hybrid v2; it earns its keep.
- **v2 lifts one gold, the other stays at k=6** → mixed signal; investigate
  why the LLM helps one judge and not the other before shipping.
- **v2 stays at k=6 on both** → the 7th-claim disagreement is genuine
  adjuster ambiguity, not closeable by LLM judgment. Defer hybrid;
  ship S1 as v1.
- **v2 drops to k≤5 on either** → LLM re-rank actively hurts; do not
  ship.
- **v2 tau drops materially (>0.1) on either gold** → re-rank is
  scrambling the top slice in ways that hurt ordering even if the SET
  improves; flag for investigation.

### Failure modes that flip the eval to FAIL regardless of metric values

- Judge output fails schema validation (wrong N, duplicate IDs, IDs
  not in input slice).
- Judge model changed between this spec lock and the benchmark run.
- N changed between this spec lock and the benchmark run.
- Gold CSVs regenerated between v1 commit and v2 run.

## Implementation surface

| file | purpose |
|---|---|
| `docs/specs/triage-ranker-hybrid-v2.md` | this spec |
| `docs/evals/triage-ranker-hybrid-v2-thresholds.md` | locked thresholds (next file to write, before any code) |
| `src/argos/services/triage/hybrid.py` | the re-rank layer; pure orchestration around the OpenAI Responses API |
| `scripts/run_triage_hybrid_benchmark.py` | runs v2 against both independent golds, computes deltas vs v1, applies locked thresholds |
| `tests/triage/test_hybrid.py` | schema validation tests, slice-only tests, deterministic-fixture tests (no live API calls in pytest — those go in scripts) |

## What v2 explicitly does NOT prove

- Generalization to a fresh caseload. Same N=20 fixture as v1.
- Robustness across judge model swaps. Locked to GPT-5.5-pro.
- Production deployability. No latency, cost, error-rate measurement
  in scope.

All three are v3 concerns. v2's question is narrow: *does an LLM
materiality re-rank close the v1 k=6 → k=7 gap on independent golds?*
