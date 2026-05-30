---
tags:
  - project/argos
  - type/plan
  - status/archived
created: 2026-05-26
archived: 2026-05-27
aliases:
  - Claims Ops Intelligence Plan (v0.1, archived)
---

# Claims Operations Intelligence Layer — Build Plan

*Companion to PRD.md and MARKET_ANALYSIS.md · v0.1 · 2026-05-26*

> **ARCHIVED 2026-05-27.** Superseded by the phased plan at `~/.claude/plans/we-will-go-lmm-keen-glacier.md` and by `THESIS.md` (skeleton) + `MARKET_ANALYSIS.md` (v0.3). This document is kept as a historical reference for the still-valid technical decisions in §4 (topology), §5 (evals), §6 (stack), and §10 (interview narrative) — those carry forward into the future `TECH_PLAN.md` in Phase 7. The premature sections (§2 ontology, §4 specific agent list, weekend breakdown) are superseded and should not be treated as current.

This plan is the spec. It does not change without explicit decision. Code matches this; if reality forces a deviation, this doc updates first.

---

## 0. North star and non-goals

### North star

Ship one excellent end-to-end vertical slice — first-party auto collision claims, FNOL → adjuster, with a real ontology, real SQL transforms on real data, and a governed multi-agent layer with a working eval suite — in 2–3 weekends. The slice is portfolio-defensible for both Palantir FDE and AI PM interviews.

### Explicit non-goals (the things this slice does NOT do)

- Third-party liability, litigation, SIU referral, salvage. Out of scope for the slice but reflected in the ontology as state branches we don't implement.
- Workers' comp / disability (long-duration). The ontology is shaped to extend there, but no agents or data are built for it.
- Claimant-facing portal. No customer UX.
- Vendor / repair shop orchestration. Inspections exist as objects; we don't drive an outside scheduling flow.
- Production-grade ops: no dbt, no Airflow, no Postgres cluster, no Temporal. DuckDB + Python is the right stack for a portfolio slice; we name the production replacements in this doc but don't build them.
- Pretty UI. One Streamlit dashboard, enough for an interviewer to walk a claim.

If a feature isn't in the weekend breakdown below, it isn't in the slice.

---

## 1. The vertical slice, in one paragraph

A real auto loss event (sourced from NHTSA FARS) is paired with an LLM-generated FNOL transcript, a synthetic repair estimate PDF, and adjuster notes. The system ingests these unstructured artifacts, the IntakeExtractionAgent resolves them into a typed Claim object (with PartyRoles, Coverage attachment, LossEvent, Documents), the deterministic state machine transitions Filed → Triaged → Assigned → InvestigationOpen → DamageAssessed → ReserveSet, the ReserveRecommendationAgent proposes per-coverage reserves grounded in SQL-computed peer comparisons from historical claims, and at the end the NextBestActionAgent surfaces what's next on the claim. Every agent action is audit-logged with confidence and reasoning trace; sub-threshold confidence drops to a human review queue rendered in the dashboard.

---

## 2. The ontology (the highest-leverage section)

This is the section a Palantir interviewer will probe hardest. We model objects, relationships, grain, and invariants — not just a list of tables.

### 2.1 Core objects

| Object | Grain (one row =) | Why it exists |
|---|---|---|
| **Policy** | One coverage contract, time-versioned | Coverage container; many-to-one with Claim |
| **Coverage** | One line item on a Policy (Liability, Collision, Comp, UM, PIP) | Reserves and Payments attach to Coverages, not to Policies directly |
| **Party** | One person or business, identity-resolved across systems | Persistent identity; same Party can appear on many Claims in different roles |
| **PartyRole** | One (Party, Claim, Role) tuple | **The key modeling move.** A Party is not a role; a Party plays roles on claims |
| **LossEvent** | One incident in the real world | Decoupled from Claim because one multi-vehicle incident can spawn multiple claims |
| **Claim** | One coverage-applicable consequence of a LossEvent | The unit of work; lifecycle managed by the state machine |
| **Document** | One artifact (FNOL transcript, photo, estimate, police report), typed via DocumentKind | Polymorphic input; everything unstructured lands here first |
| **Inspection** | One damage assessment event | Has an Inspector (a PartyRole), produces Documents, gates DamageAssessed |
| **Reserve** | One financial commitment on (Claim, Coverage), time-versioned | Bitemporal: as-of system time AND effective time. Tracks the evolution of "how much will this claim cost" |
| **Payment** | One cash outflow | Reduces active Reserve balance on a Coverage |
| **Handoff** | One transfer-of-ownership event (from_role, to_role, reason, ts, latency) | **The unit that stalls.** Surfacing handoff latency is half the product |
| **StateTransition** | One change in Claim.state (from, to, fired_by, reason, ts) | The audit-grade lifecycle log; replay any claim from these |
| **AgentAction** | One read or write by an LLM agent (agent_id, claim_id, input_hash, output, confidence, reasoning, escalation_outcome) | The other audit-grade log; **this is the governance layer made real** |
| **EntityResolution** | One (source_system, source_id, party_id, confidence) match | How identity is reconciled across fragmented source systems |

### 2.2 The three modeling moves worth understanding

**(a) PartyRole as a join entity, not Party-as-claimant.** A naïve model gives Claim a `claimant_id` and `insured_id` and `at_fault_id`. That model breaks the first time you have a multi-vehicle accident where Party A is insured on Claim 1 but the claimant on Claim 2. The PartyRole model lets the same Party play any role on any Claim, queries `WHERE role = 'Subrogee'` are trivial, and identity resolution lives in one place (Party.entity_resolution_id) rather than scattered across foreign keys. This is the kind of pattern Palantir's ontology round is explicitly looking for.

**(b) Bitemporal Reserves.** A Reserve is not a number on a claim; it's a series of values over time. We store both `effective_at` (when the carrier decided this reserve applies) and `recorded_at` (when the system actually wrote it). This lets you reconstruct "what was our reserve on this claim 30 days ago" — the question every reserves analyst asks. Single-temporal models (just one timestamp) can't answer it correctly when reserves are corrected retroactively.

**(c) Handoff as an entity, not an event log line.** The "claims stall in handoffs" thesis only becomes operational if Handoff is a first-class object with `from_role`, `to_role`, `reason`, `ts`, `expected_latency`, `actual_latency`, `breach_flag`. Then "stalled claim" is a SQL query, not a vibe. This is the move that lets one CTE answer "where is every claim in the book stalled right now."

### 2.3 Invariants (enforced at the data layer, tested in CI)

1. A Reserve cannot exist without an active Coverage on the Claim's Policy.
2. `SUM(Payment.amount WHERE coverage=X) <= MAX(Reserve.amount WHERE coverage=X AND effective_at <= NOW())`.
3. Every StateTransition has a non-null `fired_by`, which is either `'rule:<rule_id>'` or an `AgentAction.id`.
4. Every AgentAction below the configured `confidence_floor` must have `escalation_outcome IN ('pending_human', 'human_accepted', 'human_edited', 'human_rejected')`.
5. A Party referenced on any Claim must have at least one PartyRole; a Party with zero PartyRoles is orphan and flagged.

Invariants are not just rules — they're how you prove the system has integrity. Each gets a SQL check that runs nightly.

### 2.4 Schemas in the repo

DDL lives at `db/schema.sql`. Pydantic models mirror it at `app/ontology.py`. Pydantic is the in-memory truth; SQL is the persistence truth; the two are kept in sync by a generation script (`scripts/check_schema_drift.py`) — if they ever disagree, CI fails. This is a small thing but it's the kind of detail that sells the "I take data engineering seriously" story.

---

## 3. Data layer

### 3.1 Source data

**Primary (real, public):** [NHTSA FARS](https://www.nhtsa.gov/research-data/fatality-analysis-reporting-system-fars). Real fatal motor vehicle crash data, 1975–present, ~30K incidents/year, with structured fields for vehicles, persons, locations, weather, severity. Public, downloadable, MIT-style permissive use.

- **Tradeoff:** FARS is fatalities-only, so severity is biased upward. We acknowledge this in the README and sample 20% of incidents to seed; the rest of the "claims population" is generated to look more like an actual auto book (skewed toward minor fender-benders with occasional total losses).

**Secondary (real, public, for the expansion arc only — not in the slice):** [FEMA NFIP claims](https://www.fema.gov/openfema-data-page/fima-nfip-redacted-claims-v2). ~2M property flood claims. We'll use it in the expansion arc to demonstrate the ontology extends to property, but we don't ingest it in the slice.

**Why not Guidewire/CCC sample data:** Their schemas are public but their sample datasets are gated behind partnership. Generating synthetic data against their *published schemas* (which we do for the FNOL transcripts and adjuster notes) gives us the same shape with no licensing risk.

### 3.2 Synthetic layer (the part that motivates the LLM extraction story)

For each real loss event, we generate:

- **FNOL call transcript** (~300–800 words, two speakers, named speaker turns, varying levels of clarity). Some include rambling, some include critical detail buried in the middle, some include false starts and self-corrections. We seed about 10% with intentional ambiguity (claimant says "the other driver" without identifying which vehicle).
- **Repair estimate "PDF"** (a structured-but-messy markdown doc that mimics a real estimate, with line items, labor hours, parts, taxes, and a total).
- **Adjuster notes** (short free-text observations).
- **Optional photo descriptions** (we don't actually generate photos in the slice; we stub a `photo_caption` field that downstream pretends came from a vision model).

These are generated by Claude Haiku 4.5 with carefully written prompts that bake in the underlying real facts so the extraction can be measured.

### 3.3 Pipeline

```
NHTSA FARS CSV → (Python loader) → DuckDB raw.* tables
                                        ↓
                          (SQL transforms in db/transforms/*.sql)
                                        ↓
                              DuckDB stg.* and mart.* tables
                                        ↓
              (Python ingestion → synthetic doc generation → Document rows)
                                        ↓
                       (Agent runs against Claim object view)
```

`db/transforms/` is the directory the Palantir SQL round cares about. Every transform is hand-written, named, tested, and documented with intent.

### 3.4 SQL exemplars (the work)

Six transforms ship in the slice. Each is hand-written, has a 1–2 sentence header comment explaining the *intent* (not the *what*), and has a paired test that runs against a small fixture dataset.

| File | What it does | SQL technique on display |
|---|---|---|
| `stg_party_resolution.sql` | Probabilistic match across raw FARS person records to deduplicate Parties | `GROUP BY` + similarity scoring + window function for rank |
| `mart_claim_object.sql` | Denormalizes ~8 tables into one queryable Claim view | Multi-CTE with explicit join semantics; one row per Claim |
| `mart_handoff_latency.sql` | Computes actual vs expected latency per Handoff, with breach flag | `LAG`/`LEAD` window functions; `CASE` on threshold |
| `mart_peer_reserve_comparison.sql` | For each Claim, find the cohort of 50 most-similar historical claims and compute reserve percentiles | Self-join via similarity score; `PERCENTILE_CONT` window function |
| `mart_stalled_claims.sql` | Claims with most-recent Handoff > N days old and no AgentAction since | CTE + `NOT EXISTS` correlated subquery |
| `mart_subro_candidates.sql` | Closed Claims where at-fault PartyRole != Insured, and no SubroOpened branch exists | CTE chain + role-pivot |

The peer-comparison transform is the showpiece. It implements the "surface prior-loss data in the adjuster's screen in 3 seconds" pattern from the McKinsey-cited case study, with real SQL.

---

## 4. State machine + agent topology

### 4.1 The deterministic spine

```
Filed → Triaged → Assigned → InvestigationOpen → DamageAssessed → ReserveSet
                                                                       ↓
                                                                  Negotiating
                                                                       ↓
                                                              SettlementProposed
                                                                       ↓
                                                                     Paid
                                                                       ↓
                                                                    Closed

Branches (modeled, not implemented in the slice):
  → Reopened (from Closed)
  → Litigated (from any open state)
  → SubroOpened (from Closed or ReserveSet)
  → Denied (from any state pre-ReserveSet)
```

States are an enum. Transitions are declared in `app/state_machine.py` with explicit `from_state`, `to_state`, `guard` (callable that returns bool), and `effect` (callable that fires side effects).

Each transition is either **rule-fired** (the guard is a deterministic check on the Claim object) or **agent-fired** (the guard checks whether an agent has produced a sufficient-confidence proposal, the effect commits the proposal to the Claim). This is the "deterministic skeleton + LLM at named boundaries" pattern — the LLM never moves the state directly; it produces a proposal that a deterministic rule applies.

### 4.2 The agents

Four agents in the slice. Each has: a name, the transition or trigger it serves, an input schema, an output schema, a confidence floor, a defined escalation, an eval set.

| Agent | Trigger | What it produces | Confidence floor | Escalation if below floor |
|---|---|---|---|---|
| **IntakeExtractionAgent** | Filed → Triaged | Structured Claim draft (parties, coverage attachment, loss event, severity estimate) from FNOL transcript + initial documents | 0.75 | Routes to human review queue with extracted fields pre-filled |
| **ReserveRecommendationAgent** | DamageAssessed → ReserveSet | Per-coverage reserve proposal, with reasoning grounded in the peer-comparison SQL output | 0.70 | Routes to senior adjuster review with peer cohort attached |
| **NextBestActionAgent** | Triggered nightly on every open Claim with stalled Handoff | One named action with owner ("call vendor X about estimate", "set initial reserve") | 0.65 | Action is shown as suggestion in dashboard, no auto-fire |
| **SubroDetectionAgent** | Triggered on every Claim entering Closed; daily on open Claims | Subrogation candidate flag with rationale and recoverable amount estimate | 0.80 | Always lands in subro queue, never auto-actioned (subro is high-stakes) |

### 4.3 Why this topology beats the alternatives

We considered three topologies and rejected two:

- **Event-driven agents on shared ontology (AIP-style)** is the most architecturally interesting and the closest to Palantir's actual product. We rejected it for the slice because debugging emergent behavior across 4 autonomous agents in 2–3 weekends is a recipe for shipping nothing. We design the ontology to *support* this pattern in the expansion arc (every Claim emits structured state-change events that agents could subscribe to), but the slice runs sync.
- **Orchestrator + specialist tools (LangGraph-style)** is the easiest to build but tells the weakest interview story. "I used LangGraph" is what every applicant says. The hybrid pattern below requires you to articulate *why* you put the LLM where you did, which is the more interesting answer.
- **Hybrid: deterministic state machine + LLM at named boundaries** *(chosen)*. The state machine is the governance layer made structural — the LLM cannot move a claim through its lifecycle by itself; every state change either has a rule-based provenance or an explicit human-approved agent provenance. This is also how real claims systems are built. The interview narrative: *"the deterministic skeleton is what makes the LLM safe to deploy; the LLM is what makes the skeleton flexible enough to handle real-world messiness."*

### 4.4 The audit trail

Every AgentAction row stores: `agent_id`, `agent_version`, `model_id`, `input_hash` (SHA256 of the structured input the agent saw), `output` (full JSON), `confidence`, `reasoning_trace` (the model's own justification, captured via a required field in the output schema), `escalation_outcome`, `created_at`. This is the table you replay to answer "why did we set the reserve at $12,400 on claim 9817" three months after the fact. It's also the table the dashboard reads to show reviewers what the system did.

---

## 5. Evals and human-in-the-loop

### 5.1 The eval suite

Three layers, each catching what the layer above misses:

**(a) Schema/structural checks** — does the output validate against the output schema; are required fields present; are enums in range. Caught by Pydantic at runtime.

**(b) Golden case tests** — 30–50 hand-curated synthetic claims with known ground-truth structured representations. For IntakeExtractionAgent, the test is: given this FNOL transcript, did we extract these specific (party, role, vehicle, severity) facts. Field-level precision/recall reported. Lives in `evals/golden/*.json` and runs as pytest.

**(c) LLM-judge evaluation** — for the open-ended outputs (NextBestAction reasoning, Reserve rationale), a Claude Haiku judge model scores against a rubric anchored with 5 high-quality examples and 5 low-quality examples. Score thresholds gate CI: if judge mean drops below baseline, the run fails. Lives in `evals/judge/`.

Evals run on every commit. Eval results are version-controlled (small JSON files), so regressions show up as diff lines in PRs.

This is the answer to the PM-interview question *"how do you know your NBA recommendation is right?"*: I don't trust any single check; I layer three.

### 5.2 Human-in-the-loop

Two-state review queue:

1. **Pending** — any AgentAction below confidence floor. UI shows the agent's proposed output, the input it saw, and a form for the reviewer to accept / edit / reject. Reject reasons are an enum (wrong extraction, missing context, hallucinated fact, low-confidence-but-correct, other).
2. **Resolved** — reviewer's decision recorded as a new AgentAction with `escalation_outcome` set. The original agent's input + the human's correction becomes a new golden case automatically, if flagged.

This closes the loop: every human correction is an eval data point. The eval suite grows as the system runs. This is the story that sells "I think in feedback loops, not in fire-and-forget LLM calls."

---

## 6. Stack

| Layer | Choice | Why this, not the obvious alternative |
|---|---|---|
| Language | Python 3.11+ | Default for data; supports DuckDB, Pydantic, Anthropic SDK natively |
| Warehouse | DuckDB | Real SQL engine, zero ops, ships in-process, demos cleanly. Production replacement: Postgres + dbt |
| Schema models | Pydantic v2 | Runtime validation, codegen-friendly, mirrors DDL |
| Agent framework | **Anthropic SDK direct** (no LangChain/LangGraph) | Showcases understanding of the primitives. Frameworks add weight without showing the work. |
| State machine | Hand-rolled in `app/state_machine.py`, ~200 lines | A custom state machine is small and legible; libraries (`transitions`) hide the architecture |
| Model — main | Claude Sonnet 4.6 (`claude-sonnet-4-6`) | Strong reasoning, good structured-output adherence, reasonable cost |
| Model — judge | Claude Haiku 4.5 (`claude-haiku-4-5-20251001`) | Cheap, fast, sufficient for rubric-scoring |
| UI | Streamlit | One file, one command, enough for an interview demo. Replace with Next.js in production |
| Eval runner | pytest + custom fixtures | Standard, shows up well in code review |
| Test data | Generated synthetic, seeded with NHTSA FARS records | Reproducible (fixed seed), version-controlled |

**Prompt caching** is on for every agent call (the system prompt + ontology schema get cached). This is the kind of detail a PM interviewer notices.

---

## 7. Weekend breakdown

### Weekend 1 — Ontology + data foundation

**Goals:** A queryable Claim object view backed by real data and a working synthetic-document generator.

- Define all 14 ontology objects as `db/schema.sql` DDL + `app/ontology.py` Pydantic models.
- Implement `scripts/check_schema_drift.py`.
- Ingest NHTSA FARS into DuckDB (`raw.fars_*` tables).
- Write the six SQL transforms in `db/transforms/`. Each gets a test against fixture data.
- Generate 200 synthetic claims (each is one FARS-seeded LossEvent + one Claim + 1–3 PartyRoles + 1–3 Documents).
- Generate FNOL transcripts and repair estimates for each via Haiku.

**Deliverable to test the weekend went right:** `SELECT * FROM mart_claim_object LIMIT 5;` returns five denormalized Claim rows with all their PartyRoles, Documents, and Coverage attached. Plus: `pytest db/transforms/tests/` passes.

### Weekend 2 — State machine + first two agents

**Goals:** End-to-end ingestion of one synthetic FNOL into a structured Claim, with reserves set and a full audit trail.

- Implement the state machine and AgentAction logging.
- Build IntakeExtractionAgent + ReserveRecommendationAgent.
- Wire them into the relevant state transitions.
- Build the eval harness; write 20 golden cases for IntakeExtractionAgent and 10 for ReserveRecommendationAgent.
- Run the full pipeline end-to-end on all 200 synthetic claims; record eval results.

**Deliverable:** `python -m app.run_pipeline --claim-id <id>` walks a Claim from Filed → ReserveSet, emits AgentActions, all assertions pass. `pytest evals/` passes with documented baseline scores.

### Weekend 3 — NBA + UI + interview polish

**Goals:** A demo-ready system and the artifacts that sell it.

- NextBestActionAgent + SubroDetectionAgent.
- Streamlit dashboard: claim detail view + review queue + (small) cohort-comparison view for the showpiece SQL.
- Write README with: problem statement (one paragraph), architecture diagram, how to run, eval baseline numbers.
- Write `docs/INTERVIEW_NARRATIVE.md` — the cheatsheet for what to say in each interview round.
- Record a 5-minute Loom walkthrough.

**Deliverable:** A shareable GitHub link with a working demo, a clean README, a video, and a set of design-decision artifacts in `docs/`.

---

## 8. The expansion arc (designed for, not built)

The ontology is shaped so adding the following requires new code, not rewrites:

- **Long-duration claims (workers' comp, disability):** add `ClaimKind` enum, add LD-specific state branches, add LD-specific agents (TreatmentPlanAgent, ReturnToWorkAgent). The bitemporal Reserve model already handles long-tail revisions natively.
- **Third-party / subrogation flows:** SubroDetectionAgent is in the slice; the SubroOpened state branch needs SubroNegotiationAgent + a vendor-facing handoff loop.
- **Carrier integration (Guidewire / CCC):** the EntityResolution table is the seam. Source-system adapters write into raw.* with a `source_system` column; the resolution logic stays unchanged.
- **Property (FEMA NFIP) as second domain:** add an IngestionAdapter for NFIP, add property-specific Coverage types, reuse the entire state machine and agent set.

The interview talking point: *"the slice is auto/property because it ships in 3 weekends, but the ontology and the topology are designed so the long-duration version — where the $730M value is — is a v2 feature add, not a v2 rewrite."*

---

## 9. Risks and what we'll do about them

| Risk | Mitigation |
|---|---|
| NHTSA FARS is biased toward fatal crashes; severity distribution is unrealistic | Sample 20% of FARS, generate the remaining 80% of the synthetic claim book to mimic a real auto severity distribution. Flag this in README. |
| Synthetic FNOL transcripts may be too clean; the extraction agent looks better than it would on real audio transcripts | Bake intentional ambiguity, false starts, and self-corrections into the prompt. Hold out 10 cases with extreme messiness as a stress eval. |
| LLM judge collapses on subjective rubric items | Anchor the rubric with concrete examples per score. Track inter-judge agreement (run the judge twice on the same case, expect agreement). |
| 2–3 weekend estimate is optimistic | Weekend 3 is the cut line. If WK2 ends and the agent loop isn't end-to-end, drop the SubroDetectionAgent and use WK3 for polish. |
| Streamlit demo crashes during interview | Pre-record the Loom; it's the fallback. Demo from local DuckDB, no network deps. |
| "Why aren't you using LangGraph/CrewAI" interviewer question | Prepared answer: deliberately rolling primitives shows the architectural understanding the framework would hide. |

---

## 10. Interview narrative (what each artifact proves)

| Interview moment | The artifact that wins it |
|---|---|
| Palantir ontology round | Walk through `app/ontology.py` and explain PartyRole, bitemporal Reserve, Handoff-as-entity. Pull up the invariants. |
| Palantir SQL round | Open `mart_peer_reserve_comparison.sql` and `mart_stalled_claims.sql`. Read aloud and explain the window functions. |
| Palantir system-design round | Whiteboard the state machine + agent-at-boundaries diagram. Defend why the deterministic spine is the governance layer. |
| AI PM — problem framing | PRD + the persona-bottleneck section. The "swivel chair" diagnosis. |
| AI PM — AI architecture | The four agents, their confidence floors, their escalation paths. The "LLM at named boundaries, not as orchestrator" framing. |
| AI PM — failure modes + evals | Open `evals/golden/` and the LLM-judge rubric. Show the human-in-loop → golden case feedback loop. |
| AI PM — go-to-market thinking | The market analysis doc: TPA-first wedge, segment expansion to long-duration, integration as the moat. |

---

## 11. Open questions deferred to build time

These do NOT block starting; we'll decide when we hit them.

- How many synthetic claims is enough to make the peer-comparison query meaningful? Start with 200; raise to 1000 if cohorts feel sparse.
- Do we use Pydantic-AI for typed tool-use or hand-write the JSON schema → validator path? Lean hand-written for legibility; revisit if it's >100 lines.
- Should the dashboard include a "explain this AgentAction" expander that calls the LLM live? Nice-to-have; only if WK3 has slack.
- Do we publish the synthetic-claim generator as its own mini-tool? Yes if it's a clean module; no if it stays tangled with pipeline code.

---

*End of plan. Approve, push back, or amend before any code is written.*
