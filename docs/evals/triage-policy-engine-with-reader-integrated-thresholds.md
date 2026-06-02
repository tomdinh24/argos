---
tags:
  - project/argos
  - type/eval-thresholds
  - status/locked
created: 2026-05-31
locked_before_run: true
---

# Triage policy engine + Document Reader integration — locked thresholds

**Locked before any model run.** Same single-run discipline as v1/v2/v3
of triage and v1/v2 of the Reader. This document pins:

1. The extended N=20 fixture (`build_caseload_with_realistic_docs`)
   with realistic document bodies on selected claims.
2. The pre-registered Reader output for each unread doc.
3. The pre-registered bucket gold (without and with Reader integration).
4. The pre-registered top-7 orderings (baseline and integrated).
5. The pass/fail rules for the integration.

The v3 policy-engine spec, thresholds, and run remain unchanged. This
is a separate experiment built on top of v3, not a re-evaluation of
it. The v3 fixture (`build_caseload`) stays untouched; the integration
uses a new fixture function.

## What integration changes

Triage v3 bucket 6 trigger today:

```
incurred ≥ $250K  AND  unread_document_count ≥ 1
```

After integration:

```
incurred ≥ $250K  AND  material_unread_document_count ≥ 1
```

`material_unread_document_count` = of the unread docs on this claim,
how many did the Reader classify as `material=True`.

The policy engine stays pure (no LLM calls inside `rank_policy()`).
The Reader runs separately, produces a `relevant_doc_counts: dict[claim_id, int]`,
and `rank_policy()` accepts it as an optional parameter. When `None`,
behavior is identical to v3 (uses raw `unread_document_count`).

## Extended fixture — pinned changes from v3

Only 5 claims get realistic document bodies; the other 15 keep their
v3 state. Each body is pinned verbatim below so the Reader's output is
reproducible.

### REQ-007 (hi-cat, $1.75M catastrophic auto BI)

**v3 state:** 0 unread docs → bucket 7.
**Integration state:** 2 unread docs, 1 inert + 1 material.

- **Doc 1 (inert):** Routine adjuster correspondence acknowledging
  receipt of claimant counsel's last status request. Pre-registered
  Reader output: `material=False`, `posture_changed=None`.
- **Doc 2 (material — reserve posture):** Treating-provider medical
  records with new MRI finding ("MRI dated 2026-05-15 reveals C5-C6
  disc herniation with nerve root impingement") and surgical cost
  estimate ("Estimated cost of cervical discectomy and fusion:
  $85,000–$120,000"). Pre-registered Reader output: `material=True`,
  `posture_changed="reserve"`, excerpt overlaps the MRI/cost sentence.

**Reader integration impact on REQ-007:** `relevant_unread_count = 1`,
which combined with `incurred ≥ $250K` → bucket 6 fires.
Pre-integration: B7. Post-integration: **B6** (Reader promotes).

### REQ-008 (hi-serious-1, $585K serious auto BI)

**v3 state:** 0 unread docs → bucket 7.
**Integration state:** 1 unread doc, inert.

- **Doc 1 (inert):** Routine acknowledgment letter from co-defendant
  carrier's counsel ("we are still reviewing your tender, please
  expect a response within 30 days"). Pre-registered Reader output:
  `material=False`, `posture_changed=None`.

**Reader integration impact on REQ-008:** `relevant_unread_count = 0`.
Pre-integration: **B6** would fire on raw `unread_document_count=1`.
Post-integration: B7 (Reader demotes — routine doc shouldn't trigger
B6 escalation).

### REQ-013, REQ-014, REQ-015 (unread-1, unread-2, unread-3)

These already have unread doc counts in v3 (1, 2, 3 respectively) but
with placeholder bodies. Integration replaces the placeholders with
realistic bodies so the Reader has real content to classify. None of
these claims cross the $250K incurred threshold, so B6 doesn't fire
on them regardless — bucket assignment is unchanged from v3.

- **REQ-013 (1 unread):** routine claimant status update. Reader:
  `material=False`. No bucket change.
- **REQ-014 (2 unread):** 1 routine + 1 material (e.g., a settlement
  inquiry — material=True, posture=damages). Material count = 1. No
  bucket change (below incurred threshold).
- **REQ-015 (3 unread):** 2 routine + 1 material (a co-defendant
  carrier denial — material=True, posture=coverage). Material count
  = 1. No bucket change.

The purpose of giving these claims real bodies is to exercise the
full integration pipeline end-to-end, not to move them between
buckets. They confirm the Reader is being called on every unread doc,
not just the ones that matter for bucket assignment.

## Pre-registered Reader output (9 total doc calls)

| claim | doc | expected material | expected posture |
|---|---|---|---|
| REQ-007 | doc 1 (acknowledgment) | False | None |
| REQ-007 | doc 2 (medical/MRI) | True | reserve |
| REQ-008 | doc 1 (carrier ack) | False | None |
| REQ-013 | doc 1 (status update) | False | None |
| REQ-014 | doc 1 (status update) | False | None |
| REQ-014 | doc 2 (settlement inquiry) | True | damages |
| REQ-015 | doc 1 (status update) | False | None |
| REQ-015 | doc 2 (settlement inquiry) | True | damages |
| REQ-015 | doc 3 (carrier denial) | True | coverage |

Wait — REQ-015 has 3 docs. To keep "1 material, rest routine" for
shape consistency, only doc 3 is material. Let me lock that:

| claim | doc | expected material | expected posture |
|---|---|---|---|
| REQ-007 | DOC-007-01 (acknowledgment) | False | None |
| REQ-007 | DOC-007-02 (medical/MRI) | True | reserve |
| REQ-008 | DOC-008-01 (carrier ack) | False | None |
| REQ-013 | DOC-013-01 (status update) | False | None |
| REQ-014 | DOC-014-01 (status update) | False | None |
| REQ-014 | DOC-014-02 (settlement demand) | True | damages |
| REQ-015 | DOC-015-01 (status update) | False | None |
| REQ-015 | DOC-015-02 (status update) | False | None |
| REQ-015 | DOC-015-03 (carrier tender denial) | True | coverage |

Total: **9 doc Reader calls**, **4 material** (REQ-007 doc 2,
REQ-014 doc 2, REQ-015 doc 3), **5 inert**.

Material counts by claim: `{REQ-007: 1, REQ-008: 0, REQ-013: 0,
REQ-014: 1, REQ-015: 1}`.

## Pre-registered bucket gold

### Baseline (no Reader, uses raw unread_document_count)

Only REQ-007 and REQ-008 change from v3 (they now have unread docs):

| claim | v3 bucket | baseline bucket | reason |
|---|---|---|---|
| REQ-007 | 7 | 7 → still B7 because $1.75M ≥ $250K AND unread ≥ 1, so actually fires B6 | wait — REQ-007 has $1.75M incurred + 2 unread now → **B6** |
| REQ-008 | 7 | **B6** | $585K ≥ $250K + 1 unread |
| REQ-013-015 | 7 | 7 | below $250K |

Correcting the table — both REQ-007 and REQ-008 fire B6 in baseline:

| claim | label | baseline bucket | why |
|---|---|---|---|
| REQ-007 | hi-cat | **6** | $1.75M + 2 unread docs |
| REQ-008 | hi-serious-1 | **6** | $585K + 1 unread doc |

All other claims keep their v3 buckets.

### Integrated (with Reader-supplied relevant_doc_counts)

| claim | label | integrated bucket | why |
|---|---|---|---|
| REQ-007 | hi-cat | **6** | $1.75M + 1 *material* unread (MRI) |
| REQ-008 | hi-serious-1 | **7** | $585K but 0 *material* unread (routine ack) |

REQ-013/014/015 unchanged (below incurred threshold either way).

### Pre-registered top-7 orderings

Locked-policy buckets 1–5 keep their v3 membership:
B1: REQ-001/002/003 (SLA), B2: REQ-004/005 (statute imminent),
B3: REQ-016/017 (lit + clock), B4: REQ-018 (regulatory escalation),
B5: REQ-006 (statute approaching).

**Baseline top-7 (no Reader):** {B1, B2, B3} concatenated =
`REQ-001, REQ-002, REQ-003, REQ-004, REQ-005, REQ-016, REQ-017`.

REQ-007 and REQ-008 land in B6 (positions 9, 10 ish) — but they don't
crack top-7 because there are already 7 claims in buckets 1–3.

**Integrated top-7 (with Reader):** Same as baseline. REQ-007 still
lands in B6 (position 8), REQ-008 demotes from B6 to B7.

**The integration test is NOT about top-7 changes** — the top-7
disagreement window is already settled by buckets 1–3. The integration
test is about the **B6 membership** changing because the Reader
correctly distinguishes material from routine unread docs.

## Pass/fail rules

### Q1 — Reader output matches pre-registered predictions

All 9 doc Reader calls must return the pre-registered
`material` boolean and `posture_changed` value. If any single Reader
call diverges, the integration fails on Q1. (Reader v2 already passed
4/4 anchor pairs, so this is mostly a regression check on real bodies
under realistic claim context.)

### Q2 — Baseline bucket assignment matches pre-registered baseline gold

Running `rank_policy(caseload, weights)` with `relevant_doc_counts=None`
on the extended fixture must produce:
- REQ-007 in B6
- REQ-008 in B6
- REQ-013/014/015 in B7
- All other claims in their v3 buckets

If the baseline diverges, the fixture extension introduced an
unintended side effect.

### Q3 — Integrated bucket assignment matches pre-registered integrated gold

Running `rank_policy(caseload, weights, relevant_doc_counts=reader_output)`
must produce:
- REQ-007 in **B6** (promoted by Reader catching the MRI)
- REQ-008 in **B7** (demoted by Reader catching the routine ack)
- REQ-013/014/015 in B7 (Reader-classified but below incurred threshold)
- All other claims in their v3 buckets

### Composite

PASS only if Q1 + Q2 + Q3 all pass. Single Q failure flips composite
to FAIL.

## Pre-committed not-allowed moves

- Cannot change fixture bodies after seeing Reader output.
- Cannot change bucket gold after seeing engine output.
- Cannot re-run Reader to "average across runs."
- Cannot soften the bucket-membership rule to "REQ-007 lands in
  any high-priority bucket."
- One shot per Reader call. One shot for the engine.

## What success demonstrates

The Reader and the policy engine working together on the same
caseload, end-to-end. Specifically:

- The Reader correctly classifies routine vs material content on
  realistic (not anchor-pair-paired) document bodies, in realistic
  claim context.
- The policy engine's B6 trigger swaps cleanly from raw unread count
  to material unread count via the `relevant_doc_counts` parameter — no
  refactor needed.
- The integration correctly **promotes** a claim that was hiding
  (REQ-007) and **demotes** a claim that was falsely escalating
  (REQ-008).

This is the architectural payoff promised by the v3 spec: policy
engine + LLM extraction working together, each doing what it's
actually good at, with the LLM nowhere in the ranking decision.
