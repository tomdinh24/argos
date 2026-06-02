---
tags:
  - project/argos
  - type/spec
  - status/design
created: 2026-06-01
---

# Reserve workflow — how it plugs into the system

> Companion to [docs/specs/reserve-workflow.md](./reserve-workflow.md)
> (what the workflow does) and
> [docs/research/reserve-estimation-methods.md](../research/reserve-estimation-methods.md)
> (how it estimates). This doc shows where it sits in the wider
> architecture, who triggers it, what it reads, what happens to its
> output, and how the adjuster commits the resulting number.

## The flow at a glance

```
                  ┌──────────────────────────────┐
                  │  New material doc arrives    │
                  │  OR scheduled review cadence │
                  │  OR manual adjuster refresh  │
                  └──────────────┬───────────────┘
                                 │
                                 ▼
              ┌──────────────────────────────────────┐
              │  advance_claim(caseload, claim_id,   │
              │                new_inbound_docs,     │
              │                job_queue, ...)       │
              └──────────────┬───────────────────────┘
                             │
                  ┌──────────┴──────────┐
                  │                     │
              correspondence       analysis re-trigger
              advance              (every newly-arrived doc)
                  │                     │
                  ▼                     ▼
        (drafts, ingests)      Document Reader
                                       │
                                       ▼
                            posture_changed = "reserve"
                                  or "damages"
                                       │
                                       ▼
                            dispatch() → Job("reserve", ...)
                                       │
                                       ▼
                              JobQueue.enqueue
                                       │
                                       ▼
                      ┌────────────────────────────┐
                      │   WorkflowRunner drains    │
                      │   on its own cadence       │
                      └────────────────┬───────────┘
                                       │
                                       ▼
                          ┌──────────────────────┐
                          │  RESERVE WORKFLOW    │
                          │  (this is the thing) │
                          └──────────┬───────────┘
                                     │
                                     ▼
                      ┌────────────────────────────┐
                      │  ReserveAnalysis output    │
                      │  (per-component bands +    │
                      │   notice obligations +     │
                      │   authority level)         │
                      └────────────────┬───────────┘
                                       │
                                       ▼
                  ┌────────────────────────────────┐
                  │  Persists to:                   │
                  │  data/workflow-results/         │
                  │  {claim_id}/reserve.json        │
                  └────────────────┬────────────────┘
                                   │
                                   ▼
                  ┌────────────────────────────────┐
                  │  Brief re-runs and incorporates │
                  │  reserve recommendation into    │
                  │  the cockpit's main view        │
                  └────────────────┬────────────────┘
                                   │
                                   ▼
                  ┌────────────────────────────────┐
                  │  Adjuster opens claim, sees     │
                  │  recommendation in cockpit      │
                  │  with citations + bands         │
                  └────────────────┬────────────────┘
                                   │
                          ┌────────┴────────┐
                          │                 │
                       Commit            Defer / disagree
                          │                 │
                          ▼                 ▼
            apply_reserve_decision     No state change;
            (future writeback)         notes in cockpit
                          │
                          ▼
              ┌─────────────────────────┐
              │ LedgerEntry written      │
              │ ("reserve_set" or        │
              │  "reserve_adjusted")     │
              │ Notice obligations fire   │
              │ AgentAction logged        │
              └──────────────────────────┘
```

## Step-by-step — what happens in order

### 1. Trigger

Three paths, all converge on the same workflow runtime:

**Path A: New doc arrives.** Adjuster (or a fax/email intake worker)
drops a new document into the claim. `advance_claim` is called with
`new_inbound_docs=[that_doc]` and a `job_queue` supplied. Existing
behavior (just shipped this morning):

1. Doc is classified as `reply_candidate` or `disclosure`
2. Disclosures land in `caseload.documents`; replies pass through
   `IngestReply.apply_outcome` which also lands them in `documents`
3. Analysis re-trigger fires: for every newly-added doc, the
   Document Reader runs and emits a `RelevanceCall`
4. If `posture_changed == "reserve"` or `"damages"`, the dispatcher
   emits a `Job(workflow="reserve", ...)` and the queue enqueues it

**Path B: Scheduled review cadence (future).** A cron sweep walks
every open claim and checks `claim.last_reserve_review`. Claims past
`review_cadence_days` get a Reserve Job enqueued directly (no
Reader call needed — the trigger is age, not new evidence). This
catches stale claims with no fresh docs.

**Path C: Manual refresh.** Adjuster clicks "Re-run Reserve" in the
cockpit. The cockpit calls `JobQueue.enqueue(Job(workflow="reserve",
triggered_by_doc_id="manual", ...))`. Same workflow, same output
shape. Useful when the adjuster has read the file and wants a fresh
take.

### 2. WorkflowRunner picks up the Job

The runner is single-threaded by design (it's a function the user
calls, not a daemon). On `process_one()`, it pulls the next pending
Job, looks up the registered workflow function:

```python
WORKFLOW_REGISTRY: dict[str, WorkflowFn] = {
    "coverage": _run_coverage_via_adapter,
    "reserve": _run_reserve_via_adapter,    # NEW (replaces stub)
    "liability": _stub_workflow("liability"),
    "brief":    _make_brief_runner(results_root),
}
```

`_run_reserve_via_adapter`:
1. Pulls the claim from the caseload
2. Adapts to `SyntheticClaim` shape (existing adapter)
3. Reads `claim.coverage_posture` and passes it as explicit input
4. Calls `run_reserve(synth, coverage_posture=...)` — the LLM call
5. Returns `(summary, analysis.model_dump(mode="json"))`

The runner persists the JSON to
`data/workflow-results/{claim_id}/reserve.json` and marks the Job
done.

### 3. Inside the workflow — what `run_reserve` actually does

One Anthropic tool_use call. System prompt embeds the per-component
methodology from
[reserve-estimation-methods.md](../research/reserve-estimation-methods.md):
the decomposition (indemnity + ALAE + ULAE + …), the per-component
methods (multiplier ranges by tier, phase-based defense budgets,
ULAE percentage default), jurisdiction handles (comparative
negligence rule, statutes), citation discipline.

User message renders the claim:
- Policy + period (limits, deductible, retention, jurisdiction)
- Coverage request + current ledger state (current reserves per
  component, payments to date)
- Documents (every relevant doc in the file)
- Sourced legal rules from `SpecialistConfig`
- `coverage_posture` framing line

Model returns a `ReserveAnalysis`:
- `per_component`: for each of indemnity / ALAE / ULAE / etc. that
  applies — current outstanding, recommended band (p10/p50/p90),
  rationale, triggers fired, evidence citations
- `notice_obligations_triggered`: who needs to be told, by when,
  with evidence
- `authority_required_level`: which authority tier the
  recommendation requires
- `no_change_warranted`: true if current reserves sit in band

On Pydantic validation failure, retry once with the error fed back
as a corrective system message (same pattern as Coverage).

### 4. Brief re-runs and the recommendation surfaces

The Brief workflow's job is to assemble the one-screen cockpit view.
When a new Reserve recommendation lands, the next Brief run picks
it up from `data/workflow-results/{claim_id}/reserve.json` and
incorporates:

- `since_last_touch_diff` flags "reserve recommendation moved from
  $X to $Y (per_component breakdown)"
- `missing_info` notes if the recommendation flagged gaps (e.g.,
  "severe injury, no life-care plan on file")
- `workflow_recommendations_summary` carries a one-line pointer to
  the full Reserve recommendation

The adjuster sees this in the cockpit the next time they open the
claim.

### 5. Adjuster decides

The cockpit shows:
- The recommended band per component with rationale and citations
- The current outstanding vs recommendation diff
- Notice obligations triggered with required-by-dates
- Authority level required
- A "Commit" button that fires the writeback action

The adjuster's options:
- **Commit at p50** (default) — one-click acceptance
- **Commit at a different point** — adjuster picks anywhere in
  band (or outside, with a justification field)
- **Defer** — note the disagreement (or the "not yet" reason),
  reserve unchanged
- **Re-run** — if the adjuster has additional context, they can
  type it into a free-text override and the workflow re-runs with
  the adjuster's note appended to the user message

### 6. Writeback (future — `apply_reserve_decision`)

When the adjuster commits, the cockpit calls:

```python
apply_reserve_decision(
    caseload,
    claim_id,
    request_id,
    *,
    per_component_decisions=[
        ComponentDecision(
            component="indemnity",
            new_outstanding=120_000.0,
            source_recommendation_band=ReserveBand(...),
            justification=None,  # in-band, no override
        ),
        ComponentDecision(
            component="defense",
            new_outstanding=15_000.0,
            source_recommendation_band=ReserveBand(...),
            justification=None,
        ),
        # ...
    ],
    fire_notices=["excess_carrier"],  # which of the recommended
                                       # notices the adjuster
                                       # commits to firing
    source_recommendation_id="REC-RES-2026-06-01-CLM007",
) -> Caseload
```

The writeback:
1. Validates the adjuster's authority covers the new reserve total
   (rejects if not — sends to next authority tier as
   `AuthorityRequest`)
2. Writes new `LedgerEntry` rows of type `reserve_adjusted` or
   `reserve_set`, one per component
3. Fires each named notice obligation (in v1, this might just be
   logging — production wires email/portal/EDI)
4. Logs an `AgentAction` row: who saw what, who committed what,
   what notices fired, source recommendation ID for provenance
5. Sets `claim.last_reserve_review = now`

Authority validation is symmetric to coverage's. The writeback is
the single point where reserve changes can happen — there's no
side-channel for the LLM to move money directly.

### 7. The cycle closes

Next time new evidence arrives on this claim, `advance_claim` fires
again. Reader sees the new doc, may flag posture_changed = reserve,
new Reserve Job lands in the queue, runner processes it, new
recommendation surfaces with a delta against the previous reserve.

If the new evidence doesn't change anything material, the Reader
flags `relevant=False` and no Job fires. Cheap pass.

If the scheduled review cadence fires on a stale claim with no new
evidence, the workflow runs on the existing file and emits
`no_change_warranted=True` if everything still sits in band.
Adjuster sees "no action needed" in the cockpit; no commit
required.

## Interactions with other workflows

### Coverage → Reserve

Coverage flips `claim.coverage_posture`. Next Reserve run reads the
new posture and adjusts framing:

- `under_investigation` / `clean` / `accepted` → exposure-weighted
  bands (assume we'd pay)
- `ROR_issued` → exposure-weighted bands, flag uncertainty in
  rationale
- `denied` → indemnity p10 = p50 = p90 = 0 (or defense-only),
  defense/ALAE/expert_fees stay populated for the cost of holding
  the denial

The link is data-flow, not code-call. Coverage's writeback flips
the posture field; Reserve reads the field on its next run. No
direct dependency.

### Liability → Reserve

Liability emits a fault distribution. v1 Reserve does NOT consume
this — the adjuster applies the fault haircut at commit time
(picks a lower p50 from the band, or sets a lower point estimate
than the recommendation). v2 may chain Liability's fault
distribution as an explicit input to Reserve so the
indemnity band emerges already weighted.

### Brief consumes Reserve

Brief reads `data/workflow-results/{claim_id}/reserve.json` and
incorporates it into the cockpit view. No reverse dependency.

### InfoGap → outbound requests
NOT directly linked to Reserve. InfoGap proposes outbounds to fill
open questions on the claim. If a Reserve run flagged "missing
life-care plan," the adjuster (or a future InfoGap policy) could
trigger an outbound to the treating physician. This wiring exists
at the human level today; not coded.

## What changes in the codebase

**New files:**
- `src/argos/workflows/reserve.py` — the runtime (mirrors `coverage.py`)
- `tests/workflows/test_reserve.py` — unit + anchor-pair tests
- `docs/evals/reserve-anchor-pair-thresholds.md` — locked thresholds

**Modified files:**
- `src/argos/services/orchestrator/runner.py` —
  `WORKFLOW_REGISTRY["reserve"] = _run_reserve_via_adapter`
  (replaces stub)
- `src/argos/workflows/brief/brief.py` — Brief's read of
  `reserve.json` once Reserve writes real output (Brief already
  reads `coverage.json`; same pattern)

**Future (separate decision, not now):**
- `src/argos/services/orchestrator/reserve_actions.py` —
  `apply_reserve_decision` writeback
- Cockpit UI surfacing the recommendation + commit button
- Real notice-firing wires (email, EDI, portal)

## What this flow does NOT do

- **Does NOT change reserves automatically.** The workflow emits
  recommendations. The adjuster commits. The legally-bearing piece
  stays human.
- **Does NOT bypass authority bands.** The workflow flags the
  required level. The writeback enforces it. An adjuster with
  handler authority cannot commit a manager-level reserve through
  any path.
- **Does NOT decide coverage.** Coverage posture is INPUT, not a
  thing Reserve influences.
- **Does NOT track reserve history.** That's the ledger's job.
  Reserve reads the ledger; the writeback writes to it. The
  workflow itself is stateless.
- **Does NOT send notices.** It identifies WHICH notices triggered
  and by WHEN. Actually sending the notice is a downstream action,
  invoked by the writeback when the adjuster commits to firing it.

## Open questions

- **Per-component commit granularity.** When the adjuster commits,
  do they have to commit each component separately, or can they
  bulk-accept all components at recommended p50? v1 should support
  both (one-click accept-all OR per-component review).
- **Re-trigger frequency cap.** If multiple docs arrive in one day,
  do we want N Reserve runs that day or one batched run? v1 lets
  them all fire; the runner's JobQueue idempotency keys on
  `(workflow, claim_id, triggered_by_doc_id)` so each doc gets one
  run, but a 5-doc day = 5 runs. This is probably fine for cost
  given Reserve is one LLM call.
- **Override learning.** When the adjuster repeatedly overrides the
  recommendation in a consistent direction (e.g., always picks p25
  instead of p50), should the workflow learn to adjust its
  recommendation toward that adjuster's calibration? Not in v1 —
  but worth tracking the override deltas for an eventual
  fine-tuning signal.
