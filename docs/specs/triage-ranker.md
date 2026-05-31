---
tags:
  - project/argos
  - type/spec
  - component/triage
created: 2026-05-30
last_updated: 2026-05-30
status: locked
supersedes_draft: 2026-05-30-initial
---

# Triage Ranker spec

> **Note (2026-05-30):** This spec describes the deterministic linear-
> weighted-sum ranker that shipped as `services/triage/ranker.py`. It
> reaches k=6 against independent OpenAI golds and is the current
> production path. A subsequent hybrid v2 attempt was killed on first
> run (see `docs/evals/triage-ranker-tuning-procedure.md`). The Codex
> post-mortem on v2 identified the architectural lesson: free-form LLM
> ranking is an oracle problem with no canonical answer. The target
> architecture for the next triage iteration is captured in
> `docs/specs/triage-ranker-policy-engine.md` — deterministic policy
> gates + within-bucket scoring + LLM only for extraction/materiality.

## Problem

An adjuster opens their software in the morning carrying 125–250 open
claims, with 8–12 new arrivals overnight, an 8-hour day, and diaries firing
on dozens of files. The first question is not "what does this claim mean"
but **"which of these do I touch today, and in what order?"** Cited in
`docs/research/adjuster-workflow.md` — Liberty Mutual benchmark 200,
Sedgwick 160+ pending, WC 170–190 pending, capped regional carriers at
125.

The pain underneath: "Spent most nights at home trying to catch up."

## Solution shape

A continuously re-ranked **work queue**. The adjuster opens the app and
sees a stack-ranked list of "Today's top N," each with a one-line reason
("SLA fires in 4h," "new police report contradicts statement," "subro SOL
in 11 days," "silent 14 days"). They click into the top item. No
dashboard, no chart, no chatbot.

The queue re-ranks on every state change across the caseload — not just when
the adjuster opens the app — so what's at the top reflects what's most
important *now*.

## Prerequisite: ontology extension

The triage ranker is the first **cross-claim** service in Argos. The
existing ontology (`src/argos/ontology/types.py`) models per-claim
entities for the Coverage specialist: Policy, PolicyPeriod, PolicyCoverage,
CoverageRequest, Document, SyntheticClaim. It does **not** yet model the
cross-claim state triage depends on. Before any ranker code, extend the
ontology with:

**New entities:**

| Entity | Purpose | Foundry analogue |
|---|---|---|
| `Claim` | The unit of adjuster work; aggregates one or more exposures | `Claim` object type |
| `AgentAction` | Audit trail of every system action on a claim (specialist run, validator pass, ranker update) | `AgentAction` object type per AGENT_ARCHITECTURE §4.4 |
| `WorkItem` | Recorded human touch on a claim (adjuster note, status change, click) | `WorkItem` / `AdjusterTouch` object type |
| `ServiceDeadline` | A named deadline attached to a claim or exposure (24h-contact, 30-day-status, custom) | `ServiceDeadline` object type |
| `ScheduledTask` | A scheduled follow-up task on a claim, with a fire date | `ScheduledTask` object type |
| `LedgerEntry` | A paid or reserved dollar event on an exposure | `LedgerEntry` object type |
| `Communication` | A recorded interaction with a party (claimant, counsel, vendor) | `Communication` object type |
| `LegalDeadline` | A legal deadline on an exposure (subro SOL, coverage notice deadline) | `LegalDeadline` object type |

**Field additions:**

- `Claim`: `opened_date`, `status` (open / closed / reopened / suspended), `severity_tier_summary`, `litigation_flag`, `rep_flag`, `complaint_flag`
- `CoverageRequest`: `severity_tier` (catastrophic / serious / standard / minor), `paid_to_date` (derived from `LedgerEntry`), `reserve_current` (derived from `LedgerEntry`)

The ontology extension is a focused session of its own, done before
triage code. Each entity gets the same shape as existing types: Pydantic
v2 model, minimal subset to support the use case, expanded as later
specialists need more. Source of truth marker: `foundry/ontology/
object-types.yaml` (to be added in the same session).

## Feature set

Once the ontology extension lands, the ranker computes these features
per exposure. All twelve are derived from structured fields on the
extended ontology — no document reading.

| Feature | Source on extended ontology | Direction |
|---|---|---|
| `hours_until_sla_breach` | `min(sla.deadline - now)` over open `ServiceDeadline`s attached to claim or exposure | lower → higher priority |
| `hours_since_last_touch` | `now - max(action.timestamp)` over `AgentAction` and `WorkItem` for the claim | higher → higher priority |
| `days_until_statute` | `min(statute.deadline - now)` over open `LegalDeadline`s on exposure | lower → higher priority |
| `open_diary_count` | count of `ScheduledTask.cleared = false AND fire_date <= now` for the claim | higher → higher priority |
| `severity_tier_score` | `severity_tier` enum on exposure → numeric 1–4 | higher → higher priority |
| `incurred_amount` | `paid_to_date + reserve_current` on exposure | higher → higher priority |
| `reserve_adequacy_gap` | `abs(reserve_current - reserve_recommended)` if a Reserve specialist has run; else 0 | higher → higher priority |
| `days_since_claimant_contact` | `now - max(communication.timestamp)` for `role = claimant` | higher → higher priority |
| `unread_document_count` | count of `Document.received_date > max(AgentAction.timestamp)` for the claim | higher → higher priority |
| `litigation_flag` | bool on `Claim` | True → priority bump |
| `rep_flag` | bool on `Claim` (claimant represented by counsel) | True → priority bump |
| `complaint_flag` | bool on `Claim` (DOI complaint, BBB, escalation) | True → priority bump |

**Note on `unread_document_count`:** This is the deterministic shadow of
"did something material change." It counts arrival, not weight. If a
police report contradicts a recorded statement, this feature can only
say "1 doc arrived." Reading whether the doc *matters* requires a
specialist. The gap between unread-count and material-change is exactly
what the hybrid v2 LLM layer is for; v1 is intentionally specialist-blind
on this dimension. See "What v1 cannot see" below.

## Scoring function

### Normalization (mandatory step before scoring)

Every feature is normalized to `[0, 1]` *across the current caseload* before
weighting. Without this step, `log(1 + incurred_amount)` for a $1M claim
(score 14) dominates `open_diary_count` (typically 0–3) regardless of
weights, and weight-tuning becomes uninterpretable.

Normalization function per feature: min-max scaling, applied across all
coverage requests in the caseload at ranking time. Implemented in `features.py` so
the ranker always receives normalized vectors.

```
norm_x = (x - min(caseload[feature])) / (max(caseload[feature]) - min(caseload[feature]) + epsilon)
```

For inverse-direction features (`hours_until_sla_breach`,
`days_until_statute`), normalize then invert: `1 - norm_x`. This ensures
"more urgent" always means a larger normalized value, so all weights are
positive and the same direction.

### Scoring (S1 — linear weighted sum on normalized features)

```
score = w_sla     * (1 - norm(hours_until_sla_breach))
      + w_stat    * (1 - norm(days_until_statute))
      + w_aged    * norm(hours_since_last_touch)
      + w_diary   * norm(open_diary_count)
      + w_sev     * norm(severity_tier_score)
      + w_amt     * norm(incurred_amount)
      + w_reserve * norm(reserve_adequacy_gap)
      + w_contact * norm(days_since_claimant_contact)
      + w_unread  * norm(unread_document_count)
      + w_lit     * litigation_flag
      + w_rep     * rep_flag
      + w_compl   * complaint_flag
```

Weights start at `1.0` and tune against the gold ranking. Boolean flags
contribute directly (no normalization) since they're already in `[0, 1]`.

### Why S1 over tier-buckets (S2)

S2 (bucket-then-tiebreak) is closer to how adjusters describe their own
thinking, but S1's continuous score is what the benchmark-tuning loop
needs. If S1 produces good ranking agreement after tuning, the bucket
behavior can be reconstructed by binning the scores. If S1 fails after
tuning, switching to S2 is a v2 question.

## What v1 cannot see

The deterministic ranker is **specialist-blind by design**. It can count
that a new document arrived but cannot judge whether it matters. It can
see the reserve gap if a Reserve specialist has run but cannot read the
ledger and decide if reserve is wrong. The features that require
reading content or calling specialist judgment are *not* in v1 — they're
the hybrid v2's job.

Known v1 ceilings:

- **Material-change detection.** "New police report contradicts statement"
  collapses to "1 unread doc."
- **Reserve adequacy judgment.** Only available if Reserve specialist
  ran; otherwise the gap is 0 by default and the feature contributes
  nothing.
- **Escalation prediction.** Litigation/rep/complaint flags are
  set-or-not booleans; the ranker can't predict "this claim is about to
  go to litigation."
- **Cross-adjuster load balancing.** One ranker for the caseload, not
  personalized per adjuster.

Naming these now so we don't discover them at benchmark time and act
surprised. They are the boundary the hybrid v2 has to cross.

## Fixture — the synthetic caseload

N=20 open exposures (revised down from 50 — hand-ranking 50 is more
cognitive load than it sounds; 20 carefully is better than 50 sloppily).

The 20 are sampled to cover corners (not uniform):

- 3 SLA-imminent (hours out)
- 3 statute-approaching (days out)
- 3 high incurred / high severity
- 3 aged / silent (no touch in 14+ days)
- 3 with recent unread evidence (1–3 docs arrived since last system touch)
- 2 with litigation + rep flags
- 1 with complaint flag
- 2 obvious backburner (low severity, no clocks firing, recent touch)

This shape gives the gold ranking clear must-touch and obvious-backburner
anchors at both ends, with real ambiguity in the middle.

Fixture builder lives at `src/argos/ontology/synthetic_caseload.py`, sibling
to existing `synthetic.py`. Produces a list of `Claim` objects each
linked to one `CoverageRequest` plus its dependent state (SLA, diary,
ledger, communications, agent actions).

## Gold ranking

**As designed:** Tom hand-ranks all 20 exposures by priority,
top-to-bottom, saved to `data/eval-runs/triage-ranker/gold_hand.csv`.
LLM-as-judge gold deferred to hybrid v2 to avoid scope creep.

**As executed:** the gold was sourced from Opus 4.8 (single-pass, full
caseload context) and saved to `data/eval-runs/triage-ranker/gold.csv`.
This swap was a methodology change mid-stream — using an LLM to produce
the gold the deterministic ranker is benchmarked against introduces
same-family-bias risk that the original "human gold" design avoided.
The v1 run mitigated this after the fact with a cross-model
independent-gold check (GPT-5 and GPT-5.5-pro produced their own
rankings on a feature-name-neutralized prompt with shuffled block
order). See `docs/evals/triage-ranker-tuning-procedure.md` for the
results. Future runs should re-source the gold from a hand ranking, or
treat the LLM gold as one of multiple independent golds rather than
the sole reference.

## Metric

Two metrics, both computed against the gold (see "Gold ranking" above
for the design-vs-executed difference):

- **Top-7 Jaccard agreement.** Jaccard overlap of ranker's top 7 with
  gold's top 7 (a "today's work" slice scaled to N=20). Range 0–1.
- **Kendall's tau on the full N=20 ranking.** Range -1 to 1. Reported as
  a secondary metric.

Both target thresholds are locked before any benchmark run in
`docs/evals/triage-ranker-thresholds.md`, per the established eval
methodology (`docs/evals/methodology.md`).

## Decision rule

| Top-7 Jaccard | Kendall tau | Read |
|---|---|---|
| ≥ 0.80 | ≥ 0.6 | Deterministic is enough. Hybrid is icing, defer. |
| 0.60–0.80 | 0.4–0.6 | Deterministic is the base; LLM layer adds material lift on edge cases. Build hybrid v2. |
| < 0.60 | < 0.4 | Deterministic misses the heart of what makes a claim priority. Hybrid is structural for v1. |

Thresholds locked. The thresholds doc must include the noise-floor
calculation: random ranker over N=20 has expected top-7 Jaccard of
`7²/20 ÷ (14 - 7²/20) = 2.45 / 11.55 ≈ 0.21`, and random Kendall tau is
mean 0 with stddev ≈ `1/√20 ≈ 0.22`. So 0.80 top-7 is ~3.8× noise (solid),
0.60 top-7 is ~2.9× noise (interesting), and tau 0.4 is 1.8σ above noise
(marginal), tau 0.6 is 2.7σ (solid). Numbers written down means the
verdict is interpretable, not vibes.

## Test plan

Tests live alongside source (`tests/triage/`) and run with the project's
existing `pytest` setup.

```
src/argos/services/triage/features.py
  tests/triage/test_features.py
    ├── unit: each feature extractor on a known exposure → expected value
    ├── unit: missing-field handling (no SLA → 0 or sentinel, never crash)
    ├── unit: normalization preserves order (rank of raw == rank of normalized)
    ├── unit: normalization is min-max with epsilon (no divide-by-zero on flat caseloads)
    └── property: feature extraction is deterministic (same input → same vector)

src/argos/services/triage/ranker.py
  tests/triage/test_ranker.py
    ├── unit: score() on hand-crafted normalized vector → expected score
    ├── property: monotonicity — increasing SLA urgency ↑ score
    ├── property: monotonicity — increasing incurred amount ↑ score (positive weight)
    ├── unit: rank(caseload) returns claims in score-descending order
    └── unit: ties broken deterministically (e.g., by request_id)

src/argos/ontology/synthetic_caseload.py
  tests/ontology/test_synthetic_caseload.py
    └── unit: caseload size N=20, includes each named corner case at least once
```

100% line coverage on `features.py` and `ranker.py`. Property tests with
`hypothesis` for the monotonicity claims.

## Build plan

1. **Ontology extension session.** Add the 8 new entities + field
   additions to existing types. Pydantic v2, no behavior beyond data
   modeling. Lock entity shapes against AGENT_ARCHITECTURE.md.
2. `src/argos/ontology/synthetic_caseload.py` — N=20 corner-covering caseload
   generator. Includes the 8 new entity types.
3. `docs/evals/triage-ranker-thresholds.md` — lock thresholds + record
   noise-floor calc. Written before any benchmark run.
4. `src/argos/services/triage/features.py` — feature extractor with
   per-caseload normalization. Pure function. Unit + property tests.
5. `src/argos/services/triage/ranker.py` — S1 weighted-sum scorer +
   `rank()` entry point. Unit + property tests.
6. Tom hand-ranks the 20 → `data/eval-runs/triage-ranker/gold_hand.csv`.
7. `scripts/run_triage_benchmark.py` — runs ranker, computes top-7
   Jaccard + Kendall's tau, prints verdict against locked thresholds.
8. Run, record output to `data/eval-runs/triage-ranker/`, decide per
   the decision-rule table.

## What v1 is NOT doing

- Reading any document content (hybrid v2's job).
- Personalizing per adjuster.
- Learning from past adjuster behavior (no feedback loop).
- Deciding *what to do* with each claim — only which to look at first.
- Team-load balancing or routing across adjusters.
- LLM-as-judge gold ranker (deferred to v2 comparison).

## Files

| Path | Phase | Purpose |
|---|---|---|
| `src/argos/ontology/types.py` | 1 | Extended with 8 new entities + field additions |
| `src/argos/ontology/synthetic_caseload.py` | 2 | N=20 fixture generator |
| `docs/evals/triage-ranker-thresholds.md` | 3 | Locked thresholds + noise-floor calc |
| `src/argos/services/triage/__init__.py` | 4 | Package init |
| `src/argos/services/triage/features.py` | 4 | Feature extractor with normalization |
| `src/argos/services/triage/ranker.py` | 5 | S1 scorer + rank() entry |
| `tests/triage/test_features.py` | 4 | Feature extractor tests |
| `tests/triage/test_ranker.py` | 5 | Ranker tests |
| `tests/ontology/test_synthetic_caseload.py` | 2 | Fixture tests |
| `data/eval-runs/triage-ranker/gold_hand.csv` | 6 | Tom's hand ranking |
| `scripts/run_triage_benchmark.py` | 7 | Benchmark runner |
| `data/eval-runs/triage-ranker/run_<timestamp>.json` | 8 | Benchmark output |
