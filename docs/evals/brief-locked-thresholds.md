---
tags:
  - project/argos
  - type/eval-thresholds
  - status/locked
created: 2026-05-31
revised: 2026-05-31 (after run 3 — see docs/evals/brief-eval-runs/2026-05-31-run3.md)
---

# Brief specialist — locked thresholds

Pre-registered before the first eval run. Spec → lock → build → one
run → verdict. No threshold rationalization after the fact.

## Revision history

- **r1 (2026-05-31, after run 1):** two corrections, both eval-side
  not Brief-side. (a) C3 expected sets updated to reflect what the
  orchestrator demo actually persists (stub specialists write result
  files too). (b) C4 match predicate loosened from exact-string-vs-
  `humanize_variable()` to case-insensitive token-substring of the
  rule variable against the LLM-produced item names — the LLM is
  permitted to use better names ("ISO claim search result" vs "Iso
  claim search"). Variable *set* still locked; only the matching
  predicate changes.
- **r2 (2026-05-31, after run 2):** one Brief-side fix and one
  eval-method change. (a) `narrative.py` SYSTEM_PROMPT gains two
  rules: structured flags (`represented:`, `litigation_flag:`,
  `coverage_status:`) from the loss-facts hint are authoritative —
  do not infer rep/litigation from attorney correspondence, do not
  paraphrase "pending" as "ROR". (b) C1 method: judge runs N=3 and
  the verdict uses the *median* hallucination count (must be 0 for
  pass) to suppress single-run LLM-judge non-determinism. The
  zero-hallucinations bar itself is unchanged.
- **r3 (2026-05-31, after run 3):** three eval-method/prompt fixes,
  no Brief substance change. (a) Judge parser: strip markdown
  emphasis (`**`, `*`, backticks) from the HALLUCINATIONS line —
  earlier run silently returned sentinel `-1` when the judge bolded
  the verdict. (b) Judge prompt: gains AUTHORITY RULES — structured
  flags trump document inferences; meta-commentary and soft hedges
  are not facts to flag. (c) Brief prompt: explicit ban on absence-
  editorializing ("loss details not yet documented", "named insured
  not on file") — those belong in the gap list, not the narrative.

## What we're evaluating

`run_brief(caseload, claim_id, results_root=...)` end-to-end on the
extended fixture (`build_caseload_with_realistic_docs()`). Three
claims chosen for coverage:

| Claim | Severity | Docs on file | Coverage result expected | Litigation |
|---|---|---|---|---|
| CLM-007 | catastrophic | 2 (1 corr + 1 medical) | none | no |
| CLM-013 | standard | 1 (correspondence) | none | no |
| CLM-015 | serious | 3 (3 corr, one coverage-material) | yes (from orchestrator-demo) | no |

The orchestrator demo writes `coverage.json` for CLM-015 only, so the
Brief on CLM-015 should consume it; the other two should mark
coverage status as "pending".

## Four pass/fail criteria (all four must pass)

### 1. Narrative factual accuracy

For each of the 3 briefs, the `story_paragraph` must contain **zero
hallucinations**. A hallucination is any concrete fact (dollar amount,
date, name, coverage type, severity, party, status) that is not
present in either the loss_facts_hint or one of the cited documents.

- **Pass:** 0 hallucinations across 3 briefs.
- **Fail:** any.

Method (r2): LLM judge prompt feeds the brief + loss_facts_hint +
cited doc bodies, asks for a list of concrete facts in the narrative
and whether each is supported. Judge runs **N=3 per brief**; the
verdict for that brief uses the *median* hallucination count. This
suppresses single-run LLM-judge non-determinism observed in r1.

### 2. Coverage status correctness

For each brief, `current_status_snapshot.coverage_status` must match
the expected value:

| Claim | Expected coverage_status | Why |
|---|---|---|
| CLM-007 | `"pending"` | No `coverage.json` in results_root |
| CLM-013 | `"pending"` | No `coverage.json` in results_root |
| CLM-015 | `"pending"` (from CoverageRequest default) | Coverage specialist result is consumed via workflow_recommendations_summary, but status_snapshot.coverage_status still mirrors the CoverageRequest unless overridden — and the request default is "pending" |

- **Pass:** 3/3 match exactly.
- **Fail:** any mismatch.

Note: if Coverage's persisted result indicates ROR or denial, the
assembler currently does not override status_snapshot from the
result file — it only pulls the request default. The locked
expectation reflects current implementation. If we want
status_snapshot to track specialist output, that's a separate
follow-up; do not change it during this eval run.

### 3. Material activity completeness

For each brief, `workflow_recommendations_summary` must include
every persisted specialist result file present for the claim. Locked
expectations reflect what the orchestrator demo actually writes to
`data/orchestrator-demo/workflow-results/`:

| Claim | Expected `{specialist}` set |
|---|---|
| CLM-007 | `{reserve}` (stub) |
| CLM-013 | `{}` (orchestrator dispatched nothing for this claim) |
| CLM-015 | `{coverage}` (real Coverage result) |

- **Pass:** exact set match across 3 briefs.
- **Fail:** any extra or missing entry.

If the demo run is re-executed and the persisted set changes, the
expected sets in this section must be re-locked before the next eval
run (with another `revised:` line).

### 4. Gap detection recall

For each brief, `missing_info` (after the gap-rationale LLM call) must
include every variable the deterministic rule layer would emit for
that claim. The rule layer is the ground truth here — Brief's LLM
must NOT drop any rule-detected gap. Pre-registered expected gap
variables per claim:

| Claim | Expected gap variables (rule-detected) |
|---|---|
| CLM-007 | `policy_declarations`, `iso_claim_search`, `coverage_analysis` (catastrophic + medical doc on file → no medical_records gap) |
| CLM-013 | `policy_declarations`, `iso_claim_search`, `coverage_analysis` (standard severity → no medical gap; not litigated → no counsel gap) |
| CLM-015 | `policy_declarations`, `iso_claim_search` (Coverage result present → no coverage_analysis gap; serious severity but no medical docs on file → `medical_records` also expected) |

Recompute these from the rule layer at run time (do not hand-edit) to
catch fixture drift.

- **Pass:** for each claim, every rule-detected variable
  (e.g., `iso_claim_search`) appears as a case-insensitive
  substring of *some* `m.item` in `brief.missing_info`, after
  splitting the variable on underscores and treating each token as a
  required substring (e.g., `iso_claim_search` must match an item
  containing `iso` AND `claim` AND `search`, all case-insensitively).
  Recall = 1.0 by this predicate.
- **Fail:** any rule-detected variable not covered by any item.

The variable set itself is still locked (table above); only the
matching predicate changed in r1.

## Composite verdict

**PASS** iff all four criteria pass for all three claims.
**FAIL** if any one criterion fails on any one claim.

A single eval run produces the verdict. Re-runs require re-locking
this doc (with a `revised:` line) before the new run.

## Procedure

1. Ensure `data/orchestrator-demo/workflow-results/CLM-015/coverage.json`
   exists. If not, run `scripts/run_orchestrator_demo.py` first.
2. Run `scripts/run_brief.py CLM-007`, then `CLM-013`, then `CLM-015`.
3. Run the eval script (`scripts/run_brief_eval.py`, built alongside
   this doc) — it loads the three briefs from `data/brief-demo/`,
   computes the four criteria, prints PASS/FAIL per criterion per
   claim and a composite verdict.
4. Record the verdict + verbatim eval output in
   `docs/evals/brief-eval-runs/<utc-iso-date>.md`. Append-only.

## Cost expectation

3 claims × 2 LLM calls each = 6 calls. ~$0.05–$0.10 total.

## What this eval does NOT cover

- Wall-clock latency (out of scope for v1).
- Multi-claim batch behavior (Brief is one-claim-at-a-time).
- The Changelog "what changed since last touch" feature — explicitly
  out of scope per the Brief spec.
- The `pending_communications` field (correspondence system not built).

These are noted so reviewers don't read a passing verdict as
broader-than-it-is.
