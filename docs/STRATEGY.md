---
tags:
  - project/argos
  - type/strategy
  - status/draft
created: 2026-05-28
updated: 2026-05-28
aliases:
  - Claims Ops Strategy
---

# STRATEGY — Claims Operations Intelligence Layer (Argos)

> Downstream of [THESIS.md](./THESIS.md). Defines the user, the product, the wedge, the metrics, the moat, and the competitive position. Target audience: an AI Product Manager interviewer first, an FDE interviewer second. Companion to [research/specialty-tpa-auto-property-workflow.md](./research/specialty-tpa-auto-property-workflow.md) (the workflow ground truth) and the [data-exploration notes](./data-exploration/) (the data foundation).

---

## §1 — Who this is for: the adjuster at a specialty mid-tier TPA

The user is a claims adjuster at a $50M-$500M specialty auto + property TPA — someone like a transportation claims handler at NARS, a property desk examiner at Raphael & Associates, or a senior liability adjuster at Engle Martin. They handle 150-250 pending claims at any time, spread across four-to-six different client programs, each with its own coverage rules, reserve thresholds, settlement authority limits, and reporting requirements.

Their day starts with a queue of 40+ diary alerts firing, 5-10 new claims handed over from intake, 15+ emails from claimants and attorneys and contractors, and a few voicemails to return. They pick a file, spend ten minutes reloading the context (re-reading recent notes, scrolling through the documents folder, reconstructing the timeline), respond to whatever is most urgent, update the file, move on. They do this 30-50 times in a day. Then they go home.

What eats their hours is not the *decisions*. The decisions are fast once the facts are organized. What eats their hours is **document reading, context reloading, and the cross-referencing work that keeps the file accurate** — reading a 12-page police report to find the line that names the at-fault driver, comparing two contractor estimates line-by-line in Xactimate, summarizing a 180-page demand package into a one-page evaluation, checking whether a reserve change crosses any of six different client programs' excess-notification triggers.

Their job rewards throughput. Their pain is that the document-and-data work that *enables* good throughput is exactly what gets cut when the queue is full. Claims close that shouldn't have. Reserves drift up. Recoveries get missed. Loss runs go out with errors. Each of these is documented in the workflow research as a real, recurring failure pattern — not a hypothetical.

**This is the user.** The product makes the document-and-data work invisible so the adjuster spends time on the decisions only they can make.

---

## §2 — What's broken today

Three categories of failure recur across every credible source we examined. They are not edge cases. They are the operating reality.

**1. Reserve drift — the cardinal sin.** A claim opens at a $5K reserve, more info comes in, the reserve should move, the adjuster is busy and defers it, and the claim eventually pays out at $50K. The client's financials missed the loss. The excess carrier may not have been notified on time. The TPA looks incompetent. This pattern is well-documented across practitioner job descriptions (NARS, Creative Risk Solutions, the Complex Claims Director TPA Oversight role) and the cause is structural — re-reserving requires re-reading the file, recalculating the exposure, writing a rationale. It is time-consuming, so it gets deferred. The system needs to do it on every material event, not when the adjuster gets to it.

**2. Recovery leakage — missed money.** When a third party is at fault for a covered loss, the TPA can pursue recovery from the at-fault party's insurance. Closed-file audits routinely find 5-15% of files had a recovery opportunity that nobody pursued — police report identified the adverse driver, but the file closed without a recovery referral; failed dishwasher caused water damage, contractor threw away the evidence, manufacturer subrogation became impossible. At a TPA handling 10,000 claims a year averaging $20K, that is potentially $10-30M in missed recovery annually. The cause is structural — adjusters are measured on closing claims, not on recovery, and recovery signals are buried in long documents nobody has time to read closely.

**3. Closure incompleteness — files closed before they should be.** Adjusters close files with missing releases, unresolved invoices, weak rationale, or recovery never considered. Loss runs delivered to clients have errors. QA audits catch these later. Clients notice the pattern over time. Engle Martin's appraisal practice explicitly names this — "we not only include an accurate estimate but also a detailed summary within our closing report" — because most TPAs do not, and the documentation quality is what clients evaluate the TPA on.

**Why don't existing tools fix this?** Because the existing tool categories don't sit where the adjuster sits.

- **Claims management systems** (Guidewire ClaimCenter, Origami, Riskonnect) are systems of record. They store the file. They do not read the file or recommend actions on it.
- **Point AI tools** (Snapsheet for FNOL, Tractable for damage photo assessment, CCC for estimating) each automate one stage in isolation. None of them sit across the lifecycle.
- **Horizontal multi-line AI vendors** (FurtherAI is the public example) chase breadth across insurance verticals rather than depth in any one workflow. They cannot encode the per-customer authority schedule that a specialty TPA's adjusters operate inside.
- **Policy administration platforms** (Avallon, Bindable) sit upstream of claims. They do not touch the operating workflow at all.

The gap is the intelligence layer that sits **inside** the adjuster's day, reads everything they would read, and surfaces decisions they need to make. That gap is what we fill.

---

## §3 — The product: an intelligence layer the adjuster works inside

The product is not five separate AI agents. It is one intelligence layer made of three parts that fit together. The framing in [THESIS §5](./THESIS.md) is the canonical version; here is the AI-PM-flavored restatement.

### The hospital analogy that explains the architecture

A patient's chart is the canonical record of everything known about them. A team of specialists — cardiologist, radiologist, oncologist — each reads the same chart but asks a different question of it. The doctor's workstation is where the chart and the specialists' findings come together in one place, where the actual decisions get made.

Our system has the same shape: a **structured claim file** (the shared record), a **team of specialists** that each watches the file for one thing, and a **unified workspace** where the adjuster sees everything together and makes the call.

### The structured claim file (the shared record)

Today's claim file is a folder of PDFs and a row in a claims management system. We build the structured version: every document gets read once, key facts extracted, stored as queryable data. Police reports, medical bills, recorded statement transcripts, repair estimates, contractor scopes, demand packages, photos. The shared file holds who's involved, what coverage applies, where reserves stand, every payment and every recovery, and every event that has happened on this claim. It is the substrate everything else reads from.

### The team of specialists

A set of narrow specialists watches the shared file. None of them make binding decisions — they surface evidence, quantify uncertainty, and draft work product the adjuster approves. **Specialists never recommend a decision; they show evidence and probabilities and let the human pick the path.** This shape is calibratable (you can measure whether 80%-confident outputs resolve as predicted) and it avoids anchoring the adjuster psychologically before they've reasoned through the evidence themselves.

The full team across the lifecycle:

| Specialist | What it watches for | What it emits |
|---|---|---|
| **Brief** | Anything that changed on this claim since the adjuster last touched it | A one-screen summary: claim story, what changed, what each other specialist is recommending, what's missing, what's pending |
| **Coverage** | Whether the policy responds to this loss, and where the gray areas sit | Evidence found, probability per outcome path (covered / ROR / denial), drafts of the memo, ROR letter, and denial letter — all with cited evidence |
| **Liability** | What the evidence says about fault, under the jurisdiction's comparative-fault rule | Evidence found, probability distribution over fault allocations, draft assessment — all with cited evidence |
| **Reserve** | Whether something happened that should change the reserve | A probability band per component with citations, plus the notice obligations the change triggers |
| **Recovery** | Whether anyone other than the insured is recoverable-against, and what evidence preservation needs doing | Probability that a recovery opportunity exists, recovery type, SOL status, draft demand — all with cited evidence |
| **Closure** | Whether the file is actually ready to close, or whether obligations remain open | Probability ready-to-close, blocking defects with citations |

Plus two supporting services that aren't specialists but power the cockpit:

| Service | What it does |
|---|---|
| **Priority Scorer** | Ranks the queue so the adjuster opens the right claim first. Inputs: statutory clocks, diary deadlines, reserve adequacy drift, financial exposure, AgentAction backlog, inactivity risk. Output: ranked list with **reason chips** ("SOL 12d", "demand received no draft response", "new medicals +$5.8K since reserve review") so the adjuster sees not just the order but why. |
| **Correspondence service** | Sends outbound communications. Routine recipients (body shop, medical provider, insured, tow, police records) → auto-send. Adversarial recipients (claimant's counsel, opposing counsel, court, excess carrier) → auto-draft, one-click send. Tracks responses against diary deadlines and auto-fires follow-ups. |

### Automatic vs human-approved — the governing principle

Most of what each specialist does is invisible data work that happens in the background. **Approval is only required when language will be read by an adversarial party, when the decision is contested, or when money moves above the handler's authority.** That's the entire human-only column. Everything else — extraction, drafting, sending routine info requests, ranking the queue, summarizing the file, calculating probabilities — is AI work.

| Happens automatically | Requires human approval |
|---|---|
| Extract structured fields from every document | Approve a coverage decision (covered / ROR / deny) |
| Calculate probability per coverage outcome path with cited evidence | Approve the language of a denial letter or ROR letter |
| Apply the comparative-fault rule and produce a fault allocation distribution | Approve a contested fault percentage |
| Recalculate specials when a new medical bill arrives | Approve a reserve change above handler authority |
| Update the timeline as events fire | Approve a recovery referral or send a demand to an adverse party |
| Detect a recovery signal and draft the demand | Approve closure of the file |
| Refresh the Brief on any data change | Approve sending notice to an excess carrier or opposing counsel |
| Send routine info requests (body shop, medical provider for records, insured, police records, tow) | Approve a payment above handler authority |
| Track completion of every closure-required item | Approve final settlement offer numbers |
| Draft the excess-carrier notice with the trigger evidence and effective date | (Nothing else.) |

The principle is sharper than "data work vs decisions." Data work auto-runs. Routine correspondence auto-sends. **Legally-bearing claims surface evidence and probability — the human picks the path.** The human-only column collapses to: approve adversarial language, approve contested decisions, approve money above authority.

This is the structural reason the system is safe to ship into a TPA workflow. A reserve change above authority becomes an `AuthorityRequest` routed through the escalation chain — never silently applied. A coverage decision is always a human click — the AI never recommends a path because recommendation anchors the adjuster before reasoning. A recovery demand goes to the adverse party only after the adjuster approves the language. A loss run going to a client carries the citations and reasoning trail the AI built. These are not UX choices — they are structural protections.

### The specialist surface — the core product moment

Every specialist that bears on a legally significant decision presents three layers, always in the same shape:

1. **Evidence found** — the documents, statements, and sourced rules the AI read, each clickable to the source
2. **Probability per underlying question** — how each piece of the decision pencils out, with cited evidence behind every probability
3. **Probability per outcome path** — the distribution over the choices the adjuster faces, plus *what would shift the distribution*

There is **no "recommended decision" field**. By design. The AI's job is surfacing evidence and quantifying uncertainty; the human picks the path. This shape is calibratable, it avoids anchoring the adjuster, and it places the legally-bearing decision exactly where it belongs.

A concrete illustration of the data shape (not a finalized UI — the actual cockpit layout is open until implementation and review). A demand package arrives in an active BI claim. The Liability specialist runs and surfaces:

> **Liability Specialist — Claim #4471**
>
> **Evidence found (9 items):**
> - ✓ Insured skid marks ~12 ft before impact   [police-rpt §4 + scene photos]
> - ✓ Damage pattern: rear-end, square impact   [repair-est §1, photos]
> - ✓ Witness A: "insured was riding the claimant's bumper"   [rec-stmt-witness-A p.2 ¶3]
> - ⚠ Witness B: "claimant changed lanes right in front of him, no signal"   [rec-stmt-witness-B p.1 ¶4]
> - ⚠ Insured: "claimant cut in suddenly"   [rec-stmt-insured p.3 ¶2]
> - ✗ Claimant: "in lane for ~30 seconds before impact"   [rec-stmt-claimant p.2 ¶1]
> - (absence) — no signaling evidence either way
> - ✓ Florida modified-51 rule applies   [sourced legal rule `FL_negligence_modified_51_2023`]
>
> **Probability per question:**
> - Was insured following too close?   **85%** — physical evidence + Witness A; no contradicting evidence
> - Did claimant change lanes abruptly?   **55%** — disputed; two statements support, one disputes, no independent source
> - Was claimant signaling?   **25%** — only claimant's own statement supports
>
> **Probability per fault allocation:**
> ```
> 100 / 0   ████░░░░░░░░░░░░░░░░░░░░  18%
>  80 / 20   █████████████░░░░░░░░░░░  42%
>  70 / 30   ███████░░░░░░░░░░░░░░░░░  23%
>  60 / 40   ████░░░░░░░░░░░░░░░░░░░░  11%
>  50 / 50   █░░░░░░░░░░░░░░░░░░░░░░░   5%
>  40 / 60 (claimant barred)   ░░░░░░  1%
> ```
>
> **What would shift this:**
> - Dashcam or vehicle telematics → collapses lane-change dispute (~30% mass shift)
> - Independent confirmation on signaling → shifts 70/30 → 60/40 mass
> - Insured admission of distraction → ~95% mass on 100/0
>
> **Draft assessment ready** — cites evidence rows above.   [view] [edit] [attach to file]
>
> **Your call:**   [ 100/0 ]   [ 80/20 ]   [ 70/30 ]   [ Other... ]   [ Request more info ]

Every specialist that touches a legally-bearing decision works this way. **The AI did the reading. The human picks the path with evidence in front of them.**

**Reserve specialist** sees a police report come in, an attorney letter come in, and new medical bills come in → extracts everything, calculates an updated reserve *band* per component with citations, surfaces it: *"BI reserve band $42K–$51K (median $46.5K, 80% CI), driven by E1 (demand $48K), E2 (3 medicals $11.2K), E3 (attorney rep). Authority required: handler ($46.5K is within $50K cap)."* The adjuster picks the point and approves.

**Recovery specialist** sees a police report come in → extracts the adverse driver, verifies their carrier, drafts the recovery demand → surfaces: *"Recovery opportunity probability: 88%. Recoverable amount band: $11K–$17K. Florida 2-year SOL applies. Evidence preservation: vehicle still at body shop — recommend hold. Draft demand attached, cites police report ¶3, ¶7 and damage photos."* The adjuster reviews the evidence and approves the referral.

**Closure specialist** continuously tracks the closure checklist → when a file is procedurally ready to close, surfaces: *"Ready-to-close probability: 94%. Blocking defects: 0. Or: 1 blocking defect — open Recovery in `potential` status (referenced AgentAction from 2026-02-04)."* If a defect exists, the Action Type validator in the substrate refuses the close write until it's resolved — not as a policy, as the only way a write can pass.

**Brief specialist** does no decision work. It anchors the cockpit: the moment the adjuster opens a claim, the Brief is already there showing what happened since the last touch, what each other specialist is surfacing, what's missing, and what correspondence is in flight.

### Why this division is non-negotiable

The TPA's delegated authority is contractually capped at exactly the decisions we require approval for. Coverage denials, reserve changes above threshold, settlements above limit, consent-to-settle — these are the decisions the client / carrier holds final authority on, by contract. Automating them would directly contradict the operating model the TPA exists inside, and would create bad-faith exposure that is expensive, discoverable, and relationship-ending. We require approval at exactly these points by design — both because the operating model demands it, and because that is where the product is genuinely safe.

### The unified workspace

When the adjuster sits down for the day, the workspace shows them the prioritized queue — which claims to work on today, ordered by SLA risk, exposure trajectory, and specialist-surfaced urgency. When they open a file, they see one curated brief: the current state of the claim, the recommendations each specialist has surfaced, the decisions pending. They review, approve, modify, dismiss. They move on.

The whole experience is **one workspace, one workflow, one decision loop** — not a tangle of tabs and tools.

---

## §4 — The wedge: what ships

The product ships with the shared file, the workspace, and the full lifecycle covered:

**Six specialists** — Brief, Coverage, Liability, Reserve, Recovery, Closure
**Two services** — Priority Scorer, Correspondence

The earlier draft of this strategy deferred Coverage and Liability on bad-faith-exposure grounds, scoped Notice as a separate specialist, and left out Brief and the priority/correspondence services entirely. That scoping was wrong on every front. Coverage and Liability *do* belong in the wedge because the legally-bearing decision is narrow — approving denial language, picking contested fault percentages — and everything upstream of that decision is AI work. Notice doesn't need a separate specialist because notice obligations are detected by Brief and Reserve and routed through Correspondence. Brief is the missing piece that makes everything else useful: without a one-screen summary refreshed on every change, the adjuster re-reads the file from scratch every time they touch it.

### What each specialist addresses

| Specialist | Cardinal sin it addresses | Strongest argument |
|---|---|---|
| **Brief** | Cold-open reading time | The adjuster never starts a claim from zero again — the AI has read it and summarized what changed since last touch |
| **Coverage** | Coverage analysis is expensive, slow, and inconsistent across adjusters | Probability-shaped evidence presentation lets the adjuster make the call faster and with more defensibility than the manual workflow |
| **Liability** | Fault allocation is judgment-heavy and uneven across handlers | Distribution over allocations + jurisdictional rule applied + cited evidence — the adjuster picks the bucket with the full picture in front of them |
| **Reserve** | Reserve drift | Stops the financial-accuracy failure clients audit TPAs against most harshly. Band + citations let the adjuster pick the point. |
| **Recovery** | Recovery leakage | Direct dollar ROI; "we found $X in recoverable money your adjusters missed" is the cleanest sales pitch in claims |
| **Closure** | Closure incompleteness + silent recovery leakage at close | Touches every claim. Closure can't physically happen if a recovery is unresolved — enforced by the substrate, not by policy |

### Where the services earn their keep

| Service | What problem it solves |
|---|---|
| **Priority Scorer** | A queue ordered by "open / not started" is meaningless. The adjuster needs the queue ranked by what they should work next — SOL clocks, drift since last touch, exposure, awaiting-approval backlog. Reason chips per claim so the ranking is legible. |
| **Correspondence service** | If the system knows what's missing, it should act on it. Routine recipients get the request auto-sent; adversarial recipients get an auto-drafted one-click send. The adjuster doesn't compose the email. |

### What we explicitly exclude

**SIU / Fraud specialist** — fraud detection requires adversarial-noise modeling we are not anchoring on real adjuster-validated fraud signal. Out of scope until the synthesis pipeline produces realistic fraud cases.

**Multi-line expansion (workers' comp, professional lines)** — the specialty auto+property TPA wedge is the lock-in choice; horizontal expansion comes after that customer profile is proven.

**Automating the legally-bearing decision** — the human-only column in §3 stays human-only by design. Auto-applying coverage decisions or contested liability allocations is not a future feature; it's the bad-faith trap the entire architecture is built to avoid.

### What the demo shows

The shape below is a narrative walkthrough of the *flow* — what the adjuster encounters, in what order, with what backing data. The specific UI elements (button labels, card layouts, ranking visualization) are illustrative; the actual cockpit design is open until implementation and review.

A single adjuster's morning, compressed. They open the cockpit. The queue is ranked by the Priority Scorer, with per-claim reason chips so the order is legible. The top three claims surface with evidence of why they're at the top — something like a tight SOL, a demand received without a draft response, or a closure blocked by an unresolved Recovery flag.

They click the first claim. The Brief is already there — claim story, what changed since their last touch, a list of awaiting-approval items from the other specialists. Coverage was clean enough that the adjuster's only step is reviewing the evidence and clicking through. Three cards await:

- **Liability** — distribution over fault allocations, evidence behind every bucket, drafted assessment. Adjuster reads the evidence, picks a bucket, approves.
- **Reserve** — band per component with citations. Adjuster picks a point in the band, approves.
- **Settlement counter** — drafted range based on jurisdictional templates and the locked liability assessment. Adjuster edits if needed, approves the send. Correspondence service handles delivery to claimant's counsel (one-click approve because counsel is an adversarial recipient).

A few minutes on the highest-priority claim. Moves to the next.

**Three minutes of demo. Three claims. The AI read everything, drafted everything, sent the routine pieces. The human approved the legally-bearing ones with full evidence in front of them. Ninety minutes of pre-AI adjuster work, compressed to clicks.**

This is the demo moment the wedge is built around. Exact UI choices are decided in implementation, against real interaction with real claim data, not from a doc.

---

## §5 — How we'll know it's working

Per-specialist metrics ladder up to system-level metrics ladder up to a single PMF signal.

### Per-specialist metrics (in-product)

Two metric families: **operational impact** (does the specialist move the workflow numbers we care about) and **integrity** (is the AI's output trustworthy enough for the adjuster to actually use it).

**Operational impact:**

- **Brief specialist:** time-to-first-action on a claim (target: <60s from cockpit open to first decision, vs current 5–10 minutes of re-reading)
- **Coverage specialist:** coverage-decision turnaround time (target: same-day vs current 2–5 days)
- **Liability specialist:** time from evidence-complete to liability assessment finalized (target: same-day vs current 7–14 days)
- **Reserve specialist:** reserve-drift reduction (paid-to-final-reserve ratio); time from material event to reserve update (target: same-day vs current average of 7–14 days)
- **Recovery specialist:** recovery dollars identified per 1,000 claims; recovery-referral-to-recovered-dollar conversion rate (versus baseline closed-file audit findings)
- **Closure specialist:** closure-defect rate caught pre-close (releases missing, reserves unreconciled, recovery not considered); closure-cycle-time reduction

**Integrity (the four-layer truth eval — see AGENT_ARCHITECTURE §8):**

- **Calibration** — at predicted probability *P*, what fraction of golden-set cases actually resolve as predicted? A well-calibrated specialist's 80%-confident outputs resolve as predicted ~80% of the time. Calibration failures are actionable in either direction. This is the strongest argument for the probability + evidence output shape over recommendations.
- **Evidence recall** — did the specialist find every piece of evidence a human reviewer cited as relevant? Measured on the golden set.
- **Citation grounding** — what fraction of probabilistic claims carry citations that the verifier confirms exist and say what they're cited as saying? Schema enforces ≥1 citation; the eval confirms the citations are real.
- **Layer C-statutory accuracy** — for sourced legal rules, did the specialist apply them correctly?
- **Layer C-policy accuracy** — for client-configured rules, did the specialist apply them correctly?
- **Layer D rubric** — cross-model judge on golden-set rationale quality

### System-level metrics (workflow-wide)

- Adjuster hours saved per claim (target: 35-45 minutes per active file based on document-summarization + reserve-recalculation savings)
- Adjuster NPS on the workspace itself (target: +40 after 60 days of use)
- Client retention at the TPA buyer (a real-customer signal — the TPA's clients staying because TPA's loss-run accuracy improved)

### The single PMF signal

**Caseload throughput at constant quality.** A specialty TPA with the product can handle 1.5-2× the caseload per adjuster at the same audit-pass rate. That is what specialty TPAs would pay for — because their cost structure is per-adjuster and their revenue is per-claim. We move both numbers in their favor.

If we can demonstrate that signal at one TPA over six months, we have PMF.

---

## §6 — The moat: per-customer configuration corpus

The architecture (shared file + specialist team + workspace) is shippable; a competent horizontal AI vendor could replicate it. The moat sits one level deeper, at the **specialist configuration interface**.

Every specialist runs against client-specific rules:
- Reserve specialist needs each client's reserve authority thresholds and material-event definitions
- Recovery specialist needs each client's recovery-pursuit rules (in-house vs vendor, contingency split, minimum-dollar thresholds)
- Closure specialist needs each client's loss-run format, DOI reporting requirements per state, and closure-audit standard

These rules are encoded once per customer, validated against their real claim handling agreement and authority matrix, and they become the configuration corpus that drives the specialists at that customer. Every new customer adds a new configuration. Every new configuration is a new data point about how real specialty TPAs operate.

This configuration corpus is what a horizontal AI vendor structurally cannot ship. They can match the model. They cannot encode 200 specialty TPAs' authority schedules without rebuilding the forward-deployed engineering practice required to do it. The longer we operate, the wider the corpus gets, and the harder it is to displace.

The same configuration corpus is the **expansion lever**. The architecture that works at a $200M specialty TPA works at a $5B regional carrier. The configuration grows in scope (more programs, more reporting requirements, more compliance) but the engineering investment carries forward.

---

## §7 — Competitive position

The market is crowded, but it is crowded around the *wrong* places. No incumbent owns the layer we are building.

| Category | Examples | Where they play | Why they don't compete with us |
|---|---|---|---|
| **System of record** | Guidewire ClaimCenter, Origami, Riskonnect | Storing the claim, workflow routing | They are the file; we are the layer on top of the file. We integrate with them. |
| **Point AI — FNOL** | Snapsheet, Lemonade's internal AI | Auto FNOL only | Single-stage; doesn't sit across the lifecycle |
| **Point AI — damage assessment** | Tractable, CCC Smart Image | Auto + property photo damage | Single-stage; doesn't touch reserves, recovery, closure |
| **Estimating** | Xactimate (Verisk), CCC | Property line-item scope | Single-stage; doesn't sit at the workflow level |
| **Horizontal multi-line AI** | FurtherAI | Multi-line, multi-vertical AI | Breadth over depth; cannot encode the per-customer authority schedule we live inside |
| **Policy administration** | Avallon, Bindable | Upstream of claims | Different problem; not in our lane |
| **Generalist TPA platforms** | Sedgwick's internal stack | Internal tooling for one TPA at scale | Built for one company; not productized for the LMM market |

**Our position is unoccupied.** A specialty mid-tier auto + property TPA today is choosing between (a) building it themselves (no engineering capacity), (b) buying a point AI tool that automates one stage (doesn't touch the lifecycle), (c) buying a horizontal AI vendor that doesn't fit their workflow, or (d) doing nothing. The fourth option is what most of them do.

The bet is that a lifecycle-spanning intelligence layer, configured to their specific authority schedule, is more valuable than any of (a)-(c). The data + workflow research supports this position.

---

## §8 — Risks and what would kill this

Five risks, each plausible, each with a falsifying signal we would watch for.

**1. Customer acquisition risk — LMM TPAs may not have software budgets.** Specialty mid-tier TPAs run lean; software procurement may take longer than the LMM thesis predicts. *Falsifying signal:* first three sales cycles run >12 months despite procurement-velocity claims. *Response:* shift to MGA programs (faster procurement) or smaller-tier carriers, both adjacent buyer pools.

**2. Configuration cost risk — each new customer is FDE-heavy.** If encoding a customer's authority schedule takes 6 engineer-weeks per deployment, unit economics break before scale. *Falsifying signal:* first deployment takes >8 weeks; second takes >4 weeks. *Response:* invest in configuration tooling (form-driven, customer-self-service) before scaling deployments.

**3. Incumbent response risk — CCC or Snapsheet ships specialist watchers.** If CCC (with $2.65B market cap) decides to build the same layer, they have the SOR relationships, the data, and the distribution. *Falsifying signal:* CCC or Guidewire announces a "claims intelligence layer" product. *Response:* depth-of-configuration is harder to copy than the architecture; we keep building configuration corpus.

**4. Data risk — real customer data access becomes harder.** Without paid customer data, we cannot validate the specialists at production quality. The portfolio project survives on synthetic generation grounded in public data; the real product needs real data. *Falsifying signal:* first customer refuses access to their CMS for integration. *Response:* deploy in observe-only mode initially (analyzes without integrating), build trust, expand access over time.

**5. Liability risk — a specialist recommendation contributes to a bad-faith claim.** Even with human-in-the-loop, the system's recommendation can be discoverable in litigation. *Falsifying signal:* legal counsel at any first customer flags this in diligence. *Response:* aggressive logging, clear "drafts only" labeling, contractual indemnification carve-outs.

### The bear case

We would abandon the thesis if all three of these happened simultaneously:
- First two specialty TPA sales cycles each take >18 months
- Configuration cost per customer stays above 6 engineer-weeks even after tooling investment
- A major incumbent (CCC, Snapsheet, Guidewire) ships a competing claims intelligence layer with credible adoption

Any one of those alone is survivable. All three is the signal that the wedge is wrong.

---

## §9 — What's deferred to PRD

STRATEGY locks the wedge, the user, the architecture, the metrics, the moat, and the competitive picture. The following decisions belong in PRD because they require the strategic frame to already be locked.

- **The exact PMF metric and target threshold.** STRATEGY names caseload throughput at constant quality; PRD specifies the measurement protocol and the target number.
- **The data scope for the demo.** Which datasets we use (FARS, CRSS, NFIP are the public foundation), what we synthesize on top (unstructured documents, parties as policyholders, coverages, reserves over time, payments, recoveries), and what the demo dataset looks like end-to-end.
- **The ontology schema in detail.** STRATEGY locks the three-part architecture; PRD specifies the entities, attributes, and relationships.
- **The configuration schema.** STRATEGY locks "per-customer configuration is the moat"; PRD specifies what configuration fields each specialist requires and how they're authored.
- **The evaluation framework.** Per-specialist golden sets, LLM-judge prompts, schema-validation rules, regression-test patterns.
- **The weekend-by-weekend build sequence.** Defer to PRD.

---

*STRATEGY refinement follows the first PRD draft and any customer-discovery conversation that surfaces new evidence on the §6 configuration corpus.*
