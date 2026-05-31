---
tags:
  - project/argos
  - type/architecture
  - status/draft
created: 2026-05-28
updated: 2026-05-28
aliases:
  - Agent Architecture
---

# Agent Architecture — Claims Operations Intelligence Layer (Argos)

> Specialist topology, runtime, prompt structure, tool surfaces, state-machine boundaries, eval wiring, failure modes. Companion to [SYSTEM_ARCHITECTURE.md](./SYSTEM_ARCHITECTURE.md).

---

## §1 — Purpose

This document answers, for the agent layer:

1. **What are the agents?** (Specialist topology)
2. **How does one specialist run?** (Runtime sequence)
3. **What's the deterministic spine that gates them?** (State machine + Action Type validators)
4. **What tools do they have?** (Foundry Functions + Action Types)
5. **How is the prompt structured?** (System prompt + user template + output schema)
6. **How are they evaluated?** (Four-layer truth wiring)
7. **What's the human-in-the-loop boundary?** (Automatic vs human-approved)
8. **How does configuration drive behavior?** (Per-customer config as moat)
9. **What are the failure modes?** (LLM-specific + integration-specific)

---

## §2 — Specialist topology

Six specialists and two supporting services.

```
                  ┌───────────────────────────────────────────┐
                  │  Substrate (Foundry)                       │
                  │  ─ CoverageRequest (7 status dimensions)    │
                  │  ─ LiabilityAssessment chain              │
                  │  ─ FinancialTransaction + FinancialPosting│
                  │  ─ Document + DocumentExtraction          │
                  │  ─ EvidenceCitation                       │
                  │  ─ SpecialistConfig                       │
                  │  ─ AgentAction (audit + citations link)   │
                  └───────────────────────────────────────────┘
                                    ▲
                       reads / writes via Action Types
                                    │
   ┌────────────────────────────────┴────────────────────────────────┐
   │  SPECIALISTS — each emits LegallyBearingClaim outputs (§3)      │
   │                                                                  │
   │   ┌────────┐   ┌──────────┐   ┌──────────┐                      │
   │   │ BRIEF  │   │ COVERAGE │   │ LIABILITY│                      │
   │   └────────┘   └──────────┘   └──────────┘                      │
   │   ┌────────┐   ┌──────────┐   ┌──────────┐                      │
   │   │RESERVE │   │ RECOVERY │   │ CLOSURE  │                      │
   │   └────────┘   └──────────┘   └──────────┘                      │
   ├──────────────────────────────────────────────────────────────────┤
   │  SERVICES — infrastructure used by specialists + cockpit        │
   │                                                                  │
   │   ┌──────────────────┐      ┌──────────────────────┐            │
   │   │ Priority Scorer  │      │ Correspondence svc   │            │
   │   └──────────────────┘      └──────────────────────┘            │
   └──────────────────────────────────────────────────────────────────┘
                                    ▲
                                    │ triggered by
                                    ▼
                    ┌─────────────────────────────┐
                    │  Event Triggers              │
                    │  (Foundry Event Types        │
                    │   + Railway scheduler)        │
                    └─────────────────────────────┘
```

### §2.1 The six specialists

Every specialist output is shaped as a `LegallyBearingClaim` (§3): probability + reasoning + cited evidence. No bare recommendations. No assertion without a source.

| Specialist | Trigger | Output | Auto-apply |
|---|---|---|---|
| **Brief** | Any state change on the claim (doc arrival, ledger change, status change, new AgentAction) | `ClaimBrief { story, since_last_touch_diff, missing_info, pending_communications, specialist_recommendations_summary, citations }` | Always refreshes (it's a view, not a mutation). Citations required for every diff item. |
| **Coverage** | New claim with policy linkage; new endorsement; new evidence touching exclusions | `CoverageReport { evidence[], per_question_probabilities[], outcome_path_probabilities{clean, ROR, denial}, would_shift_distribution, draft_memo, draft_letters{ROR, denial}, citations[] }` | **Never.** Adjuster always clicks. AI surfaces evidence + probability; human owns the decision. |
| **Liability** | Police report arrival; new statement; evidence touching fault analysis | `LiabilityAnalysis { evidence[], per_question_probabilities[], fault_allocation_distribution, would_shift_distribution, draft_assessment, citations[] }` | **Never.** Adjuster always clicks. AI surfaces evidence + distribution; human picks the point. |
| **Reserve** | New evidence affecting reserve adequacy; daily review past `review_cadence_days` | `ReserveAnalysis { per_component[], notice_obligations_triggered, authority_required_level, citations[] }` | Below handler authority → auto-applied. Above → AuthorityRequest. |
| **Recovery** | LossOccurrence created; doc arrival affecting recovery analysis | `RecoveryAnalysis { opportunity_probability, recovery_type, evidence[], sol_status, evidence_preservation_alerts, draft_demand, citations[] }` | Detection / surfacing → auto-applied. Pursuit / referral → always human (legal action). |
| **Closure** | "Ready to close" signal; daily closable-exposure scan; defect-affecting evidence | `ClosureAnalysis { ready_probability, blocking_defects[], rationale, citations[] }` | Advisory + Action Type block → auto-applied. Closure execution itself → always human. |

### §2.2 Supporting services

Not specialists — they don't emit `LegallyBearingClaim` outputs. They power the cockpit and feed specialists.

| Service | Job | Where it runs |
|---|---|---|
| **Priority Scorer** | Rank the queue of open claims by what the adjuster should work next. Candidate features: statutory clocks, diary deadlines, reserve adequacy drift, financial exposure, AgentAction backlog, inactivity risk, negotiation cadence. Output: ordered CoverageRequest IDs with **reason chips** derived from per-claim feature attribution. | Ranking is a learned problem from day one. We hold opinions about which features matter (priors / weight biases) but the actual weights come out of training against eval signal — does the predicted rank correlate with the order adjusters work in, with hindsight of which work order produced the best outcomes? Both the feature set and what counts as "good outcome" are revisable as we learn what adjusters actually optimize for. |
| **Correspondence service** | Route outbound communications by legal weight. Routine recipients (body shop, medical provider, insured, tow, police records) → auto-send. Adversarial recipients (claimant's counsel, opposing counsel, court) → auto-draft, queue for human approval. Track receipt against `DiaryTask` deadlines; auto-fire follow-ups. | Railway FastAPI service. Templated routine messages; LLM-drafted adversarial ones (which themselves go through the `LegallyBearingClaim` contract). |

### §2.3 Why six specialists, not three

The earlier scoping deferred Coverage and Liability on bad-faith-exposure grounds. That was lazy. The legally-bearing decision in each stage is narrow — approving denial language, picking contested fault percentages. Everything upstream of that decision (reading the policy, matching exclusions, drafting the memo, applying the comparative-fault rule, citing evidence) is AI-eligible.

Brief is the missing fourth piece: the one-screen summary the adjuster sees the moment they open a claim, refreshed on every data change. Without it, the adjuster spends ten minutes re-reading the file every time they touch it. With it, the AI has done the reading; the adjuster scans and acts.

The principle: **AI does the reading and the drafting. The human approves the legally-bearing language and the contested decision. Nothing in between is left to the human as work.**

---

## §3 — The legally-bearing output contract

Every specialist output that bears on a legally significant decision must carry, per claim:

1. A **probability** (or distribution over outcome paths)
2. **Per-claim reasoning** explaining how the probability follows from the evidence
3. **Cited evidence** from the substrate — `Document` IDs, `EvidenceCitation` rows pointing at specific document locators, or sourced legal rule IDs. **Minimum one citation per probabilistic claim.**

No bare numbers. No "we recommend X." No assertion without a source.

### §3.1 Why this shape

A recommendation anchors the adjuster psychologically before they've reasoned through the evidence themselves. Probability + evidence forces independent reasoning while front-loading the reading work. It's also the only shape that's **calibratable** — you can measure whether 80%-confident outputs resolve as predicted 80% of the time across the golden set. A recommendation cannot be evaluated that way; you can only ask whether the human agreed, which conflates AI quality with anchoring effect.

The decision and its language stay with the human. The AI's job is surfacing evidence, quantifying uncertainty, and drafting the work product the human approves.

### §3.2 The Pydantic contract

Enforced at the output-schema layer. Outputs missing citations are rejected before they reach Foundry as proposed `AgentAction` rows.

```python
class EvidenceCitation(BaseModel):
    document_id: str | None = None      # FK → Document
    sourced_rule_id: str | None = None  # FK → SpecialistConfig.sourced_legal_rules
    ledger_entry_id: str | None = None  # FK → FinancialTransaction
    locator: str                         # page / paragraph / section / field
    text_excerpt: str                    # what the cited source actually says
    relation: Literal["supports", "refutes", "contextual"]

    @model_validator(mode="after")
    def at_least_one_source(self):
        if not any([self.document_id, self.sourced_rule_id, self.ledger_entry_id]):
            raise ValueError("EvidenceCitation must point at a Document, sourced rule, or ledger entry")
        return self


class ProbabilisticClaim(BaseModel):
    claim_text: str
    probability: float = Field(ge=0.0, le=1.0)
    reasoning: str
    evidence_citations: list[EvidenceCitation] = Field(min_length=1)


class OutcomePathDistribution(BaseModel):
    paths: list[ProbabilisticClaim]
    would_shift_distribution: list[str]  # what evidence would move the mass

    @model_validator(mode="after")
    def probabilities_sum_to_one(self):
        total = sum(p.probability for p in self.paths)
        if not (0.99 <= total <= 1.01):
            raise ValueError(f"Outcome path probabilities must sum to 1.0; got {total}")
        return self
```

Every specialist's output schema composes these primitives. The schema is strict (Anthropic validates server-side); Pydantic re-validates client-side as defense-in-depth.

### §3.3 What the cockpit needs to surface

The data the cockpit consumes per legally-bearing output is three-layered: evidence found, probability per underlying question, probability per outcome path — plus drafted work product and the action affordance. **The visual rendering below is an illustrative sketch of how the data could surface — not a finalized UI.** Component layout, control labels, bar styling, and interaction patterns are all open until implementation and review. The contract this section locks in is the *data shape* the cockpit receives, not the chrome it wears.

```
┌─ Layer 1 — Evidence found ─────────────────────────────────────────────┐
│  ✓ Policy in force on loss date              [decs page §A]            │
│  ✓ Coverage grant Part A applies              [policy Part A §III]      │
│  ✓ No intent of harm                          [police rpt ¶3]           │
│  ⚠ Personal use not documentation-backed      [rec stmt ¶7 only]        │
│  ...                                                                    │
└──────────────────────────────────────────────────────────────────────────┘
┌─ Layer 2 — Probability per underlying question ────────────────────────┐
│  Loss falls within policy period         100%   [driven by E1]         │
│  Coverage grant Part A applies            96%   [E2, E5]               │
│  Intentional-acts exclusion applies        3%   [E3]                   │
│  Business-use endorsement excludes         8%   [E4]                   │
└──────────────────────────────────────────────────────────────────────────┘
┌─ Layer 3 — Probability per outcome path ───────────────────────────────┐
│  Coverage applies, clean         ████████████████████░  89%            │
│  Coverage with ROR               ██░░░░░░░░░░░░░░░░░░░   9%            │
│  Denial defensible               ░░░░░░░░░░░░░░░░░░░░░   2%            │
│                                                                         │
│  Would shift the distribution:                                          │
│  • Personal-use documentation → drops ROR toward 0%                    │
│  • Telematics business-trip flag → raises ROR to ~25%                  │
└──────────────────────────────────────────────────────────────────────────┘
┌─ Drafts ready ──────────────────────────────────────────────────────────┐
│  Coverage analysis memo                       [view] [edit] [attach]    │
│  ROR letter (if ROR path chosen)              [view] [edit]             │
│  Denial letter (if denial path chosen)        [view] [edit]             │
└──────────────────────────────────────────────────────────────────────────┘
┌─ Your call ────────────────────────────────────────────────────────────┐
│  [ Accept coverage ]  [ Issue ROR ]  [ Deny ]  [ Request more info ]   │
└──────────────────────────────────────────────────────────────────────────┘
```

Every Layer 1 row is clickable and opens the cited source inline. Every Layer 2 and Layer 3 entry traces back to Layer 1 rows by index. **Nothing in the output is unsourced.**

### §3.4 Calibration as a first-class eval signal

AIP Evals adds a per-specialist calibration metric: at predicted probability *P*, what's the actual resolution rate across the golden set? A well-calibrated specialist's 80%-confident outputs resolve as predicted ~80% of the time, plus or minus the band the n supports.

Calibration is a hard, objective metric. It can fail in either direction — overconfidence (claiming 90% when reality is 70%) is just as actionable as underconfidence (claiming 60% when reality is 85%). Both surface as eval failures; both drive prompt revision.

Recommendations cannot be calibrated this way. This is one of the strongest arguments for the probability + evidence shape.

---

## §4 — One specialist runtime (Reserve, as the canonical example)

```
┌─────────────────────────────────────────────────────────────────────────┐
│ 1. TRIGGER                                                              │
│    ─ Event: document_received on CoverageRequest                          │
│    ─ Scheduled: daily review for exposures past review_cadence_days     │
│    ─ Manual: workspace user clicks "re-run reserve specialist"          │
└─────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 2. READ SUBSTRATE (via Foundry Functions through OSDK)                  │
│    ─ get_exposure_layer_b_snapshot(request_id, as_of):                 │
│        • CoverageRequest with all 7 status dimensions                     │
│        • Latest LiabilityAssessment in the chain                        │
│        • FinancialSnapshot from get_financials_as_of                    │
│        • All Documents received <= as_of with their DocumentExtraction  │
│        • Open AuthorityRequests + Decisions                             │
│        • Open Liens + MedicareReportingStatus                           │
│        • Recent Events (last 90 days)                                   │
│    ─ get_applicable_config(client_program_id, 'reserve', as_of):        │
│        • Material event definitions                                     │
│        • Authority matrix                                               │
│        • Step-up rules                                                  │
│        • Reporting thresholds                                           │
└─────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 3. HASH INPUT (deterministic, for audit + cache key)                    │
│    input_hash = SHA256(json.dumps(layer_b, sort_keys=True))             │
└─────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 4. EXTRACT FROM DOCUMENTS (if new docs since last run)                  │
│    For each new Document:                                                │
│      Call Anthropic SDK with extraction prompt for this document_type   │
│      Validate output via Pydantic                                       │
│      Write DocumentExtraction via Action Type                           │
└─────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 5. PROPOSE (the main LLM call)                                          │
│    Build prompt:                                                         │
│      ─ SYSTEM_PROMPT (cached at Anthropic):                             │
│          • Role: "You are the Reserve specialist for a TPA..."          │
│          • Ontology shape (object types + relationships)                │
│          • Output schema (JSON Schema)                                  │
│          • 3-5 in-context examples per recommendation pattern           │
│      ─ USER_TEMPLATE (per-invocation, not cached):                      │
│          • Layer B snapshot as structured data                          │
│          • Applicable config as JSON                                    │
│          • "Recommend the outstanding reserve for component X"          │
│                                                                          │
│    Call Anthropic SDK:                                                   │
│      response = anthropic.messages.create(                              │
│        model='claude-sonnet-4-6',                                       │
│        system=SYSTEM_PROMPT,  # cached                                  │
│        messages=[{'role': 'user', 'content': USER_TEMPLATE.render(...)}],│
│        response_format={'type': 'json_schema',                          │
│                         'json_schema': RESERVE_OUTPUT_SCHEMA,           │
│                         'strict': True}                                  │
│      )                                                                   │
│                                                                          │
│    Parse + validate:                                                     │
│      recommendation = ReserveRecommendation.model_validate_json(...)    │
│      On schema violation: retry once with explicit reminder, then 422   │
└─────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 6. EMIT AgentAction (via Action Type)                                   │
│    EmitAgentAction({                                                     │
│      specialist: 'reserve',                                              │
│      prompt_version: '1.0.3',                                            │
│      model_id: 'claude-sonnet-4-6',                                      │
│      request_id,                                                        │
│      claim_id,                                                           │
│      input_hash,                                                         │
│      output_json: recommendation,                                        │
│      confidence: recommendation.confidence,                              │
│      reasoning_trace: recommendation.reasoning_trace,                    │
│      triggered_by,                                                       │
│      requires_human_approval: eval_authority(config, recommendation),    │
│      ...                                                                 │
│    })                                                                    │
│    → Foundry-native audit log captures this automatically                │
└─────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 7. STATE MACHINE EVALUATES (Action Type validators)                     │
│    Three conditions for auto-application:                                │
│      ─ confidence >= floor (0.70 for Reserve)                           │
│      ─ recommended_outstanding within handler authority per config      │
│      ─ requires_human_approval == false                                 │
│                                                                          │
│    If all three pass:                                                    │
│      Trigger RecordFinancialTransaction Action Type                     │
│        ─ TS validator enforces posting rules                            │
│        ─ Writes balanced postings                                       │
│        ─ Sets escalation_outcome = 'applied_automatically'              │
│                                                                          │
│    If any fails:                                                         │
│      AgentAction stays in pending state                                 │
│      Workspace review queue picks it up                                 │
│      Human approves/rejects via UI → ApproveAgentAction Action Type     │
│        which then triggers the downstream Action Type                   │
└─────────────────────────────────────────────────────────────────────────┘
```

Latency: 8-20 seconds typical (dominated by the LLM call). Cost: ~$0.02-0.05 per Reserve run (Sonnet with cached system prompt).

---

## §5 — The deterministic spine (where the LLM is gated)

The most important architectural property: **specialists never mutate state directly.**

### §5.1 The pattern

```
┌──────────────┐                ┌──────────────┐                ┌──────────────┐
│  Specialist  │ ─ emits ────▶  │  AgentAction │ ─ may ─────▶   │  Action Type │
│   (LLM)      │  recommendation│              │  trigger       │  (validators)│
└──────────────┘                └──────────────┘                └──────────────┘
                                       │                                 │
                                       │ stays pending if:                │ rejects if:
                                       │  ─ confidence < floor             │  ─ illegal state combo
                                       │  ─ above authority                │  ─ posting rules violated
                                       │  ─ requires human approval        │  ─ transition guards fail
                                       ▼                                 ▼
                                ┌──────────────┐                ┌──────────────┐
                                │  Review queue│                │ Write rejected│
                                │  (workspace) │                │ (logged)      │
                                └──────────────┘                └──────────────┘
```

The LLM can propose anything. The substrate has veto power at two points:
- **Confidence + authority check** in the specialist's own logic (programmatic, easy to reason about)
- **Action Type validator** in Foundry (the data layer's own invariants — illegal combinations rejected even if specialist tried to bypass)

This is **two layers of defense** before any state changes.

### §5.2 Why this matters

- **Safe to deploy.** The LLM cannot single-handedly move a claim to a state that violates the ontology.
- **Auditable.** Every state change has either a rule-based provenance (Action Type validator passed) or an explicit human-approved provenance (someone clicked Approve in the workspace).
- **Real-claims-system pattern.** This is how real claims systems are built (Guidewire, Duck Creek, in-house carrier platforms all have analogous structures).
- **Interview narrative.** *"The deterministic skeleton is what makes the LLM safe to deploy. The LLM is what makes the skeleton flexible enough to handle real-world messiness."*

---

## §6 — Tools available to specialists

Each specialist has the same tool surface. Tools are either Foundry Functions (read-only) or Action Types (mutation).

### §6.1 Read tools (Foundry Functions called via OSDK)

| Function | What it returns |
|---|---|
| `get_exposure_layer_b_snapshot(request_id, as_of)` | Full Layer B view for one exposure as of a point in time |
| `get_financials_as_of(request_id, valid_at, recorded_at)` | Bitemporal ledger snapshot per component |
| `get_applicable_config(client_program_id, specialist, as_of)` | Effective SpecialistConfig at as_of |
| `get_aggregate_limits(claim_id, coverage_id)` | Consumed / remaining / breach status across sibling exposures |
| `get_audit_trail(claim_id)` | Chronological AgentAction history for one claim |

### §6.2 Write tools (Action Types triggered via OSDK)

| Action Type | What it does | Validators |
|---|---|---|
| `EmitAgentAction` | Record specialist recommendation | Required fields; confidence ∈ [0,1] |
| `RecordFinancialTransaction` | Write balanced ledger postings | Posting rules per kind enforced |
| `UpdateExposureStatus` | Change one or more status dimensions | Illegal-combination matrix; transition guards |
| `RecordDocumentExtraction` | Persist specialist's read of a document | Confidence-per-field shape |
| `RegisterDocument` | Ingest a new document | Required fields; valid document_type |
| `RecordLiabilityAssessment` | Append a versioned liability assessment | Fault percentages sum to 100; supersession chain |
| `RequestAuthority` | Escalate above-authority recommendation | Parent chain validation; max-level cap |

### §6.3 What specialists CANNOT do

- Mutate state directly bypassing Action Types
- Read `is_synthetic`, `source_event_id`, or any Layer A metadata
- See ground truth (Layer A facts hidden from the Layer B snapshot)
- Override config (they read it; they don't author it)
- Invoke each other directly (orchestration is in Railway, not in specialist code)

---

## §7 — Prompt structure

Per specialist, three components:

### §7.1 System prompt (cached at Anthropic)

```
You are the Reserve Specialist for a third-party claims administrator (TPA)
handling property and casualty insurance claims.

YOUR ROLE
─ Read the current state of a claim exposure
─ Identify material events since last reserve review
─ Recommend an updated outstanding reserve per component
─ Surface notice obligations triggered by the current state
─ Specify the authority level required to apply your recommendation

YOUR ONTOLOGY
[Brief description of CoverageRequest, LiabilityAssessment, FinancialTransaction
shapes, and the seven status dimensions on the exposure]

YOUR OUTPUT SCHEMA
[JSON Schema for ReserveRecommendation, validated strictly]

CRITICAL CONSTRAINTS
─ Never assert a fact not supported by the documents or the financial ledger
  in your input. Cite the document_id for every material fact.
─ If you cannot determine a reserve confidently from the input, set
  confidence < 0.70 and explain what's missing.
─ Always populate reasoning_trace with a structured explanation:
  what triggers fired, what exposure analysis you did, what jurisdiction
  considerations applied, what authority level is required.

IN-CONTEXT EXAMPLES
[3-5 examples covering common patterns: clear-liability BI with policy-limit
demand, disputed liability with multi-party, property-damage-only collision,
litigated case with mediation pending, fatality with statutory beneficiaries]
```

Length: ~3000-5000 tokens for the full system prompt. Cached for 1-hour TTL; reused across the ~10K specialist runs in the pipeline. Cache savings: ~80% of cost.

### §7.2 User template (per-invocation, not cached)

```
EXPOSURE TO REVIEW: {{request_id}}

CURRENT STATE
{{layer_b_snapshot_json}}

APPLICABLE CONFIG
{{config_json}}

NEW DOCUMENTS SINCE LAST REVIEW
{{new_documents_json}}

YOUR TASK
Recommend the outstanding reserve for each component on this exposure as of
{{as_of_timestamp}}. If no change is warranted, return the current outstanding
amounts with a `no_change_warranted: true` flag and explain why.

Respond with a ReserveRecommendation JSON.
```

Length: 5K-50K tokens depending on how many documents and how long the ledger history is. Sonnet's 200K context handles this comfortably.

### §7.3 Output schema

Composed from the §3 primitives. Every component change and every notice obligation carries cited evidence — the Pydantic validator rejects outputs missing citations.

```typescript
ReserveAnalysis = {
  request_id: string,
  reviewed_as_of: ISO8601,

  per_component: Array<{
    component: 'indemnity' | 'ALAE' | 'ULAE' | 'ALE' | 'expert_fees' | 'defense' | 'mitigation',
    current_outstanding: number,
    recommended_outstanding_band: { p10: number, p50: number, p90: number },
    rationale: string,
    triggers_fired: Array<{
      trigger_id: string,  // ref to material_event_definitions
      evidence_citations: EvidenceCitation[]  // min_length=1
    }>,
    evidence_citations: EvidenceCitation[]  // min_length=1, supports the band
  }>,

  notice_obligations_triggered: Array<{
    notice_type: 'excess_carrier' | 'reinsurer' | 'client' | 'DOI' | 'Medicare_Section_111',
    probability: number,  // [0, 1]
    reasoning: string,
    required_by_date: ISO8601,
    evidence_citations: EvidenceCitation[]  // min_length=1
  }>,

  authority_required_level: 'handler' | 'supervisor' | 'manager' | 'client',
  no_change_warranted: boolean
}
```

Two shape changes from a pre-contract output:
- **Reserve emits a band, not a point.** Adjuster sees `$42K–$51K with median $46.5K, 80% CI` and picks the point. Same calibration discipline as Coverage/Liability — you can measure whether the true ultimate lands in the band as often as predicted.
- **Every triggers_fired and every notice obligation carries its own evidence_citations list.** A trigger isn't asserted because the AI thought so; it's asserted because a specific document said so.

The schema is strict (Anthropic validates server-side). Pydantic re-validates client-side as defense-in-depth.

### §7.4 Coverage output (worked example)

Same Reserve runtime sequence (§4) with a different prompt and output schema. The Coverage system prompt's `YOUR ROLE` reads:

> Read the policy structure, the loss facts, and the documentary evidence. Identify which coverage parts apply, which exclusions might apply, whether the policy was in force at the loss date, and whether any conditions precedent (notice, cooperation, EUO) have been satisfied. Surface evidence and quantify uncertainty per outcome path. **Do not recommend a decision.** Draft the analysis memo, the ROR letter, and the denial letter. The adjuster picks the path.

Output:

```typescript
CoverageReport = {
  request_id: string,
  reviewed_as_of: ISO8601,

  evidence_found: Array<EvidenceCitation>,  // Layer 1 of the cockpit render

  per_question_probabilities: Array<{      // Layer 2
    question_text: string,
    probability: number,
    reasoning: string,
    evidence_citations: EvidenceCitation[]  // min_length=1
  }>,

  outcome_path_distribution: {              // Layer 3 — sums to 1.0
    paths: [
      { claim_text: "Coverage applies, clean", probability: number, reasoning: string, evidence_citations: EvidenceCitation[] },
      { claim_text: "Coverage with reservation of rights", probability: number, reasoning: string, evidence_citations: EvidenceCitation[] },
      { claim_text: "Denial defensible", probability: number, reasoning: string, evidence_citations: EvidenceCitation[] }
    ],
    would_shift_distribution: string[]      // "what evidence would move this"
  },

  drafts: {
    coverage_analysis_memo: { body: string, citations: EvidenceCitation[] },
    ror_letter: { body: string, citations: EvidenceCitation[] },     // present if ROR path > threshold
    denial_letter: { body: string, citations: EvidenceCitation[] }   // present if denial path > threshold
  }
}
```

The schema validator enforces `outcome_path_distribution.paths` probabilities sum to 1.0 ± 0.01, and every `evidence_citations` list has at least one entry. **There is no `recommended_path` field. By design.**

### §7.5 Liability output (worked example)

```typescript
LiabilityAnalysis = {
  request_id: string,
  reviewed_as_of: ISO8601,
  jurisdiction: string,
  comparative_fault_rule: 'pure' | 'modified_50' | 'modified_51' | 'contributory',
  comparative_fault_rule_citation: EvidenceCitation,  // sourced legal rule

  evidence_found: Array<EvidenceCitation>,

  per_question_probabilities: Array<{
    question_text: string,                  // "Was insured following too close?"
    probability: number,                    // 0.85
    reasoning: string,
    evidence_citations: EvidenceCitation[]
  }>,

  fault_allocation_distribution: {
    // Discrete distribution over (insured_fault_pct, claimant_fault_pct, other_party_fault_pct) buckets
    buckets: Array<{
      insured_fault_pct: number,
      claimant_fault_pct: number,
      other_party_fault_pct: number | null,
      probability: number,                  // sums to 1.0 across buckets
      reasoning: string,
      evidence_citations: EvidenceCitation[]
    }>,
    would_shift_distribution: string[]
  },

  recovery_barred_probability: number,      // derived from buckets that exceed jurisdictional bar

  draft_assessment: {
    body: string,                           // draft LiabilityAssessment narrative
    citations: EvidenceCitation[]
  }
}
```

The validator confirms the bucket probabilities sum to 1.0 and that the comparative fault rule citation points at a sourced legal rule (not an unvalidated config entry). **No bucket is asserted as "the recommendation." The adjuster picks the bucket.**

### §7.6 Brief output

Brief composes the per-claim summary that anchors the cockpit. It is the only specialist whose output isn't a probabilistic recommendation — it's a structured view. But the citation discipline still applies: every diff item, every "what's missing" entry, every pending-correspondence line carries the source.

```typescript
ClaimBrief = {
  request_id: string,
  generated_at: ISO8601,

  story_paragraph: string,                  // one-paragraph narrative
  story_citations: EvidenceCitation[],

  since_last_touch: {
    last_touch_at: ISO8601,
    diff_items: Array<{
      change_text: string,                  // "Demand package received 05-27 from claimant's attorney requesting $48,000"
      occurred_at: ISO8601,
      evidence_citations: EvidenceCitation[]
    }>
  },

  current_status_snapshot: {                // the seven status dimensions
    coverage_status, handling_status, settlement_status,
    representation_status, litigation_status,
    recovery_status, financial_status
  },

  financial_snapshot: ExposureFinancialSnapshot,  // from get_financials_as_of

  specialist_recommendations_summary: Array<{
    specialist: 'coverage' | 'liability' | 'reserve' | 'recovery' | 'closure',
    agent_action_id: string,
    headline: string,                       // "Reserve specialist proposes BI +$18,500 → $46,500"
    awaiting_approval: boolean
  }>,

  missing_info: Array<{
    item: string,                           // "Renewed medical authorization"
    requested_from: string,                 // "claimant's attorney"
    requested_at: ISO8601 | null,           // null if not yet sent
    response_due: ISO8601 | null,
    correspondence_status: 'auto_sent' | 'awaiting_human_approval' | 'sent_to_human_drafted' | 'not_yet_drafted',
    evidence_citations: EvidenceCitation[]  // what makes us think this is missing
  }>,

  pending_communications: Array<{
    direction: 'outbound' | 'awaiting_response',
    recipient_party_id: string,
    message_type: string,
    drafted_or_sent_at: ISO8601,
    correspondence_id: string               // ref to Correspondence service record
  }>
}
```

Brief is regenerated by event triggers (any AgentAction, any state change, any Document arrival on the exposure). The cockpit renders the Brief above the rest of the claim view; it's the first thing the adjuster reads.

---

## §8 — Four-layer truth model wiring

From [data-layer.md §7](./data-layer.md). Each layer is computed by a different mechanism with different trust properties.

### §8.1 Layer A — Latent world state

- **Source:** synthesis pipeline writes Layer A to `data/ground_truth/<claim_id>/latent.json` (or equivalent Foundry dataset)
- **Visibility:** never read by specialists. Layer-A-touching code paths are tagged in the codebase.
- **Used by:** Layer C-statutory eval (deterministic checks); Layer D rubric scoring (golden cases compare to A)

### §8.2 Layer B — Observed file state by date

- **Source:** computed by `get_exposure_layer_b_snapshot(request_id, as_of)` Foundry Function
- **Filters:** documents with `received_date <= as_of`; ledger entries with `recorded_at <= as_of`; status dimensions current at `as_of`
- **Visibility:** the specialist's only input

### §8.3 Layer C-statutory — Eval-trusted deterministic labels

- **Source:** Foundry Function evaluators (e.g., `eval_layer_c_statutory_recovery`) that read Layer A + the sourced legal rules in SpecialistConfig
- **Examples:** SOL passed (only for rules with `validation_status: sourced`); Section 111 obligation triggered; required document missing per statutory rule
- **Eval signal:** specialist either flagged it or didn't; ground truth is the rule's deterministic application

### §8.4 Layer C-policy — Specialist reproduces config

- **Source:** Foundry Function evaluators that read Layer A + the client's full SpecialistConfig
- **Examples:** trigger recognition (did specialist identify all configured material events); authority routing (did specialist request the right approval level); closure defect detection per client checklist
- **Eval signal:** rule-execution accuracy, not real-world correctness — the config could be wrong and the specialist still scores high

### §8.5 Layer D — Judgment ground truth

- **Source:** cross-model judge (OpenAI judges Claude-generated cases or vice versa) + human review on golden cases
- **Examples:** reserve within defensible band; rationale quality; recovery pursuit defensibility
- **Eval signal:** rubric-scored, not point-estimate. Caveat: cross-model independence is in weights, not in information channel (both models read the same Layer B that the generator wrote)

### §8.6 Eval runtime wiring

```
Railway Eval Orchestrator
   │
   ├─ Fetch golden set (Foundry Dataset)
   │
   ├─ For each golden claim:
   │    ├─ Build Layer B for the eval point T
   │    ├─ Run specialist (Railway internal call)
   │    ├─ Layer C-statutory: call Foundry Function evaluator
   │    ├─ Layer C-policy: call Foundry Function evaluator
   │    └─ Layer D: call Foundry Function evaluator
   │         (which internally calls OpenAI for cross-model judging)
   │
   ├─ Aggregate metrics by truth layer
   │
   ├─ Push to AIP Evals as run result
   │
   └─ Write summary to Foundry Dataset (read by Next.js /eval page)
```

---

## §9 — Automatic vs human-approved boundary

From [STRATEGY.md §3](./STRATEGY.md). Encoded as the `requires_human_approval` field on every AgentAction.

The principle: **automate the data work, automate the routine correspondence, surface evidence + probability for anything legally bearing, require human approval for adversarial language and contested decisions.**

| Specialist / service output | Auto-applied? | Why |
|---|---|---|
| Brief refresh | YES | It's a view, not a state mutation. Citations required on every diff item. |
| Document field extraction (DocumentExtraction rows) | YES | Pure data work |
| Priority Scorer ranking | YES | It's a view, not a state mutation |
| **Coverage analysis (evidence + probability + drafts)** | NO | Coverage decisions always human. AI surfaces evidence + outcome path distribution; adjuster picks the path. No `recommended_path` field exists. |
| **Liability analysis (evidence + fault distribution + drafts)** | NO | Same as Coverage. Adjuster picks the bucket. |
| Reserve change below handler authority | YES | Data work — moving a number within authorized bounds. Probability band emitted; midpoint applied. |
| Reserve change above handler authority | NO | Becomes AuthorityRequest; routed through escalation chain |
| Recovery opportunity surfacing | YES | Detection, not action |
| Recovery pursuit / referral / demand send | NO | Legal action; commits the TPA to a position |
| Closure block (Action Type validator rejects illegal closure) | YES | Doesn't mutate state — *prevents* an illegal mutation |
| Closure execution | NO | Closure is final; always human-approved |
| Notice obligation surfaced in Brief | YES | Surfacing is not committing |
| Notice send via Correspondence — routine recipient (body shop, medical provider, insured, tow, police records) | YES | No legal weight; templated |
| Notice send via Correspondence — adversarial recipient (claimant's counsel, opposing counsel, court, excess carrier) | NO | Every word is discoverable; auto-draft + human-approve send |
| Reservation of Rights letter | NO | Highest legal weight; frames the entire coverage posture |
| Denial letter | NO | Highest bad-faith exposure; supervisor co-sign required |

**The human-only column collapses to**: approve adversarial language, approve contested decisions, approve money above authority. That's all. Everything else — extraction, drafting, sending routine info requests, ranking the queue, summarizing the file, diffing new info against state, calculating probabilities — is AI work.

---

## §10 — Configuration as moat

The same specialist code behaves differently per client because the SpecialistConfig drives:
- Which events trigger reserve review
- What authority threshold applies
- What notice deadlines must be met
- Which statutes (SOL, made-whole, anti-subro) apply
- What closure checklist items must be satisfied
- Which jurisdiction's rules govern

**Concrete example.** Same claim (auto BI, FL jurisdiction, $40K demand received):

| Config | Specialist behavior |
|---|---|
| Northwind Logistics: handler authority $25K, large-loss notice at $50K incurred | Recommends reserve at $40K; flags AuthorityRequest (above handler $25K); no notice obligation triggered (under $50K) |
| Sentinel Mutual: handler authority $75K, large-loss notice at $25K incurred | Recommends reserve at $40K; auto-applies (within $75K authority); triggers notice obligation (over $25K) — surfaces it in the workspace |

The specialist code, prompt, and model are identical. Only the config differs. This is the moat: **the product is configured per customer, and that configuration is what the FDE deploys.**

The matched-pair eval test (TECH_PLAN §6.4) explicitly checks this: same claim under two configs must produce divergent recommendations, or the configuration isn't doing real work.

---

## §11 — Failure modes

### §11.1 LLM-specific

| Failure | Detection | Mitigation |
|---|---|---|
| Schema violation in LLM output | Pydantic validation fails | Retry once with explicit reminder; second failure logs AgentAction with status=schema_violation |
| **Missing evidence citations on a probabilistic claim** | Pydantic `min_length=1` on `evidence_citations` fails | Retry once with explicit reminder ("every ProbabilisticClaim must cite at least one Document, sourced rule, or ledger entry"); second failure logs AgentAction with status=schema_violation_missing_citations; **never enters production** |
| **Outcome path probabilities don't sum to 1.0** | Pydantic `probabilities_sum_to_one` validator fails | Retry once with explicit reminder; second failure logs schema_violation_distribution_invalid |
| Hallucinated document_id in evidence citations | Specialist post-processing verifies each `document_id` / `sourced_rule_id` / `ledger_entry_id` exists in Layer B + SpecialistConfig | Drop the hallucinated citation; if it was the only citation on a ProbabilisticClaim, the claim itself is dropped; flag for prompt refinement |
| Confident but factually wrong recommendation | Action Type validators reject the write | AgentAction lands in audit log; never mutates state |
| Poor calibration on golden set | AIP Evals calibration metric drifts (predicted P diverges from actual resolution rate) | Surface as eval anomaly; prompt revision; re-run on a fresh golden subset |
| LLM refusal / safety filter triggered | Empty response or refusal pattern | Log; route to human review with "LLM declined" reason |

### §11.2 Integration-specific

| Failure | Detection | Mitigation |
|---|---|---|
| OSDK call to Foundry Function times out | 30s timeout, exponential backoff | Retry 3x; on persistent failure, AgentAction error with retry-after |
| Action Type validator rejects EmitAgentAction (malformed) | 400 from Foundry | Log specialist code bug; ship fix |
| Action Type validator rejects downstream write (e.g., illegal state combo) | 400 from Foundry | AgentAction stays in pending; surfaces in review queue |
| Foundry rate limiting | 429 from Foundry | Backoff with jitter; if persistent, scale down concurrency in Railway |
| Anthropic API throttling | 429 from Anthropic | Backoff with jitter; eventually fail the request gracefully |

### §11.3 Configuration-specific

| Failure | Detection | Mitigation |
|---|---|---|
| Config has a wrong legal rule (e.g., wrong SOL value) | Specialist applies the wrong rule but Layer C-statutory eval is restricted to sourced rules → wrong rule isn't in the eval surface | Config audit + sourcing discipline (data-layer §6) |
| Config has effective dates that don't cover the claim's timeline | `get_applicable_config` returns null | Specialist surfaces "no applicable config" error; routes to human review |
| Two configs effective at the same time (overlap) | `get_applicable_config` raises overlap error | Foundry Action Type validator on SpecialistConfig writes prevents overlap |

### §11.4 Eval-specific

| Failure | Detection | Mitigation |
|---|---|---|
| Cross-model judge agrees with specialist on a Layer A wrong case | Layer D rubric score is high but Layer A check (where applicable) reveals divergence | Surface as eval anomaly; manual review |
| Layer C-policy passes universally (config-rule is too easy) | Layer C-policy approaches 100% across all specialists | Eval isn't discriminating; revisit config-rule difficulty |
| Time-to-recognition harness reveals specialist is fast but wrong | Time short, Layer D rubric low | Tune prompt; possibly add reasoning trace requirements |

---

## §12 — Observability

What you can see at runtime:

| Surface | What it shows |
|---|---|
| **AgentAction object type (Foundry)** | Every specialist call; input hash, output, confidence, reasoning, escalation outcome |
| **Foundry-native audit log** | Every Action Type invocation with caller identity, timestamp, inputs, outputs |
| **Event log (Foundry)** | Every state change with `occurred_at` + `recorded_at` (bitemporal) |
| **Railway logs (FastAPI structured logs)** | Per-request: latency, model used, prompt version, token counts, errors |
| **AIP Evals dashboard** | Aggregate metrics per truth layer, per specialist, per prompt version |
| **Next.js workspace audit drawer** | For any claim: chronological AgentAction trail with input hashes and outputs |

The combination answers "why did we set the reserve at $X on claim Y on date Z" three months after the fact. This is the production-grade audit story.

---

## §13 — Open agent-layer questions (defer to Weekend 2-3)

1. **Prompt cache TTL strategy.** Anthropic offers 5-min and 1-hour TTLs. Which one? Probably 1-hour given the run pattern, but validate cost numbers.
2. **System prompt version management.** When the prompt changes, do we invalidate the cache deliberately, or let the new prompt naturally evict? Probably explicit invalidation.
3. **In-context example selection.** Static 3-5 examples in the system prompt, or RAG-selected examples per invocation? Lean static; revisit if eval shows pattern-specific gaps.
4. **Specialist re-run policy on config change.** When a SpecialistConfig changes, do we mark all existing AgentActions stale? Probably yes for the affected client, but resolve at build time.
5. **Cross-model judge model selection.** OpenAI GPT-5 vs GPT-4o for Layer D judging. Cost vs quality tradeoff. Test on golden set.

---

## §14 — Triangulation review checklist

Before commit, this document should survive these questions:

1. **Is the deterministic spine actually preventing LLM mistakes?** Walk through an adversarial scenario: specialist tries to set `coverage_status=denied` with `financial_status=paid`. Show how the Action Type validator catches it.
2. **Does the four-layer truth model actually separate trust correctly?** Walk through a Layer C-policy result that's high and a Layer A result on the same case that's wrong. Show the truth-layer attribution surfaces the disagreement.
3. **Does configuration genuinely drive divergent behavior?** Walk through the §10 example. Confirm the same claim under two configs produces different outputs because the config changes the prompt's runtime payload.
4. **Is the audit trail genuinely sufficient to answer "why" later?** Pick a random AgentAction. Reconstruct what the specialist saw, what it proposed, what was applied, by whom. Should be possible from `AgentAction.input_hash` + `input_snapshot_path` + `output_json` + linked `EvidenceCitation` rows + Foundry audit log.
5. **Are the failure modes actually handled?** Pick three from §11. Walk through detection → mitigation. Should be concrete, not hand-wavy.
6. **Does the human-approval boundary match real adjuster work?** Walk through the §9 table with someone who's done claims. Confirm the auto-vs-approve splits reflect operational reality.
7. **No assertion without a source.** Pick any Coverage, Liability, Reserve, Recovery, or Closure output. Confirm every `ProbabilisticClaim`, every `OutcomePathDistribution.paths[].claim_text`, every fault-allocation bucket, every triggers_fired entry, and every notice obligation carries at least one `EvidenceCitation`. Confirm the Pydantic schema rejects outputs without them — try crafting a synthetic specialist output missing citations and confirm it fails before reaching Foundry.
8. **Is the calibration metric measuring what we claim?** Pull the AIP Evals calibration dashboard for a recent specialist run. Confirm predicted P bands actually correspond to resolution rates on the golden set, within the band the n supports. A specialist with high recall but bad calibration is a real failure mode, not a soft one.
9. **Is the Coverage/Liability output free of recommendations?** Grep the Coverage and Liability output schemas for `recommended_*`, `recommendation`, `decision`, `should_*`. None should exist. The schemas emit probabilities and drafts; the human picks the path.

---

*Updates land when Weekend 2 surfaces what the spec missed.*
