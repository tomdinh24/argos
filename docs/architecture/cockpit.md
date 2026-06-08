---
tags:
  - project/argos
  - type/architecture
  - status/living
created: 2026-06-04
updated: 2026-06-07
---

# Argos cockpit — single-claim, single-adjuster user surface

The cockpit is the FTE-facing UI for Argos. This doc defines the user
journey, the screens, the data each screen reads, and the actions each
screen fires. Scope is intentionally narrow — one adjuster, one claim,
demo-mode — because Argos is an FTE-configured workflow stack, not a
self-serve SaaS. Multi-tenant onboarding, supervisor escalation queues,
and account management are out of scope until a customer asks.

This is the surface for [`SYSTEM_ARCHITECTURE.md`](../SYSTEM_ARCHITECTURE.md)
§0.2 item 7 (Vercel cockpit). Stack: Next.js on Vercel, calling the
FastAPI surface at `argos-production-d382.up.railway.app`.

## Adjuster journey — full lifecycle on one demo claim

The demo claim is a moderate-severity auto BI: three-party rear-end,
soft-tissue + lien suspected, possibly subrogable. That shape exercises
every workflow in the stack — Coverage, Reserve, Liability, Recovery,
Closure — so the cockpit shows them all.

| Step | What Argos does | What the adjuster sees | What the adjuster commits |
|---|---|---|---|
| 1. FNOL lands | `intake_reader` parses the FNOL, creates `Claim` + `ClaimsV1`, runs `brief` for the opening synopsis | New row in Caseload Inbox with severity, posture, opening Brief | nothing — auto-ingested |
| 2. Coverage | `coverage` workflow extracts coverage facts, runs policy engine, emits `CoverageReport` with `EvidenceCitation`s | Coverage panel: applicable layer, posture recommendation, every probabilistic claim backed by clickable citations | `apply_coverage_decision_v2(claim, new_posture)` |
| 3. Documents arrive over days | Each new doc triggers `advance_claim`, which re-runs affected workflows. Cockpit renders **deltas** | "Coverage unchanged. Reserve +$12k on the MRI. Recovery: subrogation opportunity flagged." | nothing — adjuster opens whichever workflow's delta matters |
| 4. Reserve | `reserve` workflow emits `ReserveAnalysis` (specials, multiplier, phase-budget, ULAE) | Reserve panel: breakdown table, math source, recommended band | `apply_reserve_decision(claim, accept)` |
| 5. Liability | `liability` workflow emits `LiabilityAssessment` (per-party fault %, regime, bar status, policy gates) | Liability panel: apportionment, gate verdict, evidence | `apply_liability_decision(claim, accept)` |
| 6. Recovery | `recovery` workflow emits `RecoveryAssessment` (recoverable basis, pursuit recommendation) | Recovery panel: pursuit path, basis math, policy gates | `apply_recovery_decision(claim, decision)` |
| 7. Closure | `closure` workflow emits `ClosureAssessment` (25-gate engine output, one of 11 recommendation literals) | Closure panel: gate state, pass/block per gate, recommendation | `apply_closure_decision(claim, recommendation)` or `apply_reopen_decision(claim, reopen_reason)` |
| 8. Audit | At any point | Full AgentAction ledger — every specialist call, input hash, output, reasoning, citations, status | nothing — read-only |

Step 8 is the Boecher/Ruiz discovery-survivable record. It is not a
sequential step; it is a panel the adjuster (or counsel, or a
regulator) can open at any point in the lifecycle.

## Screens

Six surfaces. Each is defined by **the data it reads** and **the
Action Type it fires** on commit. No screen renders state it doesn't
need; no screen invents an Action Type that doesn't exist in the
ontology. Visual register and access-pattern mirror the
[Talos](https://github.com/tomdinh24/talos) demo so both products read
as one family.

### Screen 0 — Landing / Access

Two-pane gate. Left: brand orb + headline ("Sourced claims operations
for specialty TPAs") + "Private demo · by invitation" foot. Right:
access-token field with mono labels (`001 / ACCESS`, `002 / AUTH`) +
"Enter" button. Soft client-side gate via `NEXT_PUBLIC_ACCESS_CODE`;
real protection is the FastAPI bearer-token guard on every endpoint.

**Reads:** nothing. **Fires:** local `setAuthed(true)` → routes to Home.

### Screen 1 — Home (Caseload Inbox + Add Example)

The queue plus the demo-seeding affordance. Lists every claim
assigned to the adjuster, sorted by surfaced priority. Primary CTA
above the list: **"Add example claim"** opens a modal with N pre-shaped
scenarios (moderate auto BI, high-severity auto BI, lien-bearing,
recoverable). Click → seeds → `advance_claim` auto-fires intake →
brief → coverage. Row appears with a "Triaging…" progress chip that
resolves to "Coverage ready · review."

**Reads:** `GET /caseload` → list of `{claim_id, posture, latest_event,
next_action, severity_score, triage_state}`. Backed by the Pydantic
`Caseload` projection over the ontology.

**Fires:**

- Click "Add example claim" → modal → `POST /demo/seed-claim {scenario:
  "moderate_bi" | "high_severity_bi" | "lien_bearing" | "recoverable"}`.
- Click claim row → routes to Screen 2.

**Demo-mode:** starts with `CLM-001` seeded. Tom or anyone clicking
through can add 1–3 more example claims to show the home-page list
shape under load.

### Screen 2 — Claim Cockpit (the central screen)

Single-claim view. This is where 95% of the adjuster's time lives.

**Layout (shipped — revises the original left-rail console; see
[DECISIONS 2026-06-07](../DECISIONS.md)).** Mobile-first single column,
with an `.app--wide` desktop variant. Same tokens, layout-only.

- **Header card.** Insured, the facts grid (loss type, date of loss,
  severity, jurisdiction, policy, status), and a **single status chip**
  — the triage band (Now / Today / Later). No separate Eisenhower
  descriptor.
- **Three tabs — Overview / Workflow / Sources.** The Workflow tab
  carries a `N needs you` notification badge; Sources carries a count.
  - **Overview.** The claim brief (citation-chipped) + a "New
    information / since you last looked" log (unreviewed items flagged
    with a notification tag).
  - **Workflow.** A lifecycle accordion stacking all five stages
    (Coverage → Closure). Stages before the active one read as
    accepted; the first unsettled stage is the one that needs the
    adjuster and opens by default. Each stage body renders that
    workflow's assessment object — coverage map + outcome distribution
    (`CoverageReport`), reserve findings + component band ranges +
    pre-booking checks + editable amount (`ReserveAnalysis`), liability
    allocation + evidence (`LiabilityAssessment`), recovery status +
    checklist + net-economics (`RecoveryAssessment`), closure readiness
    + decision recap (`ClosureAssessment`) — and **commits inline** via
    one contextual CTA per stage (no separate drawer). Every
    `EvidenceCitation` row is clickable to Screen 4.
  - **Sources.** One searchable / type-filterable table of every
    document read — merges the old Documents tab and pinned-citations
    list. Rows and inline `[n]` chips open Screen 4.

**Reads:**

| Tab | Endpoint | Returns |
|---|---|---|
| Brief | `GET /claim/{id}/brief` | `ClaimBrief` |
| Coverage | `GET /claim/{id}/coverage` | latest `CoverageReport` + commit state |
| Reserve | `GET /claim/{id}/reserve` | latest `ReserveAnalysis` + commit state |
| Liability | `GET /claim/{id}/liability` | latest `LiabilityAssessment` + commit state |
| Recovery | `GET /claim/{id}/recovery` | latest `RecoveryAssessment` + commit state |
| Closure | `GET /claim/{id}/closure` | latest `ClosureAssessment` + commit state |
| Documents | `GET /claim/{id}/documents` | list of `Document` with metadata |
| Audit | `GET /claim/{id}/audit` | list of `AgentAction` — feeds Screen 5 |

**Fires:** none directly — the commit button opens Screen 3.

### Screen 3 — Decision Drawer (superseded — folded into per-stage commit)

> **Superseded by [DECISIONS 2026-06-07](../DECISIONS.md).** The shipped
> cockpit commits inline via one contextual CTA per stage inside the
> Workflow accordion — there is no separate drawer. The override fields
> and Approve / reject / modify affordances below now live in the stage
> body itself. The Action-Type wiring in the table is unchanged and
> remains the target backend surface.

Slides in from the right when the adjuster clicks "commit" on any
workflow's recommendation. Modal-ish but doesn't block the cockpit
behind it.

**Reads:** the recommendation payload from whichever workflow opened
the drawer. Shows:

- The action being committed (e.g. "Apply Reserve Decision: ACCEPT")
- The recommendation's basis (which `EvidenceCitation`s back it, link to Screen 4)
- Optional override fields (adjuster can modify the posture, reserve amount, etc.)
- Approve / reject / modify buttons

**Fires (on Approve):** the corresponding workflow Action Type via the
FastAPI surface, which calls the OSDK bridge:

| Workflow | API call | OSDK Action |
|---|---|---|
| Coverage | `POST /claim/{id}/coverage/commit` | `apply_coverage_decision_v2(claim, new_posture)` |
| Reserve | `POST /claim/{id}/reserve/commit` | `apply_reserve_decision(claim, accept)` |
| Liability | `POST /claim/{id}/liability/commit` | `apply_liability_decision(claim, accept)` |
| Recovery | `POST /claim/{id}/recovery/commit` | `apply_recovery_decision(claim, decision)` |
| Closure | `POST /claim/{id}/closure/commit` | `apply_closure_decision(claim, recommendation)` |
| Reopen | `POST /claim/{id}/closure/reopen` | `apply_reopen_decision(claim, reopen_reason)` |

Each call also writes a local `AgentAction` row via
[`audit_log.py::append_agent_action`](../../src/argos/services/orchestrator/audit_log.py)
and (once the `emit-agent-action` Foundry Action Type merges) mirrors
to the ontology via the AgentAction bridge.

### Screen 4 — Document Inspector

Click any `EvidenceCitation` anywhere in the cockpit → opens the
source document with the cited locator highlighted (page, paragraph,
field, or ledger row).

**Reads:** `GET /document/{id}?locator={locator}` → the document
content + highlight metadata.

**Fires:** nothing — read-only.

This is the "show me the receipts" pane. Critical for the FTE-trust
argument: every probabilistic claim has a clickable receipt.

### Screen 5 — Audit Ledger

Full `AgentAction` history for the claim. Discovery-mode view.

**Reads:** `GET /claim/{id}/audit` → list of `AgentAction` rows with
filters by `specialist`, `status`, `triggered_at` range.

**Fires:** nothing — read-only.

Each row expands to show: `input_hash`, `input_snapshot_path`,
`output_json`, `reasoning_trace`, attached `EvidenceCitation`s, and
the `escalation_outcome`. This is the Boecher/Ruiz record.

## API surface (FastAPI extension)

The current [`src/argos/api/app.py`](../../src/argos/api/app.py) is a
healthcheck stub. The cockpit needs these endpoints. All read endpoints
project from the in-process Pydantic `Caseload` and the audit JSONL;
all commit endpoints call the orchestrator's `*_actions.py` (which
mutate the Caseload Pydantic-first, then propagate via the bridges).

```
GET  /healthz                                  → {"status":"ok"} (exists)
GET  /caseload                                 → list of claim summaries
GET  /claim/{id}                               → header data
GET  /claim/{id}/brief                         → ClaimBrief
GET  /claim/{id}/coverage                      → CoverageReport
GET  /claim/{id}/reserve                       → ReserveAnalysis
GET  /claim/{id}/liability                     → LiabilityAssessment
GET  /claim/{id}/recovery                      → RecoveryAssessment
GET  /claim/{id}/closure                       → ClosureAssessment
GET  /claim/{id}/documents                     → list of Document
GET  /claim/{id}/audit                         → list of AgentAction
GET  /document/{id}                            → document content + metadata

POST /claim/{id}/coverage/commit               → apply_coverage_decision_v2
POST /claim/{id}/reserve/commit                → apply_reserve_decision
POST /claim/{id}/liability/commit              → apply_liability_decision
POST /claim/{id}/recovery/commit               → apply_recovery_decision
POST /claim/{id}/closure/commit                → apply_closure_decision
POST /claim/{id}/closure/reopen                → apply_reopen_decision
```

Auth: single bearer token in `Authorization` header, matched against
an env var. FTE-configured account — no user table, no OAuth flow.

## Out of scope (call them out explicitly)

- Supervisor escalation queue / approval routing UI
- Multi-adjuster dashboard or assignment management
- Cross-claim analytics, portfolio views, reserve roll-ups
- Account / tenant management, RBAC, audit trails of *who viewed what*
- Self-serve onboarding, billing, settings pages
- Mobile / tablet layouts — desktop-first
- Real-time push (WebSocket) for delta updates — polling on tab focus is fine

## Visual register

Deep-tech operational console, not SaaS dashboard. Closer to
Palantir Foundry / Anduril Lattice than Salesforce Service Cloud.
References live in vault memory under
[design inspiration sites](https://obsidian.md) and
[deep-tech landing techniques](https://obsidian.md).

Specific tells: hairline rules, mono labels, monochrome with one warm
accent, evidence rows render as data tables not cards, no left vertical
accent bars on anything.

## Build order (recommended)

1. Extend `src/argos/api/app.py` with the read endpoints (no commits yet) — feeds Screen 1 + Screen 2 panels.
2. Next.js scaffold: Screen 1 + Screen 2 read-only. Validate the journey by clicking through `CLM-001` end-to-end.
3. Add Screen 3 (Decision Drawer) + the commit endpoints. End-to-end click commits to Foundry.
4. Screen 4 (Document Inspector) — needed for FTE-trust demo.
5. Screen 5 (Audit Ledger) — needed for the discovery-survivable argument.

No state needed before step 1 except the seeded `CLM-001`. Once
`emit-agent-action` merges and the bridge ships, every commit flowing
through Screen 3 also lands in the Foundry-side ledger automatically.
