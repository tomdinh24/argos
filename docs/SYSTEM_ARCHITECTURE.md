---
tags:
  - project/argos
  - type/architecture
  - status/draft
created: 2026-05-28
updated: 2026-05-28
aliases:
  - System Architecture
---

# System Architecture — Claims Operations Intelligence Layer (Argos)

> Infrastructure, request flow, deployment topology, security model, failure modes, and scaling story for the build defined by [TECH_PLAN.md](./TECH_PLAN.md). Companion to [AGENT_ARCHITECTURE.md](./AGENT_ARCHITECTURE.md).

---

## §1 — Purpose

This document answers:

1. **Where does each piece run?** (Deployment topology)
2. **How does data flow through the system?** (Request flow diagrams)
3. **What's the security and auth model?** (Auth at each boundary)
4. **What happens when something breaks?** (Failure modes)
5. **How does this scale to production?** (Scaling story)

This is the architecture an interviewer asks to see on a whiteboard. It's also what a triangulation review evaluates before we commit.

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
| Typed semantic data | Foundry Ontology | Unique-to-Foundry primitive; FDE interview centerpiece |
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
   │ Returns: Claim + linked ClaimExposures + ClaimPartyRoles
   ▼
Next.js Server Component
   │ Renders shell with claim metadata
   ▼
Client-side fetch (parallel):
   ├─ Financial snapshot ──▶ OSDK ──▶ Foundry Function:
   │                                  get_financials_as_of(exposure_id, NOW, NOW)
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
   │ Body: { exposure_id, as_of }
   ▼
Specialist runner (Python):
   │
   ├─ Read Layer B via OSDK:
   │    ├─ get_exposure_layer_b_snapshot(exposure_id, as_of)
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
   │      exposure_id,
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
| User → Vercel | NextAuth: passkey or email magic link | Allowlist of emails (yours + a few recruiter accounts); no public open access |
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

All of these are appropriate for a portfolio demo. Production deployment would add them.

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
- For interview day: rehearse with the actual stack 30 min before; if anything is flaky, switch to Loom

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
