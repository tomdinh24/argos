---
tags:
  - project/argos
  - type/research
  - subject/tpa-workflow
  - status/draft
created: 2026-05-28
aliases:
  - Specialty TPA Workflow
  - TPA Workflow Research
---

# Specialty Auto + Property TPA Workflow — Practitioner-Grounded Research

> Source-grounded workflow research for the locked buyer profile (specialty mid-tier auto + property TPA). Companion to the generic [adjuster-workflow.md](./adjuster-workflow.md) — this doc applies the TPA-specific overlay. Used as primary input for [THESIS.md](../THESIS.md) §2 (work as it actually flows today) and §5 (the asset), and as scope input for STRATEGY.md / PRD.md.

---

## §1 — Purpose and scope

The buyer profile locked in Phase 3 of the [project plan](~/.claude/plans/we-will-go-lmm-keen-glacier.md) is a **mid-tier specialty TPA that focuses on auto and property claims handling**, $50M–$500M revenue range, serving self-insured corporates, captives, carriers outsourcing claims, and MGA programs. This document captures what their adjusters actually do, stage-by-stage across the claim lifecycle, with auto and property cuts separated.

The doc answers five questions at every lifecycle stage:

1. What actually happens?
2. What does the adjuster, examiner or specialist do hour-by-hour?
3. What inputs come in / outputs go out?
4. What decisions get made, by whom, and what triggers escalation?
5. What's automatable with current LLM capability vs what genuinely needs human judgment?

Stage list: Intake (FNOL) → Coverage Determination → Triage / Assignment → Investigation → Liability / Fault Determination → Reserve Setting → Negotiation / Settlement → Excess Carrier Coordination → Payment / Billing → Subrogation → Closure + Reporting.

---

## §2 — Methodology and the evidence-strength bar

The research bar was set explicitly: practitioner-attributed quotes from real specialty auto+property TPAs, with verifiable links. Two rounds of deep research surfaced the public-evidence ceiling honestly — there is not enough public material to supply 3–5 unique direct practitioner quotes for all 11 stages × 2 cuts (auto/property). Rather than pad with synthesized voice or vendor marketing, this doc uses a tiered evidence approach:

- **Tier 1 — Specialty TPA primary evidence.** Named practitioner quotes, job postings, and official operating descriptions from verified mid-tier specialty TPAs (NARS, Raphael & Associates, Custard / Riverwood, Engle Martin).
- **Tier 2 — Adjacent generalist-TPA evidence.** Used where the workflow is highly standardized industry-wide (e.g., excess-carrier reporting). Labeled explicitly.
- **Tier 3 — Industry-standard practice.** Workflow detail that is domain consensus, not single-sourced. Labeled as such.

Every stage carries an **evidence-strength flag** (strong / moderate / thin). Thin-evidence stages name what would require **customer access** to fully validate — see §4.

---

## §3 — Anchor organizations

| Organization | Why it's used | Evidence drawn from |
|---|---|---|
| **NARS (North American Risk Services)** | Best public fit: privately owned specialty P&C TPA with distinct Transportation, Commercial Property, Homeowners, Recovery and SIU functions | Current auto PD, homeowners property, senior claims job postings; official claims-service descriptions; named practitioner articles; CLM interview |
| **Raphael & Associates** | Specialty P&C claims administrator with property, auto/trucking, and SIR/excess reporting language | Property Desk Adjuster role description; SIR services description; auto/property claim-assignment workflow language |
| **Custard / Riverwood Claims Management** | Transportation- and property-focused claims operations including auto liability, heavy equipment, property, and SIU | Capacity-support workflow descriptions; heavy-equipment damage handling; SIU function; Riverwood TPA positioning and client portal |
| **Engle Martin & Associates** | Property-loss specialist (closer to monoline property adjusting than full auto+property TPA) — used for property appraisal and disputed commercial property evidence | Named practitioner interviews; senior property adjuster job description |

Revenue band verification per anchor was not always possible from public materials. The anchors were selected primarily on **workflow fit and named-practitioner availability**, not revenue exactness.

---

## §4 — The customer-access gap (the structural limit on this research)

Public sources reliably establish the **industry workflow** at a specialty auto+property TPA. They do not reliably establish the **company-specific operational reality** at any given TPA. The latter — internal authority limits, reserving philosophies, client-specific authority matrices, actual reporting cadences, and real-world reserve-trajectory patterns — is only obtainable by being on-site with a customer.

This gap maps directly to a structural point about the product itself: the durable asset (the ontology) is the industry layer; the per-customer adapter (mapping their `clm_status_cd` enum to our ontology's status field, encoding their specific authority limits) is the forward-deployed work. **The fact that public research stops where it does is the same boundary the product would stop at without a customer.** This framing should land in [STRATEGY.md](../STRATEGY.md) as the "what changes with a real customer" section.

For this document, that means: every stage marked "thin" is also a customer-discovery question. The questions are collected in §16.

---

## §5 — Verified practitioner quote bank

These are the strongest short, attributable practitioner excerpts surfaced during research. They are referenced throughout the workflow stages rather than re-quoted in each section.

> *"Our first contact with a claimant is the most important."*
> — **Peter Vrooman**, Assistant Director of Transportation Claims, **NARS**, practitioner article on early injury claim resolution.

> *"You have to be able to adapt to the different philosophies and approaches of each client."*
> — **Robert Ruryk**, CEO and Chief Claims Officer, **NARS**, CLM Alliance interview, June 2013. [Source](https://www.theclm.org/)

> *"Litigation should only be used in carefully selected cases."*
> — **Giovanna Gallottini**, Senior Litigation Adjuster, **NARS**, property assignment-of-benefits case study.

> *"The policy still needs to be applied."*
> — **Colby Chavers**, National General Adjuster, **Engle Martin**, practitioner discussion of property appraisal. [Source](https://englemartin.com/our-appraisers-are-adjusters-claims-are-what-they-do-every-day/)

> *"We not only include an accurate estimate but also a detailed summary within our closing report."*
> — **Rodgers Truitt**, General Adjuster, **Engle Martin**, on documenting appraisal resolution. [Source](https://englemartin.com/our-appraisers-are-adjusters-claims-are-what-they-do-every-day/)

A realistic specialty TPA adjuster's day is not a clean linear workflow. New losses, diary deadlines, vendor calls, reserve reviews, settlement requests, client reporting, and escalation occur in parallel. The stage-by-stage structure below describes the lifecycle; the per-stage "what the adjuster actually does" sections reconstruct what that work looks like in practice from the cited role descriptions and operating materials.

---

## §6 — Stage 1: Intake / FNOL

### Auto cut

**What actually happens.** An auto or commercial transportation claim enters through a client portal, phone intake line, email, broker, fleet manager, claimant attorney, or repair facility. NARS maintains 24/7 phone reporting and separate transportation / auto property-damage capabilities. Raphael accepts auto and trucking loss assignments through its claims-assignment workflow.

Required intake fields for a commercial auto loss:
- Client program and insured entity
- Policy or account number where available
- Vehicle / unit / trailer / driver details
- Accident date, time, location
- Claimant vehicles and passengers
- Police involvement, injuries, towing
- Repair facility, photographs, immediate mobility issues
- Attorney, fatality, severe injury, or government vehicle involvement flags

The output is not just a claim number. It's the first structured file: parties, exposure types, preliminary severity, required contacts, assigned adjuster, initial diaries, and potential escalation flags.

**Hour-by-hour.** A transportation adjuster's first block: review FNOL record → confirm client program → contact insured driver/fleet contact → contact claimant when appropriate → request police reports + photographs → decide on field inspection, appraiser, tow/salvage vendor, or senior bodily-injury adjuster.

Vrooman describes first claimant contact as the point where the adjuster establishes rapport, clarifies what happened, understands damages, and sets expectations. His framing is specifically about early injury handling, but it reveals the operating priority: first interaction affects attorney involvement, cycle time, and claimant experience.

**Inputs / outputs.** *In:* FNOL call notes, loss notice form, driver statement, police exchange, photos, tow notice, repair-shop contact, attorney representation letter. *Out:* Claim record, acknowledgement, adjuster assignment, contact plan, initial diary, appraisal/inspection request, injury escalation, vendor instruction, early client notification where warranted.

**Decisions / escalation.** Routine low-severity PD claims go directly to auto PD adjuster. Escalation triggers: severe BI, fatality, multiple claimants, potential litigation, attorney representation, suspicious facts, coverage uncertainty, commercial-vehicle downtime, exposure beyond retention or authority. NARS' commercial transportation posting assigns auto PD adjusters direct responsibility for fact-of-loss establishment, liability assessment, fraud identification, vendor management, reserve analysis, and reports under client guidelines.

**Automation cut.** *Strong:* extract FNOL details from email or call transcript; detect missing information; create structured claim summaries; route PD-only vs BI; flag severe-injury / attorney / fraud / total-loss indicators; draft acknowledgements. *Human:* emotionally sensitive claimant contact; statements involving disputed facts; severity judgment where liability or injury is unclear; coverage disclaimers; emergency vendor authority; early settlement discussions.

### Property cut

**What actually happens.** A homeowners or commercial property FNOL commonly arrives from insured, broker, property manager, restoration contractor, public adjuster, mortgage company, or attorney. Raphael accepts property and homeowner claims assignments. NARS describes immediate homeowners-loss response including inspection, temporary living arrangements, emergency mitigation coordination.

Property intake required fields differ from auto:
- Risk address and occupancy
- Date of loss and alleged cause (water, fire, wind, theft, hail, vandalism, liability)
- Building habitability
- Immediate mitigation needs (board-up, water extraction)
- Contents damage and potential additional living expense
- Mortgagee, property manager, commercial tenants
- Whether a restoration vendor, public adjuster, or assignment-of-benefits contractor is already involved
- Evidence-destruction risk from imminent repairs or cleanup

**Hour-by-hour.** For a water or fire loss the first hour is operationally urgent: confirm safety and habitability → arrange mitigation where permitted → identify temporary lodging need → schedule field inspection → request photographs → obtain initial cause + scope description. NARS' homeowners handling specifically includes immediate contact, inspection, statements, photos, estimates, origin and scope determination, covered-damage evaluation, fraud consideration, mitigation vendor dispatch, temporary-living vendor coordination for ALE.

**Inputs / outputs.** *In:* Loss notice, photographs/video, emergency-services invoice, mitigation authorization, policy/account details, insured statement, contractor communication, temporary-housing needs, public adjuster letter, AOB document. *Out:* Claim assignment, emergency mitigation instruction, field inspection request, ALE referral, document request list, cause-of-loss diary, potential SIU or coverage flag.

**Decisions / escalation.** Routine minor water or weather claims stay with desk homeowners adjuster. Escalation: major fire, suspected fraud, habitability issues, commercial business-interruption exposure, disputed late notice, multiple possible causes, AOB litigation risk, large-loss thresholds, possible excess-layer involvement. NARS' homeowners role specifically includes coverage analysis, investigation, damage assessment, vendor management, reserve analysis, settlement negotiations, fraud identification.

**Automation cut.** *Strong:* intake summarization; cause / address / urgent-needs extraction; missing-photo or policy-info detection; emergency mitigation routing; AOB or public-adjuster language detection; insured status request drafts. *Human:* habitability determination; emergency spending authority; mitigation reasonableness; evidence integrity; AOB validity; communicating with a displaced homeowner.

---

## §7 — Stage 2: Coverage Determination

### Auto cut

**What actually happens.** The adjuster determines which client program governs the loss and what coverage applies. For commercial transportation: confirm named insured, driver relationship, scheduled vehicle, permissive use, vehicle type, policy period, liability vs physical-damage coverage, deductible/SIR, other applicable coverage. NARS describes auto rental and leasing claims as requiring adjusters to determine applicable coverages and the order they apply. Commercial transportation job posting assigns adjusters direct responsibility for coverage analysis.

**Hour-by-hour.** Adjuster reviews FNOL against client handling instructions, policy/program documents, vehicle schedules, leases, rental agreements, certificates. May contact client risk manager when vehicle/driver/use is unclear. For self-insured programs, identifies retention and excess-layer relevance.

Ruryk's framing is central here: different clients have different claims philosophies; a TPA adjuster is not applying one universal playbook. Coverage determination at a TPA = which client + which program + which version of "the rules" applies, every time.

**Inputs / outputs.** *In:* Policy declarations, client claims-handling guidelines, vehicle schedules, driver information, rental/lease agreements, prior claim info, SIR documentation, excess reporting instructions. *Out:* Coverage position summary, applicable program confirmation, deductible/SIR coding, potential reservation or client referral, excess-monitoring flag, documented coverage rationale.

**Decisions / escalation.** Adjuster can autonomously confirm straightforward coverage when documentation is complete and ordinary. Escalation: unscheduled vehicle or disputed permissive use; potential excluded use; multiple possibly applicable policies; potential denial or reservation of rights; exposure approaching SIR/excess thresholds; client-specific authority requirements.

**Automation cut.** *Strong:* policy-document extraction; vehicle/driver matching; checklist generation; missing-coverage-document detection; FNOL-fact-to-policy-term comparison; relevant-endorsement surfacing. *Human:* interpreting ambiguous coverage; issuing or recommending denial; reservation-of-rights posture; deciding which client philosophy applies in a borderline claim.

### Property cut

**What actually happens.** Property coverage analysis is more form- and fact-intensive than auto PD. Adjuster identifies policy form, covered premises, applicable cause, exclusions, deductible, sublimits, contents coverage, ALE or business-income coverage, endorsements, mortgagee issues, shared/layered program participation. NARS' commercial property handlers work with package, monoline, shared, and layered coverage and with manuscript endorsements + sublimits. Homeowners workflow includes applying and explaining policy provisions.

**Hour-by-hour.** Property adjuster compares alleged cause-of-loss with inspection findings, policy language, contractor submissions. In a water-loss file: evaluate whether damage resulted from a sudden covered event, ongoing leakage, failed mitigation, or disputed timing. If a vendor holds an AOB, determine whether the assignment and invoice are valid and payable.

Gallottini's NARS case study describes the practical AOB problem: disputed access, late reporting, possible spoliation, multiple possible loss dates, invoices that may not match the covered loss. The work is forensic, not just clerical.

**Inputs / outputs.** *In:* Policy forms, endorsements, declarations, inspection reports, photographs, cause-and-origin findings, contractor estimates, mitigation invoices, proof of loss, AOB documents, public-adjuster correspondence, ALE documentation. *Out:* Coverage assessment, covered-vs-uncovered scope, deductible/sublimit application, document request, reserve basis, client referral or denial recommendation.

**Decisions / escalation.** Disputed cause; major commercial loss; business interruption; suspected prior damage; late reporting; access denial; AOB litigation; appraisal demand; potential SIU referral; exposure reaching upper program layers.

**Automation cut.** *Strong:* organize forms and endorsements; match claimed categories to limits; identify missing documents; compare estimate line items with stated cause; summarize policy questions for review. *Human:* applying exclusions to disputed physical facts; determining coverage when scope is contested; assessing credibility and spoliation; communicating a partial denial.

---

## §8 — Stage 3: Triage / Assignment / Prioritization

### Auto cut

**What actually happens.** After preliminary coverage + severity review the file is routed to the appropriate claim owner. A specialty auto TPA typically separates:
- Simple physical damage
- Commercial trucking or fleet property damage
- Bodily injury
- Serious injury or litigated BI
- Total loss and salvage
- SIU
- Subrogation/recovery
- Field inspection or specialty equipment appraisal

NARS publicly lists separate openings for commercial transportation auto PD, senior bodily injury, SIU, subrogation, and total loss. Custard describes a claims-capacity model where lower-end claims can be fast-tracked while complex claims get dedicated attention.

**Hour-by-hour.** Receiving adjuster scans new-loss queue, reviews severity + assignment notes, sets first-contact priorities, creates diaries, decides what needs immediate action vs scheduled follow-up. Supervisor or assignment function reallocates when complexity, geography, client instructions, or workload require it.

**Inputs / outputs.** *In:* FNOL record, severity indicators, injury info, litigation flags, vehicle type, repairability info, client instructions, adjuster capacity. *Out:* Assigned adjuster, specialty referral, initial diary, supervisor escalation, inspection/appraisal request, SIU or recovery alert, initial reporting route.

**Decisions / escalation.** Routine PD vs needs-senior-involvement. Injury severity, attorney representation, heavy-equipment or commercial downtime, suspected fraud, fatality, media sensitivity, high-limit exposure → senior or specialist.

**Automation cut.** *Strong:* severity classification; routing recommendations; missing-contact alerts; diary scheduling; workload dashboards; total-loss or litigation flags. *Human:* accepting a severity classification; prioritizing competing emergencies; escalating ambiguous BI or fraud indicators; assigning the right experienced handler.

### Property cut

**What actually happens.** Property triage separates ordinary homeowners losses from large commercial property, complex cause-of-loss, high-value contents, catastrophe volume, potential fraud, liability overlap, appraisal disputes, litigation. Raphael's Property Desk Examiner role covers residential + commercial losses and requires field-estimate evaluation, subrogation identification, end-to-end claim management.

**Hour-by-hour.** Property examiner reviews urgency first: active water intrusion, fire displacement, unsafe premises, emergency mitigation. Then assigns field inspection, confirms vendor involvement, flags possible ALE, decides on commercial property / litigation / SIU / appraisal specialist need.

**Inputs / outputs.** *In:* Cause of loss, occupancy, habitability, initial damage photographs, contractor involvement, reported loss amount, commercial vs residential risk, prior-claim information. *Out:* Desk-vs-field assignment, emergency mitigation approval route, ALE referral, large-loss escalation, SIU consideration, appraisal or expert referral, client reporting schedule.

**Decisions / escalation.** Major fire, commercial interruption, unsafe occupancy, suspected intentional loss, large contents exposure, disputed contractor scope, AOB involvement, layer/excess implications.

**Automation cut.** *Strong:* classify urgency; identify water/fire/ALE indicators; route field inspection; monitor catastrophe volume; identify duplicate claims or suspicious document patterns. *Human:* deciding whether an apparent emergency is reasonable; expert-need decisions; balancing insured urgency against coverage uncertainty; handling contested vendor relationships.

---

## §9 — Stage 4: Investigation

### Auto cut

**What actually happens.** Auto investigation establishes how the collision occurred, what damage resulted, which injuries are related, what vehicles or property were affected, and whether fraud or recovery exists. NARS describes transportation handling as requiring statements from all parties and prompt inspection or appraisal to reduce downtime. In taxi-fleet claims, NARS emphasizes in-depth liability investigation to limit payment to damage caused by the insured driver. Custard's specialty vehicle workflow includes photographs, estimates, inspection, agreed repair pricing, ACV analysis, salvage bids, total-loss handling.

**Hour-by-hour.** An auto adjuster's day may include:
- Calling the insured driver, claimant, and witnesses
- Reviewing police reports and accident diagrams
- Obtaining vehicle photos and repair estimates
- Coordinating an appraiser or field adjuster
- Comparing impact points with reported accident facts
- Reviewing towing, storage, rental, downtime issues
- Checking for prior damage or suspicious loss indicators
- Recording findings and updating liability + reserve assumptions

For commercial equipment, inspection may occur at a repair shop or fleet yard, with the adjuster obtaining photos, repair info, pre-loss value, salvage evidence.

**Inputs / outputs.** *In:* Statements, police report, photographs, repair estimates, appraiser report, medical documentation, towing/storage invoices, rental documentation, telematics where available, fraud indicators. *Out:* Investigation narrative, damage evaluation, liability recommendation, vendor report, reserve update, SIU referral, recovery referral, client status report.

**Decisions / escalation.** Routine repairs proceed within guidelines after inspection. Escalation: conflicting statements, injury causation questions, suspicious damage patterns, questionable repair scope, severe injury, litigation, damages exceeding authority.

**Automation cut.** *Strong:* chronology creation; statement comparison; repair-amount extraction; inconsistency identification; police-report summarization; estimate-version comparison; missing-evidence tracking; supervisor-ready investigation summary. *Human:* evaluating witness credibility; collision causation in disputed facts; interviewing upset claimants; recognizing nuanced fraud behavior; SIU referral judgment.

### Property cut

**What actually happens.** Property investigation determines origin, cause, scope of damage, covered amount, mitigation reasonableness, possible fraud, potential subrogation. NARS' homeowners handling involves contact, inspection, statements, photographs, estimates → origin, scope, covered damage, fraud, recovery determination. Uses field appraisers, temporary-living vendors, mitigation services (water extraction, board-up).

**Hour-by-hour.** Property adjuster / examiner may:
- Contact insured and schedule inspection
- Review mitigation photographs and moisture maps
- Receive field adjuster's estimate
- Compare contractor estimates with observed damage
- Review damaged contents or temporary-housing documentation
- Determine need for engineer, cause-and-origin expert, or SIU
- Review AOB documents or public-adjuster correspondence
- Document whether damages relate to the reported event

Gallottini's case study illustrates the difficulty: a water remediation vendor may submit an invoice while questions remain about when the loss occurred, whether access was provided, whether damaged material was preserved, whether the invoice reflects covered work.

**Inputs / outputs.** *In:* Inspection report, photographs, moisture documentation, contractor estimate, mitigation invoice, contents inventory, ALE receipts, engineering report, fire report, AOB paperwork, recorded statements. *Out:* Scope-of-loss evaluation, coverage recommendation, estimate review, mitigation decision, ALE determination, SIU referral, subrogation flag, reserve revision.

**Decisions / escalation.** Uncertain cause; large damage; repairs destroyed relevant evidence; insured/contractor contests scope; AOB vendor threatens litigation; commercial interruption exposure grows.

**Automation cut.** *Strong:* compare estimates; extract invoice line items; detect duplicated charges; organize photos and reports; summarize inspection findings; identify missing documents. *Human:* whether observed damage arose from the reported peril; contractor credibility; displacement handling; expert involvement; distinguishing inflated scope from legitimate complex repair.

---

## §10 — Stage 5: Liability / Fault Determination

### Auto cut

**What actually happens.** Auto liability is a formal decision about whether the insured driver caused the accident and, in comparative-negligence jurisdictions, what percentage of responsibility should be allocated among parties. NARS' commercial auto posting explicitly includes investigation of compensability, liability, negligence. Transportation materials describe liability investigation designed to pay only damages attributable to the insured driver.

**Hour-by-hour.** Adjuster reviews statements, police reports, photographs, vehicle damage patterns, traffic-control facts, witness information, possibly video or telematics. Documents:
- Accepted or disputed facts
- Applicable duty and breach
- Comparative fault considerations
- Supported damages
- Recovery potential
- Whether denial, partial acceptance, or settlement is appropriate

**Inputs / outputs.** *In:* Accident report, diagrams, claimant + insured + witness statements, photographs, video, applicable traffic rules, vehicle estimates, injury evidence. *Out:* Liability decision, percentage-allocation rationale, communication to claimant or adverse carrier, reserve adjustment, subrogation referral, client report.

**Decisions / escalation.** Ordinary rear-end or clear lane-change facts within authority. Escalation: disputed severe injuries, fatality, unclear comparative fault, multiple defendants, litigation, high reserves, possible excess involvement.

**Automation cut.** *Strong:* map evidence to a timeline; identify contradictions; draft liability-analysis summaries; compare statements with police narrative; flag likely comparative-fault questions. *Human:* final fault allocation; credibility judgments; defensibility of denial; nuanced jurisdictional application; communicating a disputed liability position.

### Property cut

**What actually happens.** In first-party property claims, "liability" is less about fault percentage and more about whether a covered peril caused covered damage. Fault matters when:
- A third party caused damage and subrogation is possible
- A premises-liability claim arises from property conditions
- A contractor, plumber, manufacturer, tenant, or neighboring property may be responsible
- A vendor seeks payment through an AOB

**Hour-by-hour.** Adjuster compares reported cause, inspection findings, policy language, contractor documents, possible third-party responsibility. In a property appraisal dispute, the adjuster must keep policy application separate from mere pricing disagreement.

Chavers (Engle Martin) frames this: even during appraisal, policy coverage remains an active claims question — "The policy still needs to be applied."

**Inputs / outputs.** *In:* Inspection documentation, expert reports, maintenance history, contractor invoices, policy provisions, subrogation indicators, witness statements, AOB records. *Out:* Covered-cause position, third-party responsibility assessment, recovery referral, vendor payment position, appraisal strategy, litigation referral.

**Decisions / escalation.** Coverage-causation disputes, suspected third-party negligence, disputed AOB standing, major commercial losses, appraisal/litigation demands → supervisor, client, or counsel.

**Automation cut.** *Strong:* identify potential responsible third parties; organize causation evidence; compare invoice scope with covered damage; draft recovery referrals. *Human:* causation, negligence, coverage application, settlement posture, deciding whether to defend or resolve a contested claim.

---

## §11 — Stage 6: Reserve Setting and Re-Reserving

> *Reserve drift — where a claim starts at $5K and creeps up to $50K — is the cardinal sin in TPA management. Clients judge TPAs harshly on reserve accuracy because reserves drive their financials directly.*

### Auto cut

**What actually happens.** Reserves are the TPA's current financial estimate of likely claim cost. Initial auto reserves may include vehicle repair or ACV, towing/storage/rental/commercial downtime, BI exposure, medical payments or UM/UIM, defense or litigation expense, salvage and potential recovery offsets. NARS' auto PD and senior BI postings require timely and appropriate reserve analysis and report completion.

**Hour-by-hour.** Adjuster sets an initial reserve after early fact collection, then revisits after key events: appraisal receipt, total-loss determination, injury documentation, demand letter, attorney involvement, mediation, lawsuit, adverse liability development, recovery opportunity. Reserve is not only an accounting number — it controls escalation, client reporting, and potential excess notification.

**Inputs / outputs.** *In:* Damage estimate, ACV calculation, medical info, liability assessment, demand, litigation budget, salvage estimate, recovery likelihood, client authority rules, SIR/excess thresholds. *Out:* Reserve components, documented rationale, system update, client report, authority request, possible excess notice.

**Decisions / escalation.** Ordinary PD within adjuster authority. Escalation: severe BI, major reserve increase, litigation, reserve above settlement authority, exposure nearing retention or excess-reporting thresholds, major deviation from initial evaluation.

**Automation cut.** *Strong:* reserve-component templates; estimate extraction; reserve-change alerts; variance analysis; reminders after material events; documentation drafts explaining changes. *Human:* injury valuation; liability-adjusted exposure; litigation risk; reserve adequacy under uncertain facts; strategic implication of a significant reserve increase.

### Property cut

**What actually happens.** A property reserve may include building damage, contents damage, emergency mitigation, ALE, business interruption or rental-income exposure, debris removal, expert/engineering expense, litigation/appraisal/defense cost, potential recovery. NARS' homeowners property adjuster role specifically includes reserve analysis and reporting; commercial property materials highlight claims involving loss of income, sublimits, layered structures.

**Hour-by-hour.** Adjuster sets early reserve based on initial cause and visible damage, then updates as inspection results, contractor supplements, contents lists, ALE duration, business-interruption estimates, appraisal demands, or litigation developments emerge.

**Inputs / outputs.** *In:* Field estimate, contractor supplement, mitigation invoice, ALE documentation, business-income calculation, policy sublimits, appraisal demand, expert report, coverage position. *Out:* Component-level reserve, reserve-change narrative, client status report, excess-monitoring notice, settlement authority request.

**Decisions / escalation.** Routine water/wind claim becomes major repair; ALE duration extends materially; business-income exposure grows; disputed coverage makes reserve uncertain; estimated loss approaches a program layer.

**Automation cut.** *Strong:* reconcile estimate versions; track ALE and mitigation payments against reserves; flag supplements; compare reserves with known documentation; draft reserve-change explanations. *Human:* estimating complex repair scope; business interruption; disputed coverage; litigation exposure; settlement posture.

---

## §12 — Stage 7: Negotiation and Settlement

### Auto cut

**What actually happens.** Auto settlement varies sharply by exposure type. **Physical damage:** adjuster negotiates repair estimates, authorizes reasonable repairs, resolves total-loss valuation, manages salvage, addresses towing/rental/commercial downtime. **Bodily injury:** adjuster evaluates medical documentation, liability, claimant circumstances, attorney demands, settlement authority. In litigation, adjuster manages defense counsel, arbitration, mediation, client reporting. NARS' commercial auto postings assign adjusters settlement negotiations, litigation management, attorney interaction, arbitration on first- and third-party claims. Custard's specialty vehicle workflow includes repair-price negotiation, ACV assessment, salvage handling, total-loss settlement.

**Hour-by-hour.** Auto adjuster's negotiation day may include:
- Reviewing a repair supplement from a body shop
- Calling a claimant about vehicle damage or rental status
- Evaluating a BI demand package
- Requesting authority from a supervisor or client
- Preparing a mediation report
- Coordinating defense counsel
- Securing a release and payment instruction

Vrooman's framing indicates that early injury settlement may be appropriate only after coverage and liability are sufficiently established — "fast settlement" is not a substitute for sound evaluation.

**Inputs / outputs.** *In:* Estimates, appraisal reports, total-loss valuation, medical bills, demand package, wage documentation, liability evaluation, defense report, mediation brief, authority instructions, release terms. *Out:* Offer, counteroffer, negotiated estimate, settlement recommendation, authority request, executed release, payment instruction, litigation strategy update, closure pathway.

**Decisions / escalation.** Within assigned authority and client guidelines. Escalation: demands exceed authority; serious injury creates large exposure; counsel recommends settlement outside range; litigation changes risk; excess carrier consent may be required.

**Automation cut.** *Strong:* summarize demand packages; compare requested damages with documented evidence; draft negotiation chronology; produce authority memos; track offers and counteroffers; identify missing release terms. *Human:* valuation of pain and suffering; claimant credibility; negotiation tone; mediation decisions; authority recommendations; whether settlement is fair and defensible.

### Property cut

**What actually happens.** Property settlement often involves negotiation over scope and price rather than BI value. Typical disputes: contractor scope vs adjuster estimate; emergency mitigation invoice; contents valuation; ALE duration and reasonableness; appraisal demand; AOB vendor claim; public-adjuster presentation; commercial property repair or business-income dispute.

Gallottini frames property vendor litigation as something that should be selected strategically rather than treated as automatic response to every disputed invoice — "Litigation should only be used in carefully selected cases."

**Hour-by-hour.** Property adjuster may review contractor supplements, compare estimate line items, discuss disputed repairs with vendors, validate ALE invoices, coordinate appraisal, prepare settlement reports, consult client or counsel where litigation is possible.

**Inputs / outputs.** *In:* Contractor estimates, mitigation invoices, inspection report, contents inventory, proof of loss, ALE receipts, appraisal demand, expert opinion, AOB contract, settlement authority. *Out:* Agreed estimate, payment recommendation, partial settlement, appraisal referral, litigation recommendation, release or final settlement documentation.

**Decisions / escalation.** Appraisal; disputed coverage; AOB litigation; major commercial loss; fraud concerns; large settlement authority requirements; potential layer/excess reporting.

**Automation cut.** *Strong:* compare line items and supplements; summarize disputed amounts; identify unsupported charges; prepare negotiation packages; track settlement versions. *Human:* evaluating true repair scope; policy interpretation; dealing with distressed insureds or adversarial contractors; selecting litigation; agreeing to final resolution.

---

## §13 — Stage 8: Excess Carrier Coordination

> **Evidence strength: thin.** Raphael's official SIR materials state TPA work includes compliance, excess-carrier reporting, and maintaining communication among insured and carrier interests in SIR programs. Public practitioner material does not disclose actual notification thresholds, consent-to-settle clauses, takeover rights, or reporting cadence for specialty auto/property programs. Those details live in client service instructions, authority matrices, and excess policy terms.

### Auto cut

**What actually happens.** In a self-insured commercial auto program, the TPA handles ordinary claims within retention until severity creates a realistic possibility of piercing the SIR or triggering excess-reporting requirements. Severe BI, fatality, multi-vehicle losses, lawsuits, large reserve jumps, or unusually adverse liability facts are common operational triggers.

**Hour-by-hour.** Adjuster or supervisor assembles reporting package: facts of loss, liability posture, injury status, reserve, litigation status, key documents, expected development, recommended next actions. Once excess is in, adjuster may submit periodic updates and seek consent before settlement per contract terms.

**Inputs / outputs.** *In:* SIR amount, excess reporting rules, reserve, BI evaluation, litigation status, authority matrix, client instructions, policy requirements. *Out:* Excess notice, status report, authority request, consent request, litigation update, documentation of excess-carrier involvement.

**Decisions / escalation.** Adjuster does not invent reporting thresholds — client program and excess terms govern. Human escalation when notice trigger is reached; when settlement may affect excess exposure; when defense strategy changes; when authority becomes unclear.

**Automation cut.** *Strong:* monitor reserves and severity flags against configured thresholds; assemble notice packets; track reporting deadlines; summarize claim developments. *Human:* whether excess exposure is reasonably implicated; what strategic information to communicate; settlement authority; consent and claim-control decisions.

### Property cut

**What actually happens.** Property excess coordination becomes relevant in large fire, catastrophe, major commercial building, loss-of-income, habitational, or layered-coverage claims. NARS' commercial property materials explicitly reference shared and layered coverage structures.

**Hour-by-hour.** Adjuster tracks building, contents, mitigation, ALE, business-income exposure; communicates significant reserve development; prepares inspection and estimate summaries; escalates when claim may affect another layer.

**Inputs / outputs.** *In:* Layer structure, reserves, expert reports, repair estimates, business-income analysis, coverage assessment, appraisal or litigation developments. *Out:* Layer notification, reserve update, large-loss report, settlement authority request, consent documentation where required.

**Decisions / escalation.** Major reserve movements; disputed coverage on large loss; possible appraisal award above retention; substantial business interruption; litigation. Exact triggers must be validated through customer interviews or actual program instructions.

**Automation cut.** *Strong:* threshold monitoring; packet assembly; document timelines; reporting reminders. *Human:* layer interpretation; coverage posture; strategic settlement recommendation; communication with excess stakeholders.

---

## §14 — Stage 9: Payment and Billing

> **Evidence strength: moderate** for claim payments; **thin** for loss-fund accounting. NARS' senior claims advocate role includes payment processing; NARS describes controls around significant financial transactions. Custard's specialty vehicle workflow includes payment recommendations, total-loss settlement, salvage disposition. NARS property materials describe ALE vendors and mitigation services. Under-documented publicly: back-office movement of funds from a particular self-insured client loss fund, replenishment mechanics, invoice approval hierarchy, TPA fee billing.

### Auto cut

**What actually happens.** Auto payment may include repair payment to shop or insured, total-loss settlement, lienholder-protected payment, towing and storage, rental or downtime, BI settlement after executed release, salvage assignment and proceeds, recovery posting where subrogation succeeds.

**Hour-by-hour.** Adjuster confirms supporting documentation, verifies settlement terms, confirms payee structure and authority, prepares payment recommendation, tracks payment issuance, coordinates total-loss or salvage processes.

**Inputs / outputs.** *In:* Approved estimate, total-loss valuation, lienholder details, settlement release, payment authority, vendor invoice, salvage documentation, client payment rules. *Out:* Payment request, approved payee record, settlement check instruction, salvage assignment, payment ledger update, claim financial report.

**Decisions / escalation.** Payment authority; disputed payees; lienholders; release adequacy; large settlements; suspicious invoices; client-specific fund rules.

**Automation cut.** *Strong:* invoice extraction; payment-packet preparation; payee-document checklists; release-presence checks; reserve-vs-payment reconciliation; salvage tracking. *Human:* releasing funds; approving exceptions; resolving lienholder questions; validating a settlement release; addressing suspected fraud.

### Property cut

**What actually happens.** Property payment can include building-damage payment, contents payment, mortgagee co-payee checks, mitigation or restoration vendor payment, ALE reimbursement or temporary-housing vendor payment, commercial income-loss payments, appraisal award or litigated settlement, payment to an assignee where a valid AOB applies.

**Hour-by-hour.** Adjuster evaluates invoices and estimates, confirms covered scope, verifies mortgagee or vendor involvement, calculates deductibles and limits, assesses ALE documentation, sends approved payment recommendations through the financial control process.

**Inputs / outputs.** *In:* Estimate, proof of loss, contractor invoice, mitigation records, mortgagee information, ALE receipts, AOB documents, settlement agreement, authority instructions. *Out:* Payment recommendation, partial payment, vendor direct-pay documentation, mortgagee check routing, ALE payment tracking, closing financial reconciliation.

**Decisions / escalation.** Disputed payee entitlement; unclear AOB validity; contractor invoices substantially exceed supported scope; ALE duration questioned; payment approaches limits; major litigation involved.

**Automation cut.** *Strong:* invoice reconciliation; document completeness; payment schedule tracking; deductible and limit calculations; identifying unsupported invoice items. *Human:* coverage-linked payment decisions; AOB standing; disputed vendor payments; mortgagee complications; settlement finality.

---

## §15 — Stage 10: Subrogation and Recovery

### Auto cut

> **Evidence strength: moderate** for the existence and operating role of a dedicated recovery function; **thin** for internal dollar thresholds, arbitration rules, and fee structure.

**What actually happens.** At a specialty auto or transportation TPA, the front-line adjuster is usually responsible for recognizing recovery potential during ordinary claim handling, but the actual recovery pursuit may transfer to a dedicated subrogation or recovery unit. NARS states its Recovery Unit handles subrogation, salvage, and deductible collection across all lines and is designed to become involved early rather than leaving the entire recovery function with the original adjuster.

For an auto claim, an adjuster can typically make an initial referral autonomously when the file contains clear indicators:
- Insured vehicle was rear-ended or struck while legally parked
- Police report identifies an adverse driver
- Another carrier has acknowledged coverage
- Repair, towing, rental, storage, or salvage amounts have been paid
- Commercial downtime or additional property-damage exposure may be documented
- Insured has a recoverable deductible

Once referred, a recovery specialist decides whether evidence is sufficient to issue a demand, whether additional documentation is required, whether liability will be disputed, whether the recovery effort should continue, be compromised, or ruled out.

**Hour-by-hour.** Front-line adjuster identifies opportunity while handling underlying claim. Recovery specialist receives evidence, confirms adverse party and insurer, sends demand package, negotiates disputes, posts recovered amounts, reports unsuccessful recovery where liability or collectability prevents repayment. Custard's specialty-equipment workflow includes subrogation audit to verify damage, repair relation, parts, labor before payment or recovery recommendations.

**Inputs / outputs.** *In:* Liability decision, adverse carrier details, police report, paid invoices, photographs, settlement documentation, salvage value, deductible information. *Out:* Recovery referral, demand package, adverse-carrier communication, recovery posting, deductible reimbursement, recovery closure or rule-out reason.

**Decisions / escalation.** Liability disputed; comparative negligence materially reduces recovery; adverse carrier denies coverage or disputes damages; commercial vehicle downtime, heavy-equipment damage, or large salvage amounts; arbitration, litigation, or outside counsel needed; client has specific rules for compromising recoveries or waiving deductibles; file was already closed and identified through recovery audit rather than ordinary handling.

**Automation cut.** *Strong:* detect recovery potential from police reports, liability notes, payment history, adverse-party info; identify paid claims that appear to lack a recovery referral; assemble demand package containing liability summary, invoices, photographs, police report, payment ledger, deductible, salvage documentation; extract adverse-carrier contact details; track response deadlines; compare paid damages with amounts demanded or recovered; flag files where salvage, deductible, or recovery proceeds remain unresolved at closure; support closed-file recovery audits by ranking files with apparent missed opportunities. *Human:* final liability and comparative-negligence analysis; whether documentation is sufficient to make or defend a recovery demand; compromise decisions; arbitration/litigation referral; negotiating contested commercial downtime, diminished value, or complex heavy-equipment losses; any decision governed by client-specific recovery authority or fee arrangements.

### Property cut

> **Evidence strength: moderate** for identifying and referring recovery opportunities; **thin** for the full property-subrogation workflow inside specialty TPAs.

**What actually happens.** Property subrogation begins when the adjuster identifies that a covered property loss may have been caused by a responsible third party rather than solely by an insured event with no recovery path. Common examples:
- Plumber or contractor causes water damage
- Defective appliance, supply line, electrical component, or roofing product contributes to a loss
- Neighboring unit, tenant, landlord, or property manager causes or fails to prevent damage
- Vehicle damages a building, fence, or other insured structure
- Utility, maintenance vendor, or restoration provider may have contributed to damage
- Fire, leak, or collapse produces evidence that should be preserved for later technical analysis

**The first important property-subrogation task is often not sending a demand — it is preserving the evidence before damaged components are discarded or repairs eliminate the ability to determine cause.**

NARS publicly states its property claim handling includes evaluating recovery potential and that its Recovery Unit handles subrogation across lines. Raphael's Property Desk Adjuster description requires property examiners to recognize subrogation potential during residential and commercial property claim handling.

**Hour-by-hour.** Property desk examiner handling a potential recovery file may:
- Review field adjuster's inspection report and photographs
- Identify whether cause suggests contractor negligence, product failure, or another responsible party
- Contact insured or property manager about damaged components, maintenance records, or prior repairs
- Ask that a failed pipe, appliance component, electrical part, or other physical evidence be retained
- Evaluate whether an engineer, fire investigator, or cause-and-origin specialist is needed
- Compare contractor or mitigation invoices with the documented damaged area
- Pay covered portions of the insured's claim while preserving recovery rights
- Create a recovery referral with paid-loss documentation, photographs, causation summary
- Respond to recovery-unit questions after additional evidence is obtained

**Inputs / outputs.** *In:* Field inspection report; cause-and-origin or engineering analysis; photographs and video; failed product or damaged-component evidence; maintenance and repair records; contractor, plumber, utility, or tenant information; building, contents, mitigation, and ALE payments; policy information relevant to covered payment and recovery rights; statements from insureds, tenants, vendors, witnesses. *Out:* Potential subrogation flag in claim system; evidence-preservation request; expert referral where cause requires technical assessment; recovery referral packet; demand package to responsible party or its insurer; recovery status updates for client; deductible reimbursement documentation; file note explaining outcome.

**Decisions / escalation.** Adjuster-level: whether file contains an apparent recovery opportunity; whether immediate preservation instructions should be issued; which paid-damage records and photographs accompany a referral; whether to diary the file for recovery follow-up. Specialist or supervisor: whether expert investigation is economically justified; whether causation evidence is adequate for a demand; whether multiple responsible parties should be pursued; whether a disputed recovery should be compromised or litigated; whether recovery efforts should be abandoned. **Triggers:** major fire, explosion, structural damage, or high-value water loss; possible product defect or complex engineering causation; destruction or disposal of evidence before inspection; multiple possible responsible parties; large business-interruption or ALE payments that expand recoverable value; contractor, vendor, or assignee disputes overlapping with recovery; potential litigation or material client reporting threshold.

**Automation cut.** *Strong:* detect references to third-party cause in field reports, statements, and vendor correspondence; flag files involving plumbers, contractors, defective equipment, adjacent units, or vehicle impact; generate evidence-preservation checklist based on cause category; assemble paid-loss schedules and supporting invoices; track whether recovery was considered before closure; draft recovery referral summary linking cause, payments, and responsible-party information; detect closed files with paid property losses and unreviewed third-party indicators. *Human:* determining physical causation; whether expert investigation is warranted; managing destroyed or incomplete evidence; assessing the strength of negligence or product-defect theories; choosing responsible parties to pursue; settling disputed recovery claims; balancing recovery activity against the insured's underlying claim resolution.

---

## §16 — Stage 11: Closure and Reporting

### Auto cut

> **Evidence strength: strong** for QA/audit categories and client reporting; **moderate** for individual adjuster closure steps; **thin** for state DOI filing workflows.

**What actually happens.** NARS publicly describes a quality-control program that audits coverage analysis, reserving, documentation, file handling, evaluation, negotiation, settlement, client reporting, vendor management, litigation handling, and subrogation. It also provides a loss-run request function and describes recovery audits for closed claims. Riverwood's client portal states clients can view claim information online in real time.

Closure is not simply paying the final bill and switching status. The file must be financially reconciled, operationally complete, recoveries considered, and sufficiently documented for client reporting and quality review. Depending on the claim:
- Repair payment or total-loss payment completion
- Rental, towing, storage, or commercial downtime resolution
- Bodily injury settlement and signed release
- Lienholder or salvage documentation
- Litigation resolution if suit was filed
- Subrogation and deductible-recovery disposition
- Final reserve reconciliation
- Required client status reporting
- Complete claim documentation sufficient for audit

**Hour-by-hour.** Auto adjuster closing files may:
- Review list of files eligible for closure or overdue for final activity
- Confirm payments issued correctly and cleared through required processing
- Verify total-loss settlement, lienholder payment, or salvage assignment complete
- Check whether BI release signed and properly stored
- Confirm whether subrogation, salvage, or deductible collection remains open
- Reduce or close remaining reserves where appropriate
- Write final claim summary explaining outcome, payments, liability, recovery, settlement rationale
- Submit final report accessible to the client
- Close diaries, vendor tasks, litigation tasks
- Respond to supervisor or QA audit questions

Supervisor or quality function may sample the file after closure, identify missing documentation or inaccurate handling, use patterns to guide training or client reporting.

**Inputs / outputs.** *In:* Final repair invoice or total-loss settlement documents; payment confirmations; release documentation; lienholder or salvage documents; recovery disposition and deductible status; litigation closure documentation; reserve history and paid-loss ledger; client reporting requirements; open diary, vendor, or compliance tasks. *Out:* Final claim note or closure report; closed reserve and financial reconciliation; client-facing status update or loss-run data; recovery closure or continuing-recovery referral; QA/audit-eligible claim file; exception note where claim closes with unresolved issue approved by authority.

**Decisions / escalation.** Adjuster-level: whether ordinary file tasks complete; whether reserves can be reduced or closed within authority; whether file is ready for routine closure; whether recovery has been considered and properly recorded. Supervisor / client / specialist: whether an unresolved payment, recovery, or litigation issue prevents closure; whether exception is acceptable under client guidelines; whether a quality defect requires correction before closure; whether complaint, large-loss issue, or compliance concern requires further reporting. **Triggers:** missing release on BI settlement; unresolved lienholder, salvage, or payee issue; remaining open litigation or defense invoices; recovery potential not evaluated; paid amount exceeding authority or reserve rationale; client complaint, regulatory issue, or audit exception; exposure involving excess-carrier reporting or unresolved consent.

**Automation cut.** *Strong:* generate closure checklist from claim type and client rules; detect open diaries, unpaid invoices, unreconciled reserves, missing releases; confirm whether recovery was referred, ruled out, or remains open; reconcile paid amounts, reserves, salvage, recoveries; draft closure narrative from structured file history; prepare client-facing loss-run fields and claim outcome metrics; identify files likely to fail QA audit because of missing documentation; surface patterns across adjusters, programs, or vendors. *Human:* deciding whether all obligations are truly resolved; whether incomplete issue acceptable for closure; approving financial exceptions; whether complaint or reporting issue requires escalation; evaluating quality of liability, settlement, or recovery reasoning; making regulatory filing decisions.

### Property cut

> **Evidence strength: strong** for disputed property-claim closing reports and appraisal-resolution documentation; **moderate** for routine TPA property closure; **thin** for DOI filing mechanics.

**What actually happens.** Property closure is more documentation-heavy than simple auto PD closure because a file may contain building damage, contents, mitigation, ALE, mortgagee issues, public-adjuster involvement, AOB disputes, appraisal, and possible recovery. The strongest direct practitioner evidence comes from Engle Martin's Appraisal & Umpire Practice:

> *"We not only include an accurate estimate but also a detailed summary within our closing report."*
> — **Rodgers Truitt**, General Adjuster, Engle Martin

This supports a key operating conclusion: in disputed property losses, closure must document the reasoning behind resolution, not simply record a final payment amount.

A property claim closes after all covered categories and related claim-management obligations are resolved or appropriately documented: final building-damage payment; contents evaluation and payment; mitigation invoice resolution; ALE or temporary-housing conclusion; mortgagee or lender payment handling; contractor, public-adjuster, or AOB dispute resolution; appraisal award or litigation disposition; recovery/subrogation disposition; reserve reconciliation; final client reporting and file documentation.

**Hour-by-hour.** Property adjuster preparing a file for closure may:
- Review building, contents, mitigation, ALE payment categories separately
- Confirm deductible, sublimits, coverage decisions applied consistently
- Check whether mortgagee, contractor, or assignee payment rights remain unresolved
- Review final contractor invoices or appraisal documentation
- Confirm end date and reasonableness of ALE payments
- Determine whether subrogation was evaluated and evidence preserved
- Reduce remaining reserves or explain why money remains open
- Draft final claim report summarizing cause, covered damage, settlement, disputed items, payments, recovery
- Provide client with documentation needed to understand the settlement outcome
- Respond to QA review, audit, or client follow-up

In appraisal or disputed-scope claims, the closing report explains why final settlement differed from an earlier carrier estimate, contractor proposal, or opposing appraiser's position.

**Inputs / outputs.** *In:* Final building and contents estimates; mitigation invoices and supporting records; ALE ledger, receipts, temporary-housing documentation; mortgagee, assignee, or contractor payment information; appraisal award, mediation agreement, or litigation resolution; expert or cause-and-origin reports; coverage determination and payment history; reserve ledger and recovery status; client reporting instructions. *Out:* Final property claim report; payment and reserve reconciliation; documented settlement rationale; closure coding in claim system; client-facing loss-run or portfolio reporting data; recovery closure or continuing recovery assignment; QA/audit-ready file; exception/escalation documentation where issue remains.

**Decisions / escalation.** Adjuster: whether ordinary building, contents, mitigation, ALE tasks complete; whether supported payments and reserves reconciled; whether file contains remaining recovery potential; whether final claim report adequately explains resolution. Supervisor / client / counsel / specialist: whether appraisal or litigation documentation sufficient for closure; whether unresolved contractor, mortgagee, public-adjuster, or AOB issues prevent closure; whether major reserve variance requires client explanation; whether a recovery, fraud, or regulatory issue requires continued handling; whether a large or layered property claim requires additional reporting. **Triggers:** open ALE or ongoing habitability issue; disputed contractor invoice or unpaid mitigation vendor; mortgagee or AOB entitlement dispute; unresolved appraisal or litigation; recovery evidence not preserved or causation still disputed; material reserve-vs-payment discrepancy; large-loss, client-reporting, or excess-layer implication; potential regulatory or complaint exposure.

**Automation cut.** *Strong:* track all financial buckets separately (building, contents, mitigation, ALE, experts, litigation, recovery); identify missing documents needed for closure; flag open ALE, vendor, mortgagee, AOB, appraisal, or recovery tasks; reconcile estimate versions, final payments, and remaining reserves; draft final property closure report from verified file materials; build a settlement-rationale timeline for client review; detect files where payment occurred but subrogation review is absent; support QA sampling and identify claim-handling patterns across programs. *Human:* confirming that covered damage and disputed scope have been resolved fairly; whether appraisal or litigation is genuinely complete; whether contractor, assignee, or mortgagee rights remain; evaluating unresolved causation or recovery questions; approving closure despite residual uncertainty; explaining material settlement decisions to the client.

### Regulatory reporting caveat

Public evidence confirms specialty TPAs may handle compliance and reporting obligations. Raphael states its self-insured/SIR services include compliance, excess-carrier reporting, and licensing requirements relating to claims. NARS describes proactive regulatory compliance and regulatory auditing. However, no practitioner-level public source describes the actual state DOI filing workflow for specialty auto or property TPA claims — which claims trigger filing, which party files, what fields are submitted, which systems are used, how filing deadlines are monitored.

For the project, **state DOI reporting should be represented as a configurable compliance workflow requiring client validation, not as a fully specified automation opportunity.**

---

## §17 — Synthesis: implications for product scope

### The shape this points at

The pattern across the lifecycle repeats at every stage: a **structured claim file** that everything reads from, a **specialist watching it** for one specific thing, and a **human approving** what the specialist recommends. The specialists differ by what they look for (reserves moving, recovery signals, notice triggers, closure readiness, etc.) but they share the same underlying file, the same workspace, and the same configuration mechanism. This is one intelligence layer made of small specialists, not a bag of separate agents. See [THESIS §5](../THESIS.md) for the full architecture (shared record + specialist team + workspace) and the hospital analogy that makes it intuitive.

### Where the credible specialist value is

Across the lifecycle, the strongest, lowest-risk automation clusters at the **document-and-data ends of every stage and the recovery/closure back office**:

- FNOL structured capture and routing (§6)
- Coverage *issue-surfacing* and dec-page / SIR / excess-tower extraction (§7)
- Severity triage of the bulk caseload (§8)
- Investigation document-chase, photo/estimate ingestion, statement summarization (§9)
- Liability fact-pattern assembly and rationale drafting (§10)
- Reserve-change trigger surfacing and consistency checks across a book (§11)
- Demand-package intake / extraction and counter-offer drafting (§12)
- **Excess notice-trigger detection and aggregate-erosion tracking** (§13) — currently a classic, expensive-error stage
- Total-loss lienholder / salvage and property staged-payment mechanics (§14)
- **Subrogation identification and demand / arbitration-contention packaging** (§15) — a genuine leakage fix
- **Loss-run assembly and closed-claim reporting** (§16)

These share three traits: **high-volume, rules-or-document-amenable, and currently manual and error-prone**. A defensible product is an **adjuster-augmentation layer** that drafts, extracts, reconciles, flags triggers, and enforces checklists / diaries — with the human on every binding decision.

### What the product should explicitly NOT claim

The product should not claim to make binding **coverage**, **liability-allocation**, **reserve**, or **settlement** decisions. Four reasons recur across the evidence:

1. **Delegated authority is capped by contract.** A TPA frequently *cannot* finalize coverage denials, large reserves, or above-limit settlements without client / carrier sign-off. An "autonomous decisioning" claim directly contradicts the operating model the TPA exists inside.

2. **Bad-faith and E&O exposure concentrate at exactly these decisions** — coverage denial, time-limit / policy-limits demands, reserve adequacy, consent-to-settle. An automated misstep here is expensive, discoverable, and the kind of thing that ends client relationships.

3. **The judgment-heavy interpretive work is not reliably automatable.** Disputed-fault reconstruction, injury causation and valuation, anti-concurrent causation, scope negotiation against incentivized public adjusters / contractors — none of these are reliably reachable with current LLM capability, and none should be claimed.

4. **"Touchless / straight-through" claims must be scoped to clean, low-severity, clear-liability files only.** Never injury, never disputed liability, never commercial-auto BI, never cause-disputed property. The marketing temptation here is real; the failure mode is leakage and complaints, which compound.

### The structural product point

The public layer of research gets you to the **industry** workflow. It cannot reach the **per-customer** specifics that determine where an agent can actually act — delegated-authority matrices, SIR / reserve / settlement thresholds, excess-reporting protocols, vendor SLAs, subrogation fee splits, and loss-run formats. Every thin-evidence flag in this document is, in effect, a customer-discovery question.

This points at the durable product shape:

> **The agent's safe operating envelope is defined by each client's authority schedule — which means the product is configured per customer, and that configuration is the moat, not the model.**

That sentence is the FDE thesis crystallized. The ontology + agent topology is the durable asset; the per-customer authority configuration is the deployment work; together they constitute the moat. Generic horizontal AI vendors cannot replicate the second half. This framing belongs in THESIS §5 (the asset) and STRATEGY (the wedge product + the moat section) verbatim.

---

## §18 — Customer-discovery questions to validate (the thin-evidence flag consolidated)

Each question below maps to a stage and is the validation list for a real practitioner conversation. Where useful, the artifact to ask to see is named. Public research cannot answer these — they require customer access. They are the contract surface between this document's industry-layer evidence and a real customer's company-specific reality.

1. **Intake (§6).** How do intake scripts and capture fields differ per client program? What SIR thresholds and 24-hour contact SLAs are contractually fixed?

2. **Coverage (§7).** What are the delegated coverage-authority dollar limits per client? How often do examiners issue RORs vs escalate? *(Ask to see a redacted TPA-client claims-handling agreement.)*

3. **Triage (§8).** What severity-scoring rubric and per-client routing rules are used? Which signals force a supervisor override? *(Ask to see a triage / assignment SOP or scoring rubric.)*

4. **Investigation (§9).** What is the vendor-panel / SLA economics — which panel shops, restoration firms, and IAs are on the panel at what negotiated rates? What client scoping guidelines constrain estimates? What's the in-house vs IA split per program?

5. **Liability (§10).** How do adjusters assign comparative-fault percentages in practice? What evaluation guideline or review governs it? How much GL / premises work does the TPA actually carry?

6. **Reserves (§11).** What is the reserving philosophy and methodology? What are the delegated reserve-authority thresholds per client? What reserve-to-attachment ratio triggers escalation? *(Ask to see a reserve-authority matrix.)*

7. **Settlement (§12).** What is the settlement-authority matrix — at what dollar thresholds do adjuster, supervisor, and client / carrier each have to approve? How are time-limit and policy-limits demands routed internally? How is appraisal triggered? *(Ask to see a settlement-authority schedule.)*

8. **Excess coordination (§13).** What per-program reporting thresholds, cadence, and format apply? At what point does the excess carrier take control of the file in practice (vs in policy)?

9. **Payment (§14).** How does the client's loss fund advance and replenish? What disbursement-authority and dual-control / fraud checks apply? What are the per-program ALE / depreciation handling rules?

10. **Subrogation (§15).** What are the recovery fee structures — in-house vs contingency vendor vs client fee-split? What are the per-client recovery-sharing terms? How is deductible reimbursement to the insured sequenced relative to recovery? *(Ask to see a recovery / fee schedule.)*

11. **Closure (§16).** What loss-run formats, cadence, and data fields does each client demand? Which states' DOI closed-claim regimes does a given program trigger? What closure-audit standards does the TPA hold itself to? *(Ask to see a sample redacted loss-run package and closing-audit checklist.)*

These map directly to fields in the eventual ontology + agent authority matrix. Each one is also a real product-design decision that cannot be made in the abstract — every "this requires customer access" flag is *also* the per-customer configuration surface the moat lives in (see §17).

---

## §19 — Source list

### Primary specialty-TPA operating evidence

- **NARS — Additional Services.** Recovery Unit (subrogation, salvage, deductible collection across lines), early recovery involvement, closed-file recovery audits, QA measures covering coverage, reserving, documentation, settlement, reporting, vendor management, litigation, subrogation. https://www.narisk.com/additional-services/
- **NARS — About Us.** TPA with dedicated recovery + SIU functions, client-specific claim directives, internal auditing, proactive regulatory compliance. https://www.narisk.com/about-us/
- **NARS — Claims Services.** Property recovery evaluation and dedicated subrogation function. https://www.narisk.com/claims-services/
- **NARS — Commercial Transportation job posting.** Coverage analysis, liability assessment, fraud identification, vendor management, reserve analysis under client guidelines.
- **NARS — Homeowners Property handling description.** Immediate contact, inspection, statements, photos, estimates, origin/scope determination, covered-damage evaluation, fraud consideration, mitigation vendor dispatch, temporary-living vendor coordination for ALE.
- **Raphael & Associates — Self-Insured/SIR/RRG.** TPA handles compliance, excess-carrier reporting, licensing requirements relating to claims for self-insured entities. https://www.raphaelandassociates.com/sir/
- **Raphael & Associates — Property Desk Adjuster posting.** End-to-end residential and commercial property claim handling, damage investigation, field-estimate evaluation, subrogation potential recognition. https://raphaelandassociates.applytojob.com/apply/zneYatRwPy/Property-Desk-Adjuster

### Named practitioner evidence

- **Peter Vrooman**, Assistant Director of Transportation Claims, NARS — practitioner article on early injury claim resolution.
- **Robert Ruryk**, CEO and Chief Claims Officer, NARS — CLM Alliance interview, June 2013.
- **Giovanna Gallottini**, Senior Litigation Adjuster, NARS — property assignment-of-benefits case study.
- **Colby Chavers**, National General Adjuster, Engle Martin — property appraisal practitioner discussion. https://englemartin.com/our-appraisers-are-adjusters-claims-are-what-they-do-every-day/
- **Rodgers Truitt**, General Adjuster, Engle Martin — same source as above; appraisal closing report discussion.

### Adjacent / labeled-as-such evidence

- **Engle Martin — Appraisal & Umpire Practitioner Article.** Used as adjacent property-claims evidence, not as proof of a full TPA workflow. https://englemartin.com/our-appraisers-are-adjusters-claims-are-what-they-do-every-day/
- **Custard Insurance Adjusters — Heavy Equipment.** Review of transportation/heavy-equipment subrogation demand documentation including loss-related repair verification, parts/labor review, payment recommendations. Used as adjacent specialty transportation evidence. https://custard.com/heavy-equipment/
- **Riverwood Claims Management — Client Portal.** Real-time client access to claim information, supporting role of client-facing reporting. https://riverwoodtpa.com/client-portal/
- **Sedgwick Claims Service Guidelines (California Courts, 2023).** Used as labeled adjacent generalist-TPA evidence for highly standardized excess-coordination and DOI-compliance stages where the workflow does not differ materially between specialty and generalist TPAs.

### Verified job postings (from prior research rounds)

- **Creative Risk Solutions (Holmes Murphy) — Liability Claims Specialist.** Verified Workday posting; coverage confirmation, adjudication, subrogation, litigation management responsibilities. https://holmesmurphy.wd1.myworkdayjobs.com/en-US/CreativeRiskSolutionsCareers/job/Liability-Claims-Specialist---Remote_R0000839
- **Engle Martin & Associates — Senior Property Adjuster.** Verified posting; field investigation, climbing ladders, traversing roofs, commercial claim investigation. https://lensa.com/job-v1/engle-martin-associates/remote/senior-property-adjuster/5969d0e0cae27de01fc989bb164cc638
- **SCA Claim Services — Auto Liability Adjuster.** Determine legal liability, damages, coverage; develop exposures; set expense + indemnity reserves. https://www.scaclaims.com/auto-liability-adjuster/
- **Saia — Claims Adjuster.** Negotiates with carriers, plaintiff attorneys, claimants; attends mediations / trials; assigns defense counsel; litigation plans and budgets. https://www.indeed.com/hire/job-description/claims-adjuster
- **Syndicate Claims (Charles Taylor Adjusting) — Field Claim Adjuster.** Coordinate construction contractors / restoration; scene inspections; recorded statements; Xactimate / Xactanalysis; CAT deployment. https://www.syndicateclaims.com/job-descriptions/
- **Wheels — Subrogation Specialist (fleet auto).** Auto subro recovery, FNOL notifications, negotiate with carriers, UM direct collections, arbitration contentions. https://builtin.com/job/subrogation-specialist/3778354
- **Complex Claims Director — TPA Oversight.** Calculate / assign timely appropriate reserves; monitor reserve accuracy throughout life of claim; attend arbitrations, mediations, settlement conferences, trials. https://www.careerbuilder.com/job-details/complex-claims-director-tpa-oversight-dallas-tx--2789734f-cfd9-4d51-830d-aa8634838b21
- **Arch — Technical Claims Supervisor, Major Case Unit.** Oversight of TPA-handled complex auto / GL / trucking, primary / umbrella / excess. https://builtin.com/job/technical-claims-supervisor-major-case-unit/4263523

### Legal, regulatory, and tool sources

- **Wiley Rein LLP via JD Supra — "No Coverage for TPA in Claim Arising from Extracontractual Exposure."** TPA E&O exposure on coverage-denial decisions. https://www.jdsupra.com/topics/policy-limits/policy-exclusions/denial-of-insurance-coverage/
- **NATL — "The Jenga Effect: Avoiding Traps in Policy Limit Demands."** Excess right to consent, good-faith duty, hammer letter, follow-form, timely disclosure of losses. https://natl.com/expertise/the-jenga-effect-avoiding-traps-in-policy-limit-demands-balancing-liability-excess-insurance-towers
- **Zalma on Insurance — "Insured Must Get Excess Insurer's Permission Before Settling."** Consent forfeiture mechanics; excess owes nothing until primary exhausted. https://barryzalma.substack.com/p/insured-must-get-excess-insurers
- **LegalClarity — "What Is Excess Insurance and How Does It Work?"** Consent-to-settle clause, attachment / retention, duty to cooperate. https://legalclarity.org/what-is-excess-insurance-and-how-does-it-work/
- **Washington WAC 284-24D-130.** Closed-claim reporting to the commissioner; excess insuring entity reports for self-insurers; self-insurers report payments / ALAE to the excess entity. https://lawfilesext.leg.wa.gov/Law/WACArchive/2022/htm/WAC%20284%20%20TITLE/WAC%20284%20-%2024D%20CHAPTER/WAC%20284%20-%2024D-130.htm
- **South Carolina Department of Insurance — Understanding the Claim Payout Process.** First check often an advance; separate structure / contents / ALE checks; ALE payable to insured alone; contractor direct-pay caution; mortgagee on dwelling check; reopen mechanics. https://doi.sc.gov/953/Understanding-the-Claim-Payout-Process
- **Safety National — Self-Insurance explainer.** Specific vs aggregate excess; loss fund / attachment mechanics. Labeled-adjacent (WC-framed, structurally general). https://www.safetynational.com/solutions/self-insurance-text-only-versions/
- **Verisk — Xactimate product overview.** Industry-standard property estimating tool; AI line-item recommendations, photo labeling, Sketch Scan. https://www.verisk.com/products/xactimate/
- **Engle Martin — "TPA vs. Insurance Carrier: Claims Oversight."** Delegated authority structure; carrier holds final authority on coverage interpretation, reserve thresholds, litigation strategy; TPA bears no financial risk for claim payments. https://englemartin.com/difference-tpa-vs-insurance-company-claims-oversight/
- **Engle Martin — "The Different Types of Claims Adjusters."** Desk / field / CAT / large-complex / specialty taxonomy. https://englemartin.com/types-of-claims-adjusters/
- **Engle Martin — "What Is a TPA in Insurance?"** Workflow structure overview. https://englemartin.com/what-is-tpa-in-insurance/
- **One Inc — "Simplifying Auto Total Loss Lienholder Payments."** Adjuster presents ACV + requests payoff; letter of guarantee ~10 business days; carrier takes title → salvage. https://www.oneinc.com/resources/blog/simplifying-auto-total-loss-lienholder-payments
- **United Policyholders — Property-claim FAQ.** Negotiation dynamics, ACV vs RCV, push-back, appraisal; ALE caps and time limits, reimbursement basis. Labeled advocacy, accurate on mechanics. https://uphelp.org/claim-guidance-publications/faqs-about-property-damage-insurance-claims/

---

*Updated 2026-05-28 with integrated synthesis (§17), expanded customer-discovery appendix (§18), and legal/regulatory source set (§19) from triangulating research across three deep-research passes. This document is a living artifact and should be revised as customer access produces new evidence on the §18 thin-evidence questions.*
