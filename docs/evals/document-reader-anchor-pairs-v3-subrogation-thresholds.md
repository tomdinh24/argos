---
tags:
  - project/argos
  - type/eval-thresholds
  - status/locked
created: 2026-06-02
locked_before_run: true
extends: document-reader-anchor-pairs-v2-thresholds.md
---

# Document Reader anchor-pair v3 — `subrogation` posture (LOCKED)

**Locked before any v3 model run.** Same paired-anchor methodology as
v1 / v2 (`docs/evals/document-reader-anchor-pairs-thresholds.md`,
`docs/evals/document-reader-anchor-pairs-v2-thresholds.md`); v3 is
**additive** — it covers the new `subrogation` posture introduced on
2026-06-02 when the `PostureChanged` literal was extended from 4 → 5
values. Pairs 1–4 (liability / coverage / damages / reserve) stay
under v2; the three new pairs below cover the subrogation routing.

## Why a new posture, not a reuse of `liability` or `damages`

A consent-to-settle letter, an Arbitration Forums (AF) eligibility
notice, and a made-whole waiver all share a property: they change
the **recoverable basis** without changing fault, without changing the
demand number, and without changing the reserve. Routing them through
`liability` (the prior fallback) spuriously triggered the Liability
workflow on docs that have nothing to say about apportionment. Routing
them through `damages` would re-run Reserve on docs that don't change
the reserve. `subrogation → [recovery]` is the precise route.

## The three new anchor pairs

Each pair shares: same claim context, same document metadata
(`document_id`, `document_type`, `source`, `received_date`), same
opening paragraph. Variants differ by **one added material sentence**
in Variant B's body. Variant A bodies are pure inert administrative
shells per the v2 lesson (`paired-anchor-controls-must-be-fully-inert`).

### Pair 5 — Subrogation posture (consent-to-settle from ERISA plan)

- **Claim context:** auto BI, severity=serious, reserve=$200K,
  litigation=False, rep=True, ERISA plan participant identified
  on the file. Subrogation file open with the plan trustees.
- **Document:** `document_type=correspondence`,
  source=erisa_plan_administrator, received_date=2026-05-28.
- **Variant A body — pure inert acknowledgment:**

  > RE: Plan Participant — [Claimant Name]
  > Plan ID: TRUSTEE-2026-PP-0042
  > Your File: ARG-SUB-005-A
  >
  > Dear Claims Representative,
  >
  > This office acknowledges receipt of your correspondence dated
  > May 8, 2026 regarding the above-referenced plan participant.
  > Your inquiry has been logged and assigned to the appropriate
  > recovery analyst for review.
  >
  > Please confirm that we have the most current contact information
  > on file for your claims department, and we will respond
  > substantively within our standard review window.
  >
  > Sincerely,
  > /s/ Trustee Services Group

- **Variant B body** = Variant A + the added sentence:

  > *"Per the terms of the underlying ERISA-governed plan, the
  > Trustees consent to your insured's settlement with the third-party
  > tortfeasor in the amount of $150,000.00, subject to the plan's
  > first-dollar reimbursement right of $42,318.74 in conditional
  > payments under 29 U.S.C. §1132(a)(3) and US Airways v. McCutchen."*

- **Expected (A):** `material=False`, `posture_changed=None`,
  `text_excerpt=""`.
- **Expected (B):** `material=True`, `posture_changed="subrogation"`,
  `text_excerpt` ≥80%-overlaps the consent-with-reimbursement sentence.

### Pair 6 — Subrogation posture (Arbitration Forums eligibility / signatory notice)

- **Claim context:** auto BI, severity=standard, reserve=$45K,
  litigation=False, rep=False, recovery target identified as a
  fellow-carrier insured. AF intercompany arbitration filing under
  consideration.
- **Document:** `document_type=correspondence`,
  source=arbitration_forums, received_date=2026-05-29.
- **Variant A body — pure inert administrative confirmation:**

  > Arbitration Forums, Inc.
  > Member Services Notice
  > Account: ARG-MS-2026-1147
  >
  > Dear Member,
  >
  > This notice confirms your member account remains active and in
  > good standing. Recent administrative updates to our case
  > submission portal have been deployed; documentation is available
  > in the member portal under "Resources → Portal Updates."
  >
  > For any account-level questions, contact Member Services.
  >
  > Arbitration Forums, Inc. — Member Services

- **Variant B body** = Variant A + the added sentence:

  > *"Per our records, the adverse carrier identified in your inquiry
  > — Mercury Casualty Group, NAIC 27553 — is a current signatory to
  > the Auto Subrogation Arbitration Agreement and the dispute as
  > described falls within compulsory jurisdiction; you may proceed
  > with filing under Rule 2-1."*

- **Expected (A):** `material=False`, `posture_changed=None`,
  `text_excerpt=""`.
- **Expected (B):** `material=True`, `posture_changed="subrogation"`,
  `text_excerpt` ≥80%-overlaps the signatory-and-compulsory-jurisdiction
  sentence.

### Pair 7 — Subrogation posture (made-whole waiver signed by claimant)

- **Claim context:** auto BI, severity=serious, reserve=$120K,
  litigation=False, rep=True, claimant in active recovery negotiation
  with a health insurer who has asserted a §768.76 lien notice.
  Made-whole doctrine is the live question.
- **Document:** `document_type=executed_agreement`,
  source=claimant_counsel, received_date=2026-05-30.
- **Variant A body — pure inert routing letter:**

  > RE: [Claimant Name] — Lien Coordination
  > Your File: CLM-SUB-007
  >
  > Dear Claims Representative,
  >
  > Enclosed please find a copy of the cover page for our client's
  > file as previously requested. This is provided for your records
  > only and is not intended to alter any prior positions taken in
  > this matter.
  >
  > We will follow up separately on remaining outstanding items.
  >
  > Sincerely,
  > Reyes & Patel, P.A.

- **Variant B body** = Variant A + the added sentence:

  > *"Our client has executed the enclosed Made-Whole Waiver, expressly
  > waiving the protections of the made-whole doctrine under
  > §768.76(2)(b) and acknowledging the health insurer's first-dollar
  > reimbursement right against any third-party recovery; the executed
  > waiver is attached as Exhibit A."*

- **Expected (A):** `material=False`, `posture_changed=None`,
  `text_excerpt=""`.
- **Expected (B):** `material=True`, `posture_changed="subrogation"`,
  `text_excerpt` ≥80%-overlaps the made-whole-waiver-executed sentence.

## Per-variant pass criteria

Unchanged from v1 / v2 (same rules 1–6):

1. Output validates against `RelevanceCall` schema (Pydantic).
2. `text_excerpt` non-empty iff `material == True`.
3. `posture_changed != None` iff `material == True`.
4. When `material == True`, `text_excerpt` is a substring (or ≥80%
   character overlap) of the input document body.
5. The boolean `material` matches expected.
6. When `material == True`, `posture_changed` matches expected
   (i.e., `"subrogation"`, NOT `"liability"` or `"damages"`).

## Paired delta criteria — must hold for each pair

Unchanged from v1 / v2 (same rules 7–8):

7. **Relevance flip.** `call(B).relevant == True` AND
   `call(A).relevant == False`.
8. **Excerpt directionality.** Variant B excerpt ≥80%-overlaps the
   *added* sentence, not a sentence that was already in Variant A.

## Composite pass rule

v3 ships iff **all 3 new pairs (5, 6, 7) pass** all criteria. A single
pair failure flips the v3 verdict to FAIL. Same one-shot discipline:
no averaging, no re-running, no widening of the substring rule.

## Specific failure mode the eval is grading against

The most likely v3 failure: the Reader emits
`posture_changed="liability"` or `posture_changed="damages"` on a
Variant B subrogation artifact, because the prior 4-posture taxonomy
is what the model has stronger priors on. That's a real signal —
either the exemplar in the system prompt isn't pulling enough weight,
or the boundary between "subrogation" and "damages" needs sharpening
(e.g. when a lien notice contains both a reimbursement number AND a
damages anchor, does it route subrogation or damages?). Either way,
the eval result IS the answer; do not re-engineer the prompt mid-run.

## Same pre-committed not-allowed moves

- Cannot change pair definitions after seeing model output.
- Cannot re-run after a failure. One shot.
- Cannot soften the substring/overlap rule for `text_excerpt`.
- Cannot move a failing pair to a "v3.5" doc.
- If v3 fails: write v4 thresholds with revised pairs; do not edit v3
  after the result.

## What v3 is NOT grading

- v3 is a Layer-1 eval — model output vs locked fixtures. It does
  NOT grade whether the dispatcher correctly routes
  `subrogation → [recovery]` (that's covered by the unit test
  `test_subrogation_posture_enqueues_recovery_only` in
  `tests/services/orchestrator/test_orchestrator.py`).
- v3 is NOT grading whether Recovery does the right thing with the
  routed docs — Recovery has its own eval slice
  (`docs/evals/recovery-thresholds.md`, green 2026-06-02).

## Run history

| Date | SHA | Pair 5 | Pair 6 | Pair 7 | Composite | Notes |
|---|---|---|---|---|---|---|
| 2026-06-02 | (pending live-API run) | — | — | — | — | Locked; awaits next intentional Reader eval refresh. |
| 2026-06-02 | e2a3c32 | PASS | PASS | PASS | **SHIP (v3)** | First live run, claude-sonnet-4-6. All 7 per-variant + paired-delta checks green on every pair. Reader's Variant B `reason` text explicitly rules out `liability` and `damages` postures on Pairs 5 and 7 ("no liability or damages posture shift" / "no liability/damages shift"), which is the specific failure mode the v3 doc was grading against. Excerpt-overlap ratios = 1.0 on all three Variant Bs. Result JSON: [`data/eval-runs/document-reader-anchors/anchor_pairs_run.json`](../../data/eval-runs/document-reader-anchors/anchor_pairs_run.json). |
