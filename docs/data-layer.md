---
tags:
  - project/argos
  - type/data-layer
  - status/draft
created: 2026-05-28
updated: 2026-05-28
aliases:
  - Data Layer Design
---

# Data Layer — what we use, what we synthesize, what shape it lands in

> Companion to [THESIS.md](./THESIS.md), [STRATEGY.md](./STRATEGY.md), [TECH_PLAN.md](./TECH_PLAN.md), and the architecture docs.

---

## §1 — Purpose

This document defines:

1. **What data we use.** Public datasets that supply realistic loss events for auto and (narrowed) property.
2. **What we synthesize.** Everything that makes a loss event into a *claim* — the insured portfolio it emerges from, parties, coverage, reserves over time, payments, recoveries, documents, lifecycle, configuration, and ground truth.
3. **How we evaluate.** A layered truth model that separates objectively-labelable facts from contestable professional judgment, with a cross-cutting calibration layer for the probability-shaped specialist outputs.

---

## §2 — What we have: the public data foundation

### NHTSA FARS 2023 — the catastrophic-fatal auto tail

- **What it is.** Federal census of every police-reported fatal motor vehicle crash on a US public road. Maintained by NHTSA, refreshed annually.
- **Shape.** 33 tables, ~37K crashes, ~58K vehicles, ~93K persons. Composite keys: `ST_CASE`, `(ST_CASE, VEH_NO)`, `(ST_CASE, VEH_NO, PER_NO)`.
- **What it gives us.** Geographic-precise (lat/long, route, milepost) fatal-crash facts: who, where, when, severity, conditions, vehicle, driver conduct. Real composite-key joins.
- **Loaded at:** `data/fars.duckdb`, schema `fars2023`.
- **Role and caveat.** FARS is 100% fatal. We use it for the **wrongful-death** scenario family — a distinct claim type with its own dynamics (estate representatives, early excess notice, litigation likelihood, policy-limits exposure, fatality-specific documentation). We do not use FARS as a generic "catastrophic auto" tail. FARS-sourced claims are tagged `scenario_family=fatality`. Multi-vehicle FARS events (where one `ST_CASE` has 2+ involved vehicles across separately-insured parties) are deliberately surfaced — they become shared-`LossOccurrence` multi-claim cases (§4 step 1).

### NHTSA CRSS 2023 — the realistic auto severity distribution

- **What it is.** Nationally representative probability sample of all police-reported crashes. Replaces NASS GES.
- **Shape.** 28 tables, ~50K sampled crashes, weighted to ~6.1M nationally. Same composite-key structure as FARS with `ST_CASE` → `CASENUM`.
- **CRSS severity mix.** 70.5% PDO, 13.4% possible injury, 10.0% suspected minor, 2.3% suspected serious, 0.6% fatal. Non-fatal injury subtotal: 25.7%.
- **Loaded at:** `data/crss.duckdb`, schema `crss2023`.
- **Role and caveat.** CRSS is *police-reported crashes*, not *insurance claims*. We use CRSS to calibrate the auto severity distribution and crash-fact templates for losses sampled into a synthetic portfolio (§4), not as the portfolio itself.

### FEMA NFIP Redacted Claims — the property money + coverage anchor (flood-scoped)

- **What it is.** Every flood insurance claim filed under the federal National Flood Insurance Program.
- **Shape.** 1 table, 1.54M rows, 73 columns. Date range 1978-01-01 → 2026-04-28.
- **What it gives us.** Real dollars (median paid building $12K, p95 $144K, total $41.3B), coverage limits, deductibles, statutory caps, named CAT tagging.
- **Loaded at:** `data/nfip.duckdb`, schema `main_nfip`.
- **Scope decision.** Property is **flood-only** for this build — NFIP can't anchor private-property fire/wind/theft/burst-pipe credibly.
- **Client archetype split.** The four target archetypes (self-insured corporate, captive, carrier outsource, MGA) are what the "per-customer configuration is the moat" thesis is exercised on. WYO is a federally-mandated workflow, not customer-configurable, so it sits as a **demo-only flood branch** that exercises cross-LOB ontology reuse without claiming it as a buyer surface. See §4 step 0.

### Foundation summary

| Source | Role | What it gives | What it doesn't |
|---|---|---|---|
| FARS 2023 | Fatality scenario family (auto); multi-vehicle shared-occurrence cases | Geographic-precise fatal crash facts; multi-party FARS events | Anything non-fatal; anything claim-shaped |
| CRSS 2023 | Severity calibration (auto) | Realistic crash-severity mix; non-fatal crash facts | Insurance-portfolio shape; geographic precision |
| NFIP | Money + coverage anchor (flood property, demo branch) | Real dollars, real coverage limits, real CAT tagging | Lifecycle dates; non-flood property |

---

## §3 — The gap: what we have to synthesize

| What the public data gives us | What we synthesize |
|---|---|
| Loss-event facts (who/what/where/when/severity) | The **insured portfolio** the loss emerges from (vehicles, properties, jurisdictions, operating territory) — see §4 step 0 |
| Vehicle / property identification | Pre-loss ACV, repair-vs-total-loss decision, scope of repair, restoration plan |
| Injury severity (KABCO) | Medical bills, treatment timeline, provider records, lien chronology |
| Persons involved | Parties cast as policyholders / claimants / witnesses / attorneys / vendors, with multi-role support |
| Crash facts / cause of loss | **Liability allocation** — modeled as versioned `LiabilityAssessment` (§5), not a static status |
| — | `Policy`, `PolicyPeriod`, `CoveragePart`, `CoverageLayer`, SIR, excess tower, reinsurance attachment |
| — | `ClaimExposure` decomposition (one claim → multiple exposures, each with own reserve / payment / recovery / closure state) |
| — | `FinancialTransaction` + `FinancialPosting` ledger (balanced postings against named accounts — see §5) |
| — | Bitemporal financial history (`effective_at` × `recorded_at`, per §5) |
| — | Claim lifecycle as **disambiguated status dimensions** (six on the exposure + one on the claim), with explicit illegal-combination matrix |
| — | **All unstructured documents** |
| — | **Inconsistency and noise across documents** — LLM-injected at generation, then deterministically fuzzed by a Python post-pass (§4 step 6) |
| — | Recovery taxonomy (subrogation, salvage, contribution, deductible recovery, reinsurance reimbursement) |
| — | The client program assignment + per-customer configuration (authority matrix, notice rules, compliance obligations) |
| — | Federal compliance entities — `MedicareReportingStatus` (modeled at shape level only), `Lien`, MSA exposure |
| — | Claim-level `AggregateLimitsTracker` so per-occurrence limit erosion across exposures is visible |

---

## §4 — The synthesis pipeline (portfolio-first, with liability, yield-validated, and fuzzed)

### Step 0 — Generate synthetic client portfolios

For each of N synthetic TPA clients, generate the insured portfolio *before* sampling any loss. For the demo, **4 client programs** (restored to original strategy alignment):

1. **"Northwind Logistics"** — self-insured corporate trucking fleet. ~200 tractors and 280 trailers across 8 states. SIR $250K per occurrence, excess tower attaching above SIR up to $25M. Auto (commercial).
2. **"Pinnacle Captive"** — single-parent captive for a hospitality-real-estate parent. ~120 owned and managed properties across 12 states. Captive layer $1M per occurrence, fronting carrier above. **Property is architecture-ready but not empirically exercised** (the NFIP-flood data anchor can't realistically populate a generic private-property captive book — see §10 limitation). The Pinnacle config and ontology rows exist; the synthetic claim book for Pinnacle is not generated.
3. **"Sentinel Mutual"** — regional carrier outsourcing personal auto claims to the TPA. ~50K policies-in-force across 4 states. Reinsurance attaching at $500K.
4. **"RoadMile Underwriters"** — non-standard auto MGA. ~30K policies across 6 states. Carrier behind the MGA dictates handling rules.

**Plus one demo-only branch:**

5. **"Coastal WYO Group"** — Write-Your-Own flood carrier. ~15K residential and small-commercial flood policies across FL/TX/LA/NC/SC. **Status: demo-only, not a target archetype.** WYO workflow is FEMA-mandated; it exercises cross-LOB ontology reuse and shows the system handling a federally-governed handling regime, but it does *not* demonstrate the "per-customer configuration is the moat" thesis (that thesis is exercised by the four archetypes above). The demo narrative is explicit about this distinction.

Each portfolio carries: jurisdictions, insured units (vehicles or properties), policy structure, claims-frequency expectation, and the per-specialist configuration (§6).

### Step 0.5 — Yield validation

Before locking the four portfolios + flood branch, empirically count FARS/CRSS rows surviving each portfolio's filter:

- Northwind: CRSS rows where vehicle body type ∈ {commercial truck, tractor-trailer} AND state ∈ Northwind's 8 — required minimum: 800+ rows to support 150 distinct synthetic claims
- Sentinel: CRSS personal-auto rows in Sentinel's 4 states — required minimum: 1500+ rows
- RoadMile: CRSS rows representing the non-standard auto risk profile (younger drivers, older vehicles, urban areas) in 6 states — required minimum: 1000+ rows
- Coastal WYO: NFIP rows in FL/TX/LA/NC/SC with residential or small-commercial occupancy — yield is not at risk (1M+ rows)

**Gate:** if any portfolio's yield is below 5× target claim count, broaden the portfolio (more states, broader vehicle types) until threshold passes. Document the actual yield in the run log.

### Step 1 — Sample loss events into the portfolio

For each synthetic claim slot, sample a loss event *that could plausibly occur to a unit in the portfolio* per the yield-validated filters. Auto sampling uses CRSS for severity-distribution shape and FARS for the fatality-tagged subset.

**Multi-vehicle shared-occurrence.** For ~5-10% of claims, sample a FARS event with 2+ involved vehicles where the vehicles plausibly belong to separately-insured parties. These produce one `LossOccurrence` linked to multiple `Claim` records (one per involved insured) across multiple `ClientProgram` rows. This makes `LossOccurrence` non-trivial and gives the FDE-loop demo the "one event, many claims, traversal across policies" surface. Without it, `LossOccurrence` is pure indirection on `Claim`.

### Step 2 — Cast parties (with multi-role support)

Parties hold multiple roles via `ClaimPartyRole`.

### Step 3 — Determine liability (auto) / causation (flood)

Liability is generated as a `LiabilityAssessment` row (versioned, not a status field). Each assessment carries:
- Allocation percentages per involved party
- Assessment status (preliminary / revised / final / disputed)
- Effective date
- Author (party_id of the adjuster or specialist who set it)
- Basis (which documents supported the allocation)

Real claims revise liability multiple times as new evidence arrives; we model this as a sequence of assessments, not a single field.

For flood: causation assignment (flood-only / flood-plus-wind / non-covered).

### Step 4 — Apply coverage from the client's program

Generate Policy → PolicyPeriod → CoveragePart → CoverageLayer rows from the client's program template.

### Step 5 — Generate the claim timeline

Two clarifications:

- **Per-exposure reserves.** One BI reserve per injured claimant exposure (not one BI reserve for the claim). Initial reserves are written as `FinancialTransaction` rows of kind `reserve_revision` with a single `outstanding_indemnity +X` posting (§5).
- **Payment lifecycle is event-log, not financial-ledger.** A payment request, issuance, clearing, and voiding are tracked as `Event` rows. Only the cleared cash event produces a `FinancialTransaction` of kind `indemnity_payment` (or `expense_payment`) with two balanced postings.

### Step 6 — Generate the unstructured documents (with deliberate inconsistency + programmatic fuzzing)

Three-pass document generation:

**Pass 1: LLM seed-fact generation.** Generate clean documents from the claim's structured facts.

**Pass 2: LLM noise injection.** Separate prompt template, different from Pass 1. Introduces:
- Contradictions across sources (insured vs claimant vs police report)
- Inferred-not-stated facts (representation arrives via letter; lien arrives via notice)
- Late and missing documents
- ~5% wrong-claim or duplicate documents
- Inconsistent name spellings ("Robert Smith" / "Bob Smith" / "R. Smith")
- Format heterogeneity in adjuster notes

**Pass 3: Programmatic Python fuzzing.** A Python post-pass applied after both LLM passes. LLMs are bad at mundane noise — they generate cartoonish errors ("died Tuesday, walked into clinic Thursday") rather than the structural noise real claim files have. Python fuzzing adds:
- Random character drops (~0.3% of chars in long-form text)
- Inconsistent date formats across documents (`12/15/2024` / `2024-12-15` / `Dec 15 2024` / `15-Dec-24`)
- OCR-style substitutions (0↔O, 1↔l↔I, S↔5, B↔8) in scanned-document approximations
- Occasional truncated text blocks (simulating a missing page)
- Misspelled names with consistent typos within a document, varying across documents

This pass is deterministic given a seed and is excluded from the eval-set holdouts (otherwise the eval learns the fuzz pattern).

### Step 7 — Embed ground truth (layered truth model — see §7)

At synthesis time, Layer A (latent world state) and Layer C-statutory (statutory facts) are written. Layer C-policy (config-derived facts), Layer B (observed file state), and Layer D (judgment labels) are derived later by separate mechanisms.

---

## §5 — Ontology schema

The substrate is a relational ontology stored in the [TECH_PLAN.md](./TECH_PLAN.md)'s chosen Foundry layer. The schema reshapes the financial ledger as a transaction-header + balanced-postings model, treats liability as versioned assessments, aggregates limits across exposures, disambiguates status fields into seven independent dimensions, and explicitly marks which entities are built first vs deferred to schema-only.

### Build scope marker

**Built first** (prove the specialists traverse it live):
- ClientProgram, Policy, PolicyPeriod, CoveragePart, CoverageLayer
- LossOccurrence, Claim, ClaimExposure
- Party, ClaimPartyRole
- LiabilityAssessment
- FinancialTransaction, FinancialPosting
- AggregateLimitsTracker
- Recovery (single-exposure attachment)
- Document, DocumentAssociation
- Event log
- DiaryTask, AuthorityRequest (with `parent_request_id`), AuthorityDecision
- NoticeObligation (basic structure)
- Lien (basic structure)
- SpecialistConfig
- RiskUnit (insured assets only — claimant assets modeled implicitly via `Party` and `ClaimExposure.claimant_party_id`)

**Schema-only, operational logic deferred** (model the shape so the ontology survives stress test, but do not build the runtime behavior):
- `MedicareReportingStatus` — model the existence-of-obligation detection so Closure can flag it; do *not* build Section 111 EDI filing logic. CMS reporting is a labyrinthine compliance project that distracts from the AI value prop.
- `Disbursement` + `DisbursementAllocation` — single-exposure payment attachment suffices for the demo. Multi-exposure settlement check allocation is out of scope.
- `Organization` + `Program` + `HandlingAgreement` separation — `ClientProgram` is sufficient. Architecturally correct decomposition is out of scope.
- `Asset` separated from `InsuredRiskUnit` — `RiskUnit` (insured-only) + claimant party references suffice. Third-party asset entity is out of scope.
- `RecoveryMatter` + `RecoveryAllocation` — single-exposure recovery suffices for the demo.

The build follows the slice. The diagram includes the deferred entities so the ontology shows the future-state shape — but no code populates them.

### Portfolio layer

```
ClientProgram
  client_program_id (PK)
  client_name
  client_type (enum: self_insured_corp, captive, carrier_outsource, MGA, WYO_demo_only)
  lines_handled (auto, flood, both)
  effective_period (valid_from, valid_to)
  handling_agreement_summary
  is_empirically_exercised_in_v1 (bool)  // false for Pinnacle Captive

Policy
  policy_id (PK)
  client_program_id (FK)
  policy_number
  named_insured_party_id (FK → Party)
  policy_form (e.g., CA00 commercial auto, NFIP SFIP residential)
  jurisdiction_state

PolicyPeriod
  policy_period_id (PK)
  policy_id (FK)
  effective_from
  effective_to
  status (in_force, expired, cancelled, non_renewed)

CoveragePart
  coverage_part_id (PK)
  policy_period_id (FK)
  coverage_type (enum: auto_BI, auto_PD, auto_UM_UIM, auto_collision, auto_comprehensive,
                       auto_medpay, auto_rental, flood_building, flood_contents, flood_ICC)
  limit_per_occurrence
  limit_per_person (nullable — BI)
  limit_aggregate (nullable)
  deductible
  SIR
  sublimits_json
  exclusions_json

CoverageLayer
  coverage_layer_id (PK)
  policy_period_id (FK)
  layer_type (enum: primary, SIR, excess, reinsurance, captive_layer)
  attachment_point
  layer_limit
  carrier_party_id (nullable for SIR/captive layer)
  reporting_threshold
  reporting_deadline_days

RiskUnit  // insured vehicle or property only
  risk_unit_id (PK)
  policy_period_id (FK)
  unit_type (enum: vehicle, property)
  unit_details_json
```

### Claim layer

```
LossOccurrence  // one event; may produce multiple claims across multiple policies
  loss_occurrence_id (PK)
  date_of_loss
  jurisdiction_state
  loss_facts_json
  source_event_id  // FK to FARS/CRSS/NFIP source
  scenario_family (enum: fatality_auto, severe_BI_auto, moderate_BI_auto, PDO_auto,
                         flood_residential, flood_commercial, flood_with_wind_dispute,
                         multi_vehicle_shared_occurrence)

Claim
  claim_id (PK)
  client_program_id (FK)
  loss_occurrence_id (FK)
  policy_period_id (FK)
  fnol_date
  fnol_reporter_party_id (FK → Party)
  lifecycle_status (enum: open, administratively_closed, reopened)  // claim-level only

ClaimExposure  // financial/operational pivot
  exposure_id (PK)
  claim_id (FK)
  coverage_part_id (FK)
  claimant_party_id (FK → Party — for BI/liability; null for first-party physical damage)
  damaged_risk_unit_id (FK → RiskUnit — for property/collision; null for BI)
  exposure_type (enum: auto_BI_claimant, auto_PD_claimant, auto_UM_first_party,
                       auto_collision_first_party, auto_medpay_first_party,
                       flood_building_first_party, flood_contents_first_party, flood_ICC)

  // Seven disambiguated status dimensions — see illegal-combination matrix below
  coverage_status (enum: pending, accepted, denied, reservation_of_rights)
  handling_status (enum: open_investigation, in_negotiation, settled, withdrawn, closed)
  settlement_status (enum: not_applicable, in_progress, executed_release, paid_in_full)
  representation_status (enum: unrepresented, represented)
  litigation_status (enum: none, suit_filed, in_discovery, in_mediation, in_trial, resolved, dismissed)
  recovery_status (enum: not_screened, no_potential, potential, pursuing, settled, abandoned, closed)
  financial_status (enum: no_payment_due, reserves_outstanding, partially_paid, paid, reconciled)
```

**Why disambiguation matters.** A single `resolution_status=accepted` would be ambiguous (coverage accepted? liability accepted? handling accepted? settlement accepted?). Each is a separate field.

### Illegal-combination matrix

These combinations are invalid and must be rejected at write time:

| Field A | Value | Field B | Value | Rule |
|---|---|---|---|---|
| coverage_status | denied | financial_status | partially_paid OR paid | No payment without coverage |
| handling_status | closed | financial_status | reserves_outstanding | Closure requires zero outstanding |
| handling_status | closed | recovery_status | pursuing | Recovery must resolve before closure |
| handling_status | closed | litigation_status | in_discovery / in_mediation / in_trial | Pending litigation blocks closure |
| settlement_status | executed_release | handling_status | open_investigation | Release implies handling concluded |
| recovery_status | settled | handling_status | open_investigation | Recovery resolution implies primary handling resolved |

Combinations that *look* contradictory but are valid:

| Combination | Why valid |
|---|---|
| handling_status=settled + litigation_status=suit_filed | Matter settled; dismissal paperwork pending |
| representation_status=unrepresented + litigation_status=suit_filed | Pro se litigant — rare but real |
| coverage_status=reservation_of_rights + financial_status=partially_paid | Defense provided under ROR while coverage dispute continues |

Transition guards apply per-dimension (e.g., `litigation_status` cannot skip from `none` directly to `in_trial`; must pass through `suit_filed` and `in_discovery`).

### Liability layer

Versioned, not a status. Real liability is revised as new evidence arrives.

```
LiabilityAssessment
  assessment_id (PK)
  exposure_id (FK)
  insured_fault_pct
  claimant_fault_pct
  other_party_fault_pct (nullable — multi-party crashes)
  comparative_fault_rule (enum: pure, modified_50, modified_51, contributory)
  assessment_status (enum: preliminary, revised, final, disputed)
  assessed_at
  assessed_by_party_id (FK)
  basis_document_ids (array)
  rationale_text
  superseded_by_assessment_id (FK, nullable)
```

### Party layer

```
Party
  party_id (PK)
  party_type (enum: individual, organization, attorney_firm, vendor, carrier, government)
  display_name
  contact_info_json

ClaimPartyRole
  role_id (PK)
  claim_id (FK)
  party_id (FK)
  role (enum: named_insured, additional_insured, insured_driver, claimant, witness,
              attorney_for_claimant, attorney_for_insured, defense_counsel,
              mortgagee, public_adjuster, contractor, IME_provider, accident_reconstructionist,
              repair_shop, tow_operator, independent_adjuster)
  applies_to_exposure_id (FK, nullable)
  effective_from
  effective_to (nullable)
```

### Financial ledger

A single `Transaction` table with one signed `amount_delta` would be single-entry; `Incurred = Paid + Outstanding` would not be preserved by construction. The ledger uses a transaction-header + balanced-postings model.

```
FinancialTransaction  // the header — one row per accounting event
  transaction_id (PK)
  exposure_id (FK)  // every financial event is exposure-scoped
  transaction_kind (enum: reserve_revision, indemnity_payment, expense_payment,
                          recovery_received, recovery_anticipated_change,
                          transfer_between_components, correction_reversal)
  effective_at  // business-effective time (valid time)
  recorded_at   // system time
  source_document_id (FK → Document, nullable)
  authority_decision_id (FK → AuthorityDecision, nullable)
  rationale_text
  reverses_transaction_id (FK, nullable)  // for corrections; preserves audit trail

FinancialPosting  // the balanced legs — one or more rows per transaction
  posting_id (PK)
  transaction_id (FK)
  account (enum: outstanding_indemnity, paid_indemnity,
                 outstanding_ALAE, paid_ALAE,
                 outstanding_ULAE, paid_ULAE,
                 outstanding_ALE, paid_ALE,
                 anticipated_subro, received_subro,
                 anticipated_salvage, received_salvage,
                 deductible_billable, deductible_recovered,
                 ceded_recoverable)
  amount_delta  // signed
  component (enum: indemnity, ALAE, ULAE, ALE, expert_fees, defense, mitigation)
  gross_net_basis (enum: gross, net_of_recovery, net_of_deductible, net_of_SIR, net_of_excess)
```

**Posting rules per transaction kind:**

| `transaction_kind` | Required postings |
|---|---|
| `reserve_revision` | One: `outstanding_<component> ± X` |
| `indemnity_payment` | Two balanced: `paid_indemnity +X` AND `outstanding_indemnity -X` |
| `expense_payment` | Two balanced: `paid_ALAE +X` AND `outstanding_ALAE -X` (or same pattern for ULAE/ALE) |
| `recovery_anticipated_change` | One: `anticipated_subro ± X` (or salvage) |
| `recovery_received` | Two: `received_subro +X` AND `anticipated_subro -X` (zeros out anticipation when realized) |
| `transfer_between_components` | Two balanced: `outstanding_<from> -X` AND `outstanding_<to> +X` |
| `correction_reversal` | Mirrors the postings of the transaction it reverses with inverted signs |

The constraint is enforced at write time (a Python validation layer on every `FinancialTransaction` insert verifies the posting set matches the kind's required pattern). The accounting identity `Incurred = Paid + Outstanding` holds by construction across any sequence of valid transactions.

**Payment lifecycle is NOT in the ledger.** A payment going through request → approval → check issued → check cleared → check voided is an *operational* sequence, captured as `Event` rows. The financial ledger only sees the cleared cash event (which writes one `indemnity_payment` or `expense_payment` `FinancialTransaction`). If a cleared check is later voided, that writes a `correction_reversal` with inverted postings — the original financial event is never edited or supersession-flagged; the audit trail shows both events.

**True bitemporality.** `effective_at` is when the transaction is effective in the claim's business timeline; `recorded_at` is when the system recorded it. Together they support backdated entries, corrections, audit restatements, and as-of-then-from-now loss runs. Querying as-of-any-pair is mediated by the `get_financials_as_of(exposure_id, as_of_effective, as_of_recorded)` Python tool (§9) — specialists do not write bitemporal SQL.

**Derived snapshot view.**

```
ExposureSnapshot  // computed, not source-of-truth
  exposure_id
  component
  outstanding
  paid_to_date
  recovered_to_date
  incurred  // = paid + outstanding
  ultimate_projected
  as_of_effective_time
  as_of_recorded_time
```

### Aggregate limits tracker

Per-occurrence and aggregate limits live on `CoveragePart`. With multi-exposure claims, specialists at the exposure level can't see when sibling exposures have eroded the shared limit. The tracker rolls this up at the claim level.

```
AggregateLimitsTracker
  tracker_id (PK)
  claim_id (FK)
  coverage_part_id (FK)
  limit_basis (enum: per_occurrence, per_person, aggregate, per_loss)
  limit_amount
  consumed_amount  // computed: SUM(paid + outstanding) across child exposures
  remaining_amount  // computed
  breach_status (enum: under_limit, approaching_limit, at_limit, breached)
  approaching_threshold_pct  // e.g., 0.85 = warn at 85% consumed
```

Maintained as a view computed from `FinancialPosting` rows on the relevant exposures.

### Recovery

```
Recovery  // single-exposure attachment
  recovery_id (PK)
  exposure_id (FK)
  recovery_type (enum: subrogation, salvage, contribution, deductible_recovery,
                       restitution, reinsurance_reimbursement)
  status (enum: potential, referred, demanded, in_arbitration, in_litigation, recovered, abandoned)
  adverse_party_id (FK → Party, nullable)
  adverse_carrier_party_id (FK → Party, nullable)
  estimated_gross_amount
  recovered_gross_amount (nullable)
  recovery_costs (nullable)
  net_recovery_to_client (computed)
  statute_of_limitations_date  // populated only when SOL rule is sourced (§6)
  evidence_preservation_status (enum: secured, at_risk, lost)
  made_whole_status (enum: not_applicable, not_made_whole, made_whole)
```

Multi-exposure recovery allocation (`RecoveryMatter` + `RecoveryAllocation`) is out of scope.

### Documents + associations

```
Document
  document_id (PK)
  claim_id (FK)  // primary claim association — most documents
  document_type (enum: see expanded list below)
  received_date
  source (enum: insured, claimant, attorney, vendor, third_party, system_generated,
                adverse_carrier, government, court, medical_provider)
  file_path
  is_synthetic (bool — never exposed to specialists; see §7)

DocumentAssociation  // cross-exposure linkage
  association_id (PK)
  document_id (FK)
  entity_type (enum: occurrence, claim, exposure, party, recovery, lien, notice)
  entity_id
  association_type (enum: primary_subject, evidence_of, related_to, supersedes)

DocumentExtraction  // specialists' read of a document — not source-of-truth
  extraction_id (PK)
  document_id (FK)
  extracted_by (enum: specialist_reserve, specialist_recovery, specialist_closure, human)
  extracted_at
  extracted_fields_json
  confidence_per_field_json
  extraction_prompt_version
```

Document types: police_report, recorded_statement, medical_record, medical_bill, repair_estimate, contractor_estimate, demand_package, inspection_report, photos, adjuster_notes, ALE_receipts, NFIP_proof_of_loss, proof_of_loss, reservation_of_rights_letter, coverage_analysis_memo, subrogation_demand, lien_notice, hospital_lien, attorney_letter_of_representation, IME_report, mediation_brief, settlement_release, denial_letter.

### Operational entities

```
DiaryTask
  diary_id (PK)
  exposure_id (FK)
  task_type (enum: follow_up, document_request, payment_processing, notice_send,
                   reserve_review, recovery_review, closure_review)
  due_date
  assigned_to_party_id (FK → Party)
  status (enum: open, completed, overdue, cancelled)

AuthorityRequest
  request_id (PK)
  exposure_id (FK)
  requested_action (enum: reserve_change, payment_authorize, settlement_authorize,
                          counsel_assign, expert_engage, recovery_pursue, recovery_waive, close)
  requested_amount (nullable)
  requested_by_party_id (FK)
  required_approver_level (enum: handler, supervisor, manager, client)
  parent_request_id (FK, nullable — escalation chain)
  status (enum: pending, approved, denied, escalated)

AuthorityDecision
  decision_id (PK)
  request_id (FK)
  decided_by_party_id (FK)
  decision (enum: approved, denied, partially_approved, escalated)
  decision_amount (nullable)
  rationale_text
  decided_at

NoticeObligation
  notice_id (PK)
  exposure_id (FK)
  notice_type (enum: excess_carrier, reinsurer, client, DOI, court, Medicare_Section_111)
  triggered_by_event_id (FK)
  required_by_date
  delivered_at (nullable)
  delivery_method (enum: email, certified_mail, portal_upload)
  delivery_confirmation (nullable)
```

### Compliance entities (shape-only)

```
Lien
  lien_id (PK)
  exposure_id (FK)
  lien_type (enum: hospital, medical_provider, ERISA, Medicare_conditional_payment,
                   Medicaid, attorney, child_support, workers_comp)
  lienholder_party_id (FK → Party)
  asserted_amount
  resolved_amount (nullable)
  status (enum: open, negotiated, paid, disputed, waived)
  notice_received_date

MedicareReportingStatus  // shape modeled for Closure to detect obligation; not a functioning S111 filer
  reporting_id (PK)
  exposure_id (FK)
  claimant_medicare_eligible (bool)
  ORM_status (enum: not_applicable, ongoing, terminated)
  TPOC_required (bool, nullable)
  TPOC_amount (nullable)
  MSA_required (bool, nullable)
  reporting_responsible_party_id (FK → Party — always set to client; not enforced)
  scope_note: "Shape-only entity. Closure specialist detects 'reporting obligation exists.' Federal filing logic is out of scope — see §10 limitation 8."
```

### Event log

```
Event
  event_id (PK)
  claim_id (FK)
  exposure_id (FK, nullable)
  event_type (enum: fnol, coverage_determined, exposure_added, liability_assessed,
                    financial_transaction_recorded, document_received,
                    authority_requested, authority_decided,
                    payment_requested, payment_issued, payment_cleared, payment_voided,
                    statement_taken, notice_triggered, notice_delivered,
                    litigation_event, recovery_identified, recovery_referred, lien_received,
                    closure_attempted, closure_completed, file_reopened)
  occurred_at  // business-effective time
  recorded_at  // system time
  triggered_by (party_id, specialist_id, or 'system')
  details_json
```

Note: `payment_requested`/`payment_issued`/`payment_cleared`/`payment_voided` are *event-log entries only*. Only `payment_cleared` triggers a `FinancialTransaction` (and `payment_voided` triggers a `correction_reversal`).

### AI provenance entities

Two first-class entities back the AI side of the substrate. They are populated by the Railway specialists writing through Action Types and are queryable for audit, eval, and workspace rendering.

```
AgentAction  // the audit row for every specialist invocation
  agent_action_id (PK)
  specialist (enum: brief, coverage, liability, reserve, recovery, closure)
  exposure_id (FK, nullable — Brief refreshes are claim-scoped)
  claim_id (FK)
  prompt_version
  model_id  // e.g., claude-sonnet-4-6
  input_hash  // SHA256 of the structured input the specialist saw
  input_snapshot_path  // pointer to Foundry Dataset where the full input is stored
  output_json  // the validated LegallyBearingClaim or ClaimBrief output
  reasoning_trace
  triggered_by (party_id or 'system' or 'event:<event_id>')
  triggered_at
  status (enum: proposed_pending_approval, auto_applied, human_approved,
                human_rejected, schema_violation, schema_violation_missing_citations,
                schema_violation_distribution_invalid, llm_refusal)
  escalation_outcome (enum: applied_automatically, approved_by_human,
                            rejected_by_human, routed_to_authority_chain)
  approved_by_party_id (FK, nullable)
  approved_at (nullable)

EvidenceCitation  // every probabilistic claim a specialist makes points at one or more of these
  citation_id (PK)
  agent_action_id (FK)
  document_id (FK → Document, nullable)
  sourced_rule_id (FK → SpecialistConfig.sourced_legal_rules, nullable)
  ledger_entry_id (FK → FinancialTransaction, nullable)
  // exactly one of document_id, sourced_rule_id, ledger_entry_id is populated
  locator  // page, paragraph, section, field, or row identifier
  text_excerpt  // what the cited source says
  relation (enum: supports, refutes, contextual)
  claim_text  // the specialist's claim that this citation backs
  probability (nullable)  // the probability the cited claim carries, if applicable
```

**Why EvidenceCitation is a first-class object, not just JSON inside `AgentAction.output_json`:**

1. **Calibration eval needs it queryable.** "Across all AgentActions where the specialist claimed P(coverage applies) = 80%, what fraction resolved as clean coverage?" is a SQL query against citations and their associated claims, not a JSON-walk per action.
2. **Audit needs it linkable.** When the workspace renders a Coverage analysis, it shows each evidence row as a clickable link to the source Document. The link target needs to be a foreign key, not an embedded string.
3. **Hallucinated-citation detection needs it auditable.** A specialist could output a citation pointing at a `document_id` that doesn't exist on the exposure. Post-processing verifies each EvidenceCitation row's target exists in Layer B; rows pointing at hallucinated sources are dropped before the AgentAction is finalized. A first-class row makes this enforceable.
4. **The Pydantic contract requires it.** The output schema (`AGENT_ARCHITECTURE.md §3.2`) requires `min_length=1` on `evidence_citations` for every `ProbabilisticClaim`. Persisting them as queryable rows is the substrate-side complement.

**Foundry implementation:**
- `AgentAction` is a Foundry object type written via `EmitAgentAction` Action Type
- `EvidenceCitation` is a Foundry object type written via the same Action Type (atomic with the AgentAction)
- Link types: `AgentAction → EvidenceCitation (1:many)`; `EvidenceCitation → Document | SourcedLegalRule | FinancialTransaction (many:1)`
- The Action Type validator rejects an AgentAction whose `output_json` claims probabilities without matching EvidenceCitation rows

### Configuration entity

```
SpecialistConfig
  config_id (PK)
  client_program_id (FK)
  specialist (enum: brief, coverage, liability, reserve, recovery, closure)
  config_json  // specialist-specific schema (§6)
  effective_from
  effective_to (nullable)
  approved_by  // who at the client signed off
```

---

## §6 — Configuration schema (sourced legal rules, authority matrix)

Unsourced legal rules are a trap (e.g., Florida PI/PD SOL at 4 years is wrong post-2023 — current Florida Statutes §95.11 governs contemporary negligence at 2 years post-March 2023). This config carries a small set of *sourced* rules with citation and effective-from date, and marks the rest as `validation_status: unvalidated`.

### Reserve specialist config

```json
{
  "material_event_definitions": [
    {"trigger": "medical_bills_received_total", "threshold": 5000, "action": "review"},
    {"trigger": "attorney_representation_filed", "action": "step_up_to_demand_estimate"},
    {"trigger": "demand_package_received", "action": "review_within_days_5"},
    {"trigger": "litigation_filed", "action": "review_and_add_ALAE"},
    {"trigger": "supplement_to_repair_estimate", "threshold_pct_of_original": 0.15, "action": "review"},
    {"trigger": "ALE_duration_days", "threshold": 60, "action": "review"},
    {"trigger": "expert_report_received", "action": "review"},
    {"trigger": "policy_limit_demand_received", "action": "escalate_excess_notice"}
  ],

  "authority_matrix": [
    {"action": "reserve_change", "lob": "auto", "component": "indemnity_BI",
     "level": "handler", "max_amount_per_occurrence": 25000},
    {"action": "reserve_change", "lob": "auto", "component": "indemnity_BI",
     "level": "supervisor", "max_amount_per_occurrence": 100000},
    {"action": "reserve_change", "lob": "auto", "component": "indemnity_BI",
     "level": "client_required", "max_amount_per_occurrence": 250000},
    {"action": "reserve_change", "lob": "auto", "component": "indemnity_PD",
     "level": "handler", "max_amount_per_occurrence": 50000},
    {"action": "payment_authorize", "lob": "auto", "component": "indemnity_BI",
     "level": "handler", "max_amount_per_occurrence": 10000}
  ],

  "step_up_rules": {
    "no_stair_stepping": true,
    "set_to_expected_ultimate": true,
    "downward_reserve_requires_approval": true,
    "downward_reserve_approver_level": "supervisor"
  },

  "reporting_thresholds": {
    "large_loss_notice_to_client": {"trigger_basis": "incurred", "amount": 50000, "deadline_days": 1},
    "excess_carrier_notice": {"trigger_basis": "pct_of_SIR", "pct": 0.50, "deadline_days": 5},
    "reinsurance_notice": {"trigger_basis": "pct_of_attachment", "pct": 0.50, "deadline_days": 10}
  },

  "review_cadence_days": 30,
  "minimum_reserve_components_at_open": ["indemnity_BI", "ALAE"],
  "basis": "gross"
}
```

### Recovery specialist config

```json
{
  "minimum_pursuit_threshold": 1500,
  "pursuit_model": "in_house",
  "outsource_vendor_party_id": null,
  "fee_structure": "percentage_of_recovery",
  "fee_percentage": 0.20,
  "deductible_reimbursement_sequencing": "before_recovery_fee",
  "recovery_types_pursued": ["subrogation", "salvage", "contribution", "deductible_recovery"],
  "referral_required_above": 500,

  "sourced_legal_rules": [
    {
      "rule_id": "FL_negligence_SOL_2023",
      "scope": {"jurisdiction": "FL", "cause_of_action": "negligence", "accrual_after": "2023-03-24"},
      "rule": "statute_of_limitations_years",
      "value": 2,
      "source": "Florida Statutes §95.11(3)(a) (as amended HB 837, eff. 2023-03-24)",
      "validation_status": "sourced",
      "effective_from": "2023-03-24"
    },
    {
      "rule_id": "FL_negligence_SOL_pre2023",
      "scope": {"jurisdiction": "FL", "cause_of_action": "negligence", "accrual_before": "2023-03-24"},
      "rule": "statute_of_limitations_years",
      "value": 4,
      "source": "Florida Statutes §95.11 (pre-HB 837)",
      "validation_status": "sourced",
      "effective_from": null,
      "effective_to": "2023-03-24"
    }
  ],

  "unvalidated_rules": [
    "TX/CA/NY SOL values, made-whole doctrine encodings, anti-subrogation rules, GOL §5-335 applicability — held out pending source validation. The Recovery specialist treats SOL as an open question and surfaces it for human review rather than asserting a deterministic answer. See §7 Layer C-statutory discipline."
  ],

  "evidence_preservation_required_for": ["vehicle", "policy_documents", "police_report",
                                         "recorded_statements", "medical_authorization"]
}
```

The reduction in sourced rules is deliberate: a small set of correct rules with citations is more defensible than a large set of plausible-looking unsourced rules. Layer C-statutory eval is restricted to the sourced rules. Future PRs add sourced rules incrementally.

### Closure specialist config

```json
{
  "closure_checklist_per_exposure": [
    "all_payments_cleared_or_voided",
    "release_on_file_for_BI",
    "lien_resolution_documented",
    "Medicare_Section_111_obligation_evaluated",
    "recovery_addressed_or_waived_with_approval",
    "reserves_zeroed_or_explained",
    "all_diaries_closed",
    "litigation_resolved_or_documented",
    "1099_issued_if_required",
    "uncashed_check_escheatment_addressed"
  ],

  "closure_authority_matrix": [
    {"basis": "incurred", "level": "handler", "max_amount": 50000},
    {"basis": "incurred", "level": "supervisor", "max_amount": 250000},
    {"basis": "incurred", "level": "client_required", "max_amount": "unlimited"}
  ],

  "loss_run_schema_version": "client_specific_v3",
  "loss_run_cadence": "monthly",
  "DOI_reporting_states": ["CA", "TX", "NY", "FL"],
  "closure_QA_sample_rate": 0.10,
  "reopening_authority_required_above_days_since_closure": 90
}
```

**Effective-dating.** Every config row carries `effective_from` / `effective_to`. Specialists running over historical claims must use the configuration in force at the relevant timestamp.

---

## §7 — Ground truth (layered truth model: A, B, C-statutory, C-policy, D, E)

Layer C is split into C-statutory and C-policy because conflating statutory facts (externally anchored) with config-derived facts (the generator applying a config the generator wrote) would muddy what the eval is actually measuring.

### Layer A — Latent world state (generator-known, specialist-hidden)

At synthesis time the generator commits to the underlying facts (actual liability, damage, eventual payments, eventual recovery, complete document set, complete timeline). Never visible to the specialist.

### Layer B — Observed file state by date (the specialist's input)

At evaluation moment T, the specialist sees documents/ledger/notes/coverage/parties as of T, plus the applicable configuration as of T. No metadata leaks the synthetic origin.

### Layer C-statutory — Eval-trusted deterministic labels

For facts anchored to *externally validated* rules — statutes, regulations, federal compliance — the generator can write the answer key with confidence:

- Has a sourced SOL deadline passed? (only for rules carrying `validation_status: sourced` in §6)
- Was a Section 111 reporting obligation triggered (Medicare-eligible claimant + TPOC/ORM)? Shape-only — the system detects obligation existence, not federal filing correctness.
- Is a required document missing per a statutory filing requirement?

C-statutory is the small, defensible eval surface. Metrics here can be reported rate-precise (at the n that supports it — §8).

### Layer C-policy — Specialist reproduces config

For facts derived from *the client's configuration* — closure-blocking defects, authority approval requirements, client notice thresholds — the generator applies the config to produce the answer key, then grades the specialist on reproducing that application.

This is **rule-execution accuracy**, not deterministic ground truth. The specialist could be perfect at reading the config and the config could still be wrong (e.g., the client's authority threshold is misconfigured). C-policy measures the system's ability to operate as configured, which is a real product question — but the eval honestly cannot conclude "the specialist arrived at the right answer about the real world," only "the specialist correctly executed the encoded rule."

Metrics reported under C-policy are labeled accordingly. An interviewer asking "where does Layer C ground truth come from?" gets a layered answer:
- C-statutory: from sourced statutes with citations
- C-policy: from the client config (which the generator wrote); measures execution fidelity, not real-world correctness

### Layer D — Judgment ground truth (human-validated, eval-trusted)

A different model from the generator proposes judgment answers; human review on golden cases produces authoritative rubric labels. Metrics framed as "within defensible band" not "matches the correct number."

Caveat: cross-model judging reduces same-style bias but does not produce truly independent ground truth. The information channel still runs generator → documents → judge; if the generator telegraphs intent through prose, a different judge model may still recover it. This is a residual circularity, named not denied.

### Layer E — Calibration (probability is the right shape)

A signal cutting across layers A–D. Every specialist that emits probabilities (Coverage, Liability, Reserve, Recovery, Closure) is evaluated for calibration: across the golden set, at predicted probability *P*, what fraction of cases actually resolve as predicted? A well-calibrated specialist's 80%-confident outputs resolve as predicted ~80% of the time, plus or minus the band the n supports.

**Why this is its own layer:** Layers A–D measure whether the specialist's *answer* is right. Calibration measures whether the specialist's *uncertainty* is right. Both are independently necessary.

**Computed as:** bucket all probabilistic claims from `AgentAction.output_json` into deciles by predicted probability. For each bucket, compute the actual resolution rate against Layer A (where applicable) or Layer C-statutory (where the rule is sourced). Report calibration plot per specialist per prompt version.

**Failure modes:**
- **Overconfidence** — claiming 90% when actual is 70%. Bad for adjuster trust (they learn to discount); bad for downstream decisions that use the probability.
- **Underconfidence** — claiming 60% when actual is 85%. Loses information; routes things to human review that didn't need it.

Both are actionable. Both surface as eval failures with directional signal for prompt revision. **A recommendation cannot be calibrated this way** — this is one of the strongest arguments for the probability + evidence output shape over recommendation outputs.

**Citation grounding as a parallel signal:** every `ProbabilisticClaim` carries `EvidenceCitation` rows. Citation grounding measures whether those rows (a) point at real Documents / sourced rules / ledger entries that exist in Layer B, and (b) say what they're cited as saying (the `text_excerpt` matches the source). A failure here is a hallucinated citation, which is worse than a missing one. The post-processing layer drops hallucinated citations before the AgentAction is finalized; the eval surface confirms the drop logic catches them.

### What this means per specialist

**Brief specialist.**
- Diff-item recall (Layer C-policy) — did Brief surface every change between the prior touch and now? full set
- Diff-item precision (Layer C-policy) — did Brief surface things that weren't actually changes? full set
- Missing-info identification (Layer C-policy) — full set
- Citation grounding (Layer E) — every diff item carries a verifiable citation

**Coverage specialist.**
- Outcome-path calibration (Layer E) — P(clean) and P(ROR) predictions vs golden-set resolution
- Evidence recall (Layer A) — did Coverage find every policy provision, exclusion, and endorsement a human reviewer cited?
- Citation grounding (Layer E) — every probability carries verifiable citations
- Layer C-statutory: policy-in-force determination on sourced cases
- Layer C-policy: client-specific coverage rule application

**Liability specialist.**
- Fault-allocation calibration (Layer E) — does the predicted bucket distribution match observed final allocations?
- Comparative-fault-rule application (Layer C-statutory) — sourced jurisdictional rules
- Evidence recall + citation grounding (Layer E)
- Rationale quality (Layer D)

**Reserve specialist.**
- Within-band rate (Layer D) — golden set
- Band calibration (Layer E) — does the 80% CI actually contain 80% of the true ultimates?
- Material-event trigger recognition (Layer C-policy) — full set
- Notice obligation recognition (Layer C-statutory for sourced rules + Layer C-policy for client thresholds) — labeled per metric
- Citation grounding (Layer E)

**Recovery specialist.**
- Recovery-opportunity detection calibration (Layer E) — P(recoverable) prediction vs actual recoverability
- Recovery basis classification (Layer C-policy) — type label is per-config
- SOL-blocked detection (Layer C-statutory) — only on sourced SOL rules; otherwise the specialist surfaces "SOL unknown, please review" with explicit uncertainty
- Recovery amount band (Layer A + Layer E) — ±25% of latent eventual recovery, calibrated
- Citation grounding (Layer E)

**Closure specialist.**
- Ready-to-close probability calibration (Layer E)
- Defect catch rate (Layer C-policy for client defects; Layer C-statutory for Medicare/lien/document-required defects) — labeled per metric
- False-block rate
- Per-exposure correctness
- Citation grounding (Layer E)

---

## §8 — Scale targets and statistical power

### For the interview demo

- ~300 synthetic auto claims (across Northwind, Sentinel, RoadMile portfolios; CRSS calibration; FARS fatality subset)
- ~200 synthetic flood claims (Coastal WYO demo branch)
- 4 active client programs (Northwind, Sentinel, RoadMile, Coastal WYO) + Pinnacle Captive schema-only
- ~50% active, ~50% closed
- ~5-10% of auto claims are multi-vehicle shared-occurrence cases (one LossOccurrence → 2+ Claims)

Total: ~500 claims, ~3000-4000 documents.

### Recovery prevalence

Real-world recovery prevalence (10–15%) at n=500 produces 50–75 positives — too sparse for rate-precise eval. Synthetic recovery prevalence is set to **~30%** (~150 positives) — a deliberate over-weighting to support specialist eval defensibility, flagged in §10. The Recovery specialist's reported metrics carry a note: "evaluated on a synthetic book over-weighted for recovery cases; deployed performance against a real book will differ."

### Statistical power, by metric category

| Metric class | Layer | n at hand | What we report |
|---|---|---|---|
| Sourced-statute deterministic detection (SOL passed, S111 obligation) | C-statutory | n=50 golden + ~150 recovery positives | Rate with CI |
| Config-execution accuracy (trigger recognition, defect catch, authority routing) | C-policy | n=50 golden + full ~500 | Rate with CI |
| Recovery binary detection at 30% synthetic prevalence | A | ~150 positives, ~350 negatives | Detection rate with CI; FPR directional unless n_negatives raised |
| Reserve within-band rate, rationale rubric | D | n=50 golden | Rate with CI on golden set only |
| Time-to-recognition | D | n=50 golden via incremental replay | Median + IQR |
| **Probability calibration** (Coverage outcome paths, Liability allocation distribution, Reserve band, Recovery opportunity, Closure ready) | E | full ~500 AgentActions (each predicting probabilities across multiple claims) | Calibration plot per specialist per prompt version: predicted P vs actual resolution rate, bucketed by decile. Reliability diagram + Brier score. |
| **Citation grounding** | E | every `EvidenceCitation` row from all AgentActions | Fraction of citations whose target exists in Layer B (`document_id` / `sourced_rule_id` / `ledger_entry_id`) and whose `text_excerpt` matches the source. Hallucinated-citation rate as the inverse. |
| **Evidence recall** (did specialist find every piece a human reviewer cited?) | E + Layer A | n=50 golden | Recall % vs human-curated evidence set |

### Time-to-recognition harness

Built for the golden set (50 claims per specialist). Replays documents in temporal order, runs the specialist incrementally at each arrival, compares output at step i to ground truth as-of step i. Non-golden claims get a single end-state run.

### Matched-pair config sensitivity test

For ~30 claims, duplicate the file under a second client's config and run the specialist twice. Expected divergence is the signal that configuration is load-bearing.

### Scaling beyond demo

For a real customer pilot: 10K-50K real claims, real documents, real configuration. The synthesis layer drops out; substrate + specialists + workspace remain.

---

## §9 — Implementation tooling

- **Substrate storage:** DuckDB (`data/claims.duckdb`). Postgres migration path clean.
- **Document storage:** local filesystem under `data/documents/<claim_id>/`. S3 in production.
- **Document generation (Pass 1 + Pass 2):** Anthropic SDK direct. Pydantic-validated.
- **Programmatic fuzzing (Pass 3):** Python post-pass. Deterministic given a seed. Excluded from eval-set holdouts.
- **Document extraction:** Anthropic SDK. Per-specialist prompts.
- **Eval framework:** layered (§7). Layer C-statutory and C-policy are pure code. Layer D judgment runs through a different LLM than the generator (cross-model). Layer E calibration is computed from `AgentAction.output_json` predicted probabilities bucketed against Layer A / Layer C-statutory ground truth — pure code, runs on every AIP Evals run.
- **Bitemporal access.** Specialists access ledger state via `get_financials_as_of(exposure_id, as_of_effective, as_of_recorded) → ExposureFinancialSnapshot`. Implemented in Python with window-function SQL against `FinancialPosting`. **Specialists never write bitemporal SQL.** DuckDB has no native `AS OF SYSTEM TIME` and LLMs are unreliable at authoring temporal SQL.
- **Versioning.** Versioned document artifacts via Git-LFS are authoritative. Seed reproduces only the structured/sampling layer.
- **Generation idempotency and caching.** Idempotent per `(claim_id, document_type, pass_number)`. Successful generations cached.
- **Source-event traceability.** Every synthetic claim retains its `source_event_id`.

### Cost and wall-clock budget

Estimate before committing to the full pipeline:

| Pipeline stage | Approx LLM calls | Notes |
|---|---:|---|
| Pass 1 document generation (seed) | ~3500 | 500 claims × ~7 docs average |
| Pass 2 noise injection | ~3500 | Same set, different prompt |
| Pass 3 Python fuzzing | 0 | Deterministic, no LLM |
| Layer D judgment (golden set, cross-model) | ~150 | 50 golden × 3 specialists |
| Layer D judgment (non-golden, single-model judge) | ~450 | One per non-golden claim per specialist; subsampled |
| Specialist extraction runs | ~5000 | Per specialist per claim, varies |
| Incremental replay for time-to-recognition (golden only) | ~1200 | 50 × ~8 arrival points × 3 specialists |

**Total: ~14K LLM calls per full pipeline run.** At Claude Sonnet pricing (~$3 input / $15 output per MTok) and assuming average call sizes of ~3K input / ~1K output tokens: ~$220 per full pipeline run for inference. Allow 3-5× for dev iteration, retries, prompt tuning: **~$700-$1100 total LLM spend** for the build phase.

Wall-clock: at ~1 call/sec sequential = ~4 hours per full run; at 10× concurrency = ~25 minutes. Plan for multiple full runs (3-5) during iteration: **~2-3 hours of cumulative pipeline compute.**

This budget is approximate; first real pipeline run validates it. If actual cost is >2× estimate, cut prevalence (the n=500 target) before cutting features.

---

## §10 — Synthesis limitations (named, owned)

1. **Document format fidelity is markdown-approximate, not Xactimate / UB-04 / HCFA-1500.** Real estimates and medical bills are deeply structured forms with coded line items, ZIP-based pricing, O&P rules, spatial layout. Our synthesis produces markdown approximations capturing content (line items, codes, totals) but not form layout. A fielded extraction system on real claims would need OCR + form-aware extraction.
2. **Judgment ground truth is rubric-scored, not point-estimate truth.** Layer D uses a different model than the generator, plus human review on golden cases. Metrics framed as "within defensible band."
3. **Property scope is flood-only.** NFIP can't anchor private-property fire/wind/theft/burst-pipe. Captive (Pinnacle) is architecture-ready but not empirically exercised; WYO (Coastal) is demo-only, not a target archetype.
4. **Generator and extractor may share a model family.** Layer D judgment runs on a different model than generation; extraction-layer eval still shares the model. Residual circularity through the information channel (generator → docs → judge) is named, not eliminated.
5. **Recovery prevalence is over-weighted at ~30% synthetic vs lower real-world rate.** Deliberate, for specialist eval defensibility. Reported metrics carry a note.
6. **Statistical power on rate metrics is limited at n=50 golden cases.** Layer C-statutory and C-policy metrics at the full ~500 are rate-precise; Layer D metrics are rate-precise only on golden set.
7. **Auto fatality tail comes from FARS, which is 100% fatal.** Real catastrophic non-fatal injury (TBI, spinal) is not in our book. FARS-sourced claims tagged `scenario_family=fatality`.
8. **Fatality damage model is not modeled.** Fatality claims differ from BI: no future medicals; wrongful-death/survival economic + non-economic across statutory beneficiaries; consortium claims; statutory damage caps in some jurisdictions. FARS is routed to the fatality scenario family but the distinct damage structure is out of scope.
9. **Auto book is calibrated from police-reported crashes, not insurance claims.** CRSS shapes severity distribution; portfolio shapes claim frequency and selection. Real books differ in deductible-influenced reporting, late-reporting drift, coverage-driven selection.
10. **Section 111 / MSP entities are shape-only.** `MedicareReportingStatus` reflects the data shape so Closure can detect the obligation. Filing Section 111 reports and EDI compliance are out of scope.
11. **Synthetic noise is bounded.** The Python fuzzing pass produces structural noise (character drops, format drift, OCR-style substitutions). Truly adversarial noise (fraudulent documents, deliberately ambiguous medical chronologies, contested causation expert reports) is not modeled at the realism level a fraud-detection specialist would require. Fraud SIU is out of scope.
12. **Layer C-statutory is restricted to sourced rules.** Only legal rules with citations and effective-from dates are eval-trusted. Unsourced rules are removed from the eval surface; the Recovery specialist surfaces them as "human-review-required" rather than producing a deterministic answer.

---

## §11 — What's deferred to PRD or build phase

- Exact synthesis prompts per document type
- Specialist extraction prompts
- Judgment-layer LLM-judge prompts
- Workspace UI (PRD scope)
- Configuration authoring UI for real customers
- Postgres migration
- Generic private-property data anchor (replacing flood-only)
- Form-aware extraction (Xactimate, UB-04, HCFA-1500)
- Multi-state DOI reporting integration
- Bordereau and reinsurance reporting outputs
- Section 111 EDI filing logic
- Disbursement / DisbursementAllocation (multi-exposure payment allocation)
- RecoveryMatter / RecoveryAllocation (multi-exposure recovery allocation)
- Organization / Program / HandlingAgreement / RiskFinancingArrangement decomposition (`ClientProgram` is sufficient)
- Asset / InsuredRiskUnit separation (claimant assets modeled implicitly)
- Fatality damage model (wrongful-death/survival/consortium)
- Fraud SIU specialist

---

## §12 — Validation checkpoint

Before declaring the data layer ready and moving to architecture, the spec must pass:

1. **Realism check.** A property/liability adjuster reviews 10 synthetic auto + 5 synthetic flood claims. **Substitute if no adjuster available:** use AIC/CPCU training corpora, public court records of disputed claims (PACER / state court systems), or industry exemplar claim files from carrier training materials as the realism benchmark. Document the substitute used. The check is *not* skipped — if the realism benchmark can't be sourced, the realism claim is unfalsifiable and that's a build-blocking risk.
2. **Eval discriminates.** Rule-based baseline scores clearly worse than LLM baseline on Layer C-statutory and C-policy metrics. If they score the same, the eval isn't discriminating.
3. **Ontology survives stress test.** A Reserve specialist runs against (a) a multi-vehicle fatal FARS-sourced shared-occurrence claim with 3 BI exposures across 2 claims, (b) a multi-feature flood claim with building + contents + ICC, and (c) a coverage-disputed reservation-of-rights file. All three execute against the same ontology without forking. Status transitions follow the illegal-combination matrix.
4. **Configuration is load-bearing.** Matched-pair test (§8): two clients with different reserve thresholds produce different specialist recommendations on identical claims.
5. **Bitemporal works through the Python tool.** `get_financials_as_of(...)` correctly returns historical state under backdated `effective_at` transactions and correction reversals. Specialists never author the temporal SQL.
6. **Accounting identity holds.** Across any sequence of valid `FinancialTransaction` writes, `incurred = paid + outstanding` per component per exposure. Verified by a property-based test.
7. **Truth-layer attribution is clean.** Every reported metric points to its truth layer (A / B / C-statutory / C-policy / D / E) in the eval output.
8. **Yield validation passed (§4 step 0.5).** Each portfolio's FARS/CRSS filter yields at least 5× target claim count, documented.
9. **Cost budget held.** Pipeline cost on the first real run is within 2× the §9 estimate.
10. **Citation contract enforced.** Every `AgentAction` from Coverage, Liability, Reserve, Recovery, or Closure carries at least one linked `EvidenceCitation` per probabilistic claim in `output_json`. A test crafts an output missing citations and confirms it fails the Action Type validator before reaching the substrate. Hallucinated citations (pointing at non-existent Documents / rules / ledger entries) are caught by post-processing and dropped before AgentAction finalization.
11. **Calibration is computable.** The Layer E calibration plot can be generated for each specialist from `AgentAction.output_json` joined to ground truth, with at least 50 probabilistic claims per decile bucket. If the n in a bucket is too small, the eval surfaces that the bucket is non-reportable rather than reporting a noisy rate.

These checks happen before declaring the data layer ready and moving into architecture.

---

*The doc is at the point of diminishing returns on further spec polish. Next move: build the slice (§5 minimum viable slice marker) and let the build surface what the spec missed.*
