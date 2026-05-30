---
tags:
  - project/argos
  - type/research
  - status/draft
created: 2026-05-27
aliases:
  - Adjuster Workflow Research
---

# Adjuster Workflow Research — Day-in-the-Life by Lifecycle Stage

## Context

This is the Phase 1 research artifact for the [Claims Operations Intelligence Layer](../THESIS.md) project. It captures how a real auto/property P&C claims adjuster works day-to-day, organized by claims lifecycle stage, with verbatim quotes from named-employer practitioners (Sedgwick, Liberty Mutual, Progressive, Allstate, Gallagher Bassett, AAA, AIG, State Farm) where available. This doc feeds THESIS §2 (the work as it flows today) and §5 (the unified data layer) in Phase 4.

**Source mix.** ~21 Reddit quotes (r/adjusters, r/WorkersComp, r/Insurance), ~10 Indeed/Glassdoor anonymous-but-employer-attributed reviews, sworn Senate HSGAC testimony from Cliff Millikan (Allstate catastrophe adjuster, late 2024/early 2025), trade press (Claims Journal Sep + Oct 2025), and Five Sigma's published US claims workflow data.

**Source caveats.** Reddit identities are self-reported. Indeed reviews are anonymous-by-design but carry employer + role + date metadata. Senate testimony is named and sworn. Where a quote is role-only (not employer-named), it is flagged as such in the attribution line.

**What's not here.** X first-person voices (structurally locked off from non-authenticated crawlers — confirmed via parallel passes by ChatGPT and Grok), and InsurTech MGA-specific adjuster voices (Hippo / Lemonade / Branch / Kin / Pie — would require LinkedIn pivot, deferred).

---

## The lifecycle spine

A US auto/property claim moves through this rough path. Branches happen at almost every stage.

```
FNOL & Intake
   ↓
Triage & Assignment ─→ (reassignment on turnover)
   ↓
Investigation & Documentation
   ↓
Decision-making & Reserve Setting
   ↓
Settlement, Payment & Closure
   ↓
Branches: Reopen · Litigation · Subro · Salvage · Denial
```

The rest of this doc walks each stage with one main theme, 3–4 supporting quotes from named-employer adjusters where possible, and one line on what each stage implies for the intelligence layer.

---

## Stage 1 — FNOL & Intake

**What happens.** New claims arrive through phone, email, portal, or paper. Carrier SLAs typically require contact within 24 hours. Intake volume varies from 3–5 new files per week per adjuster in low-pressure environments up to 10+ per day in heavy-volume contexts. New claims interrupt work-in-progress on existing files.

**Main theme — *continuous inflow with interrupt-driven fragmentation.***

The defining property of intake isn't volume per se — it's that intake is *interruptive* of work-in-progress elsewhere in the queue. A live-transferred call about a new claim arrives while the adjuster is mid-task on three other files, and the prior work is left incomplete.

> "8-12 new claims a day **PLUS 1-3 transfer claims even on YOUR DAYS OFF!!!** Phone adherance 45%+"
> — u/WarAccomplished1142, 3-year **Sedgwick** adjuster, [r/adjusters, Jan 16 2025](https://www.reddit.com/r/adjusters/comments/1i19stz/sedgwick/m7ipvrx/)

> "Newly assigned claim begins with 4 per day and will increase to 10 plus. Need to contact all parties on claim within 24 hours from when the claim was assigned to you."
> — Anonymous **Progressive** Claims Adjuster, [Indeed review](https://www.indeed.com/cmp/Progressive/reviews?fjobtitle=Claims+Adjuster&ftext=claim)

> "You will get 30 claims a week as soon as your 3 months of training is finished. Each claim takes about 3 hours total all around to resolve. **You do the math!**"
> — Anonymous **Progressive** Claims Adjuster, Tampa FL, [Indeed review](https://www.indeed.com/cmp/Progressive/reviews?fcountry=US&floc=Tampa,+FL&fjobtitle=Claims+Adjuster)

> "It's hard to do one thing in a claim and get a warm transferred call which is a new claim and before you know it, **you have 4 different claim notes open and incomplete.**"
> — u/Upstairs_Purchase322, BI adjuster *(employer not named)*, [r/adjusters, Jul 9 2024](https://www.reddit.com/r/adjusters/comments/1dz25g0/high_volume_adjusters_what_are_your_best_practices/)

The Progressive Tampa quote does the math for us: 30 × 3 = 90 hours of assigned work per 40-hour week.

**Implication for the intelligence layer.** The interrupt pattern means the system must persist partial-work context across interruptions automatically — the adjuster cannot be relied on to manually checkpoint when a new call comes in. This is an ontology-layer requirement: every claim object needs to carry its in-progress state across the gap.

---

## Stage 2 — Triage, Assignment & Inheritance

**What happens.** New claims are assigned by line of business, severity, region, or round-robin. Reassignments happen on adjuster turnover and team realignment. Specialized teams ("simple claims" units, "return to work" teams, fast-track units) attempt to siphon low-complexity work but often fail to carry forward investigation context.

**Main theme — *triage failure compounds into a death spiral of orphaned files and undertrained handoffs.***

When an adjuster quits, their files don't redistribute cleanly. They sit untouched for months, then land on a new hire alongside that new hire's normal intake — and the new hire is set up to fail.

> "Liberty Mutual has a massive problem with employee turnover and how empty desks are (not) handled. **New hires are immediately overloaded with complex caseloads that were not touched in months to even a year**, and then berated by angry employers, employees, and management if claims are not brought up to..."
> — Anonymous **Liberty Mutual** Claims Specialist, [Indeed review](https://www.indeed.com/cmp/Liberty-Mutual-Insurance/reviews?fcountry=ALL&fjobtitle=Claims+Specialist)

> "I came to GB with 35 years liability claims experience, field a Director of many catastrophic injury claims. **Driven away b/c I was offered to every account that was 'mishandled' by a prior adjuster so I ended up with a huge caseload** and had a supervisor who micromanaged me, with crazy metrics. Quit after 11 months."
> — u/Pacificstan, 35-year veteran at **Gallagher Bassett**, [r/adjusters, Jul 30 2025](https://www.reddit.com/r/adjusters/comments/1mdeq8l/gallagher_bassett_employees_are_you_mentally_okay/n6175lr/)

> "We even have a team that is supposed to handle simple claims, but the reality is they just get transferred over to the return to work folks, and **we get a claim with 0 information gathered, angry insured and injured worker, and a whole mess to sort out.**"
> — u/Most-Ad-5277, WC adjuster *(employer not named)*, [r/adjusters, Jan 21 2026](https://www.reddit.com/r/adjusters/comments/1qij7rm/average_claim_volume_wc_adjuster/o0ruy66/)

> "I've been with my company three years, and **we lose an adjuster every six months. We're a small team and last year I was thrown into high-level files with zero training.**"
> — Anonymous 3-year adjuster, [Claims Journal "The Silent Liability", Sep 4 2025](https://www.claimsjournal.com/news/national/2025/09/04/332713.htm)

**Implication for the intelligence layer.** The handoff is not just a routing event — it's where context is supposed to transfer but doesn't. The ontology must store enough investigation state that a new owner can re-enter a stalled claim without re-interviewing every party. This is the single feature that, if it works, directly attacks the turnover→orphan→burnout death spiral.

---

## Stage 3 — Investigation & Documentation

**What happens.** Adjusters gather facts: photos, recorded statements, police reports, contractor estimates, medical records, witness interviews. Property investigation increasingly relies on third-party "picture takers" feeding photos into a portal; the licensed adjuster reviews from the desk. Documentation must be entered into the claims system, often with system-mandated duplication.

**Main theme — *field work is shrinking and being replaced by photo-fed desk review, with documentation overhead that bloats the record over time.***

The major shift is the disappearance of the field adjuster as decision-maker. The corpus is unusually thin on named-employer quotes for this stage (most surfaced from r/adjusters threads with role attribution but no employer), but the Allstate Senate testimony and one job-listing system stack carry the load.

> "Allstate has stripped all field adjusters of decision-making authority. **Adjusters now act as 'picture takers and estimate writers,'** submitting their work to reviewers who approve or deny claims and dictate revisions."
> — Cliff Millikan, **Allstate** catastrophe adjuster (Pilot Catastrophe), [Senate HSGAC testimony, late 2024 / early 2025](https://www.hsgac.senate.gov/subcommittees/dmdcc/hearings/examining-the-insurance-industrys-claims-practices-following-recent-natural-disasters/millikan-testimony)

> "Field adjuster here. **My carrier doesn't currently allow in person inspections so we depend on photos from EMS/contractors.** If the photos justify the supplement I'll gladly add it to my estimate."
> — u/gosnowboardin, field adjuster *(employer not named)*, [r/adjusters, Jan 13 2021](https://www.reddit.com/r/adjusters/comments/kb9vye/desk_adjusters_and_supplements/gj2q2rx/)

> "About 70% of those claims were in a system that had a tendency to create multiple redundant tasks, e.g. **handling a new piece of mail required that I not only label the document, but also required that I put a note in the notes section every. single. time.** As you can imagine, trying to sift through the notes on a year+ old file was a fucking nightmare because of all the extraneous and irrelevant information, which further slowed things down."
> — u/Dus-Sn, complex WC adjuster *(employer not named)*, [r/adjusters, Apr 24 2025](https://www.reddit.com/r/adjusters/comments/1k69g54/management_dumping_claims_from_other_departments/moqkmxd/)

> "My whole day consist of **80% backend work and 20% inspections.**"
> — u/RamboBoujee, property claims adjuster *(employer not named)*, [r/adjusters, Dec 11 2020](https://www.reddit.com/r/adjusters/comments/kb9vye/desk_adjusters_and_supplements/gfh1deo/)

**Implication for the intelligence layer.** Two things. First, the investigation evidence stream is now structured photo input plus contractor estimate PDFs, not free-form adjuster notes — extraction agents have clean input shapes to operate on. Second, system-mandated redundant documentation is THE concrete swivel-chair example to feature in the THESIS: the system requires duplicate logging, then the duplicate logging destroys the legibility of the file. Pull the Dus-Sn quote verbatim into THESIS §2.

---

## Stage 4 — Decision-making & Reserve Setting

**What happens.** Coverage determination, initial reserve setting, ongoing reserve adjustment, approval routing for payments above threshold. Authority is increasingly centralized into review chains; decisions that used to sit with the adjuster now sit with reviewers, often without visible attribution.

**Main theme — *decision authority is being centralized into non-transparent review chains, and adjusters are metric-managed instead of empowered.***

This is the strongest single-source insight in the entire corpus, anchored by a named, sworn witness.

> "Adjusters now act as 'picture takers and estimate writers,' submitting their work to reviewers who approve or deny claims and dictate revisions, **often without transparency, as their name does not appear on the estimate.**"
> — Cliff Millikan, **Allstate** catastrophe adjuster, [Senate HSGAC testimony](https://www.hsgac.senate.gov/subcommittees/dmdcc/hearings/examining-the-insurance-industrys-claims-practices-following-recent-natural-disasters/millikan-testimony)

> "Never seen anything like the **crazy diary system and constant emails asking you to click this button** or fill this screen. **No focus on actual work product and all on button.**"
> — Anonymous **Sedgwick** Claims Adjuster, Plano TX, [Indeed review](https://www.indeed.com/cmp/Sedgwick/reviews?fcountry=US&floc=Plano,+TX&fjobtitle=Claims+Adjuster)

> "I was told we should only have about 70 claims on our desktop when I left **everyone had about 130.**"
> — Anonymous **Liberty Mutual** Claims Adjuster, St. Louis MO, Jan 2020, [Indeed review](https://www.indeed.com/cmp/Liberty-Mutual-Insurance/reviews?fjobtitle=Claims+Adjuster&start=60)

> "Numbers, metrics and surveys, that's about it. The workload has become unbearable and no one cares."
> — Anonymous **Liberty Mutual** Claims Adjuster, [Indeed review](https://www.indeed.com/cmp/Liberty-Mutual-Insurance/reviews?fcountry=ALL&fjobtitle=Claims+Adjuster&start=60)

**Implication for the intelligence layer.** The audit-trail problem is named, on the record, and worse than any AI critique of AI-driven claims tools could ever be — *even human reviewers* operate without traceability. An intelligence layer that logs every action (human or agent) with attribution doesn't have to beat humans-with-audit; it just has to beat humans-without. This reframes the governance pitch from defensive ("AI needs audit trails") to offensive ("the current system has no audit trails — adding one is the wedge"). Pull the Millikan reviewer-chain quote verbatim into THESIS §2 and §5.

---

## Stage 5 — Settlement, Payment & Closure

**What happens.** Negotiation with claimants, attorneys, and vendors; payment issuance; file closure; plus branches into subrogation (recovering from at-fault parties) and salvage. Per Five Sigma's US claims-time data, **62.3% of total handling time is spent here** — the back half of the lifecycle, not the front.

**Main theme — *the back half is where most time leaks, and the practitioner voice for this stage is structurally quieter than for intake or triage.***

Adjusters complain less about settlement than about intake and triage — partly because settlement is where they finally exercise judgment, and partly because settlement delays are often externally caused (waiting on counsel, medical records, vendor estimates, state-level payment timing rules). The structural data is the strongest evidence we have for this stage.

> US claims time allocation per claim:
> - Claim creation: **<25%** of total handling time
> - Damage assessment: **17.4%**
> - **Assessment → payment: 62.3%**
> *(UK comparator: ~25 / 46 / 45, so the US payment-handling bottleneck is geographically specific)*
> — [Five Sigma exclusive workflow data](https://fivesigmalabs.com/blog/exclusive-data-claims-adjusters-day-to-day-workloads/)

> "Typical day included managing a caseload of up to 250 claims. **Seemed that there was never enough time in an 8 hour shift to get the work done correctly.** Spent most nights at home trying to catch up."
> — Anonymous **Progressive** Claims Adjuster, Plymouth Meeting PA, [Indeed review](https://www.indeed.com/cmp/Progressive/reviews?fcountry=US&floc=Plymouth+Meeting,+PA&fjobtitle=Claims+Adjuster)

> "Most claim adjusters start at about 7 a.m. and finish late in the evening. You have no life other than claims... **Because of the sheer volume of claims, everyone loses: the customer loses due to slow response times, and the employee loses because they have no life.**"
> — Anonymous **Progressive** Claims Adjuster, [Indeed review](https://www.indeed.com/cmp/Progressive/reviews?fjobtitle=Claims+Adjuster&ftext=claim)

> Tim Parker (30+ year veteran) shared a personal claim: **carrier's initial assessment was ~$6,000; appraisal settlement reached $78,000+.**
> — [Claims Journal, "What's Happening in The Claims Profession?", Oct 29 2025](https://www.claimsjournal.com/news/national/2025/10/29/333765.htm)

**Implication for the intelligence layer.** Settlement-stage value capture is harder to *demo* than intake-stage value capture (less practitioner narrative to anchor on), but it's where the dollars are (62% of handling time, plus the magnitude of the Parker $6K→$78K gap as the leakage canary). The product strategy should probably *demo* intake while *measuring* settlement cycle-time as the primary success metric.

---

## Cross-cutting realities

These conditions don't sit cleanly in one lifecycle stage; they're present at every stage.

### The multi-system stack adjusters actually use

> "Ours is **Guidewire Claim Center** for the claims and activities and **Outlook is just for emails.**"
> — u/JonB505, [r/adjusters, May 10 2024](https://www.reddit.com/r/adjusters/comments/1cokdo7/how_do_you_keep_track_of_your_claims_and_emails_i/l3f1o2l/)

> "I use **JobNimbus** to track files and outlook for emails."
> — u/adjuster_cody, field adjuster, [same r/adjusters thread, May 2024](https://www.reddit.com/r/adjusters/comments/1cokdo7/how_do_you_keep_track_of_your_claims_and_emails_i/)

> "**You work in serval [sic] systems** and carry alot of responsibilities but they pay you the very minimum."
> — Anonymous **Sedgwick** Claims Adjuster, Philadelphia PA, [Indeed review](https://www.indeed.com/cmp/Sedgwick/reviews?fcountry=US&floc=Philadelphia,+PA&fjobtitle=Claims+Adjuster)

> Job listing language for a Senior MedPay Adjuster role at **AAA / ACSC** (regional carrier): "Update database production reports, document and update claim files via company systems, i.e. **CACS, HUON, HOC, GUIDEWIRE**..."
> — [CareerBuilder listing](https://www.careerbuilder.com/jobs-insurance-adjuster)

Tools named across the corpus:

| Tool | Vendor | Primary function | Typical buyer |
|---|---|---|---|
| **Xactimate** | Verisk | Property damage estimating (industry standard) | All P&C, restoration contractors |
| **Guidewire ClaimCenter** | Guidewire | Enterprise claims system of record | Top-100 carriers |
| **Duck Creek Claims** | Duck Creek | Enterprise claims SOR | Mid/top carriers |
| **CCC ONE** | CCC | Auto estimating + body-shop network | Auto carriers + shops |
| **Mitchell DecisionPoint / ClaimsIQ** | Mitchell (Enlyte) | Injury valuation + workflow | Auto carriers |
| **Snapsheet** | Snapsheet | Photo-based auto estimating | Mid-tier carriers |
| **OnBase / FileNet / Documentum** | Hyland / IBM / OpenText | Document management | Enterprise |
| **JobNimbus** | JobNimbus | File tracking for IAs / small firms | Independent adjusters |
| **Outlook + Excel** | Microsoft | Email + status tracking (universal fallback) | Everyone |

**Implication.** The LMM workflow does NOT live in one SOR. It's stitched together from a domain-specific estimator (Xactimate or CCC ONE) + a workflow tracker (Guidewire if you're lucky, JobNimbus if you're solo, Excel if all else fails) + email + per-client portals. The unified-data-layer wedge is the layer that ties these together — exactly what no incumbent currently sells at LMM scale.

### TPA vs regional carrier — the buyer-profile signal

The single most directionally important quote in the entire research pull. This reopens the Phase 3 buyer-profile question.

> "When I worked at a **larger TPA**, I was told 150 was the average. By the time I left, **my average was 225**. Went to a **regional carrier** where I was told the **max is 125**. Have yet to exceed that with a full caseload. **Always have the ability to move, settle and close files.**"
> — u/rsae_majoris, [r/WorkersComp, Dec 22 2024](https://www.reddit.com/r/WorkersComp/comments/1hjmh0s/average_claim_caseload/m38jt9m/)

> "Some of these accounts are very chaotic from the branch managers on down. **Especially the new mgrs who come from large carriers and try to handle GB claims and processes the same way. It never works.**"
> — u/Ok-Reach5743, **Gallagher Bassett** claims worker, [r/adjusters, Jul 30 2025](https://www.reddit.com/r/adjusters/comments/1mdeq8l/gallagher_bassett_employees_are_you_mentally_okay/n612an4/)

> "You will never know until you meet your direct boss and the account you are on... I work for **Sedgwick** and absolutely love my job. **I'm on a different account obviously.**"
> — u/BaggerVance_, [r/adjusters, Jan 14 2025](https://www.reddit.com/r/adjusters/comments/1i19stz/sedgwick/m74fg1e/)

> "I am at a **TPA** with a branch that handles 4 jurisdictions... **MO stays strictly MO so the client doesn't get charged IND rate** for a simple claim. There's no way I could handle MO volume while appropriately being able to handle my IND and litigated claims."
> — u/oh_hayyy, former WC adjuster now supervisor at a TPA, [r/adjusters, Jan 21 2026](https://www.reddit.com/r/adjusters/comments/1qij7rm/average_claim_volume_wc_adjuster/o0s6kel/)

**Implication for THESIS and Phase 3.** TPAs have the higher pain (caseload + chaos + per-client protocol fragmentation), which usually means higher buying urgency. But TPAs also have the *least operational space* for a tool to actually demonstrate impact — adjusters there are surviving, not optimizing. Regional carriers offer the inverse: capped caseloads and the ability to actually close files, which makes them a better demo environment but a weaker urgency signal. **The "obvious" TPA-first answer is no longer obvious.** Surface this fork explicitly when Phase 3 starts.

### Caseload as the constant pressure underneath

| Source | Employer | Caseload data |
|---|---|---|
| Anon Liberty Mutual | **Liberty Mutual** | Target 70, **actual 130** |
| Anon Liberty Mutual | **Liberty Mutual** | **200 claim benchmark** with new incoming daily |
| Anon Progressive | **Progressive** | **250 active claims**, 8-hour shift insufficient |
| Anon Sedgwick | **Sedgwick** | **300+ claims** |
| u/WarAccomplished1142 | **Sedgwick** | **160+ pending**, 8–12 new/day plus 1–3 transfers on days off |
| u/odiomnibusvobis | (WC, employer not named) | **170–190 pending**, 7–9 new/week |
| u/carlloserpants | (auto, employer not named) | **~1,200 claims handled in one year**, 60+ hr/week, 12–14 hr days |

The 100–250 range cited in trade press holds up. The Sedgwick 300+ tail is the worst end. **Liberty Mutual's target-vs-actual gap (70 → 130) is the single best illustration of the policy-vs-reality problem that ops leaders would buy a tool to surface.**

### The burnout death spiral

Burnout isn't a soft theme — it's the supply-side constraint underneath everything else. When adjusters quit, files orphan, new hires inherit them stale, the new hires burn out, repeat.

> "**Choose Wisely Door A:** Work/Life Balance is absolutely possible BUT your numbers will suffer, EVERYONE will get complaints about you, and you'll eventually promote yourself to being a customer. **OR Door B:** Every month your numbers are above goal and you get a 'Exceeds Expectations' on your performance reviews every year BUT your 8 hour days are now 12, you log in when your supposed to be off, and you'll learn first hand that 'Claims Burnout' isn't a myth."
> — Anonymous **Allstate** Liability Adjuster, [Glassdoor](https://www.glassdoor.com/Reviews/Allstate-Liability-Adjuster-Reviews-EI_IE2341.0,8_KO9,27.htm)

> "I honestly really like what I do and I work hard. At this point it's putting a strain on my mental missing out on sleep because I can't sleep from stress. **I'm not even eating at this point throughout the day because I'm so focused on getting the claims done.**"
> — u/Ok-Reach5743, **Gallagher Bassett** claims worker, [r/adjusters, Jul 30 2025](https://www.reddit.com/r/adjusters/comments/1mdeq8l/gallagher_bassett_employees_are_you_mentally_okay/n617v7c/)

> "At this point I'm so desperate and just want peace... **I'd be willing to take a 50% or more pay cut doing something else if I could have peace sometimes.**"
> — u/carlloserpants, auto adjuster *(employer not named)*, [r/adjusters, Dec 14 2023](https://www.reddit.com/r/adjusters/comments/18i8oer/im_so_stressed_out_as_an_adjuster_all_the_time_do/)

**Implication.** A tool that genuinely reduces work hours has a willingness-to-pay measurable in adjuster retention, not just productivity. CUNY School of Public Health estimates burnout costs $4,000–$21,000 per employee annually in lost productivity and turnover ([cited in Claims Journal, Sep 2025](https://www.claimsjournal.com/news/national/2025/09/04/332713.htm)). The ROI conversation to an ops leader runs: "every adjuster you retain who would have quit saves you $4K–$21K, plus the cost of the orphaned files they would have left behind."

---

## What this means for THESIS

For **§2 — the work as it actually flows today.**
Use the lifecycle spine above as the narrative structure. The four anchor quotes for §2 are:
1. WarAccomplished1142 (Sedgwick intake reality)
2. Upstairs_Purchase322 (4 incomplete claim notes from interruptions)
3. Anon Liberty Mutual (target 70, actual 130)
4. Cliff Millikan (Allstate reviewer chain without name attribution)

These four quotes together tell the story: high inflow → interrupt-driven fragmentation → policy-vs-reality gap → governance gap. Each is from a named employer or sworn witness.

For **§5 — the unified data layer.**
The LMM data reality is that there is no Guidewire. The data lives across Xactimate, Outlook, OnBase/FileNet, JobNimbus, per-client portals, and Excel — confirmed by the JonB505, adjuster_cody, Sedgwick "serval systems," and ACSC job-listing quotes. The unified data layer at LMM is harder than at enterprise (no SOR to integrate against) *and* more valuable (no incumbent has solved it). That's the wedge.

For **Phase 3 — LMM buyer profile decision.**
The TPA-vs-regional-carrier question is a real fork. Recommended framing for Phase 3:
- **TPAs** win on urgency (acute pain, fast procurement) but lose on demo environment (adjusters are surviving, not optimizing)
- **Regional carriers** win on demo environment (capped caseloads, ability to actually close files) but lose on urgency (less burning pain)

Decide based on which evidence resonates more once we see the actual data shape in Phase 2.

---

## Gaps in the research

What we don't have, and why:

- **X first-person voices.** Structurally locked off from non-authenticated crawlers. ChatGPT and Grok both hit the same wall in parallel passes. Not pursuable via web search.
- **InsurTech MGA adjuster voices.** Hippo / Lemonade / Branch / Kin / Pie / Next — none surfaced. Would require LinkedIn pivot.
- **Reserve-setting practitioner detail.** Adjusters complain about "metrics" and "constant emails to click buttons" but rarely walk through reserve decisions specifically. Reserves are likely the most invisible part of the workflow from the outside.
- **Payment-stage practitioner voice.** Five Sigma quantifies that this is 62% of US handling time, but practitioner voice on *why* is thin. Likely involves vendor coordination, medical billing reconciliation, and state-level payment rules — would need separate research pass.
- **Subrogation, salvage, litigation branches.** Not covered. Adjacent to the slice scope; defer to Phase 7 tech plan.
- **Closure rituals & post-closure metrics.** Not covered. Defer.

---

*End of Phase 1 research. Feeds THESIS §2 and §5 in Phase 4, and the LMM buyer-profile decision in Phase 3.*
