---
tags:
  - project/argos
  - type/eval-thresholds
  - status/locked
created: 2026-05-30
---

# Triage ranker — policy-engine thresholds (LOCKED)

Pre-registered. Same discipline as v1 + hybrid-v2: thresholds and the
gold (bucket assignments) get written and committed BEFORE the policy
engine code runs against the fixture. The verdict is whatever the
locked rules say it is, no spin.

The spec this implements is `docs/specs/triage-ranker-policy-engine.md`.

## What is locked here

1. The bucket triggers (Boolean expressions over `RawFeatures`).
2. The bucket precedence order.
3. The within-bucket scorers.
4. The per-claim bucket assignment for the N=20 fixture (the *bucket
   gold*).
5. The pass / fail rules vs v1 and vs the two independent LLM golds.

Once committed, none of the above changes for the benchmark run. A
change to any of them invalidates the experiment.

## Bucket triggers (raw-feature thresholds, absolute not relative)

Evaluated in order. First match wins. Every claim lands in exactly
one bucket.

| # | bucket | trigger |
|---|---|---|
| 1 | **same-day mandatory** | `hours_until_sla_breach < 24.0` |
| 2 | **statute imminent** | `days_until_statute <= 7` |
| 3 | **litigation + clock** | `litigation_flag == 1.0` AND (`days_until_statute <= 60` OR `open_diary_count >= 1`) |
| 4 | **regulatory escalation** | `complaint_flag == 1.0` |
| 5 | **statute approaching** | `7 < days_until_statute <= 30` |
| 6 | **high exposure + action trigger** | `incurred_amount >= 250_000` AND (`unread_document_count >= 1` OR `open_diary_count >= 1`) |
| 7 | **routine work** | everything else (no other trigger fired) |

Two notes on the threshold choices:

- `incurred ≥ $250K` for bucket 6 is a placeholder carrier policy.
  In a real deployment this is configurable per shop. Locking it here
  so the benchmark is reproducible.
- Bucket 4 fires on any complaint flag. A real carrier policy would
  distinguish regulator complaint (DOI, BBB) from internal complaint.
  Fixture only has `complaint_doi` so the distinction does not bite
  here — captured as a known carrier-config TODO in the spec.

## Within-bucket scorers (deterministic, no LLM)

Sort within each bucket by these keys; ties broken in the order listed.

| bucket | primary sort | tiebreak 1 | tiebreak 2 |
|---|---|---|---|
| 1 | `hours_until_sla_breach` asc | `severity_tier_score` desc | `incurred_amount` desc |
| 2 | `days_until_statute` asc | `severity_tier_score` desc | `incurred_amount` desc |
| 3 | `min(days_until_statute, 0 if open_diary_count >= 1 else 999)` asc | `severity_tier_score` desc | `incurred_amount` desc |
| 4 | `days_since_claimant_contact` desc | `severity_tier_score` desc | `incurred_amount` desc |
| 5 | `days_until_statute` asc | `severity_tier_score` desc | `incurred_amount` desc |
| 6 | `incurred_amount` desc | `unread_document_count + open_diary_count` desc | `severity_tier_score` desc |
| 7 | S1 tuned weighted sum desc (drop `reserve_adequacy_gap`, which is inert) | `request_id` asc |

Final tiebreak everywhere: `request_id` ascending (alphabetical).

## Bucket gold for the N=20 fixture

Pre-registered. This is the assignment the policy engine must
reproduce; failing to match it = policy engine bug, not metric loss.

| request_id | label | bucket | why |
|---|---|---|---|
| REQ-001 | sla-1h | 1 | SLA 1h |
| REQ-002 | sla-4h | 1 | SLA 4h |
| REQ-003 | sla-6h | 1 | SLA 6h |
| REQ-004 | stat-3d | 2 | statute 3d |
| REQ-005 | stat-7d | 2 | statute 7d (boundary, inclusive) |
| REQ-006 | stat-14d | 5 | statute 14d (in 8–30 window) |
| REQ-007 | hi-cat | 7 | $1.75M but no unread doc / no overdue diary |
| REQ-008 | hi-serious-1 | 7 | $585K but no trigger |
| REQ-009 | hi-serious-2 | 7 | $875K but no trigger |
| REQ-010 | aged-15d | 7 | aged, no clock, no exposure-with-trigger |
| REQ-011 | aged-21d | 7 | same |
| REQ-012 | aged-30d | 7 | same |
| REQ-013 | unread-1 | 7 | $18K below $250K threshold |
| REQ-014 | unread-2 | 7 | $55K below threshold |
| REQ-015 | unread-3 | 7 | $90K below threshold |
| REQ-016 | lit-rep-1 | 3 | litigation + overdue diary (clock) |
| REQ-017 | lit-rep-2 | 3 | litigation + statute 45d (≤60d) |
| REQ-018 | complaint-doi | 4 | complaint flag (no SLA, so not bucket 1) |
| REQ-019 | bb-minor-1 | 7 | minor, no clock |
| REQ-020 | bb-minor-2 | 7 | minor, no clock |

**Bucket distribution:** 1→3, 2→2, 3→2, 4→1, 5→1, 6→0, 7→11.

**Expected top-7 (concat in bucket order):**
`{REQ-001, REQ-002, REQ-003, REQ-004, REQ-005, REQ-016 or REQ-017,
REQ-017 or REQ-016}` — order of 016 vs 017 inside bucket 3 decided
by the within-bucket sort.

REQ-016: `open_diary_count >= 1` → effective clock = 0 days; statute
sentinel. REQ-017: statute 45d, `open_diary_count = 0`. Sort key for
B3 is `min(stat, 0 if diary>=1 else 999)` asc → REQ-016 (0) before
REQ-017 (45). So the **locked top-7** is:

```
1. REQ-001 (B1, SLA 1h)
2. REQ-002 (B1, SLA 4h)
3. REQ-003 (B1, SLA 6h)
4. REQ-004 (B2, stat 3d)
5. REQ-005 (B2, stat 7d)
6. REQ-016 (B3, lit + overdue diary)
7. REQ-017 (B3, lit + stat 45d)
```

## Verdict rules — what counts as a pass

The policy engine is benchmarked on three orthogonal questions.

### Q1 — Bucket-assignment accuracy (the new primary metric)

Does the engine assign each claim to its locked bucket?

| outcome | rule | meaning |
|---|---|---|
| **PASS** | 20/20 bucket matches | engine implements the policy correctly |
| **FAIL** | <20/20 bucket matches | engine has a bug — fix and re-run, the only legitimate re-run |

This metric has no random noise. 20/20 or bust.

### Q2 — Top-7 overlap (k) against the two independent LLM golds

Compute k = |policy top-7 ∩ gold top-7| against `gold_gpt5.csv` and
`gold_gpt55pro.csv`. v1 hit k=6 on both. The policy engine top-7 is
fully determined by the bucket gold above.

| outcome on (gpt5, gpt55pro) | verdict |
|---|---|
| (k=7, k=7) | extraordinary; investigate gold contamination before celebrating |
| (k=6, k=6) | **equivalent to v1 on the set metric**; ship — the operational shape is the win, not the k |
| (k=6, k=7) or (k=7, k=6) | mixed lift; ship — strictly ≥ v1 on both, strictly > v1 on one |
| (k=5, anything) or (anything, k=5) | regression on set metric; investigate before shipping. The structural argument may still justify shipping, but write the analysis first |
| (k≤4, anything) | hard fail; bucket triggers do not match what real adjuster judgment is doing — back to the spec |

### Q3 — Kendall tau on the full N=20 vs each independent gold

Compute tau against gpt5 and gpt55pro golds. v1 baselines: ~0.40
range with σ ≈ 0.16 noise floor.

| outcome | verdict |
|---|---|
| tau within 0.1 of v1 on both | ordering preserved at noise level; pass |
| tau drops > 0.1 on one | flag; the precedence-based ordering is scrambling the tail in a way that hurts the metric. Decide whether to ship |
| tau drops > 0.2 on either | hard regression; the bucket-precedence-over-score model loses ordering information v1 had |

### Pre-committed *not-allowed* moves

- Cannot change bucket triggers after seeing engine output.
- Cannot change bucket gold after seeing LLM-gold overlap.
- Cannot re-tune within-bucket scorers after seeing tau.
- Cannot rationalize a k=5 result by appealing to "the structural
  argument" without writing the structural argument first.
- One run. Same as v1 + v2.

## Why we expect k=6 on both, not k=7

The 7th-claim disagreement in v1 was 016/017 (us+Opus) vs 006 (GPT-5)
vs 018 (GPT-5.5-pro). The policy engine puts **both** 016 and 017 in
the top-7 (slots 6 and 7) because bucket 3 (lit+clock) precedes
bucket 4 (regulatory) and bucket 5 (statute approaching). So we get:

- vs gpt5 gold (which had 006 in slot 7): policy has 017 instead → k=6
- vs gpt55pro gold (which had 018 in slot 7): policy has 017 instead → k=6

Same k as v1. The point is not that the metric improves — it is that
the disagreement is now *visibly a policy call* ("lit-active-with-
clock outranks regulator-escalation") rather than an implicit weight
imbalance. A carrier who wants the opposite ordering edits one line
of the bucket table.

This is the structural lift the policy engine is paid for. If it also
moves the k metric, that is bonus, not the thesis.

## Failure modes that flip the run to FAIL regardless of metric

- Bucket gold above is incorrect for any claim (re-check spec
  before re-running).
- Engine assigns a claim to multiple buckets (precedence broken).
- Engine within-bucket sort is non-deterministic across runs.
- Within-bucket scorers consult information the spec did not list
  (drift from locked design).

## Implementation surface for the run

| file | purpose |
|---|---|
| `docs/specs/triage-ranker-policy-engine.md` | architecture spec |
| `docs/evals/triage-ranker-policy-engine-thresholds.md` | this file |
| `src/argos/services/triage/policy_engine.py` | bucket triggers + within-bucket scorers + final ordering |
| `scripts/run_triage_policy_benchmark.py` | run engine vs fixture, compute bucket accuracy + k + tau vs both independent golds, apply locked thresholds |
| `tests/triage/test_policy_engine.py` | unit tests on bucket triggers and within-bucket sort stability |

The script writes its result to `data/eval-runs/triage-ranker/policy_engine_run.json`
and prints the verdict in the same format as `run_triage_hybrid_benchmark.py`.
