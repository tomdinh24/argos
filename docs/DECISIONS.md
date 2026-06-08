---
created: 2026-06-01
last_updated: 2026-06-04
title: Argos Architecture Decisions Log
status: living
tags:
  - project/argos
  - type/decisions
  - status/load-bearing
---

# Argos — Architecture Decisions Log

> **Load this before any session that touches architecture, naming, flow,
> or what we're building next.** Append-only record of what we decided,
> why, and what's explicitly out of scope. The goal is to never
> re-litigate a settled decision.
>
> Companion to [SYSTEM_ARCHITECTURE.md](./SYSTEM_ARCHITECTURE.md) and
> [AGENT_ARCHITECTURE.md](./AGENT_ARCHITECTURE.md), which describe the
> system as-is. This log captures *how we got there* — the rationale
> and the rejected alternatives.

## How to use this file

**Reading.** Scan newest first. Before making any architectural
suggestion, check that no prior entry already settled it.

**Writing.** When a load-bearing decision is made in a session, append
a new entry. Newest on top. Format: date + short title + four fields
— **Decision**, **Why**, **Out of scope**, **Code touched**. To
overturn a prior decision, add a NEW entry that explicitly supersedes
it (`Supersedes: 2026-XX-XX — <title>`). Never edit history.

**Cost-of-entry filter.** Only record decisions a future reader would
want context for. Skip: variable renames driven by simple style, lint
cleanup, fixture tweaks. Keep: anything that changes architecture, an
LLM-facing surface, an eval baseline, the build plan, or how
specialists compose.

**Operating rule.** Code and plans should align with what's in this
doc. If you're about to write code that contradicts an entry, stop
and surface the conflict.

---

## 2026-06-07 — Hosted backend = Railway (Phase 5 host pick + turnkey deploy config)

**Decision:** The hosted demo backend runs on **Railway** (Tom's pick; the
Vercel-hosted cockpit already targets it via `NEXT_PUBLIC_API_BASE`). The repo is
made turnkey-deployable without a `pip install .` step: `railway.json` pins the
Nixpacks builder + a `/healthz` health check + the start command
`PYTHONPATH=src uvicorn argos.api.app:app --host 0.0.0.0 --port $PORT`;
`requirements.txt` mirrors `pyproject.toml` for deterministic dep install;
`.python-version` → 3.11 (the interpreter all evals/tests ran on); `Procfile` aligned. The two hero claims' pre-run results
(`data/workflow-results/CLM-001`, `CLM-004`) are committed so a fresh deploy renders
rich dossiers with no cold LLM run. Runbook: `docs/DEPLOY_RAILWAY.md`.

**Why:** Procfile/Heroku-style app + small pure-Python dep set fits Railway's
Nixpacks path with the least config. `PYTHONPATH=src` (vs `pip install .`) removes a
build-time failure mode and keeps the start command identical local↔host.

**Out of scope:** `ARGOS_FOUNDRY_BRIDGE_ENABLED` stays **OFF** on Railway until the
OSDK is re-pinned to ontology `88f01e1f` (blocker below) — hosted decisions write the
local JSONL audit log, not the ontology. Railway disk is ephemeral: committed pre-run
results survive redeploys; runtime-written decisions do not (attach a volume for
durable state). Secret entry (`ANTHROPIC_API_KEY`, `ARGOS_DEMO_TOKEN`) is operator-only.

**Code touched:** `railway.json`, `requirements.txt`, `.python-version`, `Procfile`,
`docs/DEPLOY_RAILWAY.md` (new); CORS `ARGOS_CORS_EXTRA` hook already present in
`api/app.py`.

---

## 2026-06-07 — Cockpit wired LIVE end-to-end; Foundry write blocked by OSDK ontology drift (lesson: integration seams need a default-suite test)

**Decision:** The cockpit now runs on the real backend pipeline rather than
front-end fixtures. Three seams were wired and verified:

1. **Read path** — the Next.js cockpit (`web/lib/api.ts`, `NEXT_PUBLIC_API_BASE`)
   consumes the FastAPI surface on `:8071`. CORS allowlist corrected to include
   the dev origin `:3007` (`api/app.py`).
2. **Decision-commit path** — `POST /api/claims/{id}/decisions` now routes by
   workflow to the orchestrator `apply_*_decision` handlers (was: logged an audit
   row + advanced the chain, but **never called the handlers** — so no bridge
   ever fired). The new caseload is written back to in-process state. The
   human-decision audit row stays the single source (handlers called without
   `audit_log_root` to avoid double-logging). Frontend CTAs call `postDecision`.
3. **Live dossier** — the detail page renders from real workflow results via a
   new `mappers.to_dossier()` + `ClaimDossier` wire schema (`api/schemas.py`).
   Citations join `document_id → Document.body_text` so the viewer highlights the
   cited passage in the real document. Coverage + liability are demo-rich; reserve
   /recovery/closure render real but are thin where the synthetic claim lacks
   structured financial inputs.

**Eval-safe data enrichment:** both existing caseload builders are eval-locked
(`synthetic_caseload.py` → triage-ranker; `caseload_with_realistic_docs.py` →
reader-integration thresholds). Rather than mutate them, the cockpit uses a new
**`ontology/cockpit_caseload.py`** wrapper that adds named insureds, varied loss
types, and rich hero-claim documents. The locked fixtures are untouched (134
ontology+triage tests still green). Triage-band display mapping (`_band_from_severity`)
now surfaces serious/catastrophic as red — display-only, not eval-locked.

**Why (the headline finding):** turning the Foundry write on
(`ARGOS_FOUNDRY_BRIDGE_ENABLED=1`) proved the bridge wiring is correct — the
decision routes to the handler, the handler invokes the OSDK action, and the
asymmetric-commit degrades gracefully (local row commits, Foundry failure logged
not raised). **But every bridge returns `ActionTypeNotFound`.** Root cause: the
installed `argos_live_sdk` is **v0.2.0**, bound to the legacy ontology
`d7926c75-…`; the 2026-06-04 entry verified **v0.1.0**, bound to the live ontology
`88f01e1f-…`. The SDK drifted to a wrong-ontology build after that verification.
The `ActionTypeNotFound: apply-reserve-decision` we hit is the exact signature row
2 of that entry's diagnostic ladder flagged as the legacy binding. So the
"6/6 bridges live-verified" claim is **stale — currently 0/6**.

**Why it went undetected (the lesson):** `pyproject.toml` sets
`addopts = "-m 'not eval and not foundry_integration'"` — the live Foundry tests
are **excluded from the default suite**. When the SDK regressed, no default test
failed. *Integration seams need a default-suite test that fails when a layer
silently stops connecting; "each layer's unit tests pass" ≠ "the layers are
connected," and an opt-in integration marker is invisible to that failure mode.*

**Remaining steps (documented, not silently dropped):**

- **Foundry write (external):** regenerate/pin `argos_live_sdk` to ontology
  `88f01e1f-…` from the correct Foundry Developer Console OSDK Application; use the
  matching token; re-run `pytest -m foundry_integration` (expect pass, or
  `ObjectNotFound` → seed the claim row). No Argos code change needed — wiring is done.
- **Pin the SDK** so a wrong-ontology bump can't silently land again.
- **Calc-stage data depth:** reserve needs structured specials inputs to model
  non-zero bands on payable claims (a "payable" hero, CLM-004, was added to show
  the non-barred shape).
- **Stage-header reconciliation:** the accordion summary labels come from
  `_pending_rec_from_result` and can disagree with the dossier sections; unify.
- **Hosted:** Vercel cockpit + deployed backend (`ARGOS_DEMO_TOKEN` must be set so
  the API isn't open).

**Out of scope (this session):** reserve-input extraction upgrades; per-stage
structured-output emission for reserve/liability citations beyond what coverage
already does.

**Code touched:** `api/app.py` (CORS, decision routing, state write-back, json
import), `api/schemas.py` (`ClaimDossier` + sections, `Citation.body`,
`ClaimDetail.dossier`), `api/mappers.py` (`to_dossier` + helpers, `_num` for
string-decimal coercion, liability/recovery decimal-bug fixes, band mapping),
`ontology/cockpit_caseload.py` (new), `web/lib/api.ts` (`runWorkflow`,
`postDecision`), `web/components/App.tsx` (`acceptStage` → `postDecision`),
`tests/api/test_decision_flow.py` (new default-suite guardrail).

---

## 2026-06-07 — Cockpit claim-detail IA: Overview / Workflow / Sources tabs + lifecycle accordion, inline per-stage commit

**Decision:** The claim-detail screen (Screen 2 in
[cockpit.md](./architecture/cockpit.md)) ships as a mobile-first single
column with three tabs — **Overview / Workflow / Sources** — not the
earlier left-rail-tabs + main-pane + right-rail console.

- **Overview** — the claim brief (citation-chipped) + a "New
  information / since you last looked" log.
- **Workflow** — a lifecycle accordion stacking all five stages
  (Coverage → Closure). Each stage renders its own structured body
  (coverage accident→provision map + outcome distribution; reserve
  findings + component band ranges + pre-booking checks + editable
  amount; liability allocation bar + evidence; recovery status +
  checklist + net-economics; closure readiness + decision recap) and
  commits **inline** via one contextual CTA per stage.
- **Sources** — one searchable / type-filterable table of every
  document read (merges the old "Documents" tab and the "pinned
  citations" list). Rows and inline `[n]` chips open the citation
  detail sheet.

This **revises cockpit.md Screen 2 and folds in Screen 3**: there is no
separate Decision Drawer — commit is the per-stage CTA. Screen 4
(Document Inspector) ships as the lightweight citation detail sheet.
Screen 5 (standalone Audit Ledger) and the right-rail AgentAction
timeline are not in the demo surface; "what changed" is carried by the
Overview new-info log and the closure recap. Priority is a **single
status** (the triage band chip — Now / Today / Later), not a band plus
a separate Eisenhower descriptor.

**Why:** The prior single-recommendation detail page overloaded one
pane. The new IA chunks the claim into scan-able sections with
progressive disclosure (accordion), so an adjuster sees stage status at
a glance and drills into only the active one; inline per-stage commit
removes a modal hop; merging documents + citations into one searchable
table matches how adjusters look for "the receipt." Selected as Variant
C after a human-gated design loop. Design tokens unchanged (light
deep-tech console, muted indigo) — layout-only.

**Out of scope:** The backend endpoints in cockpit.md's Reads table are
unchanged targets — the shipped surface is fixture-backed
(`web/lib/api.ts`) and several sub-surfaces are tagged `proposed`
(reserve breakdown, pre-booking checks, new-info log, recovery
checklist, coverage distribution) because the workflow result objects
don't emit them yet. No eval-locked surface touched (band strings, the
7-bucket structure, ranking metrics all unchanged). Standalone Audit
Ledger (Screen 5) remains deferred.

**Code touched:** `web/components/App.tsx` (ClaimDetailScreen rewritten
to tabs + accordion + per-stage bodies + searchable Sources; old
`PendingRecPanel` / `WorkflowChainView` / `DecisionLog` /
`CitationsList` removed), `web/lib/types.ts` (+`ClaimDossier` structured
types), `web/lib/api.ts` (+fixture dossier), `web/app/globals.css` (+v3
component styles on the existing tokens). `tsc --noEmit` clean; verified
live at `localhost:3007` across all three tabs + citation sheet.

**Palantir mapping:** None — UI-only; no ontology, Action Type, or OSDK
change.

---

## 2026-06-06 — `argos-ontology` consolidated: no standing local clone; re-host via one-shot push

**Decision:** There is no longer a maintained `~/Projects/argos-ontology` working
copy. The single source of truth for the ontology spec is **here** in argos:
`foundry/ontology/object-types.yaml` → `scripts/generate_foundry_ontology_spec.py`
→ `foundry/ontology/ai-fde-spec.json`. The Foundry-side code repo (Stemma git,
RID `ri.stemma.main.repository.addcda60-…/Argos`) stays **parked on the stack**
purely to give AI FDE a code-repo RID to read a spec by — it is not a dev surface.

**Why:** Keeping a second local repo produced exactly the drift it invites — the
`argos-ontology/specs/ai-fde-spec.json` snapshot had already diverged from the
canonical generated artifact (stale 3-value closure enum vs. the corrected
11-value Pydantic Literal). The spec is a generated file, not source; the dead
`src/agent/` Code Agent template (see 2026-06-03 entry) carried no live role.
One home avoids the mess.

**Re-host workflow when a future ontology batch needs AI FDE:**
1. Edit `foundry/ontology/object-types.yaml` (source of truth) in argos.
2. Run `scripts/generate_foundry_ontology_spec.py` → fresh `ai-fde-spec.json`.
3. One-shot clone the Foundry repo, drop the generated spec into `specs/ai-fde-spec.json`, push, then discard the clone. (`git clone <stemma-RID-url>` — remote is on the Foundry stack, always recoverable.)
4. Point AI FDE chat at the code-repo RID; it executes the worklist via mounted MCP.

**Palantir mapping:** No change to the ontology RID or the AI FDE execution
surface. Only the *local* artifact-hosting habit changed.

---

## 2026-06-04 — AgentAction bridge shipped and live-verified; Foundry bridge arc fully closed (6/6 green)

**Decision:** The 6th and final Foundry bridge — [`agent_action_bridge.py`](../src/argos/services/foundry/agent_action_bridge.py) — is shipped, wired into [`audit_log.py::append_agent_action`](../src/argos/services/orchestrator/audit_log.py), and **live-verified against the Argos ontology**. Every local `AgentAction` row written to the per-claim JSONL log now also propagates to the Argos ontology via `emit-agent-action` (RID `ri.actions.main.action-type.388fb5af-6111-4c27-8861-dd0aab8d007e`).

**Test state: 25/25.** 19 unit tests + 6 live integration tests, all green.

**Foundry-side rule gap surfaced and closed mid-session:** the initial declarative `modifyObject` rule for `emit-agent-action` did not populate every non-nullable property on the `AgentAction` Object Type, returning `Actions:NonNullablePropertyContainsNull` on every invocation. A focused AI FDE follow-up corrected the rule (defaults applied for system-generated fields like `created_at`; `requires_human_approval` silently defaults to `false`). Zero code changes on the Argos side — the bridge call signature was already correct.

**Code touched:**

- New: `src/argos/services/foundry/agent_action_bridge.py` (the bridge module, ~180 lines)
- New: `tests/services/foundry/test_agent_action_bridge.py` (3 unit + 1 integration xfail)
- Modified: `src/argos/services/orchestrator/audit_log.py` (wires the bridge into the append path)
- Modified: `docs/architecture/foundry-bridge-pattern.md` (status table + deferred function-backed upgrade with pre-baked TypeScript source)
- Modified: `docs/SYSTEM_ARCHITECTURE.md` §0.1 (bridge layer row updated)

**Bridge mapping (local Pydantic AgentAction → Foundry emit-agent-action):**

The local `AgentAction` carries 7 fields; the Foundry Object Type takes 16. Bridge fills documented defaults for fields the local model doesn't capture (`prompt_version="v0"`, `model_id="claude-sonnet-4-6"`, `triggered_by="system"`, `escalation_outcome="applied_automatically"`). Local `action_type` literal maps to Foundry `status` via a registry that treats system-emitted rows as `auto_applied` and validator failures as `schema_violation`. Optional kwargs on the bridge let callers override when the workflow runner starts emitting richer provenance (input hashes, snapshots, reasoning traces, citations).

**Out of scope:**

- **Function-backed `emit-agent-action` for atomic `AgentAction` + `EvidenceCitation` materialization** — declined for this session. AI FDE drafted the TypeScript source; it is captured verbatim in [`docs/architecture/foundry-bridge-pattern.md`](./architecture/foundry-bridge-pattern.md) for a future single-prompt session when cross-claim citation SQL becomes load-bearing. Until then, citations stay first-class in the local JSONL.
- **Expanding the local Pydantic `AgentAction` to match the 16-field Foundry shape** — declined. The simpler local model is intentional and used everywhere in the orchestrator. The bridge does the mapping; the local model stays small.

---

## 2026-06-04 — Foundry bridges verified against live Argos ontology; OSDK package renamed `argos_osdk_sdk` → `argos_live_sdk`

**Decision:** All 5 Foundry writeback bridges (Coverage, Reserve, Liability, Recovery, Closure+Reopen) are end-to-end verified against the live Argos ontology (RID `88f01e1f-...`). The Python OSDK package consumed by `services/foundry/*_bridge.py` is now `argos_live_sdk` (v0.1.0), replacing `argos_osdk_sdk` (v0.4.0).

**Why two packages existed:** Two distinct OSDK Applications had been provisioned in Foundry Developer Console. `argos_osdk_sdk` bound to ontology `d7926c75-...` (legacy pre-scale-out); `argos_live_sdk` bound to the Argos ontology `88f01e1f-...` (poc-2b merged). The class name `OntologyD7926c75F74b4c5dA0d1E21b156c5b0aActionTypes` appears in both — confirmed to be a stale generator artifact, not the actual bound ontology. Diagnostic ladder that proved the binding difference:

| SDK + token | Result | What it told us |
|---|---|---|
| `argos_osdk_sdk` v0.4.0 + new token | `UnauthorizedError` | App-level auth rejected; SDK targets wrong ontology |
| `argos_osdk_sdk` v0.4.0 + old long-lived token | `ActionTypeNotFound: apply-reserve-decision` | Bound ontology (d7926c75) doesn't have the poc-2b actions |
| `argos_live_sdk` v0.1.0 + new token | `ObjectNotFound: primaryKey CLM-001` | Auth ✅, ontology binding ✅, action types resolve ✅; only missing seed data |

**Code touched:**

- Renamed package import `argos_osdk_sdk` → `argos_live_sdk` across `services/foundry/{client,coverage,reserve,liability,recovery,closure}_bridge.py`, `tests/services/foundry/test_coverage_bridge.py`, `scripts/foundry_smoke_test.py`.
- `coverage_bridge.py`: action name `apply_coverage_decision` → `apply_coverage_decision_v2`; parameter `claims_v1=` → `claim=`; parameter `new_parameter=` → `new_posture=`. Tracks the post-poc-2b rename AI FDE applied for the v2 collision.
- Other 5 bridges already used the v0.4.0 signatures (`claim=`, `source_assessment_id=`); no signature changes needed.

**Verification status: 21/21 GREEN.**

- 16 unit tests pass (flag-off no-ops, env-missing raises, optional-kwarg handling).
- 5 integration tests (`-m foundry_integration`) pass against the live Argos ontology. AI FDE seeded a `Claim` row with `claim_id="CLM-001"` and fixed the `apply-closure-decision` Action Type's `recommendation` enum from 3 placeholder values to the 11 real Pydantic Literal values. Every bridge round-trips: invocation → Foundry validation=VALID → `operation_id` RID returned.

**Bridge-contract addition surfaced by this verification arc:**

Bridges now validate `result.validation.result == 'INVALID'` post-call and raise their typed error if Foundry rejected parameters on a HTTP 200 response. The original contract only checked `result.operation_id`, which silently treated INVALID-validation responses as "flag was off" — masking the closure-enum drift for an entire commit. Helper lives at `src/argos/services/foundry/client.py::raise_if_action_invalid`. Every future bridge MUST call it post-OSDK-call; the bridge-pattern doc is updated accordingly.

**Out of scope:**

- **Seeding test data into the live ontology** — deferred. Either create a `CLM-001` Claim via Foundry's Object Type Manager UI, or update test fixtures to a real primary key once any real Claim row exists. Bridges don't block on this.
- **Granting list/iterate permissions on Claim** — the user token can invoke actions but cannot iterate objects. Action-write is the path Argos needs; read-iterate isn't on the critical path.
- **Decommissioning the legacy `argos_osdk_sdk` OSDK App in Foundry** — leave it; it does no harm and removing it requires Developer Console clicks not worth the time.

---

## 2026-06-03 — Foundry ontology schema ops execute through AI FDE chat; Code Agent template is the wrong abstraction

**Decision:** Argos ontology scale-out runs through a deterministic Python generator (`scripts/generate_foundry_ontology_spec.py`) that emits an AI FDE-readable worklist JSON. AI FDE chat (Palantir MCP tools) is the execution surface for schema-plane operations: Object Types, Link Types, Action Types, Global Branches, Proposals. The TypeScript Code Agent template approach (a deployed Function that calls Palantir MCP from AIP Logic) is dead — it cannot reach those tools at runtime.

**Why:** Spent a session attempting the Code Agent approach. Built and deployed an `argos-ontology` Foundry repo with `src/agent/index.ts` calling `@anthropic-ai/claude-agent-sdk` `query()` configured with the Palantir MCP server. Function registered fine; AIP Logic invocation succeeded; output was `null` in 2.04 seconds with zero tool calls. AI FDE diagnosed: **Palantir MCP only mounts inside interactive AI FDE / AIP Agent Studio sessions.** A Function invoked from AIP Logic runs in a stateless compute environment with no MCP server process listening. The `@foundry/functions-api` SDK is data-plane only — it can create/edit instances of Object Types but not the Types themselves. Schema-plane = admin-plane = AI FDE chat or undocumented internal REST endpoints that vary by stack.

Architecture as built:
```
foundry/ontology/object-types.yaml              (source of truth, hand-edited)
  → scripts/generate_foundry_ontology_spec.py    (YAML → AI FDE worklist; auto-derives links from FK property names; FK_ALIASES map for named mismatches; LINK_DROP_FK set for the 60-link cap)
  → foundry/ontology/ai-fde-spec.json            (generated artifact)
  → argos-ontology/specs/ai-fde-spec.json        (Foundry-side repo, AI FDE reads by code-repo RID)
  → AI FDE chat invocation                       (executes via mounted MCP)
  → new global branch + proposal in Foundry      (human review → merge to main ontology)
```

Shipped via this pipeline 2026-06-03:
- `argos-ontology-poc-1`: 28 Object Types, merged into main ontology
- `argos-ontology-poc-2b`: 48 Link Types + 6 Action Types (ApplyCoverage/Reserve/Liability/Recovery/Closure/Reopen Decision), pending merge

Foundry hard limits discovered: **60 one-to-many link types per ontology** (platform-enforced, not per-branch). Auto-derivation generated 56 candidate links; combined with ~12 pre-existing, this exceeded the cap. Dropped 8 lower-value links (5 audit-only `*_party_id` Party variants covered by `AgentAction → Party`, 3 self-referential edges: `parent_request_id`, `reverses_transaction_id`, `superseded_by_assessment_id`). All evidence-plane edges (`EvidenceCitation → AgentAction/Document/SpecialistConfig/FinancialPosting`, `AgentAction → Claim/ClaimExposure/Party`) preserved — they're load-bearing for the sourced-claims thesis. Also: **link type IDs collide across active branches**, not just within one; conflicting branches must be archived before re-running with the same IDs.

**Out of scope:**

- **Raising the 60-link cap via Palantir support** — declined. The 8 dropped links are audit-attribution and version-walk edges that can be derived via SQL joins on demand. Not worth a support ticket.
- **External REST client for ontology schema ops** — would technically work (`@osdk/foundry.admin` may expose them, or browser-DevTools-traced internal endpoints). Rejected because endpoints vary by stack version and require reverse-engineering for each operation. AI FDE is faster, reproducible via the versioned spec file, and the right tool for one-shot ontology scale-out.
- **Wiring the Action Types to real write-back logic in Foundry** — Action Types in Foundry serve as named schema contracts; actual write-back uses Python bridges (`src/argos/services/foundry/*_bridge.py`) per the asymmetric-commit pattern. AI FDE applied placeholder `modifyObject` rules setting `lifecycle-status` as scaffolding; replace if/when function-backed actions are introduced.
- **Foundry-side Code Agent retained as historical reference** — `argos-ontology/src/agent/` stays in place; the repo is now repurposed as the AI FDE spec host (README updated to explain). _(Superseded 2026-06-06: no standing local clone; re-host via one-shot push — see that entry.)_

**Code touched:**

- `foundry/ontology/object-types.yaml` — added `action_types:` block (6 actions with parameters + enums lifted from `services/orchestrator/*_actions.py`); renamed `EvidenceCitation.relation` → `citation_relation` (Foundry reserved word).
- `scripts/generate_foundry_ontology_spec.py` — YAML → AI FDE worklist JSON; PK registry + `FK_ALIASES` + `LINK_DROP_FK` + `FK_SKIP`; emits Object/Link/Action Type entries with `<DATASET_RID_FOR_*>` and `<ONTOLOGY_BRANCH_RID>` placeholders for AI FDE substitution.
- `foundry/ontology/ai-fde-spec.json` — generated; committed for traceability against the YAML source.
- `argos-ontology/README.md` — rewritten to flag Code Agent dead-end and document the spec-host role.
- `argos-ontology/specs/ai-fde-spec.json` — snapshots pushed for AI FDE to read by code-repo RID.
- `docs/SYSTEM_ARCHITECTURE.md` §0.1 (Foundry tenant row updated to "scale-out shipped") + §0.2 (item 6 marked shipped; item 5 bridges unblocked, now top-ranked).

---

## 2026-06-02 — Eval-design policy: every emitted field is graded-or-deferred, deterministic math defaults to zero tolerance

**Decision:** Two load-bearing policies that govern every workflow eval slice
going forward (Liability is the reference implementation; Reserve, Recovery,
Closure must inherit):

1. **Every Pydantic field a workflow emits must be either (a) asserted by
   ≥1 eval case, or (b) explicitly enumerated under "Known asterisks" in
   the threshold doc as deliberately-not-graded, with a stated reason and
   a revision trigger.** No field gets a free pass. Rich-interface fields
   without test coverage are silent liability surfaces.

2. **Numeric assertions on deterministic output default to `tolerance = 0`
   (exact equality).** Widen per-case only when there's a named
   stochastic source (LLM sampling, floating-point order-of-operations
   sensitivity, downstream rounding outside the workflow's control).
   Pre-emptive tolerance is a regression hole.

**Why:** Both rules came out of the Liability eval slice first build
(commit `c110de1`, follow-up `7798cc4`):

- The schema field `ExposureCeiling.vicarious_cap_value` shipped uneval'd.
  When GC-10 finally asserted it, the eval failed first run — the
  calculator emits the per-occurrence ceiling (`$300K`), while the schema
  field name implies per-person (`$100K`). Both numbers are statutorily
  correct but answer different questions. A Reserve writeback consuming
  `vicarious_cap_value` would have silently picked up an ambiguous figure.
  The `design-rich-implement-minimal` rule needed this missing corollary.

- `DEFAULT_FAULT_TOLERANCE_PP` was set to `Decimal("5")` defensively because
  the fact-pattern anchors use averages-of-bands. After the first green run
  I tightened to `Decimal("0")` and the suite stayed green — confirming the
  ±5pp was hiding nothing real and would have masked any future regression
  (e.g. an apportionment shift from 95% → 92%). Defensive tolerance on
  deterministic Python `Decimal` math has no upside.

**Out of scope:**

- Layer 1 (LLM extractor) eval thresholds — deferred until a live-API
  budget is set and a labeled corpus exists. The threshold doc carries the
  target numbers but the harness isn't built.
- Calibration grading (spec-vs-real-world ground truth) — deferred until
  Argos has ≥10 real closed claims with known outcomes.
- Whether `vicarious_cap_value` should surface both per-person and
  per-occurrence figures — resolution deferred to the Reserve eval slice
  (which is the first consumer that will care).

**Code touched:**

- `tests/evals/liability/_harness.py` — `LiabilityEvalCase`, `assert_case`,
  `DEFAULT_FAULT_TOLERANCE_PP = Decimal("0")`.
- `tests/evals/liability/test_golden_cases.py`, `test_adversarial.py` — 23
  cases asserting every output field on `LiabilityOutputs`.
- `docs/evals/liability-thresholds.md` — contract + run history + the
  "Open gaps and revision path" section that names triggers for each
  unresolved gap.
- `pyproject.toml` — `eval` marker registered, default suite excluded via
  `addopts = "-m 'not eval'"`.
- `docs/SYSTEM_ARCHITECTURE.md` §0.1 + §0.2 — Liability slice marked
  shipped, Reserve promoted to next.

---

## 2026-06-02 — Closure workflow architecture: extractor + 25-gate policy engine + bifurcated calculator + diligence ledger

**Decision:** Closure is the sixth and terminating analytical workflow. Same
5-stage shape as Recovery / Liability:

1. **Stage A — LLM extractor:** reads claim state + committed upstream
   assessments (Coverage, Liability, Reserve, Recovery, Brief) and emits a
   structured `ClosureInputs` payload via Anthropic tool_use. Extractor is
   bounded to fact extraction; it does not decide ready-to-close.

2. **Stage B1 — Python policy engine:** evaluates ~25 deterministic
   closure gates organized into 6 tiers — Tier A (statutory FL +
   bad-faith), Tier B (federal lien/MSP), Tier C (release evidence),
   Tier D (audit + authority), Tier E (defense-track bifurcation),
   Tier F (preservation + retention). Each gate emits pass/fail/n_a +
   cite + optional BlockingDefect.

3. **Stage B2 — Python calculator:** computes `ready_probability` (Tier
   weighting: single Tier A failure caps at 0.05; Tier B at 0.25; Tier C
   at 0.50), ranks blocking defects, bifurcates `indemnity_status` /
   `defense_status` per §624.155(6)(a), classifies into one of OIR's
   three regulatory buckets (closed_with_payment / closed_without_payment
   / reopened), and computes `preservation_until_date` floor.

4. **Stage C — Diligence ledger + templated rationale:** Boecher / Ruiz
   discoverable. Includes per-lien resolution records (Medicare,
   Medicaid, WC, ERISA, hospital, VA, TRICARE), multi-claimant global-
   settlement artifacts (Farinas / Shuster compliance), CRN state,
   notice-delivery audit, preservation plan, OIR classification.

**Recommendation surface:** 11 controlled literals
(`ready_to_close_with_payment`, `ready_to_close_without_payment`,
`closed_with_open_recovery`, four `soft_close_*` states for industry-
standard pending windows, `blocked_by_defects`, `requires_senior_review`,
`requires_legal_review`, `recommend_reopen`). Closure execution is
**always human** — auto-close stays off in v1.

**Why:** The close moment is the highest-leverage bad-faith trap in the
FL auto BI lifecycle. Berges totality-of-circumstances pulls the entire
handling history forward to the close decision; Ruiz strips work-product
privilege over every artifact created up to resolution. Federal MSP law
imposes double-damages exposure for closing a Medicare beneficiary file
with unresolved conditional payments (42 U.S.C. §1395y(b)(2)(B)(iii) +
(b)(3)(A); 42 C.F.R. §411.24(g)+(i)). NAIC Model 902 and FL §626.884
make the close action regulator-auditable. The TPA examiner manually
scans ~25 separate gates today; Closure surfaces the gate evaluations
+ ranked defects + remediation hints and routes the close-execution
decision to the human.

**Architectural calls resolved by the 2026-06-02 6-dimensional research
workflow (54 confirmed findings):**

- **Recovery decoupling — confirmed industry practice.** Open subro
  does NOT block close. Closure emits `closed_with_open_recovery` as a
  distinct state. Recovery survives as a separate file with its own
  SOL clock (Crawford & Co., Amaxx).
- **Reopen mechanics — same claim ID, not new file.** Per ClaimCenter
  precedent. `apply_reopen_decision` flips status on the existing
  Claim.
- **Indemnity-close vs defense-close bifurcation.** §624.155(6)(a)
  requires this for any multi-claimant interpleader. Schema carries
  distinct `indemnity_status` and `defense_status` fields.
- **Soft-close states.** Modeled as four `soft_close_pending_*`
  literals matching industry practice (Sedgwick, Gallagher Bassett,
  Crawford, ESIS) for pending Medicare Final Demand (60–180d
  post-TPOC), pending Section 111 confirmation (135d window), pending
  lien release letter, pending release execution.
- **OIR three-bucket classification.** Closed-with-payment /
  closed-without-payment / reopened — these are the regulatory states
  and are first-class in the schema.
- **Hospital lien search per-COUNTY, not statewide.** Shands v.
  Mercury (Fla. 2012) struck down §713.50. Closure surfaces
  `hospital_lien_county_search_status` and treats `pending` as a
  variance flag for v1.

**Refuted findings explicitly excluded:**

- **Mid-Continent Cas. Co. v. Basdeo** as multi-claimant bad-faith
  authority. Case exists but is a declaratory-judgment coverage
  action. Use Farinas (850 So.2d 555), Shuster (591 So.2d 174),
  Boston Old Colony (386 So.2d 783), §624.155(6) HB 837 instead.
- **§626.989(6) SIU confidentiality** as cited verbatim — language
  misplaced in the original research finding.

**Out of scope (v1):**

- Live CMS Section 111 RRE integration. Closure extracts
  `section_111_tpoc_log` from claim docs (transmit receipts); live
  integration deferred.
- Statewide hospital-lien registry. None exists in FL; per-county
  searches are manual. Closure surfaces `pending` as variance flag.
- AgentAction backfill enforcement. D1 fires on most files initially
  because AgentAction writes are not yet wired. v1 treats D1 as
  warning, not block.
- Auto-close even for trivially-closable cases. Ship OFF by default;
  enable after golden-set calibration.
- Distinct "reopen workflow." Reopen = existing pipeline running on a
  closed file, with Closure auto-rerunning when an upstream output
  materially shifts.

**Code touched (planned):**

- New: `src/argos/services/closure/` (policy engine, calculator,
  ledger, rationale, constants).
- New: `src/argos/workflows/closure.py` (extractor + run_closure
  orchestration).
- Refactored: `src/argos/schemas/workflows/closure.py` (full rewrite
  of current minimal scaffold).
- Modified: `src/argos/services/orchestrator/runner.py` (register
  `_run_closure_via_adapter` + `_load_closure_upstream`).
- Modified: `src/argos/services/orchestrator/dispatcher.py` (add
  `closure` to `POSTURE_TO_WORKFLOWS` for closure-trigger postures).
- New: `src/argos/services/orchestrator/closure_actions.py`
  (`apply_closure_decision`, `apply_reopen_decision`).
- New: `tests/services/closure/` (constants, policy engine, calculator,
  ledger+rationale).
- New: `tests/workflows/test_closure.py` (extractor + integration).

Full spec at `docs/specs/closure-workflow.md`. The Liability / Recovery
implementation pattern is the template (commits `9c0c1ea` + `c68df11`,
`057260d` + `40f662b`).

---

## 2026-06-02 — Recovery workflow architecture: extractor + policy engine + recoverable-basis calculator + diligence ledger

**Decision:** Recovery is the sixth analytical specialist, following the same
4-stage shape Tom validated for Liability and Reserve:

1. **Stage A — LLM extractor (Software 3.0):** reads FNOL packet, policy
   declarations, police / crash report (§316.066 admissibility flag),
   repair / medical bill registers, EOBs, and any rental / fleet / loaner
   agreement. Classifies tortfeasor vehicle per §627.732(3) (body type +
   primary-use test, NOT weight). Extracts VIN, owner / operator split,
   omnibus-insured candidates, resident-relative roster, recall signal,
   EDR-availability signal, and any release / settlement language.
   Emits structured `RecoveryInputs` only — no pursue / abstain judgment.

2. **Stage B1 — Python policy engine (Software 1.0):** applies 15 FL
   doctrines as deterministic step-function gates against
   `RecoveryInputs` + upstream `LiabilityAssessment` + `ReserveAnalysis` +
   Coverage state. Each gate emits pass / fail + cite + variance flag.

3. **Stage B2 — Python calculator (Software 1.0):** pure math.
   Recoverable basis = §768.0427-capped damages − PIP collateral source −
   made-whole shortfall, apportioned per Liability's fault percentages
   across five layered targets (operator policy, §324.021(9)(b)3 owner
   vicarious cap layer, owner direct-negligence uncapped, Fabre
   non-parties, product-defect / recall). Net economics = gross × P(recovery)
   − fee drag − fee-shifting exposure. SOL + AF + §768.76 + §627.727(6)
   countdowns computed against today's date.

4. **Stage C — Diligence ledger + templated rationale:** byte-reproducible.
   Co-equal artifact (not a side effect) discoverable under
   *Allstate v. Boecher* + *Allstate v. Ruiz*. Doubles as defense exhibit
   in downstream bad-faith litigation. Includes AF signatory check
   timestamp + source, anti-subrogation per-coverage-section cross-
   reference, made-whole computation, decision rationale, preservation
   hold status, sources cited, open requests, and evidence-not-obtained
   positive record.

**Why:** Recovery's analytical work is overwhelmingly doctrinal
gate-checking + apportioned math against external clocks. Free-form LLM
ranking of subro targets is precisely the failure mode
[[policy-engine-first-then-llm-extraction]] identifies — vendor scoring
tools (CCC Safekeep, Shift, Athenium) already commoditize identification
scores. The Argos wedge is the LAYER ABOVE: deterministic FL-aware gates
+ calibrated probability per layer + sourced evidence +
Boecher-discoverable diligence trail. Specialty TPAs leak recovery dollars
at the FRONT of the funnel (FNOL-stage missed identification + handler-
owned subro pattern + post-HB-837 regime change not re-baselined), not
the back; an AI-native layer that runs the gates deterministically before
any external demand is the leverage point.

**Output framing:** Recovery never auto-commits. Recommendation literal is
`pursue | route_to_af | route_to_litigation | route_to_negotiated_demand |
abstain | senior_review_required`. The diligence ledger + per-gate
evidence + per-layer apportionment are the primary surfaces the adjuster
reviews. Authority is keyed off **net apportioned recoverable** (not
gross damages) — Recovery is the money-back surface, the ceiling is what
we can actually get back.

**Triggers** (event-driven first, calendar fallback): `FNOL_THIRD_PARTY_SIGNAL`
(emits preservation hold only — no quantified recommendation pre-Liability);
`LIABILITY_SUBRO_REFERRAL_HINT` (primary); `RESERVE_INDEMNITY_PAID`
(triggers made-whole re-eval); `EXTERNAL_COUNTERPARTY_EVENT` (tortfeasor
carrier tender / claimant §768.76 notice / AF dismissal — each starts a
30-day or 60-day external clock); `SOL_THRESHOLD_CROSSED` (T-90 / T-60 /
T-30 against 2yr post-HB-837 or 4yr pre-HB-837 clock); `SALVAGE_RELEASE_REQUEST`
(blocks release until *Valcin* preservation documented); `CALENDAR_DIARY_90_DAY`.

**FL-specific doctrines (15) implemented as policy-engine gates:**
HB 837 51% bar (§768.81(6)); HB 837 negligence SOL selector (§95.11(4)(a) —
2yr post / 4yr pre); anti-subrogation rule (per coverage section);
made-whole doctrine (*Schonau v. GEICO* — limited-fund-only, freestanding
direct claim survives); PIP subrogability carve-out (§627.7405 commercial
vehicle only, taxicab excluded, classified per §627.732(3));
UM preservation 30-day (§627.727(6)); collateral-source 30-day (§768.76(7));
§324.021(9)(b)3 vicarious cap ($100K/$300K + $50K PD + conditional $500K
econ); §768.81(3) joint-and-several abolition + Fabre apportionment;
§627.737 verbal threshold; §768.0427 paid-not-billed (HB 837); AF
compulsory jurisdiction ($100K cap + 60-day refile); *Valcin / Martino*
spoliation preservation duty; deny+subrogate interlock (§624.155 +
*Harvey v. GEICO* — HB 837 third-party safe harbor does NOT extend to
Recovery conduct); *WQBA* step-into-shoes defenses (pre-tender release
extinguishes recovery).

**Variance zones (9)** where calculator does NOT silently commit:
comparative-fault cliff buffer [45%, 55%]; commercial-vehicle
classification ambiguity; anti-subrogation per-coverage-section ambiguity;
SOL accrual-vs-filing split (loss date within 30 days of 3/24/2023);
made-whole with partial settlement; deny+subrogate; AF signatory
unverifiable; products-liability repose boundary; release / pre-tender
settlement detected.

**Anti-patterns rejected** (12 total — see spec). The three most
load-bearing: free-form LLM ranking of subro targets; billed-amount
recoverable basis (§768.0427 strips this); demand letter before
omnibus-insured cross-reference (anti-subro gate runs BEFORE any external
communication).

**Out of scope (v1):** workers' comp / GL / commercial property subro
lines (line-specific doctrine warrants its own specialist); non-FL losses
(FL-only by design; cross-state needs lane-and-SOL selection logic);
UM-subro nuances outside §627.727(6); real-time AF signatory roster sync
(v1 ships seeded roster); calibrated P(recovery) per-program tuning
against settled-outcome corpora (v1 ships seeded scalars); cross-stream
Coverage roster real-time sync (snapshot semantics in v1).

**Code touched (planned):** `docs/specs/recovery-workflow.md` (this spec);
`src/argos/schemas/workflows/recovery.py` (full refactor — `RecoveryInputs`
+ `RecoveryAssessment` + nested types); `src/argos/services/recovery/`
(`constants.py`, `policy_engine.py`, `apportionment_calculator.py`,
`diligence_ledger.py`, `rationale.py`); `src/argos/workflows/recovery.py`
(extractor + runtime); `src/argos/services/orchestrator/runner.py` (wire
`_run_recovery_via_adapter`); test suites mirroring Liability's structure.
The Liability implementation pattern (commits 9c0c1ea + c68df11) is the
template.

**Palantir mapping:** RecoveryInputs / RecoveryAssessment → Ontology
object types; doctrine gates → Functions; preservation hold + AF filing
+ demand letter → Action Types; AF signatory roster + NHTSA recall lookup
→ Functions wrapping external data; Boecher-discoverable diligence ledger
→ first-class Ontology object with discovery-survivable schema.

---

## 2026-06-01 — Liability workflow architecture: extractor + policy engine + apportionment calculator + diligence ledger

**Decision:** Liability follows the Reserve precedent (LLM extractor + Python
calculator + templated rationale, byte-reproducible) but the calculator
decomposes into two stages AND there is a third co-equal artifact:

1. **Stage A — LLM extractor (Software 3.0):** reads documents + claim
   state, emits structured `LiabilityInputs` — fact pattern, parties +
   roles, evidence items with quoted spans, owner relationship,
   intoxication evidence, rear-end rebuttal evidence, demand state,
   ROR/CRN state.
2. **Stage B1 — Python policy engine (Software 1.0):** FL doctrine gates.
   Step-function logic. Determines applicable regime (pre/post HB-837),
   vicarious cap ceiling, Graves preemption, negligent entrustment
   branch, §768.36 intoxication bar applicability. 15 named doctrines
   versioned in `FL_DOCTRINE_REGISTRY_V1`.
3. **Stage B2 — Python apportionment calculator (Software 1.0):** anchor
   + adjustment table. Per-pattern anchor (rear_end ≈ 95% rear per
   *Birge/Pierce/Eppler*; left_turn ≈ 90% turner per FL Std. Jury Instr.
   401). Five-tier evidence weight class (hard_data ±20-25, independent
   ±10-15, party_admission ±15, rebuttable_signal ±5-10, credibility_only
   ±0-5). Per-party-pair scalar with confidence band from evidence
   completeness + inter-evidence agreement.
4. **Stage C — Diligence ledger (templated, co-equal artifact):**
   contemporaneous record of posture by party, basis evidence with
   quoted spans, change conditions, next review, open requests with age,
   evidence-not-obtained with reason, prior-posture delta, supervisor
   disagreement record. NOT a side effect. This is the *Allstate v.
   Ruiz* (901 So. 2d 802) discoverable artifact and the *Harvey v.
   GEICO* procedural-diligence defense.

**Output framing (per Tom's nudge 2026-06-01):** the primary deliverable
is the **evidence-anchored structured insight** + diligence ledger. The
apportionment percentage is what falls out of the structured record, not
what gets generated first. Liability does not auto-commit to fault; it
generates evidence aligned to FL doctrines, surfaces what the evidence
supports and what it doesn't, and produces a recommended apportionment
with confidence band + audit trail. The adjuster commits. Argos
surfaces.

**Why split into 4 stages (vs Reserve's 3):**

- **FL doctrine gates are step-functions** (51% bar, Graves preemption,
  §768.36 intoxication, Fabre pleading, dangerous-instrumentality cap)
  with binary effects on recovery. Putting them in LLM judgment is the
  hybrid-v2 trap (model infers its own policy). Per
  [[policy-engine-first-then-llm-extraction]]: deterministic gates +
  LLM for extraction only.
- **The diligence ledger is the product moat.** Under *Allstate v.
  Ruiz* the claim file diligence trail is discoverable in bad-faith
  litigation. *Harvey* lost on procedural-diligence gaps, not on
  substantive fault calls. If we ship a defensible percentage with no
  trail, we have built the wrong product. The ledger IS the trial
  exhibit plaintiff's counsel reads to the jury — designed accordingly.

**Calibration:** v1 fact-pattern anchors, evidence weights, doctrine
registry, and authority bands are practitioner-anchored seeds informed
by the 2026-06-01 multi-dimensional research workflow (73 findings, 10
verified, 62 partial, 1 uncertain, 0 refuted across apportionment
methodology, FL doctrines, source-document mapping, adjuster mechanics,
specialty-TPA practice, bad-faith diligence). Closest published anchor
proxy is MA 211 CMR 74 (codified presumptive fault). FL does not codify
equivalents — we're industry-aligning anchored to controlling cases.

**Variance zones (10 named) route around the calculator:** the
calculator does NOT silently commit through `near_51_pct_bar` (force
roundtable regardless of dollars), `fabre_non_party_evidenced_but_unpled`
(dual-scenario), `powell_clarity_ambiguity`, `sufficient_evidence_borderline`
(do not auto-start §624.155(4) 90-day clock), `siu_referral`, or any
contradiction-pattern. Step-function risk dominates dollar risk.

**Anti-patterns this rejects:**

- LLM emits final fault % directly
- Auto-start §624.155(4) safe-harbor clock on borderline sufficient-evidence
- Silent omission of evidence we didn't collect (use `evidence_not_obtained` with reason)
- Feed consistency-check contradictions silently into fault adjustment (widen band + SIU referral instead — opening-posture-as-real-call is bad-faith trap)
- Commit through a variance flag
- Output a "bad-faith exposure score" (faking that judgment invites the AI-excuse-generator-becomes-bad-faith-exhibit failure mode)
- Score Fabre non-parties without pleading check (Rule 1.110(d))

**Cost we are paying:** the rationale narrative is templated, not
adjuster-voice. Same trade as Reserve. For legally-bearing outputs in
FL bad-faith country, this is the right trade.

**Out of scope (v1, explicit):** chain-reaction crashes with single
claimant + divisible injuries across damage categories; non-FL
jurisdictions (15 doctrine gates would each need a state-specific port);
first-party UM/UIM claims; coverage-questions liability interactions
(late notice + non-cooperation + Fabre stacking); supervisor-vs-examiner
disagreement dynamics beyond metadata; bad-faith risk scoring; subro
mechanics beyond handoff flag.

**Code touched (when shipped):**
`docs/specs/liability-workflow.md` (this entry's basis),
`src/argos/schemas/workflows/liability.py` (refactor to
LiabilityInputs + LiabilityAssessment split),
`src/argos/services/liability/policy_engine.py`,
`src/argos/services/liability/apportionment_calculator.py`,
`src/argos/services/liability/constants.py`
(FACT_PATTERN_ANCHORS_V1, EVIDENCE_WEIGHTS_V1, FL_DOCTRINE_REGISTRY_V1),
`src/argos/services/liability/rationale.py`,
`src/argos/services/liability/diligence_ledger.py`,
`src/argos/workflows/liability.py` (extractor + orchestration),
`src/argos/services/orchestrator/runner.py` (replace
`_stub_workflow("liability")` with real workflow).

**Research workflow run:** wy3ekvjbs (2026-06-01). Full proposal in
session transcript; verified findings drive the doctrine registry +
anchor table + variance zones.

---

## 2026-06-01 — Reserve workflow architecture: LLM extractor + Python calculator split

**Decision:** Reserve workflow is split into two stages, not bundled
as one LLM tool_use call:

1. **Extractor (LLM, Software 3.0)** — `extract_reserve_inputs` reads
   `SyntheticClaim` documents + `coverage_posture` and emits a
   structured `ReserveInputs` Pydantic model. Bounded scope:
   classify injury bucket, surface specials, anchor permanency,
   pull demand history, flag bad-faith markers. Graded by
   per-field anchor-pair eval.
2. **Calculator (Python, Software 1.0)** — `compute_reserve` is a
   pure function `(ReserveInputs, ClaimContext, ProgramConfig) →
   ReserveAnalysis`. Multiplier tables, phase budgets, authority
   bands, notice thresholds live as versioned Python constants
   (`MULTIPLIER_TABLE_V1`, `NOTICE_THRESHOLDS_V1`). Unit-tested
   with hand-built inputs; byte-reproducible.
3. **Rationale string** — templated and interpolated by Python from
   extractor outputs + calculator intermediates. NOT LLM-generated.
   Audit trail reproducible byte-for-byte.

Authority bands, phase budgets, escalation thresholds, and
reinsurance notice triggers are loaded at runtime from per-program
`PROGRAM_CONFIG` (CHA-negotiated), not hardcoded.

**Why:**
- **[[karpathy-principles]] Software 1.0/2.0/3.0** — reserve math is
  specifiable (formulas + tables) → Software 1.0 territory.
  Extraction is unstructured → Software 3.0. Bundling collapses
  the eras and forfeits the verifiability of each.
- **[[karpathy-principles]] Verifiability + Start Simple Verify Then
  Add Complexity** — calculator is unit-testable against golden
  files; extractor is gradable per-field. Bundled tool_use is
  neither.
- **[[2026-05-30-nick-nisi-skills-lessons]] Enforce don't instruct
  + Replace trust with evidence** — the Python calculator IS the
  enforcement layer. The LLM cannot lie about math because the
  math is a function call. Unit tests are evidence; an LLM
  emitting `recommended_outstanding_band.p50 = 138_400` is trust.
- **[[applied-llms]] §3.2 architecture > model** — calculator
  outputs are stable across model swaps. Bundled tool_use would
  require recalibrating the whole workflow on every model change.
- **Hybrid v2 killed lesson** (2026-06-01 prior entry) — v2 failed
  by converting an evaluation problem into an oracle problem.
  Bundled reserve tool_use is the same trap: the model infers its
  own multiplier policy instead of executing the documented one.
- **Argos rule** ([[policy-engine-first-then-llm-extraction]]):
  deterministic gates + LLM for extraction/materiality only;
  never free-form LLM ranking. Reserve math is the policy engine.
- Bad-faith litigation in FL requires byte-reproducible audit
  trails. Fluent LLM-voice rationale strings cannot be defended
  in deposition the same way a versioned Python interpolation can.

**Cost we are paying:** the rationale string reads as
structured audit-trail prose, not adjuster-voice paragraphs.
Templated interpolation loses some natural-language nuance.
For legally-bearing outputs this is the right trade — but it is
a real trade, called out explicitly in the spec so we don't
backslide.

**Calibration:** v1 multiplier tables, severity tier dollar
bands, phase budgets, and authority bands are practitioner-anchored
seeds informed by the 2026-06-01 multi-dimensional research
workflow (66 findings, 10 verified, 55 partial, 0 refuted across
methodology, severity distributions, adjuster mechanics, specialty-TPA
practice, authority bands, FL regulatory). All flagged in the spec
as v1 defaults requiring per-program tuning against carrier
closed-claim loss-development data before production.

**Out of scope (v1, explicit):** multi-claimant interpleader,
non-FL jurisdictions, UIM/UM/PIP/PD, subrogation recovery,
coverage disputes (assumed resolved by Coverage workflow),
continuous Colossus/ClaimIQ-style severity scoring, time-value
of money on long-tail catastrophic, per-claim ULAE allocation,
separate bad-faith reserve overlay without sign-off, reinsurance
treaty mechanics beyond single notice-trigger.

**Supersedes:** any prior implicit assumption that Reserve would
be a single bundled LLM tool_use call emitting `ReserveAnalysis`
directly.

**Code touched (this commit, when shipped):**
`docs/specs/reserve-workflow.md` (rewritten),
`docs/specs/reserve-workflow-flow.md` (unchanged — still describes
end-to-end flow, calculator is internal to runner),
`docs/research/reserve-estimation-methods.md` (calibration
research, unchanged). When implemented:
`src/argos/workflows/reserve.py`,
`src/argos/services/reserve/calculator.py`,
`src/argos/services/reserve/constants.py`,
`src/argos/services/reserve/rationale.py`,
`src/argos/schemas/workflows/reserve.py` (refactor to
ReserveInputs + ReserveAnalysis split).

**Wiki consultation logged:** `_Registry/log.md` 2026-06-01
consult entry — `reserve-workflow-extractor-calculator-split`.

---

## 2026-06-01 — Analysis re-trigger on new docs inside `advance_claim`

**Decision:** `advance_claim` now closes the cross-stream loop in
both directions. After Steps 1–3 (classify, ingest disclosures,
run correspondence advance) it diffs `caseload.documents` against
its pre-advance snapshot, finds every doc that newly landed this
round, and — if a `JobQueue` was supplied — runs the Document
Reader on each, dispatches the resulting `RelevanceCall` into
Jobs, and enqueues them. The heavy analytical workflows
(Coverage / Reserve / Liability) still drain on the runner's
cadence, NOT inline.

**Why this gap mattered.** Without re-trigger, the cross-stream
story I walked Tom through earlier was half-true. A new
disclosure (e.g., police report) landed in `caseload.documents`
via Step 2, but the Document Reader never saw it, so Liability /
Reserve never re-ran on the fresh evidence. The analysis pipeline
was a one-way street with `advance_claim` doing nothing to plug
the entry. New disclosure → updated brief was a story we told
without a function that made it true.

**Scope: all newly-added docs, not just disclosures.** The
re-trigger fires on every doc that newly appears in
`caseload.documents` this round, which catches BOTH:

  - Disclosures added by Step 2 (direct add)
  - Docs added by Step 3 via `IngestReply.apply_outcome` (loop
    closure on reply candidates — match or escalate, the doc lands
    either way)

The reply-vs-disclosure classification is about correspondence
routing, not analysis materiality. A defense-counsel letter that
matched as a reply might also signal a posture change ("we're
admitting partial liability") — Reader should look at it. Doing
this with a simple `pre_doc_ids` diff means one place handles
both code paths without branching.

**Opt-in via `job_queue` kwarg.** When `job_queue=None` (the
default), the re-trigger is skipped entirely and `advance_claim`
behaves exactly as before. This preserves the cheap-coordination
posture for any caller that doesn't yet have a JobQueue wired up
— and is what every existing test still relies on (no regressions).

**Reader is fast and inline; analytical specialists are slow and
deferred.** The architecture rule "no LLM calls inline" applies
to the analytical specialists (Coverage / Reserve / Liability —
expensive, posture-shaping). Reader is a fast routing
classification (~1 LLM call, single tool emission) and inlining
it is the natural place for it: the routing decision has to
happen before any analysis Job can be enqueued. This is the same
split `screen_caseload` already uses for triage screening.

**Code:**
- `src/argos/services/triage/reader_integration.py` — new
  `retrigger_analysis_for_docs(docs, claim_id, *, caseload,
  queue, reader_fn=None)` helper. Reuses the existing
  `_build_claim_context` (ledger-aware reserve + paid roll-up)
  and `dispatch` wiring. Returns the list of Jobs the queue
  actually accepted (idempotency-filtered).
- `src/argos/services/orchestrator/claim_advance.py` —
  `advance_claim` now snapshots `pre_doc_ids` at entry, calls
  the helper after Step 3 when a queue is supplied. New kwargs:
  `job_queue: JobQueue | None`, `reader_fn: ReaderFn | None`.
  Report gains `analysis_jobs_enqueued: list[Job]`.
- Idempotency: `JobQueue.enqueue` already keys on
  `(workflow, claim_id, triggered_by_doc_id)`. Calling
  `advance_claim` twice on the same doc adds it to the file the
  first time, classifies it as "already present" the second
  time (no new Reader pass, no double-enqueue) — verified by
  test.

**Verification:** 421/421 tests pass (up from 415). 6 new tests
on `advance_claim`:
- 1 on opt-in semantics (no queue → no re-trigger)
- 3 on disclosure-path re-trigger (relevant=True enqueues
  matching workflow Jobs; relevant=False enqueues nothing;
  `damages` posture enqueues both Reserve and Liability)
- 1 on reply-borne docs (a doc that matched a reply ALSO goes
  through Reader on the same advance — both streams fire on
  the same evidence)
- 1 on idempotence (second advance on the same doc returns
  empty `analysis_jobs_enqueued`)

**What's still NOT wired:**
- Reserve and Liability workflows themselves remain stubs in
  the runner (`{"status": "not_implemented"}`). The re-trigger
  correctly enqueues Jobs for them; the Jobs sit in the queue
  and the stub workflows mark themselves done with the "not
  implemented" payload. Next gap: implement Reserve and
  Liability workflows so there's something real for the
  re-trigger to fire.
- Writebacks for Reserve / Liability — symmetric to
  `apply_coverage_decision`. Producer side is the missing
  piece; once the workflows exist, the writeback functions
  drop in cleanly.
- `AgentAction` audit log writes — schema exists, nothing
  appends yet. Becomes load-bearing once the cockpit needs to
  show "here's what AI did, here's what you committed."

**With this, the cross-stream loop closes end-to-end.** New
evidence enters via `advance_claim`, gets classified and routed,
disclosures land in the file, replies close question state, and
EVERY new doc gets a Reader pass so the analysis pipeline picks
it up on the next runner drain. The two streams are now
genuinely composed, not just structurally adjacent.

---

## 2026-06-01 — Process fix: post-compaction architecture re-read protocol

**Decision:** After context compaction, mandatory re-read of
`docs/AGENT_ARCHITECTURE.md` §2 and titles scan of `docs/DECISIONS.md`
before answering any "what's next" / "what's missing" / "did we already
solve X" / "what's the current state" question. This rule is now in
both project `CLAUDE.md` and the user-level memory system so it
survives every compaction.

**Why this exists:** After the correspondence-layer compaction this
session, I proposed building the triage ranker as the next gap. The
triage ranker has been shipped for over a week — there's a full
`src/argos/services/triage/` module (features, S1 ranker, policy
engine, hybrid v2, reader integration), three specs, four threshold
evals. I had `AGENT_ARCHITECTURE.md` on disk describing it. I didn't
re-read it. I free-associated from the within-claim work the
compaction summary captured, and proposed work that already existed.
Tom called it out: "I told you create docs of, like, our current
architecture and whatever built on top is based off that doc. Now in
this case, we're not doing that."

**Root cause:** Compaction summaries capture *what the recent session
built*, not *what the full system looks like*. Acting on the summary
alone produces confident, plausible-sounding gas-lighting. The
architecture doc is corrective; recent context is biased. The fix is
to force the corrective read before any whole-system question gets
answered.

**Three concrete mechanisms:**

1. **`docs/AGENT_ARCHITECTURE.md` §2.0 — "Current state inventory."**
   New section at the top of §2. Single source of truth for what's
   shipped, what's killed, and what's not yet built. Updated every
   time a DECISIONS entry ships or rejects something. This is what to
   read first; it's deliberately short enough to scan in one pass.

2. **Project `CLAUDE.md` — "Mandatory re-read after context
   compaction"** section. Enumerates the trigger questions ("what's
   next," "what's missing," "is X built," etc.) and the required
   reading list (`AGENT_ARCHITECTURE.md` §2 + `DECISIONS.md` titles).
   Explicit override of the temptation to answer from recent context
   alone.

3. **Rejection entries get the same rigor as ship entries.** When
   something we tried doesn't work (hybrid v2 being today's example),
   append a DECISIONS entry that's load-bearing in the same way — what
   we tried, why it failed, what we keep vs drop, the replacement
   direction. Without this, architecture docs accumulate aspirational
   pieces and drift from reality silently. Hybrid v2's `KILLED`
   frontmatter in its spec was correctly recorded; the gap was that
   `AGENT_ARCHITECTURE.md` didn't surface the rejection — fixed in
   this entry's companion architecture update.

**User-level memory:** `feedback_post_compaction_reread_architecture.md`
indexed in `~/.claude/projects/.../memory/MEMORY.md`. Persists across
projects so the same failure mode doesn't show up on a different repo.

**What this changes about session behavior:** When Tom asks "what's
next" after a long session, the answer must start by checking the
architecture doc, not by extrapolating from the conversation. If the
architecture doc looks stale (spec says one thing, doc says another),
fix the drift first via rejection entry + doc update, *then* answer
the question.

**Not a code change.** Doc + memory + protocol. Verified by writing
the protocol into both load points and adding the inventory section to
`AGENT_ARCHITECTURE.md` so the next compaction has somewhere correct
to ground.

---

## 2026-06-01 — Cross-stream scheduler shipped (`advance_claim`) + Coverage→Claim writeback (`apply_coverage_decision`)

**Decision:** Two gaps from the prior status report close together
because they're the two ends of the same loop:

1. **`advance_claim`** — single entry point that composes the
   analysis pipeline and the correspondence loop for one claim,
   one round. Classifies new inbound docs (reply candidate vs.
   disclosure), routes accordingly, runs the correspondence
   advance.
2. **`apply_coverage_decision`** — small writeback action the
   cockpit calls when an adjuster commits a coverage decision.
   Flips `claim.coverage_posture`. This is the **producer** side
   of ROR; the **consumer** (Drafter reading the posture) shipped
   earlier.

**Renamed `tick` → `advance` everywhere.** "Tick" was internal
jargon. The function name should read like what it does. Now
`run_claim_tick` → `advance_claim`, `run_correspondence_tick` →
`advance_correspondence`, `ClaimTickReport` → `ClaimAdvanceReport`,
`CorrespondenceTickReport` → `CorrespondenceAdvanceReport`. File
`claim_tick.py` → `claim_advance.py`.

**Doc classification heuristic (v1, intentionally simple):** a
new inbound doc on a claim is a `reply_candidate` if any open
outbound (`sent` or `overdue`) exists on the claim, otherwise a
`disclosure`. Reply candidates pass through the Reply Parser
inside `advance_correspondence`; disclosures get appended
directly to `caseload.documents` so the next `is_answered()`
pass picks them up. False positives are recoverable (parser
escalates with `escalate_low_confidence`, doc still lands in the
file); false negatives are not (a real reply treated as a
disclosure would skip the loop closure). So the heuristic is
permissive in the reply direction by design. Real reply-routing
signal (email-thread metadata, fax cover sheet, intake classifier)
becomes a one-line swap in `_classify_inbound`.

**What `advance_claim` does NOT do:** it does NOT run analysis
LLM calls (Coverage / Reserve / Liability / Brief) inline. Those
are expensive and the `WorkflowRunner` drains them on its own
cadence. `advance_claim` is the cheap coordination function —
classify, route, fire correspondence. The two streams stay
separable but composable.

**`apply_coverage_decision` is NOT auto-applied.** Coverage
decisions carry legal weight (ROR commits the carrier to a
posture; accept/deny binds payment). Per the multi-agent
decision framework feedback memory, **write-side actions stay
single-threaded under human control** even when the upstream
analysis was multi-agent. The cockpit's coverage-review surface
is where the adjuster commits the decision; this function is
what that button calls.

**Posture transition rules (validated, not just typed):**
- `under_investigation` → any
- `ROR_issued` → `accepted` or `denied` (resolution)
- `accepted` / `denied` → terminal (re-open is a separate flow)
- Idempotent: same posture in = no-op (cockpit double-click safe)
- `source_recommendation_id` parameter accepted but not yet
  persisted on the Claim — placeholder so future audit-log work
  doesn't need a signature change

**Code:**
- `src/argos/services/orchestrator/claim_advance.py` —
  `advance_claim`, `ClaimAdvanceReport`, `ClassifiedDoc`,
  `_classify_inbound`
- `src/argos/services/orchestrator/coverage_actions.py` —
  `apply_coverage_decision`, `CoveragePosture` literal
- `src/argos/services/orchestrator/correspondence_loop.py` —
  renamed to `advance_correspondence` / `CorrespondenceAdvanceReport`

**Verification:** 415/415 tests pass (up from 389). 26 new tests:
- 11 on `advance_claim`: classification (disclosure path,
  reply-candidate path, off-claim safety), composition
  (disclosure + correspondence in one call, no docs still runs
  correspondence), input immutability, report shape
- 15 on `apply_coverage_decision`: valid transitions (6),
  invalid transitions (4), idempotence (2), unknown claim (1),
  immutability + isolation (2)

**What's still NOT wired:**
- The Coverage *workflow* output → `apply_coverage_decision` link.
  Today, the cockpit is the trigger; eventually, the Coverage
  specialist's recommendation surfaces in the cockpit's review
  queue and the adjuster confirms it from there. That UX wiring
  is downstream of the cockpit existing.
- A real trigger fabric for `advance_claim`. Today it's a
  function; production needs a cron + event handler that calls
  it on `(doc_arrived, claim_id)` and on a sweep cadence. That
  fabric is the next architectural piece (probably a small
  scheduler module + a Vercel cron or equivalent).

**With this, the two open gaps from the prior status report close.**
The cross-stream scheduler exists; ROR posture has a producer.
The system can now be driven by external events from end to end.

---

## 2026-06-01 — ROR escalation: coverage_posture on Claim, drafter responds

**Decision:** The system now tracks coverage posture as a
first-class field on `Claim` and the Outreach Drafter responds to
it. This is the consumer-side half of the ROR-escalation gap flagged
in the prior status report. The producer-side (wiring the Coverage
specialist's recommendation back onto the claim) remains deferred —
it lives on the *analysis-pipeline → claim-state writeback* gap, not
on the correspondence layer.

**Schema:**
- `Claim.coverage_posture: Literal["under_investigation", "ROR_issued", "denied", "accepted"] = "under_investigation"`
- `OutreachDrafterInput.coverage_posture: Literal[...] = "under_investigation"`
- Default value chosen so every pre-existing fixture and call site
  keeps working without change (377 → 389 tests pass, zero
  regressions).

**Drafter prompt rule (the load-bearing behavior change):** A new
`COVERAGE POSTURE` section in `SYSTEM_PROMPT` enumerates all four
postures and ties each to required framing:

- `under_investigation` → no special framing (default; preserves v1
  behavior)
- `ROR_issued` → every letter to `claimant`/`insured`/`claimant_counsel`/`defense_counsel` MUST end with the reservation paragraph, using the carrier-standard formula verbatim ("complete reservation of rights, without waiving any defenses, expressly reserve the right to raise any policy or coverage defenses"). The reservation paragraph is the FINAL paragraph; NEVER bulleted; NEVER followed by a warm courtesy close.
- `ROR_issued` → for non-adversarial recipients (medical_provider, body_shop, police_records_office, dmv, employer, witness), the reservation paragraph is NOT required. Those letters are operational, not posture-shaping.
- `accepted` → NEVER include reservation language; the carrier has committed.
- `denied` → routine correspondence to claimant/insured/counsel should not be happening; if it is, write conservatively, no fresh concessions, no warm close.

**Plumbing (entity → drafter input → user prompt):**
- `build_drafter_input_for_outbound` now reads `claim.coverage_posture` and threads it into `OutreachDrafterInput.coverage_posture`.
- `_render_user_body` now emits a `coverage_posture: <value>` line in the OUTBOUND CONTEXT block of the user message so the model sees the signal.

**InfoGap — explicitly NOT changed.** At `ROR_issued`, routing certain questions to coverage counsel (a different `recipient_party`) instead of defense counsel is a complex policy decision that needs real data to calibrate. v1 keeps InfoGap unchanged; the Drafter alone handles ROR framing. Posture-driven routing is a future iteration once we observe real claim flows.

**Producer-side gap still open.** The system has no mechanism today for the Coverage specialist's recommendation to flip `claim.coverage_posture` automatically. Today the field is hand-flipped (or set on the synthetic claim for the demo). When the *analysis-pipeline → claim-state writeback* piece lands, the posture transition becomes automatic. The drafter doesn't care — it just reads the field.

**Code:**
- `src/argos/ontology/types.py` — `Claim.coverage_posture` field
- `src/argos/schemas/workflows/outreach_drafter.py` — `OutreachDrafterInput.coverage_posture` field
- `src/argos/workflows/outreach_drafter.py` — helper plumbing; `_render_user_body` emits the field; `SYSTEM_PROMPT` carries the new COVERAGE POSTURE section
- `docs/AGENT_ARCHITECTURE.md` §2 — refreshed to include the correspondence specialists + orchestration wires (Outreach Drafter, Reply Parser, InfoGap, DraftOutreach, IngestReply, Correspondence Loop)

**Verification:** 389/389 tests pass (up from 377). 12 new tests:
- 3 schema tests on `OutreachDrafterInput.coverage_posture` (default, accepts known values, rejects unknown)
- 4 schema tests on `Claim.coverage_posture` (default, accepts known, rejects unknown, rejects empty)
- 2 `_render_user_body` tests (posture surfaces in user prompt at both default and ROR_issued)
- 2 `build_drafter_input_for_outbound` tests (helper reads from claim at both default and ROR_issued)
- 1 load-bearing sanity test on SYSTEM_PROMPT — verifies all four posture literals AND the verbatim reservation formula are present in the prompt, so a future prompt edit can't silently delete the ROR rule

**With this, gap #6 from the prior status report is closed at the correspondence layer.** The Drafter now responds correctly to ROR posture. The remaining piece (Coverage→Claim writeback to set the field automatically) is an analysis-pipeline concern, not a correspondence concern.

---

## 2026-06-01 — Correspondence loop composes the three wires (tick function)

**Decision:** A single function `run_correspondence_tick` composes
`reply_handler`, `info_gap`, and `draft_handler` into one cycle of
the ask/answer loop. Order inside the tick is fixed:

  1. **Ingest pending inbound replies** (loop closure on existing
     evidence, before anything else evaluates the open-question set)
  2. **Propose new pending_draft outbounds** (InfoGap, with the
     post-ingest claim state)
  3. **Draft every pending_draft outbound** (DraftOutreach, including
     freshly-proposed ones and leftovers from prior ticks)

**Why order matters:** If InfoGap ran before ingest, the just-arrived
police_report wouldn't be in `caseload.documents` yet, and `is_answered`
would still consider those questions open — InfoGap would propose
new outbounds asking what the inbound just answered. Ingest-first
makes one tick a complete unit of forward progress.

**Why a separate module (not in the existing `JobQueue` /
`dispatcher.py` / `runner.py`):** The existing orchestrator is
shaped around the *read* side — `RelevanceCall` from the Document
Reader triggers analysis Jobs (Coverage/Reserve/Liability). Its
`Job` dataclass has `triggered_by_doc_id` and `posture_changed` as
required fields, neither of which fits the correspondence wires.
The correspondence loop is a different event stream (claim state →
outbound work) with its own composition. Wiring both streams to a
shared higher-level scheduler is the next architectural piece;
neither should bend to fit the other.

**Idempotency / safe to retry:** A clean tick on a fully-handled
claim is a near no-op (empty proposals from InfoGap, empty pending
list for the drafter). The ID seeder `_next_obr_id_seed` reads
existing `OutboundRequest.request_id` values and continues from
`max + 1`, so ticks coexist with manually-created outbounds without
collision (provided everyone uses the same prefix).

**Caller-supplied:**
- `recipient_directory: dict[str, str]` — party → recipient_name
- `inbound_replies: list[Document] | None` — caller decides which
  inbound docs are reply candidates this tick (in production:
  derived from email-thread routing, fax cover sheets, or human
  triage)
- Optional `openai_client` / `anthropic_client` for testing

**Report shape:** `CorrespondenceTickReport` carries the full
per-step outcome lists (ingest outcomes, info-gap outcome, draft
outcomes) plus a one-line `summary()` for audit logs. Lets the
upstream scheduler reconstruct what moved without re-reading the
caseload diff.

**Code:**
- `src/argos/services/orchestrator/correspondence_loop.py` — the tick
- `tests/services/orchestrator/test_correspondence_loop.py` — 9
  tests covering single-tick happy path, ingest-before-propose
  ordering (the load-bearing integration test), multi-tick
  convergence, ID seeding, empty-directory no-op, and off-claim
  inbound filtering

**Verification:** 377/377 tests pass (up from 368). The
`TestIngestRunsBeforePropose` test is the load-bearing assertion:
police_report inbound → tick → InfoGap proposals don't include
Q-LIA-001, AND OBR-001 flipped to `replied`, AND the doc landed in
`caseload.documents`.

**Where this leaves the architecture:** All three correspondence
wires are now composed into a single callable unit of forward
progress. The remaining architectural piece is the **cross-stream
scheduler** — the thing that decides when to call
`run_correspondence_tick` vs the existing analysis runner, and how
they interleave (e.g., "Coverage analysis updated open-question
posture → tick correspondence next"). Both sides have clean action
surfaces; the scheduler just composes them.

---

## 2026-06-01 — InfoGap detector shipped (deterministic upstream policy)

**Decision:** The third orchestration wire — `info_gap` — turns a
claim's open-question set into fresh `pending_draft` outbounds for
`draft_handler` to consume. Fully deterministic: no LLM. Per
`[[policy-engine-first-then-llm-extraction]]`, the LLM is reserved
for prose (drafter) and extraction (parser); routing/bundling
policy is code.

**Why now:** With DraftOutreach and IngestReply landed, the action
wrappers around both stateless LLM functions exist. What was
missing was the upstream piece that *creates* `pending_draft`
outbounds in the first place. Without InfoGap, the orchestrator
had no way to advance a claim from "we know X is open" to "we have
a draftable outbound asking X."

**Closes the loop architecturally:**

```
[InfoGap.propose_pending_outbounds]   ← shipped
    │  reads open Qs (via is_answered) + existing outbound state
    │  emits pending_draft OBRs bundled by (party, recipient_name)
    ▼
[DraftOutreach.handle_pending_draft]  ← shipped earlier
    │  body-fills via LLM
    ▼
adjuster sends
    ▼
[IngestReply.apply_outcome]           ← shipped earlier
    │  ingests reply doc + flips outbound state
    │  → is_answered() now sees new evidence
    ▼
[InfoGap.propose_pending_outbounds]   ← second pass: smaller open set
```

**Algorithm (7 deterministic steps):**

1. Open-question set via `is_answered()` on claim docs.
2. Drop questions whose `depends_on` IDs are still open (don't ask
   Q-COV-002 if Q-COV-001 isn't answered).
3. Drop questions already covered by an in-flight outbound
   (`pending_draft`/`drafted`/`sent`/`overdue`). `replied` does NOT
   block — if the reply didn't actually answer (deterministic check
   still says open), re-asking is correct.
4. Pick the highest-fidelity source with a *deliverable* channel
   (excludes `internal_lookup`, `api` — those don't generate
   outbounds).
5. Look up the recipient name in a caller-supplied
   `recipient_directory: dict[str, str]`. Missing entry → skip with
   `no_recipient_in_directory` (orchestrator's signal to populate).
6. Bundle remaining `(question, source)` pairs by
   `(party, recipient_name)` → one OBR per group.
7. Template a `letter_purpose` from question descriptions (no LLM).

**Outcome shape:** `InfoGapOutcome` carries both `proposals` (the
new outbounds, ready for `apply_outcome` to append) AND `skipped`
(every open question that didn't make it, with a typed reason).
Audit trail by design — the orchestrator surfaces skips to the
human so they can fix the directory, escalate dependencies, etc.

**Deferred (not in v1):**
- Rate limiting ("don't double-ask the same recipient within N
  days") — comes once we observe behavior.
- Multiple recipients per party (e.g., two lawyers at one firm).
- ROR-triggered escalation paths.
- Recipient directory persistence — today the caller passes a
  dict; future: live on `Claim` or a `RecipientRegistry` entity.

**Code:**
- `src/argos/services/orchestrator/info_gap.py` — the wire
- `tests/services/orchestrator/test_info_gap.py` — 16 tests
  covering: happy path, bundling, dependency blocking, source
  selection (incl. internal-only skip), recipient directory
  misses, in-flight blocking (4 status variants), `apply_outcome`
  semantics, and **end-to-end loop closure** (round-1 propose →
  ingest police_report → round-2 propose drops the satisfied
  questions, while freshly-unblocked dependencies surface)

**Verification:** 368/368 tests pass (up from 352). The
`TestEndToEndLoopClosure` test is the load-bearing assertion —
proves the three orchestration wires compose without any extra
plumbing.

**Where this leaves the architecture:**

All three orchestration wires + both stateless LLM functions are
shipped. The system can now run the full cycle: detect gaps →
propose outbounds → draft bodies → adjuster sends → ingest replies
→ re-detect gaps. The orchestrator-level scheduling (when to fire
each wire, on what trigger) is the next architectural piece — but
all the action surfaces it needs to call now exist.

---

## 2026-06-01 — IngestReply closes the question-state loop (no Q-state object needed)

**Decision:** The `IngestReply` Action — the symmetric counterpart
to `DraftOutreach` — is shipped as an enhancement to the existing
`reply_handler` orchestration wire, not a new module. Two object
mutations now happen atomically in `apply_outcome`:

1. **Document ingestion** — the inbound `Document` is appended to
   `caseload.documents` (idempotent by `document_id`).
2. **Outbound transition** — the matched outbound flips
   `sent → replied` (unchanged behavior, but now bundled).

**Why this closes the loop:** The Outreach Drafter (and Brief
assembler) determine "which questions are open" via the
deterministic `is_answered(question, claim, documents)` check in
`workflows/brief/answer_detector.py`. That check reads
`caseload.documents`. Once IngestReply puts the reply doc in there,
the next drafter call sees the question as answered and stops asking
about it. **No separate Q-state object is needed** — the document
list IS the Q-state, accessed via the deterministic detector.

This is a `[[policy-engine-first-then-llm-extraction]]` move: the
LLM (Reply Parser) extracts what the reply addressed, but the
*authority* on whether a question is closed remains the
deterministic doc-type check. The parser's `answered_question_ids`
output flows into thread history for adjuster review, but it does
not directly mutate Q-state.

**Document ingestion fires for escalations too** (not just matched
outcomes). The record arrived in the file; only the outbound state
transition is gated by a confident parser match. This means a
low-confidence reply still closes the deterministic-detection loop
even while the unmatched outbound stays in `sent` for human review.

**Schema change:** `ReplyHandlerOutcome.inbound_doc_id: str` →
`inbound_doc: Document`, with `inbound_doc_id` retained as a
`@property` for backwards compatibility. `apply_outcome` needs the
full document, not just the id, to ingest.

**Code touched:**
- `src/argos/services/orchestrator/reply_handler.py` — outcome
  carries full `Document`; `apply_outcome` ingests; docstrings
  updated to reflect the IngestReply Action role
- `tests/services/orchestrator/test_reply_handler.py` — 4 new
  tests covering doc ingestion (matched, idempotent, escalations);
  2 new TestLoopClosure tests proving `is_answered()` flips after
  apply_outcome
- (No new file — the wire was already named `reply_handler`; the
  Foundry Action Type is "IngestReply" but the Python module keeps
  its existing name)

**Verification:** 352/352 tests pass (up from 348). The two
TestLoopClosure tests are the load-bearing assertions —
`is_answered(Q-DAM-001, claim, new_cs.documents)` flips from False
to True after applying the outcome, proving the loop closes
end-to-end with no Q-state plumbing.

**With this and DraftOutreach landed, the two action wrappers
around the stateless LLM functions exist.** The remaining piece in
the original next-step plan is the `InfoGap` detector — the
deterministic upstream policy that turns a claim's open-question
set into fresh `pending_draft` outbounds (per recipient, per
bundling rules). That's the next session.

---

## 2026-06-01 — Identity fields on Claim + OutboundRequest (schema collapse)

**Decision:** Persisted the four identity fields the Outreach
Drafter needs directly on the entities, removing the temporary
caller-supplied kwarg pattern from the DraftOutreach handler.

**Schema changes:**
- `Claim` gains `claimant_name: str | None` and `insured_name:
  str | None` (optional — may be unknown at FNOL; intake_reader
  hydrates from documents)
- `OutboundRequest` gains `recipient_name: str` and
  `letter_purpose: str` (both required; every outbound has a real
  recipient and a stated purpose at creation time)

**Why fields live where they do:** Names are claim-level facts
(one claimant, one insured per claim). Recipient/purpose are
per-outbound (a single claim may run threads with multiple
recipients at the same party, each with its own purpose). The
info-gap detector — next-next step — owns populating
recipient/purpose on `OutboundRequest` at creation.

**Thread key tightened:** `build_drafter_input_for_outbound`
now keys threads by `(claim_id, recipient_party, recipient_name)`
— different lawyers at the same firm get separate threads, as
intended. Previously threads were keyed only by `(claim_id,
recipient_party)` because `recipient_name` didn't exist on
`OutboundRequest`.

**Handler shape after collapse:**

```python
handle_pending_draft(outbound, caseload, *, now, ...) -> DraftOutboundOutcome
```

No identity kwargs. A new soft escalation
`escalate_claim_unhydrated` fires when `claim.claimant_name` or
`claim.insured_name` is null — the orchestrator's signal to run
intake_reader (or prompt the human) before drafting.

**Code touched:**
- `src/argos/ontology/types.py` — Claim + OutboundRequest fields
- `src/argos/workflows/outreach_drafter.py` —
  `build_drafter_input_for_outbound` signature collapsed; thread
  key now includes recipient_name; raises on unhydrated claim
- `src/argos/services/orchestrator/draft_handler.py` — handler
  signature collapsed; added `escalate_claim_unhydrated` outcome
- 5 test files updated for new required fields; 4 new tests
  (2 schema-invariant, 2 escalate_claim_unhydrated)

**Verification:** 348/348 tests pass (up from 344). No regressions.

---

## 2026-06-01 — DraftOutreach action shipped (orchestration wire)

**Decision:** The `DraftOutreach` Action Type — deferred from the
v1 Outreach Drafter ship — now exists as
`src/argos/services/orchestrator/draft_handler.py`. It is the
mutation wrapper around the stateless drafter, symmetric to the
existing `reply_handler.handle_inbound_reply` wrapper around the
Reply Parser.

**Why now:** With Drafter and Reply Parser both shipped as
stateless LLM functions, they were islands — neither could move
`OutboundRequest` state. `DraftOutreach` closes the upstream side
of that gap (`pending_draft` → `drafted`). The downstream
counterpart (`IngestReply` action wrapping the parser) is the
next piece. After both action wrappers exist, the
orchestrator/Job-slot wire becomes mechanical.

**Shape — mirrors `reply_handler`:**
- `handle_pending_draft(outbound, caseload, *, ...identity..., now, ...) -> DraftOutboundOutcome`
- `apply_outcome(caseload, outcome) -> Caseload` (no input mutation)
- `DraftOutboundOutcome` is a discriminated dataclass with three
  outcome literals:
  - `drafted` — happy path, `updated_outbound` + `result` populated
  - `escalate_no_open_questions` — open-question set empty after
    info-map filtering; LLM not called
  - `escalate_drafter_failed` — drafter raised (e.g., empty body
    from reasoning-token overrun)

**Hard errors (raised, not escalated):** outbound not in
`pending_draft` state, or `claim_id` missing from caseload — both
caller bugs the orchestrator should surface immediately.

**Identity context lives on the entities** (collapsed in this
session; see "Identity fields on Claim + OutboundRequest"
amendment below):
- `recipient_name`, `letter_purpose` → on `OutboundRequest`
  (per-outbound facts; info-gap detector populates at creation)
- `claimant_name`, `insured_name` → on `Claim`
  (claim-level facts; intake_reader populates from FNOL docs;
   optional because they may be unknown at FNOL)

Handler signature is now `(outbound, caseload, *, now, ...)`. No
per-call identity threading.

**Code:**
- `src/argos/services/orchestrator/draft_handler.py` — the wire
- `tests/services/orchestrator/test_draft_handler.py` — 11 tests
  covering happy path, both pre-call hard errors, both soft
  escalations, and `apply_outcome` semantics (no mutation,
  escalation no-ops)

**Verification:** 344/344 tests pass (up from 333). No regressions.

**Next step:** `IngestReply` action — symmetric wrapper around the
existing Reply Parser that flips `sent` → `replied` and updates the
claim's question-state (which Q-IDs are now answered). After that,
the info-gap detector (deterministic policy producing fresh
`pending_draft` outbounds from the claim's open-question set).

---

## 2026-06-01 — Outreach Drafter v2 prompt: bullet rule sharpened, numbered lists, reasoning_effort="low"

**Decision:** Incremental prompt iteration on the Outreach Drafter
SYSTEM_PROMPT (same day as v1 ship). Three writing-quality changes
plus one runtime tweak:

1. **LIST SHAPE threshold lowered to 3+ items** (was 4+) with HARD
   "MUST use a list" language. At 4 items, the prior threshold was
   borderline and regressed under `reasoning_effort="none"`.
2. **Numbered list (`1. `, `2. `) support added** alongside unordered
   bullets. Rule: numbered when items are a counted set ("two issues
   remain open") or sequential; unordered otherwise.
3. **Exemplars rewritten** to demonstrate bullet/numbered structure
   for 3+ items. New 4th exemplar showing a numbered-list ROR
   pattern. Per [[exemplars-override-abstract-rules]] — the prior
   exemplars comma-stuffed 4-7 items in prose, overriding the
   abstract "use bullets" rule. Fixing the exemplars was the
   high-leverage change.
4. **`DEFAULT_REASONING_EFFORT` bumped from `"none"` to `"low"`** in
   the production runtime. At `none`, the model writes one-shot
   without rule-checking; borderline cases regress. At `low`, the
   model has a deliberation budget that catches its own rule
   violations. Cost delta: ~$0.007 → ~$0.014 per letter; tradeoff is
   worth it for consistency.
5. **Anti-slop lint now recognizes numbered lists** (was only `- `
   bullets). `1. ` / `2. ` lines now count as list paragraphs and
   are exempt from prose word-count limits.
6. **ASK SHAPE section rescoped** to apply only to 1-2 item asks; for
   3+ items the LIST SHAPE rule takes precedence. Resolves the
   internal contradiction between the two sections.

**Verification:** Bake-off run + live smoke against the production
runtime. The original 4-item regression case (`follow_up_to_counsel`)
now correctly bullets. ROR scenario uses numbered list
(`1. Notice was received... 2. The vehicle's use...`) — the new
exemplar paid off immediately.

**Code touched:**
- `scripts/bake_off_drafter.py` — prompt v2 (LIST SHAPE, ASK SHAPE,
  exemplars, reasoning_effort)
- `src/argos/workflows/outreach_drafter.py` — synced SYSTEM_PROMPT,
  added exemplars, bumped reasoning_effort default
- `src/argos/workflows/checks/anti_slop.py` — numbered-list detection
- `tests/workflows/test_outreach_drafter.py` — updated reasoning_effort
  assertion

**Still deferred** (unchanged from v1 entry):
- `DraftOutreach` action layer
- Orchestrator wire / Job registration
- ROR-paragraph lint exemption (the ROR formula itself routinely
  trips `max_paragraph_words` / `max_sentence_words` thresholds; v2
  doesn't fix this — flag for next lint iteration)

---

## 2026-06-01 — Outreach Drafter v1 shipped (thread-aware, stateless)

**Decision:** Built `src/argos/workflows/outreach_drafter.py` +
`src/argos/schemas/workflows/outreach_drafter.py` +
`src/argos/workflows/checks/anti_slop.py`. The Outreach Drafter is a
single-shot, thread-aware LLM workflow that emits the BODY of one
outbound letter from the adjuster to an external party.

Architecture: stateless LLM, stateful caller. Per
[[stateless-function-vs-agent]] — claims correspondence has a
bounded, structured information environment, so we use a stateless
function with rich structured input rather than an agent with tools
and autonomy. The "memory" is the relational layer
(`OutboundRequest` records + Reply Parser results), assembled into
structured input on each call by
`build_drafter_input_for_outbound(claim, recipient_party,
recipient_name, ..., caseload)`.

Input shape (`OutreachDrafterInput`):
- Identity: `claim_id`, `recipient_party`, `recipient_name`,
  `claimant_name`, `insured_name`, `date_of_loss`
- Current letter: `letter_purpose`, `open_question_ids`
- Thread: `conversation_history: list[OutreachThreadTurn]`,
  `older_history_summary: str | None`

Thread key (logical): `(claim_id, recipient_party, recipient_name)`.
Recipient substitution should reset the thread. Today the helper
filters by `(claim_id, recipient_party)` only — `recipient_name`
isn't yet persisted on `OutboundRequest`. Stricter keying is a
future schema enhancement; callers can pre-filter the caseload.

Thread history cap: last 5 turns verbatim + a one-line
`older_history_summary` for everything older. Prevents prompts from
unboundedly growing on long-running litigation threads.

Writer model: `gpt-5.5` with `reasoning_effort="none"`, cap 1500
output tokens. Per [[reasoning-budget-by-value]] — drafting is
low-leverage (human always edits), so reasoning tokens stay cheap;
high reasoning is reserved for judgment workflows (Coverage / Brief /
Reserve / Liability). Production unit cost: ~$0.007 per letter.

System prompt locked at v1 — see SYSTEM_PROMPT constant in
`src/argos/workflows/outreach_drafter.py`. Sections (in order):
voice-of-the-letter (no brand-name leaks, speaks as adjuster),
modern-professional voice rules, external framing, request-shape
softening, list shape (4+ items → bullets), courtesy close, opener
variety, topic grouping, word-level variety, flow & transitions
(Halliday/Williams/Brown-Levinson principles), register matching
(peer / formal-direct / legal-serious), conversation context (thread
awareness), structure, length & rhythm, "we" cap, "please" cap, and
in-context exemplars.

Anti-slop lint metrics surfaced (not gates) — see
`run_anti_slop_lint`. The drafter returns body + lint metrics; the
adjuster (or downstream action) decides whether to send or edit. v1
thresholds: 80-200 word total, 2-4 paragraphs, please ≤ 3, "we"
sentence-opener ≤ 2, max prose paragraph ≤ 32 words, max sentence ≤
24 words, no banned words, no banned openers, ROR formula not in
paragraph 1, bullet paragraphs exempt from word-count.

**Why:** Closes step 3b on the build order. The OutboundRequest data
model (step 3a) + Reply Parser (step 4) + Outreach Drafter (step 3b)
now form the outbound→reply loop end-to-end at the workflow layer:
something fills `OutboundRequest.draft_body` via the drafter;
adjuster reviews + sends; reply arrives; Reply Parser matches it;
loop closes.

**Out of scope (deferred):**
- `DraftOutreach` action that mutates `OutboundRequest.draft_body` +
  transitions `pending_draft → drafted`. Belongs in an action layer,
  separate from the workflow.
- Orchestrator runner registration. Whether the drafter gets a
  `Job`-style slot in `WORKFLOW_REGISTRY` like Coverage / Reserve /
  Liability, or fires differently (triggered by Brief gap
  recommendations rather than Document Reader posture). Architecture
  decision worth its own session.
- UI for adjuster review of drafts.
- `recipient_name` persistence on `OutboundRequest` (for stricter
  thread keying).
- Reply Parser's answered/unanswered partition stored on
  `OutboundRequest` (the helper currently assumes
  `status='replied'` ⇒ fully answered, which is a simplification).

**Code touched:**
- `src/argos/schemas/workflows/outreach_drafter.py` — new
- `src/argos/workflows/outreach_drafter.py` — new (system prompt
  locked here)
- `src/argos/workflows/checks/anti_slop.py` — new (lifted from
  `scripts/bake_off_drafter.py`)
- `tests/workflows/test_outreach_drafter.py` — new (12 tests:
  stub OpenAI client, schema mapping, prompt assembly, thread
  rendering, helper)
- `tests/schemas/workflows/test_outreach_drafter.py` — new (12
  tests: schema invariants)
- `scripts/bake_off_drafter.py` — stays as the prompt-iteration
  harness; not deleted because writing-quality work continues there
  before the next prompt revision lands

**Palantir mapping:** `OutreachDrafterInput` becomes a derived object
type (one slice of `OutreachThread` per claim/recipient). The
drafter call corresponds to a `DraftOutreach` Action Type that
materializes `draft_body` on an `OutboundRequest` and emits a
`DraftReady` event for the adjuster review queue.

---

## 2026-06-01 — Reply Parser orchestration wire shipped

**Decision:** Built `src/argos/services/orchestrator/reply_handler.py`
to glue arriving inbound documents to the Reply Parser workflow.
`handle_inbound_reply(inbound_doc, caseload, *, now, min_confidence,
_client)` returns a `ReplyHandlerOutcome` with one of three states:

- `matched` — parser returned a confident match; outcome carries the
  updated `OutboundRequest` (status flipped to `replied`,
  `reply_doc_id` and `replied_at` populated) plus the
  answered/unanswered question ID partition.
- `escalate_no_candidates` — the claim has zero open outbounds; the
  parser is NOT invoked (its contract raises on empty candidate set).
- `escalate_low_confidence` — parser returned a match but
  `confidence < min_confidence` (default 0.5); outcome carries the
  parsed result for the human reviewer but no outbound mutation.

`apply_outcome(caseload, outcome)` is a pure helper that returns a
new `Caseload` with the matched outbound replaced. Escalation outcomes
are a no-op — they're meant to land in a human queue.

**Why:** The Reply Parser itself is pure (one inbound + candidates →
one parse result). The wire owns everything around it: scoping
candidates from the caseload, gating on confidence, and producing the
immutable state transition. Keeping that logic out of the parser
keeps the LLM workflow narrow and the orchestration deterministic.
Also keeps the parser's `ValueError` on empty candidates honest —
the wire is responsible for never calling the parser with nothing.

**Out of scope (intentional):**
- Question-status flipping (no `Question` entity in the ontology yet;
  Brief recomputes gaps from current documents, so the inbound doc's
  presence in the caseload is the signal).
- Persistence — wire is pure. Caller decides where to store the
  outcome and whether to apply it.
- Live LLM calls in tests — uses the stub client pattern.

**Palantir mapping:**
- `ReplyHandlerOutcome` shape is the Action Type payload for
  `MarkReplied` (or `EscalateReply`) on Foundry's `OutboundRequest`
  object type.
- `apply_outcome` is the application-side equivalent of Foundry
  applying that Action Type to the object.
- The `matched` outcome's answered/unanswered partition is the input
  to whatever downstream pipeline owns question status.

**Code touched:**
- New: `src/argos/services/orchestrator/reply_handler.py`
- New: `tests/services/orchestrator/test_reply_handler.py` (12 tests)
- Full suite: 308/308 green

---

## 2026-06-01 — Renamed `specialist` → `workflow` codebase-wide

**Decision:** Renamed every code-level use of `specialist` to
`workflow`, reversing the earlier "keep the directory name for now"
position. Scope:

- Directories: `src/argos/specialists/` → `workflows/`;
  `src/argos/schemas/specialists/` → `schemas/workflows/`;
  `tests/specialists/` → `tests/workflows/`;
  `tests/schemas/specialists/` → `tests/schemas/workflows/`.
- Identifiers: `SpecialistRunner` → `WorkflowRunner`, `SpecialistFn`
  → `WorkflowFn`, `SpecialistResult` → `WorkflowResult`,
  `SpecialistName` → `WorkflowName`, `SpecialistRecommendationHeadline`
  → `WorkflowRecommendationHeadline`, `SPECIALIST_REGISTRY` →
  `WORKFLOW_REGISTRY`, `_stub_specialist` → `_stub_workflow`,
  `POSTURE_TO_SPECIALISTS` → `POSTURE_TO_WORKFLOWS`.
- Fields: `Job.specialist` → `Job.workflow` (queue persistence JSON
  key flipped too; no prod data); `AgentAction.specialist` →
  `AgentAction.workflow`; `ClaimBrief.specialist_recommendations*` →
  `workflow_recommendations*`; `WorkflowRecommendationHeadline.specialist`
  → `.workflow`.
- Persistence paths: `data/specialist-results/` →
  `data/workflow-results/`.
- Docstrings and comments updated where they referenced the term as
  code. Historical DECISIONS entries preserved verbatim — they record
  the past terminology truthfully.

**Why:** Tom flagged that "specialist" implies an autonomous agent,
which contradicts what these things actually are: single-shot LLM
workflows with forced tool_use, deterministic policy gating, and
runtime invariant validation. Inconsistent naming was already
leaking into prompts and comments. Rename is now, before the surface
grows further (Outreach Drafter, Liability, etc.).

**Out of scope (intentional):**
- Brief locked eval baseline: `brief.json` output keys changed
  (`specialist_recommendations_summary` → `workflow_recommendations_summary`,
  `specialist` → `workflow` on headlines). If/when the eval re-runs
  for new evidence, the baseline regenerates with new keys. No
  re-baseline needed until then.
- Historical DECISIONS entries — left as-is for truthful chronology.

**Supersedes:** the earlier 2026-06-01 terminology entry that
proposed keeping directory names while updating prompts. That entry
remains in the log as historical context; this entry is the active
rule.

**Palantir mapping:** Action Type and object type names should now
use `Workflow*` everywhere they referred to `Specialist*`.

**Code touched:**
- ~30 files (directories, schemas, runtime, tests, scripts)
- Full suite: 296/296 green after rename (pre-wire), 308/308 with the
  reply-handler tests added.

---

## 2026-06-01 — Product value-prop framing: "ask everything upfront"

**Decision:** The product's load-bearing value claim is that the
system surfaces the *complete* set of missing information per
recipient up front, so the adjuster's outbound message asks for
everything at once. The pitch is fewer round-trips → fewer days
to resolution → less human error from sequential context loss.

**Why:** This framing shapes downstream design. Outreach Drafter must
be **comprehensive, not polite-minimal** — when drafting to a
recipient, ask for every open question that recipient can answer in
one message. The info-map slicing by recipient is what makes the
"ask everything" claim true and bounded.

**Out of scope:** Optimizing message length or tone for individual
recipients. The default is exhaustive; recipient-specific tone
calibration is v2.

**Code touched:** None yet. Shapes the Outreach Drafter spec when
written.

## 2026-06-01 — Brief: pre-loaded, with nightly batch + relevance-triggered notify

**Decision:** Brief is pre-computed, not on-demand. Two triggers:

1. **Nightly batch refresh** — every open claim's brief is
   regenerated at end-of-day so the adjuster's morning view loads
   instantly with current state.
2. **Mid-day relevance notification** — when a new doc or reply
   arrives during the day AND the Reader flags it `relevant=True`,
   the claim's brief gets a "new info since last brief" indicator.
   The adjuster clicks to refresh; we do not auto-regenerate on
   every arrival.

**Why:** Adjusters open the platform expecting current state; sub-second
brief load is the UX bar. Nightly batch is predictable cost and only
touches claims that are actually open. Throughout the day we don't
burn LLM calls on noise (fax cover sheets, payment confirmations);
the Reader's relevance gate filters that. New-info-but-no-refresh
is the right state when the user hasn't asked for it yet.

**Out of scope:** Per-claim refresh schedules, predictive pre-warming
based on which claims the adjuster is likely to open. v1 is just
nightly + on-relevant-arrival.

**Code touched:** Not yet built. Needs a nightly job runner and a
"stale-brief" flag on the claim record. Likely lives in
`services/orchestrator/` (batch refresh) and a `Brief.stale_since`
field for the notification trigger.

## 2026-06-01 — Outbound status tracking is a first-class concern

**Decision:** When Outreach Drafter sends (or queues) a message, the
system records: which open question(s) the message asks about, who
it was sent to, when sent, expected reply window, and current
status. A follow-up timer fires when the reply window lapses without
a response.

**Why:** Without this, ~22 of the 39 info-map questions can never
flip to "answered" — there's no signal of "we asked X, they replied
Y." Brief, Outreach, and the open-questions panel all need this
state. It's also the substrate Reply Parser needs to attribute an
inbound reply to the outbound that asked the question.

**Out of scope:** Channel-specific delivery confirmation (read
receipts, fax tone analysis). v1 records "we sent it"; carrier
delivery status is v2.

**Code touched:** Not yet built. New table/object on the caseload
(`OutboundRequest`) carrying message_id, claim_id, recipient_party,
question_ids_asked, sent_at, follow_up_due_at, status
(`drafted` | `sent` | `replied` | `overdue`). Brief reads from this
to render outreach state in the open-questions panel.

## 2026-06-01 — Inbound Reply Handler / Reply Parser

**Decision:** When a reply arrives on any channel (email, fax, portal,
mail-scan), a new specialist parses the content, identifies which
open question(s) it answers, and flips those questions to answered.
The new info is then fed back through the Reader gate so triage can
re-evaluate the claim's bucket.

**Why:** Closes the outreach loop. Today the system has no way to
recognize that a returned police report answers Q-LIA-001 through
Q-LIA-007. Without this, the open-questions panel would never
shrink — questions get sent out, replies arrive, nothing detects
that the answer landed.

This is distinct from the existing Document Reader (which classifies
arriving docs for relevance) — Reply Parser maps reply content to
specific open-question IDs using the outbound's `question_ids_asked`
as the candidate set.

**Out of scope:** Cross-claim correlation, deduping replies that
answer multiple outstanding outbounds. v1 handles one reply →
one outbound → one or more question flips.

**Code touched:** Not yet built. Will land in
`src/argos/specialists/reply_parser/`. Consumes `OutboundRequest`
context to scope the candidate question set per reply.

## 2026-06-01 — Reserve / settlement specialist is the terminating step

**Decision:** Once "enough" open questions are answered (criterion TBD
per LOB), the orchestrator triggers the reserve specialist to produce
a payout recommendation. This is the loop's terminator: the product's
job is to *get the claim to a payout decision* with full evidentiary
support.

**Why:** Names the destination of the whole flow. The triage →
outreach → reply loop has a stopping point: when the open questions
that gate the damages decision are closed (most of Q-DAM-*), reserve
is computable. Without naming this, the loop has no completion
criterion.

The `reserve` specialist stub already exists in
`WORKFLOW_REGISTRY` returning `status='not_implemented'` — this
decision says we will implement it as the terminator.

**Out of scope:** The exact "enough" criterion per LOB. For auto BI /
FL, a reasonable starting heuristic is "all required-gating Q-DAM
questions answered + Q-COV-001/006 answered." Tune from there.

**Code touched:** Not yet built. Will land in
`src/argos/specialists/reserve.py` replacing the stub. Triggered by
the orchestrator when the answered-state crosses the LOB threshold.

## 2026-06-01 — System flow target (canonical)

**Decision:** The end-to-end target flow is:

```
Unstructured FNOL bundle
  → Intake reader (NEW)            extracts structured Claim fields
  → Caseload populated
  → Triage policy engine (existing) bucket + within-bucket rank
     ↳ Reader runs during screening; produces RelevanceCall per unread doc
  → Auto-dispatch (NEW WIRE)        RelevanceCall → orchestrator.dispatcher → JobQueue
  → WorkflowRunner (existing)     drains queue: Coverage, Reserve, Liability run
  → Results persisted under data/workflow-results/{claim_id}/
  → Adjuster opens claim
     → Brief (existing)              assembles from caseload + persisted results
     → Brief surfaces: story + Coverage insight + open-questions panel (info map)
  → Adjuster clicks "follow up on missing item"
     → Outreach Drafter (NEW)        per-recipient info-map slice → drafted message
```

**Why:** This is the canonical mental model. All future work either
implements one of the NEW boxes, or extends an EXISTING box. The
intake reader, the auto-dispatch wire, and Outreach Drafter are the
three named gaps.

**Out of scope:** Anything not in this diagram — billing, document
storage, settlement workflow, audit-export UI. If scope grows, add a
new decision entry that names what changed and why.

**Code touched:** None yet; this is the architectural target.

## 2026-06-01 — System flow target (canonical, full loop)

**Supersedes:** 2026-06-01 — System flow target (canonical). That entry
captured the initial-render flow; this one extends it with the
outreach feedback loop and the terminating step.

**Decision:** The end-to-end target flow, including the outreach
feedback loop and the payout terminator:

```
Unstructured FNOL bundle
  → Intake reader (NEW)            extracts structured Claim fields
  → Caseload populated
  → Triage policy engine            bucket + within-bucket rank
     ↳ Reader runs during screening; produces RelevanceCall per unread doc
  → Auto-dispatch (NEW WIRE)        RelevanceCall → orchestrator.dispatcher → JobQueue
  → WorkflowRunner                drains queue: Coverage runs in background
     ↳ Results persisted under data/workflow-results/{claim_id}/

  ─── Nightly batch ───────────────────────────────────────────
  → Brief pre-loaded for every open claim (NEW: nightly trigger)

  ─── Adjuster session ────────────────────────────────────────
  → Adjuster opens platform → sees ranked queue (triage output)
  → Clicks top claim
     → Coverage insight loads instantly (pre-computed)
     → Brief loads instantly (pre-loaded)
     → Open-questions panel surfaces missing info per recipient
  → Adjuster clicks "Draft" on a missing item
     → Outreach Drafter (NEW)        per-recipient slice → comprehensive draft
     → "Ask everything upfront" framing — every open question for that recipient
  → Adjuster sends
     → OutboundRequest created (NEW) status=sent, follow-up timer set

  ─── Reply feedback ──────────────────────────────────────────
  → Reply arrives on any channel (email / fax / portal / mail-scan)
     → Reply Parser (NEW)            maps reply content → open-question IDs
     → Flips questions to answered
     → Feeds new info through Reader gate → triage may re-bucket
     → Brief flagged stale → adjuster notified "new info since last brief"

  ─── Loop ────────────────────────────────────────────────────
  Continue until the answered set crosses the LOB threshold for
  reserve computation.

  ─── Terminator ──────────────────────────────────────────────
  → Reserve specialist (BUILD-FROM-STUB) → payout recommendation
```

**Why:** This is the closed loop. The earlier flow entry showed how
the adjuster opens a claim and sees pre-computed insight — this entry
adds how the system *closes the gap* between "we asked" and "we
know," and where the loop terminates.

**Out of scope (still):** Anything outside this diagram. Same list as
the prior entry. Document storage, audit-export UI, billing, multi-
recipient batched outbounds, cross-claim reply correlation.

**Code touched:** None yet. Implementation order suggested below
(separate decision when we commit to it):
1. Auto-dispatch wire (smallest, unblocks background Coverage)
2. Intake reader (demo entry point)
3. Outreach Drafter + OutboundRequest model (closes the half-loop)
4. Reply Parser (closes the full loop)
5. Reserve specialist (terminator)
6. Brief nightly batch refresh (UX polish; lowest-priority)

## 2026-06-01 — Build order locked

**Decision:** Implementation sequence for the unbuilt components in
the canonical full-loop flow:

1. **Auto-dispatch wire** — connect `screen_caseload` output to
   `orchestrator.dispatcher.dispatch()` + `JobQueue.enqueue()`. Small
   surface; unblocks "Coverage has already run by the time the
   adjuster opens the claim." Lives in
   `services/triage/reader_integration.py` or a new glue module.
2. **Intake reader** — LLM extraction from unstructured FNOL bundle
   → structured `Claim` fields. New specialist at
   `src/argos/specialists/intake_reader.py`. Makes the demo's opening
   realistic; replaces synthetic-generation of structured fields with
   actual extraction.
3. **Outreach Drafter + `OutboundRequest` model** — ship together.
   Outreach can't be useful without the persistence layer that
   records "we asked X, waiting on reply." Lives in
   `src/argos/specialists/outreach/` + `ontology/types.py`
   (`OutboundRequest`).
4. **Reply Parser** — requires `OutboundRequest` to scope the
   candidate question set per reply. Lives in
   `src/argos/specialists/reply_parser/`. Closes the full feedback
   loop.
5. **Reserve specialist** — replaces the existing stub at
   `src/argos/specialists/reserve.py`. Triggered when the answered
   set crosses the LOB threshold. Produces payout recommendation.
   Loop terminator.
6. **Brief nightly batch refresh** — orchestrator-side job that
   regenerates briefs for every open claim at end-of-day. Pure UX
   latency optimization; the loop works without it.

**Why:** Plumbing-first ordering. Auto-dispatch (step 1) is the
smallest change and removes the contradiction between "Coverage has
already run" (canonical flow claim) and "Coverage runs on demand
only" (today's reality). Steps 2–5 close the user-facing loop in the
order each piece becomes useful: extraction (input), drafter +
persistence (action), reply parser (feedback), reserve (terminator).
Step 6 is polish — defer until the loop works.

**Out of scope:**

- Multi-LOB extensions (auto BI / FL is the locked v1 slice).
- The exact "enough" threshold for triggering Reserve — picked at
  the time Reserve ships, not now.
- Building any of these in parallel with claims-of-completeness
  before the prior step is integrated. Each step must integrate
  cleanly before the next starts.

**Code touched:** None yet. Each step gets its own decision entry
when it ships (with what changed, what's still stubbed, and any
deviations from this plan).

## 2026-06-01 — Step 1 shipped: auto-dispatch wire

**Implements:** "Auto-dispatch from Reader → Orchestrator is the
missing wire" (logged earlier today) and step 1 of the locked build
order.

**Decision:** Added `dispatch_screening_results(screening, queue) →
list[Job]` to `src/argos/services/triage/reader_integration.py`. For
every Reader call where `relevant == True`, runs the pure
`orchestrator.dispatcher.dispatch()` mapping to specialist names,
then enqueues each Job via `JobQueue.enqueue()` (idempotent on
`(specialist, claim_id, triggered_by_doc_id)`). Returns the list of
*freshly* enqueued jobs so callers can see what actually changed
this pass.

**Why:** Glue, not new policy. Both ends (`screen_caseload` + pure
`dispatcher.dispatch`) already existed; nothing connected them.
Adding it as a new function (not modifying `screen_caseload`)
preserves `screen_caseload`'s pure-read semantics. Callers that
want triage-only stay on the old surface; callers that want
auto-dispatch use the new one.

**Out of scope:** Calling `dispatch_screening_results` automatically
inside `screen_caseload`. Kept separate so unit tests of triage
ranking don't need a JobQueue and so the demo flow can show
screening and dispatch as distinct steps.

**Code touched:**
- `src/argos/services/triage/reader_integration.py` — new
  `dispatch_screening_results` function + dispatcher/JobQueue imports
- `tests/triage/test_reader_integration_dispatch.py` — 7 new tests
  (empty, all-non-relevant, single-coverage, damages fan-out,
  idempotency, per-claim routing, mixed mode)
- Full suite: 247/247 green (was 240; +7 new tests)

## 2026-06-01 — Step 2 shipped: Intake Reader

**Implements:** "Intake reader is a distinct, unbuilt layer" and
step 2 of the locked build order.

**Decision:** Added the Intake Reader as a new specialist. One LLM
call per FNOL bundle → validated `IntakeExtraction` carrying
loss_date / loss_location / loss_summary / severity_tier + the
three triage flags (litigation / rep / complaint), each with a
verbatim-quote evidence field. Optional identity fields
(policy_number, insured_name, claimant_name) round out the
extraction.

Schema invariants enforced by Pydantic:
- `severity_evidence` non-empty
- Each True flag → non-empty corresponding `*_evidence`
- Each False flag → empty corresponding `*_evidence` (forces the
  model to be explicit about what it didn't find)
- `loss_summary` length capped at 600 chars

Runtime mirrors `document_reader.py`: forced tool_use, Pydantic
validation, one retry on validation failure with the error fed
back as a corrective system note.

**Why:** "Design rich, implement minimal." The richer schema (every
field meaningfully changes a triage bucket or seeds a specialist)
costs nothing at runtime — one LLM call regardless of field count —
and saves an expensive re-roll later. Evidence-iff-flag mirrors
the `RelevanceCall` pattern so future readers see one consistent
shape for "extract + cite."

**Out of scope:** Multi-modal FNOL bundles (call recordings, photos).
v1 takes a single `str` blob; callers assemble it however they want.
Calibrating prompts on real FARS narratives. Anchor-pair evals (no
locked thresholds yet for this specialist — flag in build-order
step 2.x to write them before demo).

**Code touched:**
- `src/argos/schemas/specialists/intake_reader.py` — `IntakeExtraction`
  Pydantic schema with two validators
- `src/argos/specialists/intake_reader.py` — `run_intake_reader`
  runtime with `IntakeReaderResult` dataclass + system prompt
  including 4-tier severity rubric + flag definitions + 1 worked
  example
- `tests/specialists/test_intake_reader.py` — 15 tests: 8 schema
  invariants, 2 prompt rendering, 5 runtime (validated parse, retry
  on validation failure, exhaustion, no-tool-block path)
- Full suite: 262/262 green (was 247; +15 new tests)

**Not yet wired:** Caller code that pipes `IntakeReaderResult` into a
`Claim` + `CoverageRequest`. That's downstream of this specialist
and depends on intake-side metadata (claim_id assignment, policy
lookup). Will land as part of step 3 (Outreach + OutboundRequest)
or a small intake-glue module — decide when we hit it.

## 2026-06-01 — Step 4 shipped: Reply Parser workflow

**Implements:** "Inbound Reply Handler / Reply Parser" and step 4 of
the locked build order. First specialist-level consumer of
`OutboundRequest`.

**Decision:** Added the Reply Parser as a deterministic AI workflow
(per the terminology entry — not an agent). Single LLM call per
inbound document. Inputs: the inbound `Document` + the list of open
outbounds on the claim (via `Caseload.open_outbounds_for_claim`).
Output: validated `ReplyParseResult` carrying:
- `matched_outbound_id` (which OBR-XXX this reply answers)
- `answered_question_ids` (subset of that outbound's
  `question_ids_asked`)
- `unanswered_question_ids` (the rest, so the adjuster knows what
  to chase next)
- `partial: bool`, `confidence`, verbatim `text_excerpt`, `reason`

Two layers of validation:
- **Schema layer:** OBR-prefix on outbound ID, excerpt-required-
  when-answering, partial-consistent-with-answer-state, no overlap
  between answered and unanswered.
- **Runtime layer:** matched_outbound_id must be in the supplied
  candidate set; answered ∪ unanswered must equal the matched
  outbound's full asked set (no missing, no extra). Both failures
  feed back into the retry's corrective system note.

Empty `open_outbounds` raises immediately (caller bug — parser has
nothing to match against; caller should route to human triage
instead).

**Why:** Closes the outreach loop. Reply Parser is the piece that
flips info-map questions from `open` to `answered` based on inbound
content. Without it, the open-questions panel never shrinks and the
"new info" notification for Brief never fires.

The partition invariant (answered + unanswered = asked) is
deliberately strict. It forces the model to be explicit about what
the reply did NOT answer, which is the adjuster's actual next-action
list.

**Out of scope:**
- Auto-routing the partial-reply case (re-drafting a follow-up
  asking only for the still-unanswered subset). That's a future
  drafter feature once the LLM Outreach Drafter ships (step 3b).
- Cross-outbound replies (one reply answering questions from
  multiple outbounds simultaneously). v1 picks one match. If real
  data shows this happens, v2 adds multi-match.
- Auto-flipping `OutboundRequest.status` to `replied` and the
  underlying `OpenQuestion` instances to `answered`. That happens
  via the `MarkReplied` Action Type the orchestrator triggers after
  the parser returns. The parser itself just emits the parse
  result; mutations are downstream.
- Anchor-pair evals for this workflow — flag for the "before demo"
  todo list along with intake-reader evals.

**Palantir mapping:** `ReplyParseResult` is the output of the
`RunReplyParser` Action Type. The cascading mutations
(`MarkReplied` on the `OutboundRequest` object;
`FlipOpenQuestionStatus` on each answered question's
`ClaimOpenQuestion` row) are triggered by the orchestrator after
the parser returns, not by the parser itself.

**Code touched:**
- `src/argos/schemas/specialists/reply_parser.py` — `ReplyParseResult`
  Pydantic schema with four validators
- `src/argos/specialists/reply_parser.py` — `run_reply_parser`
  runtime + `ReplyParserResult` dataclass + system prompt with
  matching rules, partition invariant, confidence rubric
- `tests/specialists/test_reply_parser.py` — 18 tests across schema
  invariants, runtime success, retry on unknown outbound, retry on
  partition mismatch, empty-outbounds guard, acknowledgement-only,
  partial replies, multi-candidate routing
- Full suite: 296/296 green (was 278; +18 new tests)

**Not yet wired:** No code calls `run_reply_parser` from the
orchestrator yet. The wire is: an inbound document arrives →
caseload's `open_outbounds_for_claim` provides the candidate set →
orchestrator invokes `run_reply_parser` → applies the cascading
mutations (`MarkReplied` + question flips). That orchestration glue
is its own small wire, not part of step 4.

## 2026-06-01 — Terminology: what we call "specialists" are AI workflows, not agents

**Decision:** What lives under `src/argos/specialists/` is a set of
**deterministic AI workflows**, not autonomous agents. Each one is a
single-shot LLM call with forced tool_use for structured output,
Pydantic validation, deterministic retry-on-failure. No autonomous
tool selection, no multi-turn reasoning, no planning loops.

The code keeps the `specialist` term and directory name because
renaming is high-churn and the existing architecture docs
(SYSTEM_ARCHITECTURE.md, AGENT_ARCHITECTURE.md) use it consistently.
But every new decision entry, every spec doc, and every reference in
prose should call these things workflows when accuracy matters.

**Why:** "Agent" implies autonomy — choosing tools, deciding next
steps, reasoning across turns. None of our LLM-using modules do
that. Document Reader, Intake Reader, Coverage, Brief, Reply Parser
(about to ship), and the eventual Outreach Drafter are all the same
shape: render a structured prompt, force one tool call, validate,
return. Calling them "agents" misrepresents what's happening, both
to ourselves and to anyone reviewing the architecture.

A true agent would matter for things like an autonomous claims
adjudicator that decides whether to invoke Coverage vs Liability vs
escalate to a human, then loops. We're not building that. The
orchestrator dispatches deterministically per the dispatcher rules;
no LLM is in that loop.

**Out of scope:** Renaming `src/argos/specialists/` to
`src/argos/workflows/`. The cost (rename across imports, docs, tests,
specs) outweighs the clarity gain. Future readers learn the term
means "deterministic AI workflow" from this entry.

**Palantir mapping:** N/A — terminology convention only.

**Code touched:** None. Documentation convention.

## 2026-06-01 — Step 3a shipped: `OutboundRequest` data model

**Implements:** "Step 3 split: 3a (OutboundRequest data) ships now"
and the data-layer half of "Outbound status tracking is a first-class
concern."

**Decision:** Added `OutboundRequest` to the ontology as a first-class
domain object. Lifecycle states: `pending_draft` → `drafted` → `sent`
→ `replied`, with `overdue` and `cancelled` branches. Each state
implies which fields are populated; enforced by a Pydantic
`model_validator`. Two new accessors on `Caseload`:
`outbounds_for_claim(claim_id)` and `open_outbounds_for_claim(claim_id)`
— the latter scopes the Reply Parser's candidate set to outbounds
in `sent` or `overdue` state.

**Why:** Builds the data layer Reply Parser (step 4) needs without
waiting on the LLM drafter's writing-quality research. Brief can
now read outbound state to render outreach status in the
open-questions panel. The schema is shipped exhaustively (every
lifecycle field) so 3b and step 4 don't need schema edits — they
just write the fields they own.

**Out of scope:**
- The LLM drafter itself (deferred to 3b).
- Per-channel delivery confirmation (read receipts, fax tone
  analysis) — `status="sent"` records "we sent it," not "delivery
  confirmed." That's v2.
- Auto-computing `follow_up_due_at` from question cycle time —
  callers set it explicitly for now; a helper for "due_at from
  question_ids" can land when an actual caller needs it.

**Palantir mapping:** `OutboundRequest` is a Foundry object type.
Creation via `RecordOutboundRequest` Action Type; status mutations
via `SendOutbound`, `MarkOverdue`, `MarkReplied`, `CancelOutbound`.
The 3b drafter mutates `draft_body` + `drafted_at` via
`DraftOutreach`. Reply Parser sets `replied_at` + `reply_doc_id` +
status='replied' via `MarkReplied`.

**Code touched:**
- `src/argos/ontology/types.py` — `OutboundRequest` class +
  `OutboundChannel` / `OutboundStatus` literals + `model_validator`
  for status-vs-field consistency. New `outbound_requests` field on
  `Caseload`. Two new helpers (`outbounds_for_claim`,
  `open_outbounds_for_claim`).
- `tests/ontology/test_outbound_request.py` — 16 tests across schema
  shape, status invariants, lifecycle constructibility, Caseload
  helpers.
- Full suite: 278/278 green (was 262; +16 new tests).

**Not yet wired:** No code calls `OutboundRequest(...)` to create one
yet — that happens when the Outreach UI (or Outreach Drafter
runtime in 3b) starts producing them. The data layer is ready
ahead of the producers.

## 2026-06-01 — Palantir mapping is a tracked field in DECISIONS entries

**Decision:** Every DECISIONS entry that introduces a schema,
specialist, data model, or runtime wire gets a `**Palantir mapping:**`
field that names where it lands in Foundry: which object type(s) it
persists as (if any), which Action Type(s) trigger or mutate it (if
any), or N/A (if pure build infra).

Going forward, the standard entry shape is:
**Decision** → **Why** → **Out of scope** → **Palantir mapping** →
**Code touched**.

**Why:** The architecture commits to Foundry as the data substrate
(see SYSTEM_ARCHITECTURE.md §2, AGENT_ARCHITECTURE.md §6). Pydantic
schemas in `src/argos/schemas/specialists/` are the Python runtime
shape — but they correspond to specific Foundry surfaces (object
types we persist, Action Types specialists call). Today the mapping
lives only in our heads and drifts silently. Recording it per
decision makes the binding explicit and durable.

**Out of scope:** Implementing the Foundry OSDK calls now. We're
still in the Railway-Python phase; the mapping is design intent,
not code. When we wire Foundry later, the Action Type / Function
names recorded in these entries become the actual OSDK identifiers
we ship.

**Palantir mapping:** N/A — this entry is convention.

**Code touched:** None. Documentation convention only.

### Retroactive mapping for prior entries

The major schema- and surface-introducing entries logged so far,
with their intended Foundry surfaces:

| Entry | Object type(s) | Action Type(s) | Notes |
|---|---|---|---|
| `RelevanceCall` (Reader output schema) | — | `RunDocumentReader` | Output wrapped in `AgentAction` record |
| `IntakeExtraction` (step 2 shipped) | — | `RunIntakeReader`; cascading `CreateClaimFromIntake` | Creates `Claim` + `CoverageRequest` |
| `INFO_MAP_AUTO_BI_FL` + `OpenQuestion` | `OpenQuestionCatalog` (reference data); per-claim `ClaimOpenQuestion` link object | TBD `FlipOpenQuestionStatus` | Catalog is read-only ref data; per-claim status flips via action |
| `Claim`, `CoverageRequest`, `Document`, `Caseload` | direct object types | various existing | Pre-existing ontology |
| Auto-dispatch wire (step 1 shipped) | — | `DispatchSpecialistJobs` → per-specialist Action Types (`RunCoverage`, `RunReserve`, `RunLiability`) | Runtime glue; no new object type |
| Brief consumes info map | — | `RunBrief` (existing) | Reads `ClaimOpenQuestion` + persisted specialist results |
| Outbound status tracking (step 3a) | `OutboundRequest` | `RecordOutboundRequest` (create); `SendOutbound`, `MarkOverdue`, `MarkReplied` (mutate) | This step ships the data model only |
| Outreach Drafter (step 3b) | — | `DraftOutreach` (mutates `OutboundRequest` body) | LLM-side; pending writing-quality research |
| Reply Parser (step 4) | — | `IngestReply` → cascading `FlipOpenQuestionStatus` + `MarkReplied` | Reads `OutboundRequest` to scope candidate questions |
| Reserve specialist (step 5) | — | `RunReserve` (replaces stub) | Loop terminator |
| Brief nightly batch (step 6) | — | `BatchRefreshBriefs` (scheduled) | Pure orchestration |

These mappings are *design intent* — they become OSDK identifiers
when we wire Foundry. Edits to the table belong in a NEW entry
that supersedes, not by mutating this one.

## 2026-06-01 — Step 3 split: 3a (OutboundRequest data) ships now; 3b (LLM drafter) waits on writing-quality research

**Supersedes:** Step 3 of "Build order locked" — the original
combined "Outreach Drafter + OutboundRequest model" entry. Both
halves still ship; this entry sequences them.

**Decision:** Split step 3:

- **3a (ship now):** `OutboundRequest` data model + persistence +
  tests. Pure schema, no LLM call. Status lifecycle, follow-up
  timer, link from question_ids_asked to info-map questions, link
  to reply Document when one arrives.
- **3b (defer):** Outreach Drafter LLM call. Paused until Tom
  completes external consult on prompt patterns for good
  professional writing. Default LLM output for outreach is
  bland / robotic / wrong-register; for messages going to real
  recipients (counsel, body shops, claimants), prompt quality is
  load-bearing and not something to throw together.

**Why:** LLM writing quality is the main risk on the drafter.
Building it on a generic prompt now and re-prompting later wastes
work and pollutes the eval baseline once we lock anchor-pair
thresholds. Shipping the data layer first unblocks Reply Parser
(step 4) and lets Brief surface outreach state in the open-questions
panel.

**Out of scope:** Doing the writing-quality research ourselves
before Tom's consult. We don't pre-empt his external research with
in-vault grepping unless he explicitly asks.

**Palantir mapping:**
- 3a: `OutboundRequest` object type; `RecordOutboundRequest` (create),
  `SendOutbound` + `MarkOverdue` + `MarkReplied` Action Types
  (status mutations).
- 3b: `DraftOutreach` Action Type — calls the LLM specialist; mutates
  an existing `OutboundRequest` from `pending_draft` →
  `drafted` (terminology TBD with schema).

**Code touched:** OutboundRequest schema + tests landing in step 3a
shipping immediately after this entry. Drafter deferred.

## 2026-06-01 — Intake reader is a distinct, unbuilt layer

**Decision:** A separate LLM call is needed to extract structured
`Claim` fields (severity tier, litigation flag, rep flag, loss date,
parties, alleged injuries, etc.) from a free-text FNOL bundle, BEFORE
the triage policy engine runs. Build this before the demo.

**Why:** Today the synthetic generator hand-populates structured
Claim fields. The demo's pitch is "we handle unstructured input";
faking the intake step undercuts that. The existing Document Reader
is a *per-doc relevance classifier* — different job, different output
shape.

**Out of scope:** Replacing the existing per-doc Reader. Both layers
will coexist: intake-time structured extractor (new), per-doc
relevance classifier (existing).

**Code touched:** Not yet built. Will land in
`src/argos/specialists/intake_reader.py`.

## 2026-06-01 — Auto-dispatch from Reader → Orchestrator is the missing wire

**Decision:** `screen_caseload` produces `RelevanceCall` records
during triage but does not enqueue specialist jobs. The dispatcher
(`orchestrator/dispatcher.py`) exists and can map a `RelevanceCall` to
a list of `Job` objects. The next wire: when the Reader flags
`relevant=True` during triage, jobs auto-enqueue so specialists run
in the background. By the time the adjuster opens a claim, Coverage
has already produced its insight.

**Why:** This is the missing connector behind Tom's mental model of
"by the time I open the claim, the system already knows what it
thinks." Today the adjuster (or a test fixture) has to call the
orchestrator manually after triage.

**Out of scope:** Replacing on-demand specialist runs. Both modes
coexist — auto-trigger on Reader signal during triage, plus explicit
invocation from the UI.

**Code touched:** Not yet wired. Will land in
`services/triage/reader_integration.py` (enqueueing step) or a new
small glue module that takes `ReaderScreeningResult` + `JobQueue` and
calls `dispatcher.dispatch(...)`.

## 2026-06-01 — Outreach Drafter consumes a per-recipient info-map slice

**Decision:** Outreach Drafter takes `(claim, recipient_party)` →
slices the info map via `INFO_MAP_AUTO_BI_FL.by_party(recipient)` →
filters to open via `answer_detector.is_answered` → drafts a message
asking for the open ones.

**Why:** Per-recipient scope makes answer-detection tractable. Body
shop has ~3 relevant questions; we don't need full-39 detection to
draft a body-shop message. Cleaner than building a comprehensive
detector first.

**Out of scope:** Multi-recipient batched messages and cross-recipient
deduplication. Each draft targets one recipient.

**Code touched:** Not yet built. Will land in
`src/argos/specialists/outreach/`.

## 2026-06-01 — `MaterialityCall` → `RelevanceCall` (Python-only rename)

**Decision:** Rename the Reader's output class from `MaterialityCall`
to `RelevanceCall`, field `.material` → `.relevant`. The JSON wire
format and the LLM tool name (`emit_materiality_call`) stay as-is
via a Pydantic field alias.

**Why:** "Materiality" is jargon. "Relevant" is plain English.
Python-only so locked anchor-pair eval thresholds stay valid — the
model sees the identical schema + tool name + prompt.

**Out of scope:** Renaming the LLM tool name or the system prompt
language. Doing so invalidates
`docs/evals/document-reader-anchor-pairs-thresholds.md`; not worth a
re-run for a cosmetic change.

**Code touched:** `src/argos/schemas/specialists/document_reader.py`
(Pydantic alias), all Python callers + tests + scripts + spec doc.
240/240 tests green.

## 2026-06-01 — `material_counts` → `relevant_doc_counts`

**Decision:** Rename the Reader-output aggregate per-claim count from
`material_counts` to `relevant_doc_counts`; rename
`material_unread_count` to `relevant_unread_count` in the policy
engine bucket logic.

**Why:** The variable read like "counts of materials" (substances)
rather than "count of significant docs." Same rationale as the
`RelevanceCall` rename. Doesn't touch any LLM surface.

**Out of scope:** Touching any LLM-facing prompt or tool name.

**Code touched:** `policy_engine.py`, `reader_integration.py`,
scripts, eval threshold doc, tests.

## 2026-06-01 — Brief gap detection consumes the info map

**Decision:** Brief's `_detect_gaps()` is now data-driven from
`INFO_MAP_AUTO_BI_FL`. `RawGap.variable` is an info-map question ID
(e.g., `Q-COV-001`). The 5 hardcoded rules (`policy_declarations`,
`iso_claim_search`, `medical_records`, `plaintiff_counsel_letter`,
`coverage_analysis`) are deleted. A new `answer_detector.py` maps 17
of the 39 questions to doc-type signals; unmapped questions remain
open by design.

**Why:** Single source of truth across Brief + Outreach Drafter. When
Outreach asks "what do I ask the body shop for," it slices the same
info map. No drift between specialists.

**Out of scope:** Detecting answered-state for questions where the
signal isn't a doc-on-file (e.g., HIPAA release sent = outbound
request tracking). Those questions stay open until that signal
exists. Also dropped: the "coverage analysis stale >7d" rule — that
was an orchestrator concern, not an adjuster open question.

**Code touched:** `src/argos/specialists/brief/answer_detector.py`
(new), `assembler.py::_detect_gaps()` rewrite,
`tests/specialists/brief/test_assembler.py::TestGapDetection`
rewrite.

## 2026-06-01 — Info map encoded as `INFO_MAP_AUTO_BI_FL`

**Decision:** The 39 open questions for auto BI / FL / post-FNOL
pre-coverage-decision live in
`src/argos/services/info_map/auto_bi_fl.py` as Pydantic-validated
`OpenQuestion` literals. Matches the hand-authored spec at
`docs/specs/info-map-auto-bi-fl.md` (revision r2 2026-05-31).

**Why:** Brief + Outreach Drafter need a programmable catalog. The
spec doc is the design surface; this file is the runtime surface.
Pydantic validators enforce: unique IDs, resolvable dependencies,
conditional questions have triggers, cycle-time max ≥ min.

**Out of scope:** Other LOBs / jurisdictions. v1 is single-slice.
Adding LOBs means new map files using the same types.

**Code touched:**
`src/argos/services/info_map/{types.py,auto_bi_fl.py,__init__.py}`,
`tests/services/info_map/test_auto_bi_fl.py` (24 tests).

## 2026-06-01 — Terminology: "open question"

**Decision:** The unit of fact-needed-for-decision is called an
**open question**. Rejected alternatives: "atom" (opaque),
"insight" (implies generating new info; actually we're surfacing
missing info).

**Why:** Plain English, adjuster-readable.

**Out of scope:** Renaming Brief's existing `RawGap` class. RawGap is
the Brief-side wrapper that adds rationale + citations; it carries
an open-question ID in its `variable` field.

**Code touched:** Schema field naming throughout the info_map
package.

## 2026-06-01 — Critical-path ordering = longest cycle + perishable-first

**Decision:** Open questions sort by:
1. Perishable atoms first (`is_perishable=True`)
2. Longest `best_case_cycle_time_days_max` desc
3. Longest min desc
4. ID asc (deterministic tiebreak)

Implemented in `InfoMap.critical_path_order()`.

**Why:** Rejected the "% complete" framing — what matters is
wall-clock to claim resolution, not what fraction of 39 questions
are answered. The longest unrequested cycle is the binding
constraint. Perishable atoms (EDR data lost on salvage = Q-LIA-011)
sort ahead of any non-perishable regardless of cycle, because their
window-to-act is irreversible.

**Out of scope:** Optimizing the *schedule* of parallel outbound
requests. v1 surfaces ordering; it doesn't optimize a batch.

**Code touched:** `services/info_map/types.py::InfoMap.critical_path_order()`.

## 2026-06-01 — Status grain: binary `open` | `answered` for v1

**Decision:** Open questions are binary open or answered. Partial-fill
(e.g., "we have 2 of 4 medical records") is deferred to v2.

**Why:** Cost of designing partial-fill semantics across 39 questions
exceeds the value for the demo. Binary is enough to drive the
open-questions panel + Outreach Drafter triggering.

**Out of scope:** v2 partial-fill semantics.

**Code touched:** Schema docstring; no implementation difference.

## 2026-06-01 — Q-DAM-013 (HIPAA release) routes to counsel only when represented

**Decision:** When `claim.rep_flag = True`, HIPAA medical-release
requests route to claimant counsel only. Direct-to-claimant requests
on a represented claim violate FL § 626.9541. Encoded as a structural
constraint in Q-DAM-013's `sources[*].notes`.

**Why:** Florida unfair-claims-practice statute. Real risk if Outreach
Drafter routes around counsel. Encoding at the data layer means every
consumer respects it without re-implementing.

**Out of scope:** Other jurisdictions' equivalent rules. Same pattern
when we add them.

**Code touched:** `auto_bi_fl.py` Q-DAM-013 source notes.

---

## Earlier decisions (pre-2026-06-01, recovered from session memory)

### Brief specialist eval: thresholds locked, run 3 passed 12/12
**Date:** 2026-05-31. Brief r3 narrative prompt fix shipped after run
2 surfaced citation drift. Thresholds locked in
`docs/evals/brief-locked-thresholds.md`. 216/216 pytest green at
that point; current session added 24 info_map tests (240/240).

### Triage architecture: policy engine first, LLM only for extraction
**Date:** pre-2026-05-30. Deterministic 7-bucket policy engine
handles ordering. LLM (Document Reader) is used only for per-doc
relevance extraction, never for free-form ranking. Hybrid v2 LLM
re-rank was killed after failing locked thresholds; postmortem at
`docs/specs/triage-ranker-hybrid-v2.md`.

### Spec docs live in the project repo, not the Tom OS vault
**Date:** standing convention. Project-specific specs, plans, and
decisions live under `~/Projects/argos/docs/`. Tom OS holds only an
index note in `Career/Workspace/Ideas/`.
