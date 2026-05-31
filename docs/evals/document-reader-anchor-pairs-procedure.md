---
tags:
  - project/argos
  - type/eval-procedure
  - status/draft
created: 2026-05-31
---

# Document Reader anchor-pair eval — procedure + run log

Companion to `docs/evals/document-reader-anchor-pairs-thresholds.md`
(the locked thresholds, pinned before run). This file is the append-
only run log + post-run analysis. Same pattern as
`docs/evals/triage-ranker-tuning-procedure.md`.

## Methodology

Paired anchors with one added material sentence per pair. Eight model
calls per full run (4 pairs × 2 variants). Per-variant criteria
(schema valid, excerpt verbatim, material/posture match expected) +
paired criteria (materiality flip A→B, excerpt directionality). Pass
requires all 4 pairs pass; one failure flips composite to FAIL.

No re-runs after seeing the result. One shot, locked verdict.

## Anchor-pair v1 run — 2026-05-31

**Composite verdict: DO NOT SHIP — 2/4 pairs passed.**

Output: `data/eval-runs/document-reader-anchors/anchor_pairs_run.json`.

### Per-pair result

| pair | posture | A pass | B pass | flip A→B | composite |
|---|---|---|---|---|---|
| 1 | liability | ✗ | ✓ | ✗ | **FAIL** |
| 2 | coverage  | ✓ | ✓ | ✓ | **PASS** |
| 3 | damages   | ✗ | ✓ | ✗ | **FAIL** |
| 4 | reserve   | ✓ | ✓ | ✓ | **PASS** |

### What actually happened

Both failures were on Variant A returning `material=True` instead of
the expected `material=False`. On both, the Reader's reasoning was
defensible:

- **Pair 1 Variant A** (police report, no fault determination in body):
  Reader flagged the asymmetric skid marks (14ft V-1 skid, 0ft V-2
  skid) and V-2's 22-foot post-impact displacement as
  liability-posture-bearing physical evidence. Reader emitted
  `posture_changed=liability` with the skid-mark sentence as
  `text_excerpt`. The reasoning: "Physical evidence bearing directly
  on fault at an uncontrolled intersection."

- **Pair 3 Variant A** (counsel correspondence, no demand number):
  Reader flagged the updated medical specials of $18,742.50 + $4,200
  lost wages as reserve-posture-changing economic damage figures.
  Reader emitted `posture_changed=reserve` with the medical-totals
  sentence as `text_excerpt`. The reasoning: "New economic damage
  figures warrant reserve reassessment."

Pairs 2 (coverage) and 4 (reserve) had genuinely inert Variant A
bodies (routine acknowledgment / routine follow-up visit) and the
Reader correctly returned `material=False` with empty excerpt on
both.

### What this tells us

**The Reader code is working.** Across all 8 calls:

- Schema validation passed every time (no Pydantic failures, retry
  never fired).
- Every `text_excerpt` on `material=True` calls overlapped the input
  body at 1.0 (verbatim — no hallucination).
- Every paired-delta directionality check on Variant B passed at
  1.0 overlap with the added sentence.
- Every `posture_changed` enum value was valid and matched the
  fixture's expected posture on Variant B.

**The fixture is what failed.** Pair 1 Variant A and Pair 3 Variant A
were not actually inert controls — they contained genuine
posture-relevant content (skid-mark physics, medical specials totals)
that a competent Reader will correctly flag. The Reader is being
*more* discriminating than my fixture assumed, not less.

This is the *good* failure mode. The opposite mistake — Reader
returns `material=True` for genuinely routine content because it
pattern-matches on document type — is what the paired-anchor design
exists to catch. We instead caught my own fixture-design bug.

### What is NOT allowed (per locked thresholds)

- Cannot re-run after seeing the result.
- Cannot soften the expected-material rule to "agree with my
  interpretation" — the fixture said Variant A is `material=False`,
  the Reader said `material=True` on two of them, that is a fail.
- Cannot back-fit a 5th anchor pair to pad the success ratio.
- Cannot quietly edit Variant A bodies and re-run without writing a
  new locked-before-run thresholds doc.

### What IS allowed (next iteration)

- Write `docs/evals/document-reader-anchor-pairs-v2-thresholds.md`
  with strictly inert Variant A bodies (no skid-mark physics, no
  specific dollar totals, no medical-treatment specifics that could
  bear on reserves). Lock it, commit, then re-run.
- The 2 passing pairs (coverage, reserve) can be carried into v2
  unchanged — they validate the methodology on truly inert controls.
- The 2 failing pairs (liability, damages) need their Variant A
  bodies redesigned to be genuinely routine: pure formality, no
  content a competent adjuster would treat as actionable.

### Architectural status

Reader v1 is not shippable per the locked rule. But:

- The Reader runtime is production-quality (Pydantic-validated tool
  use, retry on validation failure, verbatim citation enforced in
  the verifier layer).
- The eval methodology held discipline — it caught my fixture-design
  bug instead of letting a soft pass through.
- The 2 passing pairs are *positive evidence* that the policy-engine-
  plus-LLM-extraction architecture works as designed on truly inert
  controls.

### The lesson worth carrying

Paired-anchor evals demand Variant A be **fully inert** — not just
"the routine version of this document type." Any claim-relevant
content (specific numbers, physical evidence, named diagnoses) is
material content in the eyes of a competent Reader, and putting it
in a "control" variant invalidates the pair.

This is generalizable beyond Document Reader: any anchor-pair eval
where the discriminating signal is "did the model notice the added
fact" requires the unmodified variant to contain nothing the model
should reasonably flag. Easy to get wrong by accident — easier when
synthesizing realistic-looking documents — and the cost is a fail
on the locked verdict.

### Next steps

1. Commit this run's artifacts as the honest record (fail verdict,
   fixture-design lesson, working Reader code).
2. Capture the lesson in project learnings.
3. Defer Reader v2 (cleaner Variant A bodies) until the broader
   project priorities are clearer — the Reader's role in the policy
   engine integration story may not need a 4-pair eval to begin
   with; a single-pair smoke check + integration test might be
   enough to validate B6/B7 wiring.
