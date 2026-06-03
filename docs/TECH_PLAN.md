---
tags:
  - project/argos
  - type/tech-plan
  - status/draft
created: 2026-05-28
updated: 2026-05-28
aliases:
  - Tech Plan
---

# Tech Plan — Claims Operations Intelligence Layer (Argos)

> The architecture picks the right tool per layer: Foundry holds the typed semantic data layer + eval framework (where it uniquely shines); a Python backend on Railway holds the specialists + synthesis (where prompt control and iteration matter); a Next.js frontend on Vercel holds the workspace (where externally-shareable UI matters). Companion to [THESIS.md](./THESIS.md), [STRATEGY.md](./STRATEGY.md), [data-layer.md](./data-layer.md).

---

## §1 — Purpose

This document defines:

1. **The architecture decisions** — for each Foundry/AIP component, the first-principles call on use-or-replace, with the reasoning recorded.
2. **The tech stack** — what we use at each layer and why.
3. **The three-layer architecture** — Foundry / Railway Python / Vercel Next.js, with the contract between each layer.
4. **The build sequence** — four weekends with acceptance gates.
5. **The eval harness** — AIP Evals + our orchestration, wiring data-layer.md §7.

What this doc is *not*:
- It does **not** redefine the ontology (see [data-layer.md](./data-layer.md) §5).
- It does **not** redefine the synthesis pipeline (see data-layer.md §4).
- It does **not** redefine ground truth (see data-layer.md §7).

---

## §2 — Architecture decisions and tradeoffs

The driving principle: **evaluate each Foundry/AIP component on its own merits, not as a package.** Use Foundry where it uniquely shines, build elsewhere where control and iteration matter more.

### §2.1 The per-component decision matrix

| Component | What it gives us | Cost of using it | Decision | Why |
|---|---|---|---|---|
| **Foundry Ontology** | Typed semantic graph; ontology imports in Functions; the unique-to-Foundry primitive | Data model locks to Foundry; ontology authoring goes through Ontology Manager UI | **USE** | This is the one capability nothing else gives us out of the box. The semantic graph + validation + audit + branching all attached to the *type* itself is the Palantir thesis. Replacing it with Postgres + Pydantic loses the unique capability. |
| **Foundry Action Types** | The only mutation surface; TypeScript validation logic; built-in audit + permissions | All mutations go through Action Types — can't bypass | **USE** | The illegal-combination matrix from data-layer.md §5 and the financial-posting rules become Action Type validators. Invariants live at the data layer, not scattered across Python. The audit trail is automatic. |
| **Foundry Datasets** | Raw storage under the ontology | None at our scale | **USE** | Comes free with Ontology. |
| **Code Repositories (Functions)** | Git-backed Python/TS serverless runtime; ontology imports with autocomplete; built-in deployment | Foundry-hosted git is less flexible than GitHub + local IDE; iteration is slower | **USE SPARINGLY** | Only for Functions that need direct ontology access — primarily `get_financials_as_of` and a few read helpers. Bulk Python (specialists, synthesis, eval orchestration) lives in our own GitHub repo on Railway. Faster iteration, full toolchain control. |
| **AIP Logic** | Visual LLM workflow builder; built-in monitoring; callable from elsewhere in Foundry | UI-bound prompt authoring; constrained orchestration shape; less control than raw Python | **SKIP** | Our specialists are complex multi-step orchestration with precise prompt requirements. AIP Logic is great for simple "extract these fields from this text" tasks; ours are not those. We get monitoring via our own logging + AIP Evals integration. |
| **AIP Chatbot Studio** | Multi-turn conversational agent builder | Adds chat surface we don't need | **SKIP** | The workspace is a structured UI, not a chat interface. |
| **AIP Evals** | Eval framework with custom golden sets, rubrics, evaluators; built-in dashboards | Eval-specific, low lock-in cost | **USE** | Real win for the four-layer truth model. Custom Functions as evaluators map directly to Layer C-statutory / C-policy / D. The dashboard becomes a primary review surface. |
| **Workshop** | No-code dashboard builder over the Ontology | UI-bound; not externally shareable without Foundry auth | **SKIP** | Demo must be shareable via a public URL. Workshop can't do that. Building Next.js. |
| **OSDK (Ontology SDK)** | Generated typed SDK for external Python or TypeScript | None — required for any external integration | **USE** | The bridge that makes Foundry-backend + external-Python + external-Next.js work. |

### §2.2 Why the external Python backend (Railway) instead of Code Repositories

For the specialists, synthesis pipeline, and eval orchestration: we ship to Railway, not to Code Repositories.

**The control argument.** Specialists need precise prompt iteration. Iteration loop on Railway = edit file in Cursor → push to GitHub → Railway auto-deploys → curl the endpoint. Iteration loop in Code Repositories = open Foundry's web IDE → edit → save → wait for redeploy. The first loop is 10-30 seconds; the second is 1-3 minutes. Over 4 weekends of specialist tuning, this compounds.

**The toolchain argument.** Our Python stack uses pytest, hypothesis (for property tests on the ledger invariants — except now those invariants live in Action Type validators, see §5), pydantic, the Anthropic SDK, and our own logging library. All of this works natively on Railway. Code Repositories supports the major libraries but the dev experience is browser-based, not local.

**The portability argument.** A Python codebase on GitHub + Railway is portable to any cloud. Code Repositories Python is Foundry-shaped (uses `transforms`, ontology imports, Foundry's job runner). If we ever leave Foundry, the GitHub code transfers; Code Repositories code requires translation.

**The cost of this choice.** We give up the autocomplete on ontology imports in Code Repositories (we use the OSDK-generated client instead, which has similar typing). We give up the automatic deployment-to-Foundry-cluster (Railway handles deployment for us). We accept that ontology-touching Functions still live in Code Repositories (because they need direct ontology access).

### §2.3 Why Next.js on Vercel instead of Workshop

**The demo-shareability argument.** A Workshop module is gated behind Foundry auth — external viewers can't click a link. A Vercel-deployed Next.js URL is public, single-click, works on a phone, screenshots cleanly.

**The control argument.** Custom UI requirements (the audit drawer with full citation chains, the matched-pair config sensitivity view, the eval truth-layer attribution table) are easier in custom React than Workshop's drag-and-drop. Workshop is great for internal operational dashboards; ours is a custom workspace with specific narrative beats.

**The cost.** We give up Workshop's automatic ontology-data binding — the Next.js app calls OSDK explicitly. We give up Workshop's permission model — we add our own (NextAuth or pass-through Foundry token for the demo).

### §2.4 Why we skip AIP Logic but USE AIP Evals

These look like adjacent capabilities but they're not.

**AIP Logic** is workflow composition. Its surface is the *flow* — the sequence of blocks, the prompts, the typed inputs/outputs. Our specialist flows need fine-grained control (multi-turn extraction across documents, conditional branching on liability status, dynamic config-driven prompt construction). Encoding that as visual blocks fights the tool.

**AIP Evals** is measurement. Its surface is the *result* — golden sets, evaluator functions, scores, dashboards. Our four-layer truth model maps cleanly: golden cases are Foundry datasets, Layer-C-statutory / C-policy / D evaluators are Functions, the rubric is built-in, the dashboard is built-in. Measurement is bounded; orchestration is not. AIP Evals being constrained doesn't hurt us; AIP Logic being constrained would.

### §2.5 What this leaves us locked into

Honest accounting of Foundry lock-in:

| If we ever leave Foundry... | Migration cost |
|---|---|
| Re-implement Ontology in Postgres + Pydantic + custom audit | ~1 week |
| Re-implement Action Type validators as application-layer validators | ~3 days |
| Re-implement `get_financials_as_of` and other Functions in pure Python | ~1 day (we'd already have the Anthropic SDK call shape from Railway code) |
| Re-implement AIP Evals dashboard | ~2-3 days (existing OSS eval frameworks: Promptfoo, Inspect, Weights & Biases) |
| Migrate ontology data | Standard Parquet/CSV export → Postgres COPY |

Total migration cost: ~2 weeks. Manageable. We're not betting the company on Foundry; we're picking the best tool for the build.

---

## §3 — Tech stack

| Layer | Choice | Rationale |
|---|---|---|
| **Data + semantic layer** | Foundry Ontology + Action Types | Unique typed-semantic-graph capability. Built-in audit/permissions/branching. |
| **Ontology-touching compute** | Foundry Code Repositories (Python) | Functions that need direct ontology access. Limited to ~3-5 functions. |
| **Eval framework** | Foundry AIP Evals | Custom golden sets + custom evaluator Functions + rubric + dashboard. Maps to four-layer truth model. |
| **Specialist orchestration** | Python on Railway (FastAPI) | Full prompt control, fast iteration loop, local dev experience, portable. Calls Foundry via OSDK. |
| **Synthesis pipeline** | Python on Railway (the same FastAPI service or a parallel worker) | Same control/iteration argument. ~10K LLM calls per pipeline run; needs robust retry/caching. |
| **Frontend** | Next.js on Vercel | Externally shareable, custom UI, modern React stack. Calls Foundry via OSDK TypeScript client; calls Python backend via REST. |
| **Language (backend)** | Python 3.11+ | Native for Anthropic SDK, Pydantic, the hypothesis property tests on our local logic |
| **Language (frontend)** | TypeScript | Native for OSDK TypeScript client, Next.js, type safety end-to-end |
| **LLM provider — primary** | Anthropic SDK (Claude Sonnet 4.6) | Strong structured-output adherence on multi-field schemas; ecosystem familiarity |
| **LLM provider — Layer D judge** | OpenAI (GPT) | Cross-model independence for judgment-layer eval per data-layer.md §7 |
| **Synthesis model** | Claude Haiku 4.5 | Cheap, fast, sufficient for document generation |
| **Schema validation (Python)** | Pydantic v2 | Runtime validation; generates JSON schemas for LLM structured output; mirrors OSDK-generated types |
| **Testing (Python)** | pytest + hypothesis | Standard test runner; property-based tests for synthesis pipeline invariants |
| **Auth (demo)** | Foundry personal access token in env var for OSDK; NextAuth for the Next.js public-demo surface | Production would use Foundry's hosted auth flow |

**Considered and rejected:** DuckDB as substrate (Foundry Ontology gives us typed semantic graph + audit + branching that Postgres + Pydantic can't match cleanly); hand-rolled state machine library (Action Type validators put invariants at the data layer where they belong); Streamlit (not externally shareable); hand-rolled eval harness (AIP Evals gives us rubric + dashboard for free); LangChain / LangGraph / CrewAI (hide the prompt and orchestration decisions that are the architectural value).

---

## §4 — Three-layer architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│  FRONTEND — Next.js on Vercel                                        │
│  ─ Workspace UI: claim list, claim detail, review queue,             │
│    audit drawer, eval tab                                            │
│  ─ TypeScript end-to-end                                             │
│  ─ Calls Foundry via OSDK TypeScript client (read ontology,           │
│    trigger Action Types)                                             │
│  ─ Calls Python backend via REST (run specialist, run eval)          │
└──────────────────────────────────────────────────────────────────────┘
         ▲                                              ▲
         │ OSDK (HTTPS + Foundry token)                 │ REST (HTTPS)
         │ object queries, action type triggers         │ invoke specialist,
         ▼                                              │ run eval
┌──────────────────────────────────────────┐            │
│  BACKEND-A — Foundry Developer Tier      │            │
│  (hosted, free)                          │            │
│  ─ Ontology (object types, link types)   │            │
│  ─ Action Types (TypeScript validators   │            │
│    encoding illegal-combination matrix   │            │
│    + financial-posting rules)            │            │
│  ─ Code Repositories Functions           │            │
│    (ontology-touching compute only:      │            │
│     get_financials_as_of,                │            │
│     compute_aggregate_limits, etc.)      │            │
│  ─ AIP Evals (golden sets + rubrics +    │            │
│    truth-layer evaluator Functions)      │            │
└──────────────────────────────────────────┘            │
         ▲                                              │
         │ OSDK (HTTPS + Foundry token)                 │
         │ Python backend reads/writes ontology         │
         ▼                                              │
┌──────────────────────────────────────────────────────────────────────┐
│  BACKEND-B — Python on Railway (FastAPI)                             │
│  ─ Specialist runners (Reserve, Recovery, Closure)                   │
│     ─ Anthropic SDK direct                                           │
│     ─ Read ontology + financial snapshot via OSDK                    │
│     ─ Emit recommendations as Action Type invocations                │
│  ─ Synthesis pipeline (3-pass document generation)                   │
│  ─ Eval orchestration (publishes results to AIP Evals)               │
│  ─ Audit logging (every specialist call → structured log)            │
└──────────────────────────────────────────────────────────────────────┘
```

### §4.1 Contract between layers

**Frontend ↔ Foundry.** Read-only path uses OSDK queries: "list all claims for client program X," "get exposure detail with financial snapshot," "get audit trail for claim Y." Mutation path triggers Action Types: "approve recommendation N," "reject recommendation N with reason," "request authority escalation."

**Frontend ↔ Python backend.** REST endpoints: `POST /specialist/{name}/run` (triggers a specialist), `POST /eval/run` (runs eval suite), `GET /eval/latest` (latest eval report). FastAPI auto-generates OpenAPI spec; Next.js consumes the spec for typed clients.

**Python backend ↔ Foundry.** Python uses OSDK to read ontology (claim, exposure, documents, config) and to trigger Action Types (write recommendations as AgentAction records via Action Type, write reserve revisions, etc.). Authentication via Foundry personal access token in Railway env vars.

**Foundry-internal.** AIP Evals reads from Foundry datasets (golden cases) + calls Code Repositories Functions (evaluators). Action Types write Audit Records (Foundry-native).

---

## §5 — Foundry side: Ontology + Action Types + Functions + AIP Evals

### §5.1 Ontology

All in-scope entities from data-layer.md §5 become Foundry object types:

- `ClientProgram`, `Policy`, `PolicyPeriod`, `PolicyCoverage`, `CoverageLayer`, `RiskUnit`
- `LossOccurrence`, `Claim`, `CoverageRequest`
- `Party`, `ClaimPartyRole`
- `LiabilityAssessment`
- `FinancialTransaction`, `FinancialPosting`
- `Recovery`
- `Document`, `DocumentAssociation`, `DocumentExtraction`
- `Event`
- `DiaryTask`, `AuthorityRequest`, `AuthorityDecision`, `NoticeObligation`
- `Lien`, `MedicareReportingStatus` (shape-only)
- `SpecialistConfig`
- `AgentAction` (the audit-trail object type)

Link types model the relationships from §5: `Claim → CoverageRequest (1:many)`, `CoverageRequest → FinancialPosting (via FinancialTransaction, many:many)`, `Document → DocumentAssociation → CoverageRequest (many:many cross-exposure linkage)`, etc.

`AggregateLimitsTracker` is implemented as a *derived view* in Foundry — a query computed from `FinancialPosting` rows across child exposures, exposed as a typed read endpoint.

Ontology is authored in Foundry Ontology Manager (browser UI with branching, save-changes review, version history).

### §5.2 Action Types

Action Types are the only mutation surface. Each Action Type has TypeScript validation logic. The illegal-combination matrix and financial-posting rules from data-layer.md §5 are encoded here.

Action Types built:

| Action Type | What it does | Validation |
|---|---|---|
| `RecordFinancialTransaction` | Create a `FinancialTransaction` with N balanced `FinancialPosting` rows | Posting rules per `transaction_kind` enforced (e.g., `indemnity_payment` requires balanced `paid_indemnity +X` + `outstanding_indemnity -X`) |
| `UpdateExposureStatus` | Change one or more of the seven status dimensions on a `CoverageRequest` | Illegal-combination matrix enforced; per-dimension transition guards enforced |
| `RecordLiabilityAssessment` | Append a new `LiabilityAssessment` row | Supersession chain validated; fault percentages sum to 100 |
| `EmitAgentAction` | Specialist emits a recommendation | Required fields present; input hash recorded; confidence in [0,1] |
| `ApproveAgentAction` | Human approves a queued recommendation | Authority chain validated; routes to `RecordFinancialTransaction` or `UpdateExposureStatus` as effect |
| `RejectAgentAction` | Human rejects a queued recommendation with reason | Reason enum validated |
| `RequestAuthority` | Specialist requests escalation | `parent_request_id` chain; max-level validation |
| `RecordAuthorityDecision` | Authority approver responds | Status transition validated |
| `RegisterDocument` | New document ingested | Type validation; required associations |
| `RecordDocumentExtraction` | Specialist records its read of a document | Confidence-per-field shape validated |
| `CloseExposure` | Attempt to close one exposure | Closure checklist enforced (no outstanding reserves, no open recovery, no pending litigation, etc.) |
| `CloseClaim` | Attempt to close the parent claim | All child exposures closed |

Each Action Type's TypeScript validator is checked into the Code Repositories repo for the ontology. The validators ARE the state machine — they live in Foundry where the data does, not in scattered Python.

### §5.3 Code Repositories Functions

Limited to compute that needs direct ontology access. Python.

| Function | What it does |
|---|---|
| `get_financials_as_of(request_id, valid_at, recorded_at)` | The bitemporal query — returns paid/outstanding/incurred/recovered per component at the specified time-axis pair. Window-function SQL over `FinancialPosting`. |
| `get_aggregate_limits(claim_id, coverage_id)` | Computes `consumed/remaining/breach_status` from child exposures' postings |
| `get_exposure_layer_b_snapshot(request_id, as_of)` | Returns the full Layer-B view (documents received ≤ as_of, ledger ≤ as_of, parties, status dimensions, applicable config) — the specialist's input payload |
| `get_applicable_config(client_program_id, specialist, as_of)` | Returns the `SpecialistConfig` row in force at `as_of` |
| `get_audit_trail(claim_id)` | Returns the chronological `AgentAction` history for a claim |

Five Functions, all read-only from the ontology. Specialist orchestration (the LLM calls) does NOT live here — it lives on Railway.

### §5.4 AIP Evals

AIP Evals suite per specialist (Reserve / Recovery / Closure). For each:

- **Test cases dataset**: ~50 golden cases as a Foundry dataset, with Layer-A facts in hidden columns
- **Target function**: the specialist invocation (via Railway REST, or a thin Foundry Function wrapper that calls Railway)
- **Evaluator functions** (in Code Repositories):
  - `eval_layer_c_statutory_<specialist>` — deterministic check against sourced legal rules
  - `eval_layer_c_policy_<specialist>` — deterministic check against client config
  - `eval_layer_d_judgment_<specialist>` — calls the rubric grader with cross-model judge
  - `eval_time_to_recognition` — for the incremental replay harness
- **Rubric**: defined per evaluator, with anchor examples per score

AIP Evals built-in dashboard renders the results. The Next.js workspace embeds the dashboard URL or reads results via OSDK and renders custom views.

---

## §6 — Python backend on Railway

### §6.1 Project shape

```
backend/
  app/
    main.py               # FastAPI app
    config.py             # env vars: FOUNDRY_TOKEN, ANTHROPIC_API_KEY, OPENAI_API_KEY
    osdk_client.py        # OSDK wrapper, cached client instance
    specialists/
      reserve/
        __init__.py
        prompt.py         # SYSTEM_PROMPT, USER_TEMPLATE, OUTPUT_SCHEMA
        runner.py         # the orchestration: read Layer B via OSDK, call LLM, emit Action Type
      recovery/
      closure/
    synthesis/
      portfolio.py        # generate the 4 client portfolios
      sampler.py          # sample loss events from FARS/CRSS/NFIP via OSDK
      pipeline.py         # the 3-pass document generation
      fuzzer.py           # Python programmatic fuzzing pass
    eval/
      orchestrator.py     # invokes AIP Evals; reads results
      replay.py           # time-to-recognition incremental replay
      matched_pair.py     # config sensitivity test
    routes/
      specialist.py       # POST /specialist/{name}/run
      eval.py             # POST /eval/run, GET /eval/latest
      synthesis.py        # POST /synthesis/run (one-shot, generates the demo book)
  tests/
    test_specialists.py
    test_synthesis.py
    test_property_invariants.py  # hypothesis tests
  pyproject.toml
  Dockerfile
  railway.toml
```

### §6.2 Specialist runner shape

Each specialist follows the same pattern:

```python
async def run_reserve_specialist(request_id: str, as_of: datetime) -> ReserveRecommendation:
    # 1. Read Layer B from Foundry via OSDK
    layer_b = await osdk.functions.get_exposure_layer_b_snapshot(request_id, as_of)
    config = await osdk.functions.get_applicable_config(layer_b.client_program_id, 'reserve', as_of)

    # 2. Build prompt
    user_message = USER_TEMPLATE.render(layer_b=layer_b, config=config)

    # 3. Call Anthropic SDK with structured output
    response = await anthropic.messages.create(
        model='claude-sonnet-4-6',
        system=SYSTEM_PROMPT,  # cached
        messages=[{'role': 'user', 'content': user_message}],
        response_format={'type': 'json_schema', 'json_schema': RESERVE_OUTPUT_SCHEMA},
    )
    recommendation = ReserveRecommendation.model_validate_json(response.content)

    # 4. Emit AgentAction via Action Type (Foundry handles audit)
    await osdk.actions.emit_agent_action(
        specialist='reserve',
        request_id=request_id,
        recommendation=recommendation,
        input_hash=hash_layer_b(layer_b),
        confidence=recommendation.confidence,
        requires_human_approval=recommendation.requires_human_approval(config),
    )

    # 5. If auto-applicable, trigger the downstream Action Type
    if recommendation.auto_applicable(config):
        await osdk.actions.record_financial_transaction(
            request_id=request_id,
            transaction_kind='reserve_revision',
            postings=recommendation.to_postings(),
        )

    return recommendation
```

This pattern: read via OSDK, call LLM with full prompt control, emit Action Type. Foundry handles the audit. We handle the orchestration.

### §6.3 Synthesis pipeline

Same 3-pass approach from data-layer.md §4.6:
1. LLM seed-fact generation (Haiku)
2. LLM noise injection (Haiku, different prompt)
3. Python programmatic fuzzing

Outputs (Document rows + their content) are written to Foundry via `RegisterDocument` Action Types. The Document content (the actual PDF/text) is uploaded to Foundry Datasets via the OSDK upload API.

Idempotency per `(claim_id, document_type, pass_number)` — successful generations cached locally and not regenerated unless prompt template version changes.

### §6.4 Eval orchestration

Orchestrator invokes AIP Evals via the Foundry API:
- Reads the golden-set dataset
- Triggers the AIP Evals suite run (which calls our Railway specialist endpoints via the target-function wrapper)
- Polls for completion
- Reads the result dataset
- Posts a summary to the Next.js workspace's `/eval/latest` endpoint

Time-to-recognition replay and matched-pair tests are Python loops on Railway (not in AIP Evals); they call the specialist endpoints incrementally and write their own result datasets to Foundry.

### §6.5 Deployment

Railway: one service for FastAPI app, one worker for batch synthesis runs. Environment variables hold the Foundry personal access token, Anthropic API key, OpenAI API key. Auto-deploy on push to main. Health check on `/healthz`.

---

## §7 — Next.js frontend on Vercel

### §7.1 Project shape

```
frontend/
  app/
    layout.tsx
    page.tsx                       # claim list
    claims/[claimId]/page.tsx       # claim detail
    queue/page.tsx                  # review queue
    audit/[claimId]/page.tsx        # audit drawer view
    eval/page.tsx                   # latest eval report
  components/
    ClaimList.tsx
    ExposurePanel.tsx
    FinancialSnapshot.tsx
    RecommendationCard.tsx
    AuditDrawer.tsx
    EvidenceCitation.tsx
  lib/
    osdk.ts                         # OSDK TypeScript client (generated)
    api.ts                          # REST client for Python backend
    auth.ts                         # NextAuth config
  package.json
  vercel.json
```

### §7.2 Views

| View | Purpose | Data sources |
|---|---|---|
| **Claim list** | Filterable list with status dimensions, current incurred, days since FNOL | OSDK ontology query |
| **Claim detail** | One claim, all exposures, ledger snapshot, documents, status panel, recommendations, audit trail | OSDK queries + `get_financials_as_of` Function |
| **Review queue** | Pending `AgentAction` rows; accept/edit/reject controls | OSDK query + Action Type triggers for approval |
| **Audit drawer** | Chronological `AgentAction` for one claim | OSDK `get_audit_trail` Function |
| **Eval tab** | Latest eval report with truth-layer attribution | REST `GET /eval/latest` on Python backend; or embedded AIP Evals dashboard iframe |

### §7.3 Auth

For the demo: NextAuth with passkey or email-magic-link, behind a hardcoded allowlist (your email + a few demo accounts). Backend calls to Foundry use a service-account personal access token in Vercel env vars.

Production would shift to Foundry's hosted OAuth, but that's deferred.

### §7.4 Evidence citation surface

Every specialist recommendation in the Next.js UI links to the documents it cited. Citation comes from `AgentAction.output.cited_documents` (an array of document_ids). The frontend renders these as expandable cards with the document content fetched via OSDK.

### §7.5 Demo claims

Three pre-seeded demo claims targeting specific narrative beats:
1. Multi-vehicle FARS fatality with 3 BI exposures across 2 claims — exercises shared `LossOccurrence`, per-exposure reserves, aggregate limits tracker
2. Coastal WYO flood claim with building + contents + ICC — exercises cross-LOB ontology reuse
3. Coverage-disputed file with reservation-of-rights — exercises the coverage-status / handling-status disambiguation

---

## §8 — Build sequence

### Weekend 1 — Foundry foundation + scaffolds

**Goals:** Foundry Developer Tier set up, ontology authored, first Action Types and Functions deployed, Railway + Vercel scaffolds running and talking to Foundry.

- Sign up Foundry Developer Tier; document the actual capacity quotas (this answers an open question)
- Author ontology in Ontology Manager: all object types + link types from data-layer.md §5
- Implement Action Types: `RecordFinancialTransaction`, `UpdateExposureStatus`, `RegisterDocument`, `EmitAgentAction` (the four minimum to support the rest of the build). TypeScript validators encode the illegal-combination matrix and posting rules.
- Implement first Code Repositories Function: `get_financials_as_of`. Validate by writing test transactions and querying historical states.
- Scaffold Railway FastAPI app with `/healthz` and one stub endpoint
- Scaffold Vercel Next.js app with one page that queries the OSDK and lists object types
- Set up OSDK clients (Python on Railway, TypeScript on Vercel) with personal access tokens
- Seed the 4 client programs (Northwind, Sentinel, RoadMile, Coastal WYO) + Pinnacle Captive schema-only

**Acceptance gate:** Three-layer architecture is live. Vercel page reads Foundry ontology data via OSDK; Railway service triggers an Action Type via OSDK; Action Type validation rejects an intentionally illegal state change. Foundry quotas documented.

### Weekend 2 — Synthesis + first specialist

**Goals:** Generate ~100 synthetic claims, wire up Reserve specialist end-to-end.

- Implement §0.5 yield validation against FARS/CRSS/NFIP filters before locking portfolios; document numbers
- Implement remaining ontology-touching Functions: `get_exposure_layer_b_snapshot`, `get_applicable_config`, `get_aggregate_limits`, `get_audit_trail`
- Implement remaining Action Types: `RecordLiabilityAssessment`, `ApproveAgentAction`, `RejectAgentAction`, `RequestAuthority`, `RecordAuthorityDecision`, `RecordDocumentExtraction`, `CloseExposure`, `CloseClaim`
- Implement synthesis pipeline (3-pass: LLM seed + LLM noise + Python fuzzing). Generate 100 synthetic claims via Railway worker. Register Documents + DocumentExtractions via Action Types.
- Implement Reserve specialist on Railway: prompt, runner, output schema, REST endpoint
- Implement Reserve AIP Evals suite: golden set as Foundry dataset (20 golden cases for now), Layer-C-statutory + C-policy evaluator Functions in Code Repositories
- Wire Reserve specialist into Next.js claim detail page: trigger via REST button, display recommendation, show "approve / reject" controls that call Action Types

**Acceptance gate:** Reserve specialist runs end-to-end on 100 synthetic claims. AgentAction trail populated in Foundry. AIP Evals dashboard shows Layer C metrics. Next.js workspace shows recommendations with approve/reject working.

### Weekend 3 — Recovery + Closure + scale up

**Goals:** All three specialists running, full ~500-claim synthetic book, AIP Evals dashboards complete.

- Implement Recovery specialist (prompt, runner, output schema, sourced-rule SOL handling)
- Implement Closure specialist (prompt, runner, output schema, closure checklist execution)
- Scale synthesis to full ~500 claims via Railway worker (with cost budget per data-layer.md §9: ~$700-1100, ~2-3 hours compute)
- Implement Layer-D evaluator Functions with cross-model judge (OpenAI judges Claude-generated cases)
- Build the time-to-recognition replay harness (50 golden × 8 arrival points × 3 specialists) on Railway
- Build the matched-pair config sensitivity test on Railway
- Secure human-reviewed Layer-D golden labels using §12.1 substitute corpora

**Acceptance gate:** All three specialists run end-to-end on the full ~500 claims; AIP Evals dashboards populated with Layer C-statutory, C-policy, D, time-to-recognition, and matched-pair metrics; truth-layer attribution clean.

### Weekend 4 — Workspace polish + demo + walkthrough

**Goals:** Demo-ready system, Loom walkthrough.

- Polish Next.js views: claim list, claim detail, review queue, audit drawer, eval tab
- Demo walkthrough script seeding the three specific demo claims
- README with problem statement, architecture diagram, how-to-run-locally, eval baseline numbers
- 5-minute Loom walkthrough showing both the Vercel public demo URL and the Foundry side (Ontology Manager, Action Type validators, AIP Evals dashboard)

**Acceptance gate:** Shareable Vercel URL (viewer clicks → workspace works); Foundry side polished enough for a screenshare deep-dive; README and Loom recorded.

---

## §9 — Audit trail

Audit comes from two places:

1. **Foundry-native Action Type invocation log.** Every Action Type call is automatically logged by Foundry with who/what/when/inputs/outputs. This is the system-of-record audit. We don't build it; we use it.
2. **The `AgentAction` object type.** Every specialist recommendation creates an `AgentAction` row via the `EmitAgentAction` Action Type. The object holds: specialist, prompt_version, model_id, request_id, input_hash, output_json, confidence, reasoning_trace, triggered_by, requires_human_approval, applied_at, escalation_outcome, created_at.

The combination answers "why did we set the reserve at $X on claim Y on date Z" three months later. Foundry's audit log shows *what* was invoked; the `AgentAction` row shows *what the specialist reasoned and proposed*.

---

## §11 — Cut criteria

If behind schedule, drop in this order:

1. **Drop Coastal WYO synthesis.** The four-archetype demo holds without the flood branch. Auto-only book.
2. **Drop matched-pair config sensitivity test.** High-value but specialist still works without it.
3. **Drop time-to-recognition replay harness.** Keep end-state eval only.
4. **Drop AIP Evals integration; ship a custom in-repo eval dashboard in Next.js.** Risk if AIP Evals turns out to be harder to wire than expected. Custom dashboard is more work but bounded.
5. **Drop the Next.js workspace; ship Streamlit fallback.** Last resort. External viewer still sees a clickable demo, but the polish is lower. Vercel still hosts something.
6. **Drop the Recovery specialist; demo only Reserve + Closure.** Final cut. STRATEGY §6 is the framing that survives.

**Do not cut:** Foundry Ontology, Action Type validators (the illegal-combination matrix), the OSDK integration, the AgentAction audit trail. These are the structural anchor surfaces.

---

## §12 — Risks and mitigations

| Risk | Mitigation |
|---|---|
| Foundry Developer Tier capacity caps block synthesis at scale | Weekend 1 acceptance gate documents actual quotas. If too tight, scale book to ~200 claims and accept the lower n. |
| Foundry learning curve eats Weekend 1 | Block out Weekend 1 entirely for Foundry foundation; don't promise specialist work in WK1 |
| OSDK TypeScript client maturity unclear | Validate with the Weekend 1 Vercel scaffold; fall back to direct Foundry REST API if OSDK TS has gaps |
| Action Type TypeScript validators hit Foundry-specific edge cases | Mirror the validation logic as a Python pre-check in the Railway backend; specialist calls the Python validator before triggering the Action Type, so we get defense-in-depth |
| Synthesis cost exceeds budget | Cost is metered after Weekend 2's 100-claim subset run. If 5× over estimate, cut to ~300 claims |
| FARS/CRSS yield insufficient for trucking portfolio | Weekend 2 yield validation gate. Broaden portfolio if needed |
| Demo dependency on Foundry uptime during a live walkthrough | Pre-recorded Loom is mandatory fallback. Vercel demo works even if Foundry is down (with cached data) |
| "Why aren't you using AIP Logic / Workshop" question | Prepared answer (§2.4): per-component first-principles eval; AIP Logic constrains specialist orchestration; Workshop isn't externally shareable; AIP Evals IS used and is the right call there |
| Vercel + Railway + Foundry = three vendors. Operational complexity for a demo. | Acceptable. The three-vendor split is the architecture — it's the demonstration that we can integrate Foundry with arbitrary cloud infra |

---

## §13 — Open questions deferred to build

- **Foundry Developer Tier quotas in practice.** Resolved at Weekend 1 acceptance gate.
- **OSDK TypeScript client gaps.** Resolved at Weekend 1 acceptance gate via scaffolding spike.
- **Action Type validator expressiveness.** Can TypeScript validators express the full illegal-combination matrix cleanly, or do we need Code Repositories Function callouts? Resolved Weekend 1.
- **AIP Evals target-function wrapper for Railway endpoints.** Does AIP Evals call out to external HTTPS endpoints cleanly, or do we wrap in a Foundry Function? Resolved Weekend 2.
- **Document storage for synthetic PDFs/text.** Foundry Datasets vs S3? Lean Foundry Datasets (one less vendor). Revisit if file-size limits are hit.
- **NextAuth vs Foundry-hosted auth on Vercel.** NextAuth for external shareability; Foundry auth in production.

---

## §14 — Validation gates summary

Each weekend ends with a binary gate. If the gate fails, the next weekend starts with closing it before new work.

| Weekend | Gate |
|---|---|
| 1 | Foundry quotas documented; three-layer architecture live (Vercel reads Foundry, Railway writes Foundry); Action Type rejects an illegal state combination |
| 2 | Reserve specialist runs end-to-end on 100 synthetic claims with AIP Evals Layer-C metrics; yield validation passed; cost budget on track |
| 3 | All three specialists run on full ~500 claims; AIP Evals dashboard populated with all truth layers; truth-layer attribution clean |
| 4 | Vercel public URL works; Foundry side polished enough to screenshare; Loom recorded |

---

*This is the tech plan we build against. Updates land only if Weekend 1 surfaces something that materially changes the per-component decisions in §2.*
