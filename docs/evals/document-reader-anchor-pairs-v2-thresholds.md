---
tags:
  - project/argos
  - type/eval-thresholds
  - status/locked
created: 2026-05-31
locked_before_run: true
supersedes: document-reader-anchor-pairs-thresholds.md (v1)
---

# Document Reader anchor-pair v2 thresholds (LOCKED)

**Locked before any v2 model run.** Same paired-anchor methodology as
v1 (`docs/evals/document-reader-anchor-pairs-thresholds.md`); only
fixture changes. The lesson from the v1 run captured in
`docs/evals/document-reader-anchor-pairs-procedure.md` and in project
learnings (`paired-anchor-controls-must-be-fully-inert`):

> Variant A controls must be FULLY inert. Any claim-relevant content
> (specific dollar amounts, physical evidence like skid marks, named
> diagnoses, specific dates with significance) is material content in
> the eyes of a competent Reader.

v1 ran 4 pairs; Pairs 2 (coverage) and 4 (reserve) passed cleanly with
truly inert Variant A bodies. Pairs 1 (liability) and 3 (damages)
failed because the Variant A bodies leaked claim-relevant facts. v2
fixes those two fixtures.

## Changes from v1

| pair | v1 status | v2 change |
|---|---|---|
| 1 — liability | FAIL (Variant A leaked skid-mark physics) | Variant A body rewritten to pure procedural shell; Variant B unchanged |
| 2 — coverage  | PASS (Variant A inert) | unchanged |
| 3 — damages   | FAIL (Variant A leaked medical specials + lost wages totals) | Variant A body rewritten to pure administrative check-in; Variant B unchanged |
| 4 — reserve   | PASS (Variant A inert) | unchanged |

Variant B bodies and `added_sentence` values are unchanged across all
4 pairs. Only the two Variant A bodies are revised.

## Revised Pair 1 — Liability (Variant A)

Same claim context (auto BI, severity=serious, reserve=$80K). Same
document metadata (`document_type=police_report`,
source=law_enforcement, received_date=2026-04-25).

**New Variant A body — pure procedural shell, no findings, no physical
evidence:**

> TAMPA POLICE DEPARTMENT — TRAFFIC CRASH REPORT
> Case #: TPD-2026-04-22-3081
> Date of incident: 04/22/2026 16:42 EDT
> Location: Causeway Blvd × Bermuda Ave
>
> Officer responded to dispatch call of a two-vehicle collision.
> Two vehicles identified at scene; both drivers present and
> cooperative. Driver information, license details, and insurance
> information collected from both parties. Vehicle identifiers,
> registration, and insurance carrier recorded.
>
> No injuries claimed at scene by either driver. Vehicles were
> moved off the roadway pending tow.
>
> Investigation ongoing. Supplemental report to follow upon
> completion of scene reconstruction.

**Removed from v1 Variant A:**
- All skid-mark detail (14ft V-1, 0ft V-2)
- All post-impact displacement detail (22ft east, ~80° rotation)
- EMS transport of V-2 driver to Tampa General Hospital
- Specific vehicle damage descriptions

Variant B body = revised Variant A above + the same added sentence:

> *"Officer determined V-1 driver failed to yield right of way at
> uncontrolled intersection in violation of Florida Statute
> 316.123(2); citation issued to V-1 driver at scene."*

## Revised Pair 3 — Damages (Variant A)

Same claim context (auto BI, severity=serious, reserve=$120K,
litigation=False, rep=True). Same document metadata
(`document_type=correspondence`, source=claimant_counsel,
received_date=2026-05-12).

**New Variant A body — pure administrative check-in, no specifics:**

> RE: [Claimant] v. [Your Insured]
> Date of Loss: January 8, 2026
> Your Claim Number: CLM-ANCHOR-DAM-003
>
> Dear Claims Representative,
>
> Following up on our prior correspondence regarding the above
> matter. We continue to represent the claimant and remain available
> to discuss the file at your convenience.
>
> Please confirm receipt of the medical authorization we provided
> last month so that our records are aligned. If anything further is
> needed from our office, please let us know.
>
> Sincerely,
> /s/ Marcus Reyes
> Marcus Reyes, Esq.
> Reyes & Patel, P.A.

**Removed from v1 Variant A:**
- Total medical specials of $18,742.50
- $4,200 in documented lost wages
- "14 sessions of physical therapy and 6 sessions of chiropractic
  adjustment"
- "Limits her ability to perform her work as a dental hygienist"

Variant B body = revised Variant A above + the same added sentence:

> *"Accordingly, our client hereby demands the policy limits of
> $300,000.00 to fully resolve all claims against your insured. This
> demand is open for acceptance through July 15, 2026, after which
> date we will proceed with formal litigation."*

## Pass / fail rules — unchanged from v1

Same per-variant criteria (1–6) and paired-delta criteria (7–8):
schema valid; `text_excerpt` non-empty iff material; `posture_changed`
populated iff material; excerpt is substring (or ≥80% overlap) of
input body when material; material matches expected; posture matches
expected (when material); paired-delta materiality flip A→B; Variant
B excerpt overlaps the added sentence at ≥80%.

Same composite rule: **all 4 pairs must pass**. Single pair failure
flips composite to FAIL.

## Same pre-committed not-allowed moves

- Cannot change pair definitions after seeing model output.
- Cannot re-run after this v2 run to "average across runs." One shot.
- Cannot soften the substring/overlap rule.
- Cannot add a 5th anchor pair.
- If v2 fails: write v3 thresholds, do not edit v2 after the result.

## Expected output

If the v2 fixture redesign is correct, all 4 pairs should pass: the
Pairs 2 and 4 results from v1 reproduce (they're the same bodies),
and Pairs 1 and 3 now correctly return `material=False` on the
stripped-down Variant A bodies and continue to return `material=True`
with correct posture and correct excerpt on the unchanged Variant B
bodies.

If v2 still fails on Pair 1 or Pair 3 Variant A, the Reader is
flagging something I still didn't catch — and that's important
signal, not a problem to engineer around.
