---
tags:
  - project/argos
  - type/architecture
  - status/living
created: 2026-05-28
updated: 2026-06-04
aliases:
  - System Architecture
---

# System Architecture — Claims Operations Intelligence Layer (Argos)

> **Single source of truth for current state.** Infrastructure, request
> flow, deployment topology, security model, failure modes, and
> scaling story for the build defined by [TECH_PLAN.md](./TECH_PLAN.md).
> Companion to [AGENT_ARCHITECTURE.md](./AGENT_ARCHITECTURE.md) (workflow
> internals + per-workflow contracts).

---

## §0 — Current state (always read this first)

> **This document mixes two horizons.** §0 below is the **as-is**
> snapshot — what code exists right now. §2 onward describes the
> **target** Foundry + Vercel + Railway deployment that the as-is code
> will project onto. Don't confuse them. When you propose work, anchor
> in §0; when you propose roadmap, anchor in §2+.

### §0.1 — Status table (workflow + infra)

| Component | Layer | Status | Code path |
|---|---|---|---|
| **Ontology objects (Pydantic)** | data | 16 of ~26 target | [`ontology/types.py`](../src/argos/ontology/types.py) — Policy, PolicyPeriod, PolicyCoverage, CoverageRequest, Document, SyntheticClaim, Claim, AgentAction, WorkItem, ServiceDeadline, ScheduledTask, LedgerEntry, Communication, LegalDeadline, OutboundRequest, Caseload |
| **Brief workflow** | workflow | shipped | [`workflows/brief/`](../src/argos/workflows/brief/) |
| **Coverage workflow** | workflow | shipped | [`workflows/coverage.py`](../src/argos/workflows/coverage.py) |
| **Liability workflow** | workflow | shipped (deterministic core + extractor + runner) | [`workflows/liability.py`](../src/argos/workflows/liability.py), [`services/liability/`](../src/argos/services/liability/) |
| **Reserve workflow** | workflow | shipped (LLM extractor + Python calculator) | [`workflows/reserve.py`](../src/argos/workflows/reserve.py) |
| **Recovery workflow** | workflow | shipped 2026-06-02 (deterministic core + extractor + runner) | [`workflows/recovery.py`](../src/argos/workflows/recovery.py), [`services/recovery/`](../src/argos/services/recovery/) |
| **Closure workflow** | workflow | shipped 2026-06-02 (deterministic core + extractor + runner + writeback actions) | [`workflows/closure.py`](../src/argos/workflows/closure.py), [`services/closure/`](../src/argos/services/closure/), [`services/orchestrator/closure_actions.py`](../src/argos/services/orchestrator/closure_actions.py) |
| **Outreach Drafter** | correspondence | shipped (v2: bullet rule sharpened, reasoning_effort=low) | [`workflows/outreach_drafter.py`](../src/argos/workflows/outreach_drafter.py) |
| **Reply Parser** | correspondence | shipped | [`workflows/reply_parser.py`](../src/argos/workflows/reply_parser.py) |
| **Document Reader** | supporting | shipped | [`workflows/document_reader.py`](../src/argos/workflows/document_reader.py) |
| **Intake Reader** | supporting | shipped | [`workflows/intake_reader.py`](../src/argos/workflows/intake_reader.py) |
| **Triage policy engine** | supporting | shipped (deterministic gates; LLM hybrid v2 killed) | [`services/triage/policy_engine.py`](../src/argos/services/triage/policy_engine.py) |
| **Dispatcher** | orchestration | shipped 2026-06-02 (Recovery routing wired: `liability → [liability, recovery]`, `damages → [reserve, liability, recovery]`, `subrogation → [recovery]`) | [`services/orchestrator/dispatcher.py`](../src/argos/services/orchestrator/dispatcher.py) |
| **Runner registry** | orchestration | shipped; includes coverage/reserve/liability/recovery/closure/brief | [`services/orchestrator/runner.py`](../src/argos/services/orchestrator/runner.py) |
| **InfoGap (policy spine)** | orchestration | shipped | [`services/orchestrator/info_gap.py`](../src/argos/services/orchestrator/info_gap.py) |
| **DraftOutreach action wire** | orchestration | shipped | [`services/orchestrator/draft_handler.py`](../src/argos/services/orchestrator/draft_handler.py) |
| **IngestReply action wire** | orchestration | shipped | [`services/orchestrator/reply_handler.py`](../src/argos/services/orchestrator/reply_handler.py) |
| **Correspondence Advance** | orchestration | shipped | [`services/orchestrator/correspondence_loop.py`](../src/argos/services/orchestrator/correspondence_loop.py) |
| **Claim Advance (cross-stream)** | orchestration | shipped | [`services/orchestrator/claim_advance.py`](../src/argos/services/orchestrator/claim_advance.py) |
| **Coverage writeback** | action | shipped; Foundry bridge shipped 2026-06-02 | [`services/orchestrator/coverage_actions.py`](../src/argos/services/orchestrator/coverage_actions.py), [`services/foundry/coverage_bridge.py`](../src/argos/services/foundry/coverage_bridge.py) |
| **Foundry bridge layer** | infra | **live-verified 2026-06-04** — all 5 workflow bridges (Coverage, Reserve, Liability, Recovery, Closure with closure+reopen) round-trip against the live Argos ontology. 21/21 tests green (16 unit + 5 live integration against seeded `CLM-001`). Bridges via Python OSDK `argos_live_sdk` (legacy `argos_osdk_sdk` retired — bound to wrong ontology hex). INVALID-validation check added to client.py → mandatory post-call on every bridge. AgentAction emission bridge NOT built — unblocked but pending action type definition. | [`services/foundry/`](../src/argos/services/foundry/), [`docs/architecture/foundry-bridge-pattern.md`](./architecture/foundry-bridge-pattern.md) |
| **Closure writeback** | action | shipped 2026-06-02 — `apply_closure_decision` + `apply_reopen_decision` | [`services/orchestrator/closure_actions.py`](../src/argos/services/orchestrator/closure_actions.py) |
| **Reserve writeback** | action | shipped 2026-06-02 — `apply_reserve_decision` | [`services/orchestrator/reserve_actions.py`](../src/argos/services/orchestrator/reserve_actions.py) |
| **Liability writeback** | action | shipped 2026-06-02 — `apply_liability_decision` | [`services/orchestrator/liability_actions.py`](../src/argos/services/orchestrator/liability_actions.py) |
| **Recovery writeback** | action | shipped 2026-06-02 — `apply_recovery_decision` | [`services/orchestrator/recovery_actions.py`](../src/argos/services/orchestrator/recovery_actions.py) |
| **AgentAction audit log writes** | action | shipped 2026-06-02 — runner appends `analysis_emitted`/`validator_fail` per run; writebacks append `validator_pass` on commit; Closure D1 gate promoted from warning → blocker | [`services/orchestrator/audit_log.py`](../src/argos/services/orchestrator/audit_log.py) |
| **Overdue OBR sweep** | action | NOT built | — |
| **Typed `pending_recommendations` on Caseload** | data | NOT built (JSON files on disk today) | `data/workflow-results/{claim_id}/{workflow}.json` |
| **Eval suite (anchor-pair thresholds)** | eval | all four analytical workflows covered — Coverage, Document Reader, Triage, Brief, **Liability** (15 + 8, green 2026-06-02), **Reserve** (15 + 15 sub-cases, green 2026-06-02), **Recovery** (15 + 14 sub-cases, green 2026-06-02), **Closure** (15 + 9 sub-cases, green 2026-06-02) | [`docs/evals/`](./evals/), [`tests/evals/liability/`](../tests/evals/liability/), [`tests/evals/reserve/`](../tests/evals/reserve/), [`tests/evals/recovery/`](../tests/evals/recovery/), [`tests/evals/closure/`](../tests/evals/closure/) |
| **AF signatory roster** | data | seed-only (9 NAICs) — no refresh path | [`services/recovery/constants.py`](../src/argos/services/recovery/constants.py) |
| **FastAPI service** (`/workflow/{name}/run`) | infra | NOT built — runner is in-process only | — |
| **Foundry tenant** (Ontology, Action Types, Code Repos, AIP Evals) | infra | scale-out shipped 2026-06-03 — **28 Object Types** (poc-1, merged) + **48 Link Types** + **6 Action Types** (poc-2b, proposal `7eb1bbe9`, pending merge) via AI FDE-driven worklist (YAML → spec generator → AI FDE MCP execution). 8 lower-value links deferred to fit Foundry's 60 one-to-many link cap. Code Agent template approach (argos-ontology repo `src/agent/`) diagnosed dead-end — Palantir MCP doesn't mount in Function runtime, only in interactive AI FDE / Agent Studio sessions; repo repurposed as Foundry-side spec host. Original Jun-02 vertical slice (`ClaimsV1` + `apply-coverage-decision`) superseded; OSDK regen against `apply-coverage-decision-v2` + cleanup of old action type pending. AIP Evals NOT built. | [`foundry/ontology/object-types.yaml`](../foundry/ontology/object-types.yaml), [`foundry/ontology/ai-fde-spec.json`](../foundry/ontology/ai-fde-spec.json), [`scripts/generate_foundry_ontology_spec.py`](../scripts/generate_foundry_ontology_spec.py), [`scripts/foundry_smoke_test.py`](../scripts/foundry_smoke_test.py) |
| **Vercel / Next.js cockpit** | infra | NOT built — pytest is the demo today | — |
| **Railway worker** | infra | NOT built | — |

### §0.2 — What ships next (ranked, per 2026-06-02 audit)

1. ~~Document Reader `subrogation` v3 anchor-pair eval~~ — **SHIPPED 2026-06-02 (e2a3c32)**. All 3 pairs (consent-to-settle, AF eligibility, made-whole waiver) PASS on first live run; composite SHIP (v3). Variant B reasoning explicitly rules out liability/damages on Pairs 5 and 7. Run history stamped in [`docs/evals/document-reader-anchor-pairs-v3-subrogation-thresholds.md`](./evals/document-reader-anchor-pairs-v3-subrogation-thresholds.md).
2. **AF signatory roster refresh path** — scrape AF's signatory list quarterly, version the roster.
3. **Overdue OBR sweep** — `OutboundRequest.status → "overdue"` transition function.
4. **Typed `pending_recommendations` collection** — promotes JSON-files-on-disk to first-class Caseload field. Load-bearing only when Foundry projection starts.
5. ~~**Reserve/Liability/Recovery/Closure Foundry bridges**~~ — **LIVE-VERIFIED 2026-06-04.** All 5 workflow bridges round-trip against the live Argos ontology; 21/21 tests green. Package migrated `argos_osdk_sdk` → `argos_live_sdk` (correct ontology binding). INVALID-validation check added to the bridge contract. AgentAction emission bridge remains as a follow-up (unblocked but not yet built).
6. ~~**Foundry Object Types scale-out**~~ — **SHIPPED 2026-06-03 via AI FDE-driven generator** (poc-1 28 Object Types merged + poc-2b 48 Link Types + 6 Action Types pending merge). Source-of-truth in [`foundry/ontology/object-types.yaml`](../foundry/ontology/object-types.yaml); regeneration via [`scripts/generate_foundry_ontology_spec.py`](../scripts/generate_foundry_ontology_spec.py); spec snapshot lives at `argos-ontology` Foundry code repo for AI FDE to read. 8 link types deferred due to Foundry 60 one-to-many cap (audit-only Party variants + 3 self-refs). AIP Evals against the four locked threshold docs NOT built.
7. **Vercel cockpit (Next.js)** — the operator-facing UI. Build after Foundry projection so it has typed objects to render.

### §0.3 — Maintenance protocol

> **This doc is living.** Every PR that ships a workflow, changes
> dispatcher routing, adds an Action Type, modifies the ontology, or
> moves something from "NOT built" → "shipped" must update §0.1 and
> §0.2 in the same commit. The doc IS the source of truth — if §0.1
> says "shipped" and the code doesn't match, the doc is wrong, fix the
> doc.
>
> **Update conventions:**
> - Status values: `shipped` / `shipped (with caveat in parens)` / `partial` / `NOT built` / `schema only` / `killed`.
> - When a row moves from "NOT built" → "shipped," include the commit SHA in the date stamp on the row.
> - Bump the `updated:` frontmatter date.
> - Append a one-line entry to `_Registry/log.md` in the Tom OS vault noting the architecture change (not the implementation detail — the architectural fact).
> - Do NOT version this doc (`v1.2`, `v2`). It's living. Use git history for the timeline.

---

## §1 — Purpose

This document answers:

1. **Where does each piece run?** (Deployment topology)
2. **How does data flow through the system?** (Request flow diagrams)
3. **What's the security and auth model?** (Auth at each boundary)
4. **What happens when something breaks?** (Failure modes)
5. **How does this scale to production?** (Scaling story)

This is the architecture a reviewer asks to see on a whiteboard. It's also what a triangulation review evaluates before we commit.

---

## §2 — Deployment topology

Three vendors, three responsibilities. Per-component decisions in [TECH_PLAN.md §2](./TECH_PLAN.md).

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                              VERCEL (US East)                                │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │  Next.js 15 (TypeScript)                                                │ │
│  │  ─ App Router pages: /, /claims/[id], /queue, /audit/[id], /eval        │ │
│  │  ─ Components: ClaimList, ExposurePanel, FinancialSnapshot,             │ │
│  │    RecommendationCard, AuditDrawer, EvidenceCitation                    │ │
│  │  ─ Server actions for OSDK + REST orchestration                         │ │
│  │  ─ NextAuth for demo auth (passkey/email allowlist)                     │ │
│  │  ─ Edge runtime where possible; node runtime for OSDK calls             │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────┘
                  │ OSDK TS                          │ REST (HTTPS, JWT)
                  │ (HTTPS + Foundry token)          │
                  ▼                                  ▼
┌────────────────────────────────────────┐  ┌──────────────────────────────────┐
│       FOUNDRY DEVELOPER TIER           │  │       RAILWAY (Singapore/US)     │
│  ┌──────────────────────────────────┐  │  │  ┌────────────────────────────┐  │
│  │  Ontology                        │  │  │  │  FastAPI service           │  │
│  │  ─ 26 object types               │  │  │  │  ─ /specialist/{name}/run  │  │
│  │  ─ link types                    │  │  │  │  ─ /eval/run, /eval/latest │  │
│  │  ─ Action Types (TS validators)  │  │  │  │  ─ /synthesis/run          │  │
│  └──────────────────────────────────┘  │  │  │  ─ /healthz                │  │
│  ┌──────────────────────────────────┐  │  │  └────────────────────────────┘  │
│  │  Code Repositories (Python)      │  │  │  ┌────────────────────────────┐  │
│  │  ─ get_financials_as_of          │  │  │  │  Worker process            │  │
│  │  ─ get_exposure_layer_b_snapshot │  │  │  │  ─ Synthesis pipeline      │  │
│  │  ─ get_applicable_config         │  │  │  │  ─ Eval orchestration      │  │
│  │  ─ get_aggregate_limits          │  │  │  │  ─ Time-to-recognition     │  │
│  │  ─ get_audit_trail               │  │  │  │    replay harness          │  │
│  │  ─ Layer-C-statutory evaluators  │  │  │  └────────────────────────────┘  │
│  │  ─ Layer-C-policy evaluators     │  │  │                                  │
│  │  ─ Layer-D judge wrappers        │  │  │  ┌────────────────────────────┐  │
│  └──────────────────────────────────┘  │  │  │  Python 3.11 + Pydantic +  │  │
│  ┌──────────────────────────────────┐  │  │  │  Anthropic SDK + OpenAI SDK│  │
│  │  AIP Evals                       │  │  │  │  + foundry-platform-python │  │
│  │  ─ Suites per specialist         │  │  │  └────────────────────────────┘  │
│  │  ─ Golden datasets               │  │  │                                  │
│  │  ─ Rubric grader + dashboard     │  │  │  Calls outbound:                 │
│  └──────────────────────────────────┘  │  │  ─ Foundry (OSDK Python)         │
│  ┌──────────────────────────────────┐  │  │  ─ api.anthropic.com (Claude)    │
│  │  Datasets                        │  │  │  ─ api.openai.com (Layer D)      │
│  │  ─ Synthetic claim book          │  │  └──────────────────────────────────┘
│  │  ─ Generated documents           │  │
│  │  ─ Eval result datasets          │  │
│  └──────────────────────────────────┘  │
└────────────────────────────────────────┘
                  ▲                                  ▲
                  │ OSDK Python                      │
                  │ (HTTPS + Foundry token)          │
                  └──────────────────────────────────┘
                       Railway → Foundry calls
```

### What runs where

| Component | Host | Why this host |
|---|---|---|
| Workspace UI | Vercel (Next.js) | Externally shareable URL; modern React tooling; edge runtime; CDN |
| Specialist orchestration | Railway (FastAPI) | Long-running LLM calls; full Python iteration loop; not edge-suitable |
| Synthesis pipeline | Railway (worker) | Batch job, ~hours of compute, not request-shaped |
| Eval orchestration | Railway (worker) | Polling AIP Evals, batch comparisons |
| Typed semantic data | Foundry Ontology | Unique-to-Foundry primitive: typed semantic graph + validation + audit + branching attached to the type itself |
| Mutation surface | Foundry Action Types | Built-in audit/permissions; validators in TypeScript |
| Ontology-touching compute | Foundry Code Repositories | Direct ontology access; bitemporal queries |
| Eval framework | Foundry AIP Evals | Custom rubric + golden set + dashboard |
| Document storage | Foundry Datasets | Synthetic docs co-located with ontology |

---

## §3 — Request flow diagrams

### §3.1 Read flow — user views a claim

```
User clicks claim in list
   │
   ▼
Next.js page (Vercel)
   │ Server Component
   ▼
OSDK TS client
   │ HTTPS + Foundry token
   ▼
Foundry Ontology
   │ Returns: Claim + linked CoverageRequests + ClaimPartyRoles
   ▼
Next.js Server Component
   │ Renders shell with claim metadata
   ▼
Client-side fetch (parallel):
   ├─ Financial snapshot ──▶ OSDK ──▶ Foundry Function:
   │                                  get_financials_as_of(request_id, NOW, NOW)
   ├─ Documents ──▶ OSDK ──▶ Foundry Ontology: Document + DocumentExtraction
   ├─ Audit trail ──▶ OSDK ──▶ Foundry Function: get_audit_trail(claim_id)
   └─ Recommendations ──▶ OSDK ──▶ Foundry Ontology: AgentAction WHERE claim_id = ?
   │
   ▼
Hydrated UI: ExposurePanel, FinancialSnapshot, AuditDrawer, RecommendationCards
```

Read latency target: <500ms for the page shell, <2s for fully hydrated.

### §3.2 Write flow — human approves a recommendation

```
User clicks "Approve" on a RecommendationCard
   │
   ▼
Next.js Server Action
   │
   ▼
OSDK TS client → triggers ApproveAgentAction Action Type
   │ HTTPS + Foundry token
   ▼
Foundry Action Type validator (TypeScript)
   │ Validates: action_id exists, status is pending,
   │   authority chain valid, no illegal state combinations
   ▼
Action Type effect runs:
   ├─ Updates AgentAction.escalation_outcome = 'human_approved'
   ├─ Triggers downstream Action Type per recommendation type:
   │    ├─ ReserveRecommendation → RecordFinancialTransaction
   │    ├─ RecoveryRecommendation → RecordLiabilityAssessment (or status change)
   │    └─ ClosureRecommendation → CloseExposure
   └─ Writes Event row
   │
   ▼
Foundry-native audit log captures the entire chain
   │
   ▼
Next.js Server Action returns success
   │
   ▼
Client revalidates the claim view; UI updates
```

Write latency target: <1s for the Action Type chain; UI feedback is optimistic.

### §3.3 Specialist trigger flow

```
Event fires (new document ingested, or scheduled review job)
   │
   ▼
Railway FastAPI receives POST /specialist/reserve/run
   │ Body: { request_id, as_of }
   ▼
Specialist runner (Python):
   │
   ├─ Read Layer B via OSDK:
   │    ├─ get_exposure_layer_b_snapshot(request_id, as_of)
   │    └─ get_applicable_config(client_program_id, 'reserve', as_of)
   │
   ├─ Hash input → input_hash (SHA256 of Layer-B JSON)
   │
   ├─ Build prompt:
   │    ├─ SYSTEM_PROMPT (cached at Anthropic)
   │    └─ USER_TEMPLATE.render(layer_b, config)
   │
   ├─ Call Anthropic SDK:
   │    response = anthropic.messages.create(
   │      model='claude-sonnet-4-6',
   │      response_format={'type': 'json_schema', 'json_schema': RESERVE_SCHEMA},
   │      ...
   │    )
   │
   ├─ Parse + validate output via Pydantic
   │    └─ On schema violation: retry once, then 422
   │
   ├─ Emit AgentAction via OSDK Action Type:
   │    EmitAgentAction(
   │      specialist='reserve',
   │      request_id,
   │      output_json,
   │      confidence,
   │      reasoning_trace,
   │      input_hash,
   │      requires_human_approval=eval_authority(config, recommendation)
   │    )
   │
   └─ If auto-applicable AND confidence >= floor:
        Trigger downstream Action Type (RecordFinancialTransaction)
        Else: leaves AgentAction in pending state for human review
   │
   ▼
FastAPI returns the recommendation JSON
```

Latency: typically 8-20 seconds per specialist invocation (dominated by LLM call).

### §3.4 Eval orchestration flow

```
Trigger: POST /eval/run on Railway (manual or scheduled)
   │
   ▼
Eval orchestrator (Python worker):
   │
   ├─ Read golden set from Foundry Dataset via OSDK
   │
   ├─ For each golden claim, for each specialist:
   │    Run specialist via internal Railway endpoint
   │    Capture output
   │
   ├─ For each result:
   │    ├─ Layer C-statutory eval: call Foundry Function
   │    │   eval_layer_c_statutory_reserve(claim_id, output)
   │    ├─ Layer C-policy eval: call Foundry Function
   │    │   eval_layer_c_policy_reserve(claim_id, output, config)
   │    └─ Layer D eval: call Foundry Function
   │        eval_layer_d_judgment_reserve(claim_id, output)
   │        ├─ which internally calls OpenAI as cross-model judge
   │        └─ scores against rubric
   │
   ├─ Aggregate metrics per truth layer
   │
   ├─ Publish to AIP Evals as a run result
   │
   └─ Write summary to Foundry Dataset: eval_results_latest
   │
   ▼
Next.js /eval page reads eval_results_latest via OSDK; renders dashboard
```

---

## §4 — Security and auth model

### §4.1 Auth at each boundary

| Boundary | Mechanism | Notes |
|---|---|---|
| User → Vercel | NextAuth: passkey or email magic link | Allowlist of emails (yours + a few demo accounts); no public open access |
| Vercel → Foundry | Service-account personal access token in Vercel env var | Token has read-everything + trigger-specific-Action-Types scopes |
| Vercel → Railway | Signed JWT (short-lived, shared secret in env) | Each Server Action signs a JWT; Railway verifies before processing |
| Railway → Foundry | Service-account personal access token in Railway env var | Separate token from Vercel's; different scopes (can trigger more Action Types) |
| Railway → Anthropic | API key in env var | Standard bearer token |
| Railway → OpenAI | API key in env var | For Layer D judge calls |
| Foundry internal (Functions, AIP Evals) | Foundry-managed | Service-to-service auth handled by Foundry |

### §4.2 Token storage and rotation

- Vercel env vars: stored encrypted, rotated quarterly
- Railway env vars: same
- Foundry personal access tokens: scoped to specific OSDK apps; rotated quarterly; tokens lost = generate new ones in Foundry Developer Console

### §4.3 What's NOT in the demo

- Multi-tenant auth (every user sees the same demo tenant; no row-level security beyond the allowlist)
- Audit access logging beyond what Foundry provides natively
- DLP, secrets scanning, SOC 2 trail
- Production-grade rate limiting on the public Vercel surface

All of these are appropriate for the current build. Production deployment would add them.

### §4.4 Data sensitivity boundary

The synthetic data has zero real PII — it's all generated. No HIPAA, no PCI, no real claims data. This eliminates a class of risks. We label `is_synthetic: true` on every Document and never expose that field to specialists (per data-layer.md §7).

---

## §5 — Failure modes and degradation

### §5.1 Component failure scenarios

| Component down | What still works | What breaks | Demo fallback |
|---|---|---|---|
| **Foundry** | Nothing — Vercel reads Foundry directly | Workspace can't load data; Railway can't write | Pre-recorded Loom |
| **Railway** | Workspace reads current state; user can browse | Can't run specialists; can't synthesize | Pre-recorded Loom of specialist run |
| **Vercel** | Foundry + Railway healthy but UI is down | Demo is down | Pre-recorded Loom |
| **Anthropic API** | Workspace healthy; Foundry healthy | Specialists fail with 503 | Show cached prior runs in workspace |
| **OpenAI API** | Most of the system | Layer D eval fails | Layer C metrics still report |

The single irreducible point of failure is **Foundry** — the substrate. Mitigation:
- Pre-recorded Loom is the demo fallback
- Local Vercel + cached data CAN work in degraded mode (browse-only) if we cache responses
- Pre-demo: rehearse with the actual stack 30 min before; if anything is flaky, switch to Loom

### §5.2 LLM-specific failure modes

| Failure | Detection | Mitigation |
|---|---|---|
| Anthropic returns invalid JSON | Pydantic validation fails | Retry once with explicit "respond as JSON" reminder; on second failure, return 422 + log AgentAction with status=schema_violation |
| Anthropic returns confident but factually wrong | Action Type validators (illegal-combination matrix, posting rules) reject the write | Recommendation lands in audit log; never mutates state |
| Anthropic returns low-confidence above floor | confidence field below floor | AgentAction marked requires_human_approval=true; routed to review queue |
| Anthropic throttling / 429 | Exponential backoff with jitter in Railway client | Pipeline waits; doesn't fail the request |
| Cross-model judge disagrees with specialist | By design — that's the eval signal | Surface as a Layer D metric in the eval dashboard |

### §5.3 Data integrity failure modes

| Failure | Detection | Mitigation |
|---|---|---|
| Action Type validator bug allows illegal state combination | Property test on staged data; AIP Evals discrepancy on golden cases | Roll back the Action Type version in Foundry; fix; redeploy |
| Synthesis generates inconsistent documents (date predates loss) | Pipeline post-validation step rejects inconsistent timelines | Regenerate that claim |
| Specialist hallucinates a document_id in cited_documents | Workspace fails to render the citation | Show an error card; log for prompt refinement |
| Eval golden case has wrong ground truth | Layer D human review surfaces it | Update golden case; re-run eval |

---

## §6 — Scaling story (demo → production)

### §6.1 Demo scale (current)

- 4 active client programs + 1 demo flood branch + 1 schema-only captive
- ~500 synthetic claims
- ~3000-4000 documents
- 1 Foundry tenant (Developer Tier)
- 1 Railway FastAPI service + 1 worker
- 1 Vercel project

Costs: ~$700-1100 in LLM spend for the build, $0 in hosting (Developer Tier + free Vercel + Railway you already pay for), minimal compute on Foundry side.

### §6.2 Production scale (target)

| Dimension | Demo | Production |
|---|---|---|
| Tenants | 1 | Per-customer (multi-tenant Foundry or per-customer tenant) |
| Claims | 500 synthetic | 10K-100K real per customer |
| Specialists per claim | 3 | 3-7 (Reserve, Recovery, Closure, plus Coverage, Liability, Notice, SIU) |
| Daily specialist runs | ~100 (replay) | 10K-50K |
| Documents | 3-4K synthetic | Millions (real PDFs, photos, audio) |
| Storage | Foundry Datasets (synthetic) | S3 for documents + Foundry for ontology |
| Compute | Single Railway service + worker | Horizontal Railway workers behind queue |
| Auth | Email allowlist | Foundry hosted OAuth + customer SSO |
| Per-customer config | 4 hand-crafted | Authored via Configuration UI by FDE-deployed at each customer |

### §6.3 What changes in the architecture at scale

- **Specialist runs go async with a queue.** Railway worker pool consumes from Redis/SQS; specialist invocations are queued by Event triggers in Foundry.
- **Document storage moves to S3.** Foundry holds ontology + metadata; S3 holds the actual file content. Documents reference S3 URIs.
- **Form-aware extraction is added.** Xactimate, UB-04, HCFA-1500 — real form-extraction stack (Textract + custom parsers) added between document ingest and specialist read.
- **Per-customer Foundry tenants (or row-level security).** Each customer's data is isolated.
- **Production observability: Datadog/Honeycomb for Railway, Foundry-native for the ontology side.**

### §6.4 What does NOT change

- The three-layer architecture (Vercel UI / Railway Python / Foundry data) holds
- The OSDK contract holds
- The specialist topology holds (more specialists added, but same pattern)
- The four-layer truth model holds (more golden cases, more rubrics, but same wiring)

The demo architecture is the production architecture, just smaller.

---

## §7 — Architectural decisions (cross-reference)

For per-component first-principles decisions, see [TECH_PLAN.md §2](./TECH_PLAN.md). The headlines:

- USE Foundry: Ontology, Action Types, Code Repositories (sparingly), AIP Evals, OSDK
- SKIP Foundry: AIP Logic, AIP Chatbot Studio, Workshop
- USE external: Railway (Python backend), Vercel (Next.js frontend), Anthropic SDK direct, OpenAI for Layer D, Pydantic, hypothesis

---

## §8 — Open architectural questions (defer to Weekend 1)

1. **OSDK TypeScript maturity for Next.js Server Components.** Validate during Weekend 1 scaffold.
2. **Foundry Developer Tier capacity quotas.** Documented after signup.
3. **Vercel ↔ Railway latency.** Different regions could add 100-200ms per round trip. Acceptable but worth measuring.
4. **Foundry function cold-start time.** First call may have noticeable warmup; cache the warmup.
5. **Action Type validator expressiveness.** Can TypeScript validators fully express the illegal-combination matrix, or do they call out to Code Repositories Functions for complex checks? Resolve Weekend 1.

---

*Updates land when Weekend 1 surfaces what the spec missed.*
