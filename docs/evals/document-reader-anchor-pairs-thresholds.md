---
tags:
  - project/argos
  - type/eval-thresholds
  - status/locked
created: 2026-05-31
locked_before_run: true
---

# Document Reader — anchor-pair thresholds

**Locked before any model run.** Defines what counts as "the Reader
classifies materiality from evidence" vs "the Reader pattern-matches on
priors." If the criteria below are not met, the eval fails — regardless
of how plausible individual outputs look in isolation.

This is the same paired-anchor pattern that
`docs/evals/coverage-anchor-pair-thresholds.md` uses, applied to a
narrower output (boolean + posture + reason + excerpt) and across four
pairs (one per posture).

## The four anchor pairs

Each pair shares: same claim context, same document metadata
(`document_id`, `document_type`, `source`, `received_date`), same
opening paragraph. Variants differ by **one added material sentence**
in Variant B's body.

### Pair 1 — Liability posture (police report)

- **Claim context:** auto BI, severity=serious, reserve=$80K,
  litigation=False, rep=False. Loss facts: two-car intersection
  collision, fault ambiguous in initial intake.
- **Document:** `document_type=police_report`, source=law_enforcement.
- **Variant A body:** boilerplate police report narrative with crash
  diagram references, vehicle descriptions, weather. **No fault
  determination, no citation issued.**
- **Variant B body:** A + one added sentence: *"Officer determined
  V-1 driver failed to yield right of way at uncontrolled intersection
  in violation of Florida Statute 316.123(2); citation issued to V-1
  driver at scene."*
- **Expected (A):** `material=False`, `posture_changed=None`,
  `text_excerpt=""`.
- **Expected (B):** `material=True`, `posture_changed="liability"`,
  `text_excerpt` quotes (or paraphrases) the fault/citation sentence.

### Pair 2 — Coverage posture (co-defendant carrier denial)

- **Claim context:** commercial auto BI, severity=serious,
  reserve=$200K, litigation=True, rep=True. Co-defendant carrier
  tender pending.
- **Document:** `document_type=correspondence`,
  source=other_carrier_counsel.
- **Variant A body:** courteous status letter from co-defendant
  carrier's counsel: "we are still reviewing your tender, please
  expect a response within 30 days."
- **Variant B body:** same opening + added paragraph: *"After review,
  Acme Mutual declines your tender of defense and indemnity. Our
  position is that the cooperative-defense clause in the underlying
  contract does not extend to claims arising from your insured's
  independent acts. We will not be participating in defense."*
- **Expected (A):** `material=False`, `posture_changed=None`.
- **Expected (B):** `material=True`, `posture_changed="coverage"`,
  `text_excerpt` quotes the denial sentence.

### Pair 3 — Damages posture (demand letter with number)

- **Claim context:** auto BI, severity=serious, reserve=$120K,
  litigation=False, rep=True. Pre-suit demand period.
- **Document:** `document_type=demand_letter`,
  source=claimant_counsel.
- **Variant A body:** opening pleasantries, history of the matter,
  recap of medical treatment received to date, request for "open
  dialogue regarding resolution."
- **Variant B body:** same + added paragraph: *"Accordingly, our
  client hereby demands the policy limits of $300,000.00 to fully
  resolve all claims against your insured. This demand is open for
  acceptance through July 15, 2026, after which date we will proceed
  with formal litigation."*
- **Expected (A):** `material=False`, `posture_changed=None`.
- **Expected (B):** `material=True`, `posture_changed="damages"`,
  `text_excerpt` quotes the demand number (or the deadline).

### Pair 4 — Reserve posture (medical update with new diagnosis)

- **Claim context:** auto BI, severity=standard, reserve=$25K,
  litigation=False, rep=False. Claimant medical treatment ongoing.
- **Document:** `document_type=medical_records`,
  source=treating_provider.
- **Variant A body:** routine progress note. "Patient reports ongoing
  cervical strain symptoms, currently in physical therapy 2x/week,
  no medication changes, no new findings."
- **Variant B body:** same + added paragraph: *"MRI dated 2026-05-15
  reveals C5-C6 disc herniation with nerve root impingement; patient
  has been referred to neurosurgical consultation. Surgical
  intervention may be indicated if conservative treatment fails over
  the next 60 days. Estimated cost of cervical discectomy and
  fusion: $85,000–$120,000."*
- **Expected (A):** `material=False`, `posture_changed=None`.
- **Expected (B):** `material=True`, `posture_changed="reserve"`,
  `text_excerpt` quotes either the diagnosis or the cost estimate.

## Per-variant pass criteria

For each of the 8 variant runs (4 pairs × 2 variants):

1. Output validates against `MaterialityCall` schema (Pydantic).
2. `text_excerpt` non-empty iff `material == True`.
3. `posture_changed != None` iff `material == True`.
4. When `material == True`, `text_excerpt` is a substring (or
   ≥80% character overlap with) the input document body. Hallucinated
   excerpts fail.
5. The boolean `material` matches the expected value.
6. When `material == True`, `posture_changed` matches the expected
   posture.

## Paired delta criteria — must hold for each pair

The paired structure is the actual bias test (otherwise the model could
always-pass by returning `material=True`):

7. **Materiality flip.** `call(B).material == True` AND
   `call(A).material == False`. Both must hold for the pair to pass.
8. **Excerpt directionality.** On Variant B, `text_excerpt` quotes (or
   ≥80%-overlaps) the *added* sentence from the B body — not a
   sentence that was already in the A body. On Variant A, `text_excerpt`
   is empty.

## Composite pass rule

The Reader v1 ships iff **all 4 pairs pass** all 8 criteria (1–6
per-variant, plus 7–8 paired). A single pair failure flips the
verdict to FAIL. This is intentionally strict: 4 pairs is small enough
that uniform success matters more than ratio.

## Failure modes that flip the verdict regardless of metrics

- Any schema validation error on any of the 8 variant runs.
- Any `text_excerpt` that does not appear in the cited document body
  (hallucination).
- Reader returns a `posture_changed` value not in the locked enum
  (`{reserve, liability, coverage, damages, None}`).
- Reader runtime raises after exhausting retries.
- Anchor-pair fixture changes between this doc's commit and the eval
  run.

## Pre-committed not-allowed moves

- Cannot change pair definitions after seeing model output.
- Cannot re-run after a failure to "average across runs." One shot
  per pair, same as triage v1/v2/v3.
- Cannot soften the substring/overlap rule for `text_excerpt`. If the
  Reader fails on quoting precision, that *is* the result.
- Cannot add a 5th anchor pair to pad the success ratio.

## How a passing eval reads

> Pair 1 (liability) — Variant A: material=False ✓. Variant B:
> material=True, posture=liability ✓, excerpt quotes "Officer
> determined V-1 driver failed to yield…" ✓. Pair passes.
>
> Pair 2 (coverage) — Variant A: material=False ✓. Variant B:
> material=True, posture=coverage ✓, excerpt quotes "Acme Mutual
> declines your tender of defense…" ✓. Pair passes.
>
> Pair 3 (damages) — passes.
>
> Pair 4 (reserve) — passes.
>
> **PASS.** Reader classifies materiality from evidence on all 4
> postures.

## How a failing eval reads

> Pair 1 (liability) — Variant B: material=True ✓, posture=liability ✓,
> excerpt quotes "weather was clear and dry…" — sentence is in
> Variant A body, not the added sentence. Excerpt directionality
> FAILS. Pair fails. **OVERALL FAIL** even though the boolean was
> right — Reader is pattern-matching on document type, not reading
> the new evidence.

## Scope

Defines the v1 four-pair anchor set only. Expanding to more pairs
(8, 16) and per-document-type cuts has its own thresholds doc when
that work starts. Do not back-fit thresholds for additional pairs
into this file.
