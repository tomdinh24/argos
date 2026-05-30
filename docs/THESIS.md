---
tags:
  - project/argos
  - type/thesis
  - status/draft
created: 2026-05-27
updated: 2026-05-28
aliases:
  - Claims Ops Intelligence Thesis
---

# THESIS — Claims Operations Intelligence Layer (Argos)

> Written downstream of Phase 1 (adjuster workflow research), Phase 2 (real data exploration across FARS, CRSS, NFIP), and Phase 3 (buyer profile locked: specialty mid-tier auto + property TPA). Target audience: a Palantir Forward Deployed Engineer interviewer first, an AI PM interviewer second — the former-credible version is also the latter-credible version, not vice versa.

---

## §1 — What we believe

We are building an AI-governed claims operations intelligence layer for **specialty mid-tier auto and property third-party administrators (TPAs)** in the lower-middle market, where the **ontology is the durable asset** and **per-customer authority configuration is the moat**. The wedge is a specialty $50M-$500M TPA that serves self-insured corporates, captives, carriers outsourcing claims, and MGA programs across auto and property — workflows that share enough structure with enterprise carrier claims operations that the asset extends up-market over time without a rewrite. We are not building a horizontal multi-line AI vendor, and we are not building a system-of-record replacement. We are building the layer that sits between the TPA's claims system and the unstructured documents and judgment-laden decisions that consume the adjuster's day.

---

## §2 — The work as it actually flows today

A specialty auto + property TPA bears no underwriting risk, holds no premium, and disburses no money from its own balance sheet. It is a service vendor that handles claims operations for four distinct client types — self-insured corporates running on a loss fund, captives running on their own insurance subsidiary's reserves, carriers outsourcing claims under their own paper, and MGAs writing on a carrier's paper. The TPA's revenue is service fees (per-claim, percentage-of-premium, or subrogation recovery share), and its operating constraint is that **every consequential decision is contractually capped by the client's delegated authority schedule**. This is the structural fact that shapes everything that follows.

A claim moves through eleven lifecycle stages — Intake, Coverage Determination, Triage, Investigation, Liability, Reserve Setting, Negotiation, Excess Coordination, Payment, Subrogation, Closure — with the auto and property cuts diverging meaningfully at each. Auto investigation runs on statements, police reports, and the comparative-fault percentages that drive later negotiation; property investigation runs on physical inspection and Xactimate line-item scope reconciliation against contractor and public-adjuster estimates. Auto payment has the lienholder / title / salvage choreography on total losses; property payment has staged disbursement (ACV first, depreciation released only after documented completion), additional living expense reimbursement against caps, and mortgagee co-payee mechanics. The vocabulary is industry-specific and well-documented; the workflow is genuine across specialty TPAs serving these client types (NARS, Raphael & Associates, Custard / Riverwood, Engle Martin).

Three operating cardinal sins recur across every public account of the work. **Reserve drift** — a claim creeping from a $5K initial reserve to a $50K paid loss — is the failure clients audit TPAs against most harshly, because reserves drive their financials and excess-notification triggers. **Missed subrogation** — a recoverable third party never referred to recovery before file closure — is the failure that shows up on closed-file audits and accounts for measurable revenue leakage. **Late excess notice and consent failures** — missing the contractually fixed notification trigger to the excess carrier, or settling a claim above the SIR without securing consent — are coverage-forfeiture failures that create direct E&O exposure for the TPA itself.

The structural authority constraint is what bounds where automation can credibly act. Bad-faith and E&O exposure concentrate at four specific decisions: coverage denial, time-limit / policy-limits demands, reserve adequacy, and consent-to-settle. At each, the TPA's delegated authority is contractually capped, the client / carrier retains final authority, and an automated misstep is expensive, discoverable, and the kind of thing that ends client relationships. The work the adjuster actually does in a day is not autonomous decisioning. It is reading documents, drafting analysis, reconciling estimates, flagging triggers, and routing the file. The eleven-stage lifecycle is mostly document-and-data work with judgment-bound decisions at named boundaries. That structural shape is the product opportunity.

---

## §3 — Why now

Three forces converge to make this a credible bet in 2026.

**The labor cliff is here.** The Bureau of Labor Statistics and the Jacobson Group / Aon Insurance Labor Market Study both project a worker decline of roughly 400,000 across insurance through 2026, concentrated in claims and underwriting. Inside specialty TPAs the pressure is already operational: practitioner reports describe pending caseloads of 200+ claims per adjuster (Sedgwick) and 130+ at smaller regional carriers, against a target of ~70. The pain is universal across the buyer set and the demand for throughput-augmentation is real.

**LLM capability has crossed the threshold for production unstructured-to-structured extraction.** The claims file is built from exactly the document types modern LLMs handle reliably — police reports, recorded statement transcripts, repair estimates, medical bills, contractor invoices, demand packages, AOB documents. The extraction problem is no longer the binding constraint. What was a research demo in 2023 is a production-grade capability today, with confidence calibration and tool-use patterns mature enough to operate inside a regulated workflow.

**Integration is now the binding constraint, not model capability.** Models are good enough; what is hard is operating safely inside a TPA's authority schedule, against a real claims management system, with real client SLAs, real DOI compliance requirements, and real bad-faith exposure. The hard problem is the configuration surface — and that is precisely the surface where horizontal AI vendors cannot ship a product without forward-deployed engineering. Source detail on each force lives in [docs/MARKET_ANALYSIS.md](./MARKET_ANALYSIS.md).

---

## §4 — The wedge: LMM-first specialty auto + property TPA

We start with the lower-middle market and expand up. Four arguments, each independently load-bearing, all consistent with the data and workflow research now on disk.

**One — demo credibility requires real data.** Enterprise carriers run on locked proprietary data; there is no path to a credible demo without paid customer access, which is the cold-start problem that has stopped every horizontal claims AI vendor we examined. LMM workflows are buildable against real public data — NHTSA FARS (37K real auto crashes with real geography), CRSS (the realistic 70 / 23 / 0.6 severity distribution), FEMA NFIP (1.54M real property claims with $41B in paid losses and named catastrophe tagging). The data layer for an auto + property demo exists publicly, and it is real enough that the SQL transforms feel non-contrived.

**Two — LMM buyers iterate faster.** Specialty mid-tier TPAs have flat decision structures and 1-6 month procurement cycles, against 18-24 months at top-25 carriers. Procurement velocity is the rate-limiting step on PMF, and the LMM buyer is structurally faster.

**Three — PMF before enterprise is the credible path.** Revenue and references from specialty TPAs unlock enterprise conversations on credible terms 18-24 months later. The reverse — chasing enterprise without LMM proof — is the path that has burned every horizontal claims vendor in the public record.

**Four — the technical work generalizes up-market with minimal rework.** Same ontology, same agent topology, same eval architecture; what changes going up-market is the per-customer configuration adapter surface and the compliance theater (SOC 2, audit trails, model cards). The durable engineering investment carries forward.

**Specialty over generalist (the Phase 3 refinement).** A generalist mid-tier TPA also handles workers' compensation, which runs on different platforms (Origami, ClaimVantage, Mitchell), different reserve patterns (long-duration medical), and a different evidence base than the auto + property cut. A specialty auto + property TPA lets the demo cover their full book end-to-end, lets the data fit be exact (FARS + CRSS + NFIP), and avoids the implicit promise to handle their largest line of business at launch. The buyer pool is smaller but the precision of the targeting is higher, and procurement velocity is structurally fastest at specialty TPAs.

---

## §5 — The asset: one intelligence layer the adjuster works inside

The asset is not a bag of separate AI tools that each do one thing. It is a single intelligence layer the adjuster works inside, made of three parts that fit together.

**A useful analogy: a hospital.** A patient's chart is the canonical record of everything known about them. A team of specialists — cardiologist, radiologist, oncologist — each reads the same chart but asks a different question of it, and writes their findings back into the chart. The doctor's workstation is where the chart and all the specialists' findings come together in one place, where the actual decisions get made. **Three parts: shared record, team of specialists, one workspace where the human decides.** Our system has the same shape.

### Part 1 — The structured claim file (the shared record)

Today's claim file is a folder of PDFs and a row in a claims management system. We build a richer version: every document that comes in is read once, the key facts extracted, stored as structured data that the rest of the system can query. Police reports, medical bills, recorded-statement transcripts, repair estimates, contractor scopes, demand packages, photos, contractor invoices — all of them get processed into the same shared record.

The shared record holds:
- **Who is involved** — insured, policyholder, claimant, witnesses, vendors, attorneys
- **What coverage applies** — which client program, which policy, which SIR, which excess tower above
- **What the reserves are right now** — broken down by exposure type, with the trajectory over time
- **Every payment, every recovery, every vendor assignment** — with payees, amounts, dates, status
- **Every event that happened on this claim** — document received, reserve changed, statement taken, demand sent, payment cleared

This structured representation has the same shape whether the claim is auto or property, and whether the client is a self-insured corporate, a captive, a carrier outsourcing claims, or an MGA. That uniformity is what makes the asset extend across the lifecycle, across both lines of business, and eventually up-market without a rewrite.

### Part 2 — A team of specialists watching the file

Sitting on top of the shared record is a team of small, narrow specialists. Each one watches the file for one specific thing and writes back what they find. They never make binding decisions — they draft recommendations the adjuster approves or dismisses with a click.

The initial team:

| Specialist | What it watches for |
|---|---|
| **Coverage specialist** | Does coverage apply to this loss, and where are the gray areas? |
| **Reserve specialist** | Did anything just happen that means the reserve should change? |
| **Liability specialist** | What does the evidence say about fault, and what's a defensible allocation? |
| **Recovery specialist** | Is anyone other than our insured actually at fault for this loss? |
| **Notice specialist** | Did we just cross a threshold that requires excess-carrier notification? |
| **Closure specialist** | Is this file actually ready to close, or are obligations still open? |

When a new document arrives, every specialist wakes up at once. Each reads the new state of the file. Most stay silent (nothing in their lane). One or two surface a recommendation. The adjuster sees one curated summary, not six separate alerts.

Why have specialists at all instead of one big general-purpose AI? Three reasons:

1. **Specialists are small enough to test.** "Did the recovery specialist correctly identify third-party liability?" is a clean question with a clean answer. "Did the AI handle the claim well?" is not.
2. **Each specialist can be configured separately per customer.** Client A's reserve thresholds are different from Client B's. Client A's excess-notice triggers are different from Client B's. A team of small specialists lets each one carry its own per-customer rules cleanly.
3. **Adding a new capability later is cheap.** Tomorrow we want a fraud-signal specialist. We don't rebuild the AI; we add one more small specialist on top of the shared record.

### Part 3 — The adjuster's workspace

The adjuster never interacts with the specialists directly. They work inside one unified workspace.

When they sit down for the day, the workspace shows them the **prioritized queue** of which claims to work on — ordered by SLA risk, exposure trajectory, and specialist-surfaced urgency. The adjuster does not decide what is urgent. They decide what to do about the urgent things.

When they open a specific claim, the workspace shows them a **curated brief**: where the claim stands, what each specialist has surfaced, what decisions are pending, what the next action is. The adjuster reviews the brief, approves or dismisses each recommendation, and moves to the next claim. Documents are processed in the background. Reserves get re-evaluated as new info arrives. Closure is blocked structurally until specialists confirm the file is ready.

The whole experience is **one workspace, one workflow, one workout-and-decide loop** — not a tangle of separate tools and tabs.

### Where the moat lives

The shared record is something a competent horizontal AI vendor could build. The workspace is good UX — also build-able. **The moat sits inside how each specialist is configured at each customer.**

Every consequential decision in the lifecycle runs against client-specific rules: how much authority an adjuster has to settle a claim before escalation; how high a reserve has to climb before the excess carrier must be told; what counts as a "material event" that triggers re-reserving; what loss-run format the client expects on their quarterly report; which states' DOI closed-claim reporting kicks in. Every one of these is a configuration field, not a model parameter. The eleven customer-discovery questions in [research/specialty-tpa-auto-property-workflow.md](./research/specialty-tpa-auto-property-workflow.md) §18 are precisely this configuration surface.

A horizontal AI vendor can ship the shared record and the workspace. They cannot ship the per-customer specialist configurations without sitting with each customer, reading their TPA-client claims-handling agreement, encoding their reserve-authority matrix, and validating their excess-notice protocols. That work is forward-deployed engineering, and it is the moat.

> **The system's safe operating envelope is defined by each client's authority schedule — which means the product is configured per customer, and that configuration is the moat, not the model.**

The configuration corpus also compounds. Every new customer adds a new configuration; every new configuration is a new data point about how real specialty TPAs actually operate. That compound is the flywheel a horizontal AI vendor structurally cannot build.

### Why this matters for Palantir-style interview signal

This is the same architectural pattern Palantir built their entire enterprise business on: a shared ontology at the bottom, a library of composable functions that operate on it, applications on top where humans actually work. Saying *"we built a claims intelligence layer with a shared structured record, a library of specialist watchers on top, and a unified adjuster workspace"* is the language an FDE interviewer expects. Saying *"we built six AI agents"* is not.

---

## §6 — The expansion arc: LMM → up-market

The path from LMM wedge to enterprise extension is engineered, not aspirational. **What stays the same:** the industry ontology; the agent topology (a deterministic state machine with LLM at named boundaries — coverage issue surfacing, recovery identification, closure readiness review, loss-run drafting); the three-layer eval architecture (schema validation → golden cases → LLM judge); the configuration model that encodes the per-customer authority schedule.

**What changes going up-market.** Integration surface area grows — each enterprise carrier brings a different CMS (Guidewire ClaimCenter, Duck Creek, custom), a different vendor ecosystem, a different reporting stack. Forward-deployed engineering load grows — enterprise customers require more per-customer configuration to encode and more sustained on-site presence to validate. Compliance theater grows — top-25 carriers want SOC 2 Type II, formal model cards, audit-trail attestation, third-party penetration testing, and the kind of legal review that takes 9-12 months on its own.

**What this enables.** The same ontology that runs at a $200M specialty TPA runs at a $30B top-10 carrier. The agent topology that handles a TPA's program-routing logic handles a carrier's line-of-business segregation. The configuration model that encodes a TPA-client authority schedule encodes a carrier's internal authority matrix. The technical asset compounds; the GTM motion changes.

**Long-duration adjacency (WC, disability) is the expansion arc, not the wedge.** Workers' compensation runs higher per-claim value and longer settlement cycles than auto or property, and it runs on different platforms. Once the auto + property foundation is solid and revenue is real, the long-duration extension is a natural higher-margin adjacency — 18-24+ months out, not the bet.

---

## §7 — What we are explicitly NOT betting on

Six explicit non-bets keep the thesis falsifiable.

**Enterprise-first GTM.** No top-10 carriers in the first 18 months. The cold-start data problem and the procurement velocity problem make it the wrong starting point.

**Long-duration-first focus.** Workers' compensation and disability are the expansion arc, not the wedge. The data fit, the procurement velocity, and the demo path all favor auto + property first.

**Horizontal multi-line breadth.** That is FurtherAI's bet. We go vertical-depth in specialty TPA claims operations, where the per-customer configuration moat is real.

**System-of-record replacement.** Guidewire and CCC own the SOR layer. We integrate, we don't displace.

**Autonomous decisioning on coverage, liability allocation, reserve setting above threshold, or settlement authority.** Four reasons recur across the workflow evidence: TPA delegated authority is contractually capped at exactly these decisions; bad-faith and E&O exposure concentrate at exactly these decisions; the judgment-heavy interpretive work (anti-concurrent causation, comparative fault on disputed facts, ensuing loss, injury valuation) is not reliably automatable with current capability; and the failure modes are expensive, discoverable, and relationship-ending. The product enforces human authority at these decisions structurally, not as a feature.

**"Touchless / straight-through" claims on injury, disputed liability, commercial-auto bodily injury, or cause-disputed property.** Touchless is scoped to clean low-severity clear-liability files only. The marketing temptation is real; the failure mode is the leakage and complaint pattern that has burned every prior straight-through claims vendor. We do not make the claim.

Each non-bet is testable. If a top-10 carrier signs in month 6, the GTM non-bet gets re-examined. If a customer demands autonomous coverage decisioning, we say no and explain why.

---

## §8 — Open questions deferred to STRATEGY / PRD

The wedge is **the minimum viable claims intelligence layer** — the substrate plus the cockpit plus the first set of analyzers that prove the architecture works. The strategic deferrals are about which analyzers light up first, not about which standalone product to ship.

**Which analyzers light up first is the load-bearing STRATEGY decision.** Three candidates each have a different strongest argument:

- **Recovery analyzer** — strongest single-dollar-ROI pitch; closed-file audits routinely surface missed recovery; the demo moment of "the agent found money your adjuster missed" is interview-grade and customer-pitchable in one sentence
- **Reserve analyzer** — strongest "stops the cardinal sin" pitch; reserve drift is the failure clients audit TPAs against most harshly, and a reserve recommendation engine that catches material events early is the single biggest financial-accuracy lever in the workflow
- **Closure analyzer** — strongest client-trust pitch; every claim closes through it, loss-run accuracy is what clients evaluate the TPA on, and structurally enforcing closure readiness prevents the largest class of audit defects

STRATEGY.md picks which subset lights up, with the reasoning grounded in demo credibility, customer-pitch coherence, and which analyzers most efficiently exercise the substrate-plus-cockpit architecture for portfolio purposes.

**The specific PMF metric is deferred to PRD.** Candidates depend on which analyzers ship first: recovery-dollars-detected, reserve-accuracy-improvement, closure-cycle-time-reduction, audit-defect-rate-reduction.

**Long-duration extension timing is deferred indefinitely.** It exists in the arc; the trigger is auto + property PMF, not a calendar date.

**The eleven customer-discovery questions from [research/specialty-tpa-auto-property-workflow.md](./research/specialty-tpa-auto-property-workflow.md) §18** are the validation list for the per-customer analyzer configuration surface. STRATEGY.md draws on them to scope which configuration fields each analyzer requires; PRD.md draws on them to define the configuration schema; the first real customer conversation closes the gap public research cannot.

---

*Section dependencies have all been satisfied by Phase 1, 2, and 3 outputs. Next refinement comes after the first STRATEGY draft and the first customer-discovery conversation.*
