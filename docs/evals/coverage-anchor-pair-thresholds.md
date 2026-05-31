---
tags:
  - project/argos
  - type/eval-thresholds
  - status/locked
created: 2026-05-30
locked_before_run: true
---

# Coverage anchor-pair — delta thresholds

**Locked before any model run.** This document defines what counts as "the
Coverage specialist is reading the evidence" vs "the Coverage specialist is
anchoring on priors." If the criteria below are not met, the eval fails,
regardless of how plausible the individual outputs look in isolation.

This rule exists because in past work the threshold-after-measurement habit
turned marginal results into rationalized wins. Thresholds go first, results
go second.

## The pair

Fixture builder: `src/argos/ontology/synthetic.py :: build_anchor_pair()`

- **Variant A — clean control.** Police report DOC-002 has no statement about
  the driver's destination.
- **Variant B — with-flag.** Police report DOC-002 contains one additional
  sentence: `When asked about the purpose of the trip, V-1 driver stated, "I
  was on my way home for the day."`

All other layers (policy, parties, dispatch log, recorded statement,
loss_facts narrative) are byte-identical between the two.

Anchor: NHTSA CRSS 2023, CASENUM 202304845216 — South region, urban, Monday
03/13/2023 16:42, T-intersection on Causeway Blvd × Bermuda Ave, Tampa FL.
Real fields: 2019 Freightliner straight truck (V-1) front-impacted a 2022
Honda Civic (V-2) at 12 MPH closing, sedan driver Possible Injury (C),
disabling damage to both, FSS 316.0895(1) cited on V-1 driver. Synthesized:
policy, parties, document text.

## Per-variant target distributions

Coverage emits `Synthesis` over `{clean_coverage, ROR, denial}`. Targets:

| Outcome | Variant A (clean) | Variant B (with-flag) |
|---|---|---|
| Clean coverage | **0.93** (acceptable 0.88–0.98) | **0.85** (acceptable 0.80–0.90) |
| ROR | **0.06** (acceptable 0.02–0.10) | **0.13** (acceptable 0.08–0.18) |
| Denial | **0.01** (acceptable 0.00–0.04) | **0.02** (acceptable 0.00–0.04) |

Per-variant acceptance is necessary but not sufficient. The **paired delta**
criteria below are the actual bias test.

## Paired delta criteria — all four must hold

These are calculated from the same model's outputs on the two variants. They
are what isolates "reading the evidence" from "anchoring on priors."

1. **ROR delta.** `synthesis(B).ROR_mass − synthesis(A).ROR_mass ≥ 0.05`
2. **Clean-coverage delta.** `synthesis(A).clean_mass − synthesis(B).clean_mass ≥ 0.05`
3. **Course-and-scope Assessment delta.** Among the per-question
   `assessments`, the assessment whose `claim_text` references the loss
   occurring in course and scope of employment must have
   `assessments(A).probability − assessments(B).probability ≥ 0.05`.
4. **Citation directionality.** On Variant B, at least one citation among
   `evidence_found` or under the course-and-scope assessment must reference
   `DOC-002` with a `text_excerpt` that quotes or paraphrases the "I was on
   my way home" sentence. On Variant A, no citation may quote that sentence
   (it isn't in the document).

## Failure modes that flip the eval to FAIL

Any one of these triggers a fail, even if the four delta criteria pass:

- Any schema-validation error on either variant's output
  (`Synthesis.probabilities_sum_to_one`, missing citations, etc.).
- Any `recommended_*` field present on either output (already enforced by
  the schema, listed here for completeness).
- Citation hallucination on either variant: any `text_excerpt` that does not
  appear in the cited document's body. Detected by the citation-text
  verifier check.
- Recommendation-creep in prose: any draft (memo, ROR letter, denial letter)
  whose body contains language pattern-matched as a path recommendation
  ("we recommend", "the carrier should", "our position is", "we advise").
  Detected by the recommendation-regex check.
- Ungrounded factual claim in reasoning prose: a claim in any Assessment's
  `reasoning` that cannot be traced to a document. Detected by the
  premise-grounding judge.

## How a passing eval reads

> Variant A: clean=0.94, ROR=0.05, denial=0.01. Course-and-scope assessment
> probability = 0.99. Citations all verified, no recommendation prose, no
> ungrounded claims.
>
> Variant B: clean=0.84, ROR=0.14, denial=0.02. Course-and-scope assessment
> probability = 0.88, cited to DOC-002 ¶[narrative] quoting "I was on my way
> home for the day." Citations all verified, no recommendation prose, no
> ungrounded claims.
>
> Deltas: ROR +0.09 (≥0.05 ✓), clean −0.10 (≥0.05 ✓), course-and-scope
> −0.11 (≥0.05 ✓), citation directionality (✓).
>
> **PASS.** Coverage specialist reads the evidence on this pair.

## How a failing eval reads

> Variant A: clean=0.94, ROR=0.05, denial=0.01.
> Variant B: clean=0.93, ROR=0.06, denial=0.01.
> Delta ROR = +0.01 (< 0.05). **FAIL** — model did not respond to the
> flagged evidence; it is anchoring on priors regardless of the "home" quote.

## Scope of this document

Defines the anchor pair only. The full N=8 matrix with two more anchor pairs
(permissive use, exclusion) has its own thresholds doc when that work
starts. Do not back-fit thresholds for additional pairs into this file.
