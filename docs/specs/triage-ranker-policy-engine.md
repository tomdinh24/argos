---
tags:
  - project/argos
  - type/spec
  - status/design
created: 2026-05-30
---

# Triage ranker — policy-engine architecture

## Why this doc exists

The shipped deterministic ranker (`src/argos/services/triage/ranker.py`)
is a linear weighted sum on 12 normalized features. It reaches k=6
against independent OpenAI golds. The hybrid v2 attempt (LLM
materiality re-rank on the top slice) regressed against one gold and
held flat against the other — killed on first run.

The Codex post-mortem on v2 identified the root cause as architectural,
not implementation. Quoted directly because the line is load-bearing:

> v2 "completely failed" because it converted an evaluation problem
> into an oracle problem. The judge was not optimizing against any gold
> — it was optimizing against its own inferred policy, influenced by
> prompt examples. So it did exactly the dangerous thing: it made
> confident policy calls in the ambiguous band.

This doc captures what the triage system *should* look like if we were
designing it from first principles today, applying the lesson. It is
**design, not implementation** — the shipped S1 ranker stays in
production; this is the target architecture for when triage is
revisited.

## The mistake the linear-weighted-sum encodes

S1 treats every claim as a point in a 12-dimensional feature space and
scores it with a single weighted sum. That formulation has four
structural problems no amount of weight tuning fixes:

1. **It cannot express gates.** "Statute under 7 days beats everything
   except same-day SLA" is a precedence rule, not a weight. Linear
   scoring cannot enforce "this beats that no matter what else is true."
2. **It cannot model interactions.** `litigation + rep + statute` is
   not three additive bumps; it's a categorical state ("active
   litigation under deadline") with its own handling rules.
3. **Per-caseload min-max makes urgency relative.** SLA hours get
   normalized across whatever claims happen to be in the caseload that
   morning. But real deadlines are absolute — a 1-hour SLA breach is
   urgent regardless of whether the rest of the caseload is fresh or
   stale.
4. **It conflates "important" with "urgent."** A $1.75M catastrophic
   file *matters* but may have no action trigger today. A $40K statute
   file with 7 days left needs work *now*. Single-score ranking
   collapses these into one axis when they're orthogonal.

## What an expert adjuster actually does

Per Codex's seven-step blueprint, the real reasoning is "minimize
operational regret under time constraints":

1. **Identify non-negotiable clocks.** Same-day SLA, legal deadlines,
   court deadlines, DOI response windows, statute protection, mandated
   contact, diary commitments. Missing any of these creates irreversible
   harm — regulatory exposure, bad faith risk, lost subrogation rights.
2. **Ask what must happen today.** Not "is this claim important?" but
   "is there an action that must complete today or start today because
   waiting changes the outcome?"
3. **Separate irreversible from recoverable.** Statutes, service
   breaches, complaint mishandling, litigation deadlines — irreversible.
   Stale file with no event — usually recoverable. High incurred with
   no action trigger — monitor unless a decision point exists.
4. **Account for escalation posture.** Litigation, rep, complaint, DOI,
   coverage dispute, angry communications — these lower tolerance for
   delay but don't automatically beat hard clocks.
5. **Estimate action value.** What can the adjuster *do* now? Call
   claimant, acknowledge complaint, assign counsel, issue reservation,
   review new police report, protect statute, update reserve.
6. **Consider effort and batching.** A five-minute acknowledgment may
   come before a two-hour investigation.
7. **Respect carrier policy.** The missing variable in v1/v2. Different
   shops weight differently; there is no universal gold without this.

## Architecture

Three layers, each with a sharply defined responsibility.

### Layer 1 — Policy engine (deterministic, gates)

The carrier's claims-handling policy expressed as code. Sorts every
claim into one of N buckets by **absolute thresholds**, not relative
scores. Buckets are ordered by precedence: bucket 1 always beats
bucket 2 across all claims.

Initial bucket structure (the design target — actual list is
carrier-configurable):

| # | bucket | trigger |
|---|---|---|
| 1 | **same-day mandatory** | SLA < 24h OR court deadline today OR complaint requiring same-day ack |
| 2 | **statute protection imminent** | any legal deadline ≤ 7 days on the request |
| 3 | **litigation active + clock** | litigation flag AND any clock ≤ 60 days |
| 4 | **regulatory escalation** | complaint flag with regulator (DOI, BBB) or represented |
| 5 | **statute protection approaching** | any legal deadline 8–30 days |
| 6 | **high exposure with action trigger** | incurred ≥ carrier-threshold AND new docs OR overdue diary |
| 7 | **routine work** | everything else |

Carrier policy lives in a config (YAML or JSON), not in code. Each
bucket trigger is a Boolean expression over feature values, evaluated
deterministically. No LLM in this layer.

### Layer 2 — Within-bucket scorer (linear, ranks inside a bucket)

The S1-style weighted sum is the **right** tool *inside* a bucket
where the policy has already done the hard categorical work. Within
"same-day mandatory" the score might be just `hours_until_breach`
inverted, plus exposure as a tiebreak. Within "high exposure with
action trigger" the score might be `incurred + recent_doc_count * α`.

Each bucket has its own scorer; the scorers are simple because the
gating has stripped out the cross-category ambiguity. Tuning happens
**within** a bucket against gold (and the gold for each bucket is much
less ambiguous than the global gold was). No LLM in this layer.

### Layer 3 — LLM specialists (extraction and materiality only)

LLMs do narrow tasks that feed into Layers 1 and 2:

- **Document materiality.** "Does this new police report change
  liability/coverage/damages/reserve posture?" Output: Boolean +
  one-line reason. Feeds into Layer 1 (bucket 6 trigger) and Layer 2
  (bumps within-bucket score if material).
- **Next-required-action extraction.** "Given the file state, what is
  the most-leveraged next action?" Output: one of a fixed enum of
  action types (call_claimant, acknowledge_complaint, assign_counsel,
  issue_reservation, review_doc, protect_statute, update_reserve,
  clear_diary). Feeds into the output shape.
- **Escalation-language detection.** "Does this communication contain
  escalation cues (threats, attorney involvement, regulator names)?"
  Output: Boolean. Feeds Layer 1.

LLMs are explicitly **not allowed** to rank claims, pick "the best 7,"
or apply policy. Policy execution is Layer 1's job; LLMs supply facts.

## Output shape

The ranker's output is not just `(rank, request_id, score)`. It is:

```
rank | bucket | request_id | required_action | why_today | latest_safe_start | estimated_effort
```

- `bucket`: which Layer-1 bucket the claim is in.
- `required_action`: from the Layer-3 extractor's enum.
- `why_today`: one-line explanation of why this claim is in its bucket
  (the policy gate that fired).
- `latest_safe_start`: the deadline (or computed safe-start time)
  before which this work needs to start to avoid irreversible harm.
- `estimated_effort`: a coarse bucket (5min / 30min / 2hr / day) so the
  adjuster can batch.

This shape lets the adjuster see *why* each claim is on the list and
*what to do*, not just an opaque score.

## What this changes vs the shipped S1

| dimension | shipped S1 | policy-engine target |
|---|---|---|
| ordering basis | relative score across all 20 claims | absolute bucket + within-bucket score |
| handles "statute < 7d beats everything" | no | yes (bucket precedence) |
| handles feature interactions | no (additive only) | yes (bucket triggers are conjunctions) |
| sensitivity to caseload composition | high (min-max normalization) | low (absolute thresholds) |
| sensitivity to carrier policy | none (one-size-fits-all weights) | configurable per shop |
| output | rank + score | rank + bucket + action + why + when + effort |
| LLM role | none in S1; free-form ranking in v2 (killed) | extraction and materiality only |
| eval gold meaning | ambiguous (whose policy?) | well-defined per bucket |

## What we preserve from S1

- The 12 features in `features.py` are still the right raw inputs.
  Most of them feed into either a Layer-1 gate or a Layer-2 within-
  bucket score.
- Per-caseload min-max normalization stays *inside* buckets (where
  relative urgency is the right thing). It leaves Layer 1 (which
  needs absolute thresholds).
- The N=20 fixture stays valid as a regression test. Bucket
  membership for each corner is hand-checkable from the corner
  definitions.

## What this lets us evaluate honestly

The reason v1+v2 had to lean on LLM golds at all was that "what's the
right rank?" had no carrier-policy answer. Once policy is explicit:

- **Bucket assignment is checkable.** Did the policy engine put each
  claim in the right bucket? Boolean per claim, no gold needed — just
  the policy config and the feature values.
- **Within-bucket ordering is checkable against a much narrower gold.**
  "Given these 4 same-day-mandatory claims, rank them" is far less
  ambiguous than "rank these 20 claims" — three different LLMs would
  likely agree on the within-bucket ordering even if they disagreed on
  cross-bucket priority.
- **Extraction quality is checkable independently.** Document
  materiality calls can be eval'd against hand-labeled examples; this
  is the existing Argos eval methodology (exemplar-based, paired-delta).

## What we do NOT build now

- The Layer-1 policy config language. Could be YAML/JSON DSL, could be
  Python predicates, could be a small Rules-as-Code framework. Defer
  to when there's a real carrier to model.
- The Layer-3 materiality extractor. That's a small per-claim LLM
  specialist, basically a sibling of the Coverage specialist. Build
  when needed; the spec is clear about its contract.
- The bucket scorers in Layer 2. The shipped S1 weights are a
  reasonable seed for the "routine work" bucket; other buckets need
  their own simple scorers.

## Status

**Design only.** The shipped S1 ranker continues to serve. This spec
is the target architecture for the next serious triage iteration,
whenever that is. The lesson it captures is the more valuable artifact
— see `~/.claude/projects/.../memory/feedback_policy_engine_first_then_llm_extraction.md`
in the user's auto-memory for the cross-specialist version.
