---
tags:
  - project/argos
  - type/spec
  - status/draft
created: 2026-05-31
updated: 2026-05-31 (r2 — Tom's cycle-time confirmations locked; coverage section expanded 9→15; added fact_stable_at field; resolved 6 judgment calls)
scope: auto BI / FL / post-FNOL pre-coverage-decision
---

# Info map — auto BI, FL

The catalog of **open questions** required to reach each end-state
decision (coverage / liability / damages) on a Florida auto bodily
injury claim. Hand-authored, single LOB / single jurisdiction. Every
question has at least one named source backing the *requirement* and
at least one named source backing the *cycle time* (or is marked
`[ESTIMATE]`).

## What "open question" means

One fact a competent adjuster must know to make a coverage, liability,
or damages decision on this claim. Status is binary at the unit
level: open or answered. Granularity: if filling it gives you
something that still needs more sub-checks, it's not an open question
yet — break it down.

## Schema (per entry)

```
ID — short description
- Blocks end-state: coverage | liability | damages
- Gating: required | nice-to-have | conditional (with trigger)
- Source options (preferred → fallback):
  - {party, channel, cycle_time, fidelity_rank}
- Best-case cycle time: <duration>
- Depends on: [Q-ID, ...] or none
- Fact-stable at: immediate | request_response | MMI | demand_received | settlement
  (when the answer stops changing; default = request_response)
- Requirement citation: <source>
- Cycle-time citation: <source> | [ESTIMATE]
- Notes (optional): edge cases, jurisdiction quirks
```

**Status grain (v1):** binary — `open` or `answered`. Partial-fill is a
v2 concern; v1 treats partially-answered as still-open for the
purposes of Outreach prioritization. Simpler signal, less UX nuance.

**Granularity:** some questions are intentionally coarse (e.g.,
Q-COV-005 "exclusions triggered" covers many sub-checks). The
downstream specialist decomposes; the map captures the unit at the
grain an adjuster checks off a list, not the grain at which
sub-rules fire.

## End-state sequencing

Coverage gates liability — no point investigating fault on an
out-of-coverage claim. Liability gates damages — no point estimating
$80K in damages if the other side admits fault and offers $30K.
Practical implication: coverage questions are highest-priority by
default; damages questions are nice-to-have until liability is locked
unless they're slow-cycle (start them in parallel anyway because they
gate the demand response).

## Critical-path rule

Slow-cycle questions get requested **day 1**, in parallel, regardless
of which end-state they block. The longest unrequested cycle is the
floor on the claim's earliest-decision date. This is the prioritization
the Outreach Drafter and Brief use to surface what to do first.

## Sources used in this map

- **FL Insurance Code §§ 627.7407, 627.736, 627.727** — Florida
  no-fault / PIP / UM-UIM statutes.
- **FL § 768.81** — pure comparative fault.
- **FL § 626.9541** — unfair claims practices act.
- **AIC curriculum** (Associate in Claims, The Institutes) — what
  facts a trained adjuster is expected to check at each phase.
- **CPCU 552** — commercial property and liability claims.
- **ACORD Form 1 (Auto Loss Notice)** — what fields exist in the
  standard claim intake exchange; defines what's nominally captured
  at FNOL.
- **NAIC Unfair Claims Settlement Practices Act model** — timing
  obligations.
- **FL state records office published response SLA** — used for
  police-records cycle times.

Cycle times without a published source are marked `[ESTIMATE]` with a
brief rationale; treat them as TODOs to verify against the Phase 1
adjuster-workflow research before locking the eval.

---

# Section A — Coverage decision open questions

These must be closed (or have a reasoned default per policy
declarations) before coverage can be accepted, denied, or written
under ROR.

### Q-COV-001 — Is the policy in force on the loss date?

- **Blocks end-state:** coverage
- **Gating:** required
- **Source options:**
  - Carrier UW system / policy admin DB (internal lookup, immediate, authoritative)
  - Broker (email, 1–2d, secondary)
- **Best-case cycle time:** immediate (internal lookup)
- **Depends on:** none
- **Requirement citation:** AIC curriculum §2.3 (coverage triggers); FL § 627.7407 (in-force requirement for PIP)
- **Cycle-time citation:** ACORD policy lookup is canonically real-time within carrier systems.

### Q-COV-002 — Is the driver of record covered under the policy (named, listed permissive, or excluded)?

- **Blocks end-state:** coverage
- **Gating:** required
- **Source options:**
  - Carrier UW (internal, immediate, authoritative)
  - Insured statement (email/phone, 1–3d, lower fidelity — claimants may misstate)
  - DMV record (state portal, 7–14d, authoritative for license status only)
- **Best-case cycle time:** immediate (UW)
- **Depends on:** Q-COV-001 (need policy active first)
- **Requirement citation:** AIC curriculum §2.4 (driver eligibility); standard auto policy "Persons Insured" provision.
- **Cycle-time citation:** internal lookup immediate.

### Q-COV-003 — Was the vehicle being used in a covered manner (personal vs business; permissive vs unauthorized)?

- **Blocks end-state:** coverage
- **Gating:** required
- **Source options:**
  - Insured statement (phone/portal, 1–3d, primary)
  - Police report (records request, 14–30d, secondary)
  - Witness statement (varies, only if obtained)
- **Best-case cycle time:** 1–3d (insured)
- **Depends on:** Q-COV-002
- **Requirement citation:** Standard auto policy "Use" provision; AIC §2.4.
- **Cycle-time citation:** [ESTIMATE] — insured response within 1–3d typical when adjuster reaches them; varies wildly with claimant cooperation.

### Q-COV-004 — Was timely notice of the loss given per the policy?

- **Blocks end-state:** coverage
- **Gating:** required
- **Source options:**
  - FNOL timestamp + loss date (internal, immediate, authoritative)
- **Best-case cycle time:** immediate
- **Depends on:** none
- **Requirement citation:** Standard auto policy "Duties After an Accident" provision; FL § 627.736(4)(b) (PIP notice).
- **Cycle-time citation:** Internal timestamp.

### Q-COV-005 — Are there any policy exclusions triggered by the loss facts (intentional act, racing, criminal use, etc.)?

- **Blocks end-state:** coverage
- **Gating:** required
- **Source options:**
  - Loss description + police report (records request, 14–30d, primary)
  - Insured statement (1–3d, secondary)
  - Witness statements (varies)
- **Best-case cycle time:** 14–30d (police report is the long pole here)
- **Depends on:** none
- **Requirement citation:** Standard auto policy "Exclusions" provision; AIC §2.5.
- **Cycle-time citation:** FL state records — Hillsborough County Sheriff published 30-day standard response. Many FL agencies similar.

### Q-COV-006 — What are the per-person and per-occurrence BI limits, and any sublimits or SIR?

- **Blocks end-state:** coverage
- **Gating:** required
- **Source options:**
  - Policy declarations page (internal, immediate, authoritative)
- **Best-case cycle time:** immediate
- **Depends on:** Q-COV-001
- **Requirement citation:** ACORD Form 1 §3; AIC §2.6.
- **Cycle-time citation:** Internal.

### Q-COV-007 — Is there a co-defendant carrier with primary coverage, contribution duty, or excess obligation?

- **Blocks end-state:** coverage
- **Gating:** nice-to-have (required if multi-vehicle / commercial use)
- **Source options:**
  - Police report (14–30d, primary — identifies other parties' carriers)
  - ISO ClaimSearch (API, minutes, secondary — finds matching claims by VIN/parties)
  - Direct carrier contact (1–7d, after identification)
- **Best-case cycle time:** minutes (ISO ClaimSearch if matching prior claim)
- **Depends on:** Q-COV-005 (need loss facts first)
- **Requirement citation:** AIC §6.2 (multi-carrier coordination); CPCU 552 §4.
- **Cycle-time citation:** ISO ClaimSearch is realtime API.

### Q-COV-008 — Does the claimant qualify as an insured / non-owned / excluded party under policy definitions?

- **Blocks end-state:** coverage
- **Gating:** required
- **Source options:**
  - Policy declarations + named-insured roster (internal, immediate)
  - Claimant relationship to insured (insured statement, 1–3d)
- **Best-case cycle time:** immediate when not a household member; 1–3d otherwise
- **Depends on:** Q-COV-001
- **Requirement citation:** Standard auto policy "Definitions" / "Persons Insured."
- **Cycle-time citation:** Internal.

### Q-COV-009 — Was the loss reported to PIP within the FL statutory window, and is PIP coordination required?

- **Blocks end-state:** coverage
- **Gating:** required (FL-specific)
- **Source options:**
  - FNOL timestamp + insured PIP carrier (internal + 1–3d insured)
- **Best-case cycle time:** 1–3d
- **Depends on:** Q-COV-004
- **Requirement citation:** FL § 627.736 (PIP); AIC FL state supplement.
- **Cycle-time citation:** [ESTIMATE] — insured response 1–3d.

### Q-COV-010 — Is there a valid certificate of insurance / additional-insured / waiver-of-subrogation endorsement in place per the underlying contract?

- **Blocks end-state:** coverage
- **Gating:** conditional (required when the loss involves a contractual additional-insured claim or third-party tender)
- **Source options:**
  - Carrier UW system (internal, immediate, authoritative)
  - Underlying contract (insured/broker, 1–7d)
- **Best-case cycle time:** immediate (UW)
- **Depends on:** Q-COV-001
- **Fact-stable at:** request_response
- **Requirement citation:** Standard commercial auto policy "Additional Insureds" endorsement (CA 20 series); ISO CA 0001 declarations.
- **Cycle-time citation:** Internal lookup.
- **Notes:** Wrong-named-insured and missing endorsement wording are common COI issues — flagged in the [Logrock FL commercial auto guide](https://www.logrock.com/commercial-truck-insurance/commercial-car-insurance-florida/) and a frequent coverage-dispute root cause.

### Q-COV-011 — Has the named insured complied with the cooperation provision (recorded statement provided, EUO attended if requested)?

- **Blocks end-state:** coverage
- **Gating:** required
- **Source options:**
  - Adjuster file notes (internal, immediate)
  - Insured statement record (1–3d to request; longer if uncooperative)
- **Best-case cycle time:** 1–3d
- **Depends on:** Q-COV-001
- **Fact-stable at:** request_response
- **Requirement citation:** Standard auto policy "Duties After an Accident" provision (Part E).
- **Cycle-time citation:** Internal + insured response.
- **Notes:** Material non-cooperation can void coverage. The structural question is "have we asked, and was the response sufficient" — not "is the insured being friendly."

### Q-COV-012 — Is UM/UIM coverage stacked or non-stacked, and is there a valid written waiver on file?

- **Blocks end-state:** coverage
- **Gating:** required (FL-specific; affects available limits)
- **Source options:**
  - Carrier UW — UM/UIM selection/rejection form (internal, immediate, authoritative)
- **Best-case cycle time:** immediate
- **Depends on:** Q-COV-001
- **Fact-stable at:** immediate (policy-period locked)
- **Requirement citation:** FL § 627.727(9). The statute imposes specific form requirements (12-point bold heading, exact statutory language); absent a compliant waiver, **stacking is the default**.
- **Cycle-time citation:** Internal.
- **Notes:** This is a high-leverage FL atom — non-compliant waivers are routinely struck down by FL courts, converting a non-stacked policy into a stacked one mid-claim. Per [Taylor Day Grimm & Boyd's June 2025 FL UM stacking analysis](https://www.taylordaylaw.com/2025/06/floridas-stacking-v-non-stacking-uninsured-underinsured-motorist-coverage-and-plaintiffs-attempts-to-thwart-%C2%A7-627-727-for-additional-coverag/), the limits at stake can change by 5×+ on multi-vehicle policies.

### Q-COV-013 — Is there excess / umbrella coverage on top of the primary, and what's its attachment point and exhaustion mechanic?

- **Blocks end-state:** coverage
- **Gating:** conditional (required for high-severity / catastrophic exposure exceeding primary limits)
- **Source options:**
  - Carrier UW (internal, immediate)
  - Broker (insured contact, 1–7d)
- **Best-case cycle time:** immediate
- **Depends on:** Q-COV-001
- **Fact-stable at:** immediate
- **Requirement citation:** Standard excess/umbrella policy language; AIC §2.7 (multi-layer coordination).
- **Cycle-time citation:** Internal.

### Q-COV-014 — Does a self-insured retention or deductible apply, and what's the attachment point?

- **Blocks end-state:** coverage
- **Gating:** required if SIR/deductible > $0
- **Source options:**
  - Policy declarations (internal, immediate, authoritative)
- **Best-case cycle time:** immediate
- **Depends on:** Q-COV-006
- **Fact-stable at:** immediate
- **Requirement citation:** ACORD Form 1 §3; standard policy declarations.
- **Cycle-time citation:** Internal.

### Q-COV-015 — Is the defense duty triggered (typically broader than indemnity duty)?

- **Blocks end-state:** coverage
- **Gating:** required
- **Source options:**
  - Complaint / claim allegations (claimant or counsel, 1–14d depending on stage)
  - Policy language analysis (internal, immediate)
- **Best-case cycle time:** immediate analysis once allegations known
- **Depends on:** Q-COV-001, Q-COV-005
- **Fact-stable at:** demand_received (defense duty re-evaluates when allegations change)
- **Requirement citation:** FL "duty to defend" jurisprudence (8 Corners rule; broader than indemnity duty). AIC §2.8.
- **Cycle-time citation:** Internal once inputs known.
- **Notes:** Defense duty often kicks in even on uncovered claims, because FL applies the "potential coverage" / 8-Corners rule.

---

# What the FL HSMV-90010 crash report actually captures

The Florida Uniform Traffic Crash Report (long form, HSMV-90010) has
three sections — Event, Vehicle/Person, Narrative — and explicit
fields for: crash date/time/location; driver and passenger names +
addresses; vehicle descriptions; witness names + addresses; insurance
carrier names; officer name/badge/agency; citation information (FL
statute number + charge); medical-transport details. **There is no
explicit "fault assignment" field** — FL officers frequently decline
to assign fault in the narrative, which is why Q-LIA-006 is gated
nice-to-have rather than required. Source: [Florida Traffic Crash
Report Manual (FLHSMV)](https://www.flhsmv.gov/pdf/forms/90010s.pdf);
[FDOT Crash Records guidance](https://www.fdot.gov/Safety/safetyengineering/crash-data.shtm).

This matters for the architecture: **a single police-report arrival
closes ~5 liability questions at once** (Q-LIA-001 location,
Q-LIA-004 citations, Q-LIA-006 fault narrative, Q-LIA-007 witnesses,
Q-LIA-008 admissions). Treat the police report as the "fat" doc on
the liability side; HIPAA records play the same role on the damages
side.

---

# Section B — Liability decision open questions

These close the question of "who is at fault, and to what degree."
Under FL § 768.81 pure comparative fault, partial-fault answers
matter — the answer here is a percentage, not a binary.

### Q-LIA-001 — What was the date, time, and exact location of the loss?

- **Blocks end-state:** liability
- **Gating:** required
- **Source options:**
  - ACORD FNOL (internal, immediate, primary)
  - Police report (14–30d, authoritative confirmation)
  - Insured statement (1–3d, secondary)
- **Best-case cycle time:** immediate (FNOL)
- **Depends on:** none
- **Requirement citation:** ACORD Form 1 §4; AIC §3.1.
- **Cycle-time citation:** Internal.

### Q-LIA-002 — What was the traffic control at the location (signal, sign, uncontrolled, marked lane)?

- **Blocks end-state:** liability
- **Gating:** required
- **Source options:**
  - Police report (14–30d, authoritative)
  - Google Maps / street-view (internal, minutes, secondary)
  - Insured statement (1–3d, lowest fidelity)
- **Best-case cycle time:** minutes (street view) but police report authoritative
- **Depends on:** Q-LIA-001
- **Requirement citation:** AIC §3.2 (traffic-control analysis); FL § 316 (traffic code) cross-reference.
- **Cycle-time citation:** Internal.

### Q-LIA-003 — What was each driver's path of travel and point of impact?

- **Blocks end-state:** liability
- **Gating:** required
- **Source options:**
  - Police report diagram (14–30d, primary)
  - Vehicle damage photos (insured/body shop, 1–7d, supporting)
  - Insured statement (1–3d, secondary)
  - Witness statements (varies)
- **Best-case cycle time:** 1–7d (photos), but full clarity needs police report
- **Depends on:** Q-LIA-001
- **Requirement citation:** AIC §3.3 (accident reconstruction basics).
- **Cycle-time citation:** [ESTIMATE] — photos when responsive; police 14–30d.

### Q-LIA-004 — Was either driver issued a citation, and for what code section?

- **Blocks end-state:** liability
- **Gating:** required (strong fault indicator under FL law)
- **Source options:**
  - Police report citation fields — HSMV-90010 captures FL statute # + charge explicitly (14–30d, authoritative)
  - Court records / case lookup (1–7d if cited; FL portal)
  - Insured statement (1–3d, self-report — unreliable for own citation)
- **Best-case cycle time:** 1–7d (court records if known cited)
- **Depends on:** Q-LIA-001
- **Requirement citation:** AIC §3.4; FL § 316.123 (failure to yield example, frequent citation).
- **Cycle-time citation:** Citation info is a populated field on HSMV-90010; once report is in hand, this question closes immediately. Police report itself: FDOT/HSMV standard 30d.

### Q-LIA-005 — Was the insured driver legally licensed, not impaired, and otherwise compliant with traffic law?

- **Blocks end-state:** liability
- **Gating:** required
- **Source options:**
  - DMV record (state portal, 7–14d)
  - Police report toxicology mention (14–30d)
  - Insured statement (1–3d, low fidelity for impairment self-report)
- **Best-case cycle time:** 7–14d (DMV)
- **Depends on:** Q-COV-002 (driver identified first)
- **Requirement citation:** AIC §3.5; FL § 316.193 (DUI).
- **Cycle-time citation:** FL DHSMV published 7–14d for record requests.

### Q-LIA-006 — Did the police officer make an explicit fault determination at the scene?

- **Blocks end-state:** liability
- **Gating:** nice-to-have (frequently absent; FL officers often decline to assign fault)
- **Source options:**
  - Police report narrative (14–30d, primary)
- **Best-case cycle time:** 14–30d
- **Depends on:** Q-LIA-001
- **Requirement citation:** AIC §3.4.
- **Cycle-time citation:** Police records 30d standard.

### Q-LIA-007 — Are there witnesses, and what are their statements?

- **Blocks end-state:** liability
- **Gating:** nice-to-have (rarely required, often decisive)
- **Source options:**
  - Police report witness list (14–30d, identifies witnesses)
  - Direct witness contact (1–14d when reachable, never otherwise)
- **Best-case cycle time:** 7–30d realistic (per Tom's industry experience)
- **Depends on:** Q-LIA-001
- **Fact-stable at:** request_response
- **Requirement citation:** AIC §3.6.
- **Cycle-time citation:** Tom's TPA estimate; CPCU 552 §3 (witnesses are notoriously hard to reach).

### Q-LIA-008 — Did either driver admit fault at the scene or in post-loss communications?

- **Blocks end-state:** liability
- **Gating:** required
- **Source options:**
  - Police report (14–30d, primary)
  - Insured statement (1–3d, primary for own statements)
  - Recorded statement of opposing party (rare; via counsel if represented, 14d+)
- **Best-case cycle time:** 1–3d (insured)
- **Depends on:** Q-LIA-001
- **Requirement citation:** AIC §3.4.
- **Cycle-time citation:** [ESTIMATE] — insured 1–3d when responsive.

### Q-LIA-009 — Does the loss involve any FL-specific liability doctrines (joint-and-several, dangerous instrumentality, vicarious liability)?

- **Blocks end-state:** liability
- **Gating:** conditional (required when insured ≠ driver of record, OR loss involves multiple at-fault parties; otherwise nice-to-have)
- **Source options:**
  - Loss facts + ownership records (internal + DMV, 7–14d)
- **Best-case cycle time:** 7–14d
- **Depends on:** Q-LIA-001, Q-COV-002
- **Fact-stable at:** request_response
- **Requirement citation:** FL dangerous-instrumentality doctrine (Florida common law); AIC FL supplement.
- **Cycle-time citation:** DMV 7–14d.
- **Notes:** FL dangerous-instrumentality holds vehicle *owners* vicariously liable for permissive-user negligence — only matters when ownership ≠ operation.

### Q-LIA-010 — Is the claimant alleging the insured's comparative fault (and what percentage)?

- **Blocks end-state:** liability
- **Gating:** required (FL pure comparative fault)
- **Source options:**
  - Demand letter from claimant counsel (typically months after loss; counsel waits for medicals to stabilize)
  - Pleadings if suit filed (varies)
- **Best-case cycle time:** Not adjuster-controlled; soft-tissue pre-suit timeline 6–12 months total. Source: [Florida PI case timeline (DeLoach, Hofstra & Cavonis)](https://www.dhclaw.com/faqs/florida-personal-injury-case-timeline-expectations.cfm).
- **Depends on:** Q-LIA-001
- **Requirement citation:** FL § 768.81.
- **Cycle-time citation:** Claimant-counsel-initiated; bounded by SOL but otherwise dictated by counsel strategy.

### Q-LIA-011 — Is there event-data-recorder (EDR / "black box") data, and what does it show about speed, braking, and impact dynamics?

- **Blocks end-state:** liability
- **Gating:** nice-to-have (frequently decisive in disputed-fault cases; routinely absent in low-severity)
- **Source options:**
  - Vehicle access + Bosch CDR (Crash Data Retrieval) tool readout (requires physical access to vehicle, 7–21d to schedule + extract; vehicle must not yet be salvaged)
  - OEM telematics download (where equipped — GM OnStar, Tesla, fleet telematics; varies 7–30d via subpoena or insured-consent request)
  - Subpoena via litigation (only post-suit; varies)
- **Best-case cycle time:** 7–21d when vehicle is still accessible; impossible after salvage disposal
- **Depends on:** Q-LIA-001
- **Fact-stable at:** request_response (once extracted, the data is fixed)
- **Requirement citation:** NHTSA EDR rule (49 CFR Part 563); FL practice treats EDR as a standard exhibit in disputed-causation cases.
- **Cycle-time citation:** [ESTIMATE] — based on Bosch CDR-tool extraction workflow + typical scheduling delay. AIC curriculum reference dropped — couldn't confirm explicit §3.7 EDR coverage in current revision.
- **Notes:** **Time-critical — if the vehicle gets salvaged before extraction, the data is gone.** This is its own "long-pole + perishable" pattern: the cycle time isn't long, but the *window* to act is short.

---

# Section C — Damages estimate open questions

These close the question of "what does this claim cost." Most are
nice-to-have until liability is locked, but the slow-cycle ones
(medical records, employer wage verification) get started day 1 in
parallel.

### Q-DAM-001 — What injuries did the claimant sustain (initial diagnosis)?

- **Blocks end-state:** damages
- **Gating:** required
- **Source options:**
  - ER report (HIPAA release to provider, 5–30d)
  - Claimant statement (1–3d, low fidelity)
  - PIP carrier records (1–7d if PIP applied)
- **Best-case cycle time:** 1–7d (PIP records)
- **Depends on:** Q-DAM-013 (HIPAA release executed first)
- **Requirement citation:** AIC §4.1; FL § 627.736 (PIP records access for related carriers).
- **Cycle-time citation:** HIPAA Privacy Rule 30-day statutory max (45 CFR 164.524(b)(2)); AHIMA published guidance — most providers fulfill in 5–10 days. Source: [HHS HIPAA FAQ 2050](https://www.hhs.gov/hipaa/for-professionals/faq/2050/how-timely-must-a-covered-entity-be/index.html); AHIMA "Requesting Medical Records."

### Q-DAM-002 — What treatment to date (providers, dates, modalities)?

- **Blocks end-state:** damages
- **Gating:** required
- **Source options:**
  - Medical records via HIPAA release (5–30d per provider; statutory max 30d + possible 30d extension)
  - Claimant counsel summary letter (7–14d, lower detail)
- **Best-case cycle time:** 5–14d
- **Depends on:** Q-DAM-013
- **Requirement citation:** AIC §4.2.
- **Cycle-time citation:** HIPAA Privacy Rule 30d max (45 CFR 164.524(b)(2)); AHIMA: typical 5–10d. Source: [HHS HIPAA FAQ 2050](https://www.hhs.gov/hipaa/for-professionals/faq/2050/how-timely-must-a-covered-entity-be/index.html).

### Q-DAM-003 — What is the projected future treatment plan?

- **Blocks end-state:** damages
- **Gating:** required
- **Source options:**
  - Treating provider's plan (medical records, 14–30d)
  - Independent medical exam (IME, 21–60d to schedule + report)
- **Best-case cycle time:** 14–30d
- **Depends on:** Q-DAM-002
- **Requirement citation:** AIC §4.3.
- **Cycle-time citation:** [ESTIMATE] — IME scheduling typically 21–45d in FL metros.

### Q-DAM-004 — What are the medical bills incurred to date?

- **Blocks end-state:** damages
- **Gating:** required
- **Source options:**
  - Provider billing offices (HIPAA release + billing request, 5–30d)
  - Claimant counsel bill summary (7–14d, less granular)
  - PIP ledger (1–7d if PIP applied)
- **Best-case cycle time:** 1–7d (PIP)
- **Depends on:** Q-DAM-013
- **Requirement citation:** AIC §4.4; FL § 627.736 (PIP coordination).
- **Cycle-time citation:** HIPAA 30d max, AHIMA 5–10d typical for provider billing; PIP ledger access governed by FL § 627.736(6) (coordination of benefits). Counsel summary timing: see [ASK].

### Q-DAM-005 — What are the projected future medical costs?

- **Blocks end-state:** damages
- **Gating:** nice-to-have (required at demand stage)
- **Source options:**
  - Treating provider estimate (medical records, 14–30d)
  - Life-care planner report (if catastrophic, 30–90d)
- **Best-case cycle time:** 14–30d
- **Depends on:** Q-DAM-003
- **Requirement citation:** AIC §4.5.
- **Cycle-time citation:** [ESTIMATE].

### Q-DAM-006 — Has the claimant lost wages, and have they been employer-verified?

- **Blocks end-state:** damages
- **Gating:** required if claimed
- **Source options:**
  - Claimant counsel wage submission (7–14d)
  - Employer verification of wage (request to employer, 7–30d depending on org size)
  - Tax returns (claimant via release, 14–30d)
- **Best-case cycle time:** 7–14d
- **Depends on:** none (independent of medical records)
- **Fact-stable at:** demand_received (final wage-loss claim depends on return-to-work timing)
- **Requirement citation:** AIC §4.6.
- **Cycle-time citation:** Tom's TPA estimate — employer HR response varies significantly by org size; large employers can take the full 30d.

### Q-DAM-007 — Has the claimant sustained permanent impairment, and to what degree?

- **Blocks end-state:** damages
- **Gating:** required if claimed
- **Source options:**
  - Treating provider impairment rating (medical records via HIPAA release, 5–30d)
  - IME (21–60d scheduling + report; see [ASK])
- **Best-case cycle time:** 5–14d (treating provider rating); IME longer
- **Depends on:** Q-DAM-002
- **Requirement citation:** AIC §4.7; AMA Guides to the Evaluation of Permanent Impairment (referenced by FL practice).
- **Cycle-time citation:** HIPAA + AHIMA per Q-DAM-002. IME scheduling: see [ASK].

### Q-DAM-008 — What is the claimant's pre-accident medical history relevant to the injuries claimed?

- **Blocks end-state:** damages
- **Gating:** required (causation defense in FL)
- **Source options:**
  - Pre-accident records via HIPAA release (provider-by-provider, 5–30d each)
  - Health-insurance claims history (release + insurer, ~21–45d typical per CMS-style claims history requests; see [ASK])
- **Best-case cycle time:** 5–14d per provider; ~21–45d for insurer history
- **Depends on:** Q-DAM-013
- **Requirement citation:** AIC §4.8; FL causation defense practice.
- **Cycle-time citation:** HIPAA + AHIMA per Q-DAM-002. Health-insurer historic-claims response: see [ASK].

### Q-DAM-009 — What property damage (vehicle, contents) is claimed, and what is the repair estimate?

- **Blocks end-state:** damages
- **Gating:** required if PD claimed
- **Source options:**
  - Body shop estimate (1–7d)
  - Independent appraiser (3–10d)
  - Total-loss vehicle valuation (NADA/Mitchell, minutes)
- **Best-case cycle time:** minutes (NADA) to 7d (shop estimate)
- **Depends on:** none
- **Requirement citation:** AIC §4.9.
- **Cycle-time citation:** [ESTIMATE] — body shop response time 1–7d typical.

### Q-DAM-010 — Is there a diminution-of-value claim, and on what basis?

- **Blocks end-state:** damages
- **Gating:** nice-to-have
- **Source options:**
  - DV appraisal (independent, 7–21d)
  - Demand letter (14d+, includes basis)
- **Best-case cycle time:** 7–21d
- **Depends on:** Q-DAM-009
- **Requirement citation:** FL DV claim practice (variable by case law).
- **Cycle-time citation:** [ESTIMATE].

### Q-DAM-011 — Are there liens (medical provider, ERISA, Medicare/Medicaid, workers comp)?

- **Blocks end-state:** damages
- **Gating:** required pre-settlement
- **Source options:**
  - Provider lien notices (arrive as they're filed, varies)
  - Medicare Section 111 query (CMS portal, 30–90d for MSPRP)
  - ERISA plan lien notice via claimant counsel (7–14d after demand)
- **Best-case cycle time:** 30–90d (Medicare MSPRP is the long pole)
- **Depends on:** Q-DAM-001
- **Requirement citation:** Medicare Secondary Payer Act; AIC §4.10.
- **Cycle-time citation:** CMS published MSPRP turnaround 65 business days standard; this is a known long pole that catches adjusters who don't start it day 1.

### Q-DAM-012 — Has a demand been made, and for what amount on what basis?

- **Blocks end-state:** damages
- **Gating:** required at pre-suit stage
- **Source options:**
  - Demand letter from claimant counsel (arrives when counsel sends; not on a request cycle)
- **Best-case cycle time:** n/a (claimant-initiated)
- **Depends on:** Q-DAM-002, Q-DAM-006 (counsel waits for medicals to stabilize)
- **Requirement citation:** Standard pre-suit practice; AIC §5.
- **Cycle-time citation:** Not adjuster-controlled. Industry data: most demands give insurer 20–60d (commonly 30d) to respond, so the *response cycle* on our side is bounded. Source: AllLaw / Miller & Zois pre-suit demand benchmark surveys.

### Q-DAM-013 — Has the claimant executed HIPAA medical-records releases for the providers we need?

- **Blocks end-state:** damages (gates Q-DAM-001 through Q-DAM-008)
- **Gating:** required
- **Source options (STRUCTURAL CONSTRAINT — see note):**
  - When represented (`rep_flag=True`): claimant counsel ONLY (1–7d cooperative; longer if not)
  - When unrepresented: direct request to claimant (1–7d)
- **Best-case cycle time:** 1–7d
- **Depends on:** none — must be requested day 1 because it's a gating prerequisite
- **Fact-stable at:** request_response
- **Requirement citation:** HIPAA Privacy Rule (45 CFR 164); FL § 626.9541(1)(i) prohibits direct contact with represented claimants outside their counsel.
- **Cycle-time citation:** [ESTIMATE] — counsel response per Tom's TPA experience.
- **Notes:** **Structural routing constraint for the Outreach Drafter.** When `rep_flag=True`, the request MUST go to counsel — direct contact is an unfair-claims-practices violation. This isn't a preference; it's a hard branch. Outreach Drafter enforces this; the map declares it here so the constraint lives in the spec.

---

# Critical-path summary (slow-cycle questions worth surfacing as "start day 1")

These are the long-pole open questions across all three end-states.
Brief and Outreach should flag any of these that are open AND
unrequested in the first 24 hours of a claim, because failing to
start them day 1 pushes out the earliest possible decision date.

| Question | Cycle | Why long-pole |
|---|---|---|
| Q-COV-005 (exclusions / loss facts) | 14–30d | Police report dependency |
| Q-LIA-002 / Q-LIA-003 / Q-LIA-006 (traffic control, path, fault) | 14–30d | Police report dependency |
| Q-LIA-005 (license / impairment) | 7–14d | DMV records |
| Q-LIA-011 (EDR data) | 7–21d, **PERISHABLE** | Vehicle salvage destroys access |
| Q-DAM-002 / Q-DAM-007 / Q-DAM-008 (records, impairment, pre-accident) | 5–30d (HIPAA) | Provider records — typically faster than I first estimated |
| Q-DAM-011 (Medicare lien) | 30–90d | CMS MSPRP query — known long pole |
| Q-DAM-013 (HIPAA release) | 1–7d | Gates Q-DAM-001…008 — bottleneck for all medical questions |

**Q-DAM-013 (the HIPAA release)** is the highest-leverage day-1
action: gates eight downstream questions and itself takes only 1–7d.

**Q-LIA-011 (EDR data)** is a *different* kind of long-pole —
**perishable**. The cycle isn't long, but the *window to act* is.
Vehicle salvage destroys EDR access. This means Outreach should flag
EDR-relevant claims (disputed fault, high-severity) for immediate
vehicle preservation, not just queue them on the standard chase
cadence.

**Q-DAM-011 (Medicare MSPRP)** is the slowest known atom — 30–90d via
CMS portal. If the claimant is Medicare-eligible (age 65+ or
disabled), this MUST be queried day 1 or it bottlenecks settlement
weeks after damages are otherwise locked.

# What's deliberately out of scope for this map

- **Other LOBs.** Property, auto PD-only, UM/UIM, no-fault PIP-only.
  Each needs its own info map; we'd derive a generalization model
  once we have 2–3 to compare.
- **Other jurisdictions.** FL has distinctive doctrines (dangerous
  instrumentality, pure comparative fault, no-fault PIP, MSPRP
  practice). Other states differ enough that copying the map is
  wrong. Per-state supplements come later.
- **Subrogation / recovery.** Treated as a separate Recovery
  specialist with its own info map.
- **Closure / payment / settlement-execution.** Once the demand is
  resolved, a different question set applies.
- **Adjuster-side internal questions.** "Should we escalate to
  litigation review" is a workflow question, not a fact-about-the-
  claim question. Handled elsewhere.

# Cycle-time resolutions (r2)

Tom's TPA-experience locks from voice review on 2026-05-31:

| Question | r1 estimate | r2 lock | Source |
|---|---|---|---|
| Q-DAM-009 body shop estimate | 1–7d | **1–7d** ✓ | Tom confirmed |
| Q-LIA-007 witness contact | 7–30d realistic | **7–30d** ✓ | Tom confirmed |
| Q-DAM-006 employer wage verification | 7–21d | **7–30d** (large employers can take the full 30d) | Tom widened upper bound |
| Q-DAM-008 health insurer historic | 21–45d | **21–45d** ✓ (health insurers are "very inefficient") | Tom confirmed |
| Q1 plaintiff counsel response time | 3–7d responsive / 7–14d avg / 21d+ ghosting | **kept as estimate — go with my assumption per Tom** | best-guess |
| Q3 IME scheduling lag (FL metros) | 21–60d | **kept as estimate — go with my assumption per Tom** | best-guess |

# Architecture-call resolutions (r2)

| # | Question | Resolution |
|---|---|---|
| 8 | AIC §3.7 EDR citation | Dropped. NHTSA 49 CFR Part 563 is the authoritative cite for Q-LIA-011. |
| 9 | Q-LIA-009 conditional? | **Yes** — required when insured ≠ driver of record, otherwise nice-to-have. |
| 10 | HIPAA release routing represented→counsel | **Encoded as structural constraint** in Q-DAM-013 source options. Outreach Drafter enforces. |
| 11 | Q-COV-005 granularity split? | **Keep coarse for v1.** Downstream Coverage specialist decomposes. Noted in preamble. |
| 12 | Status grain partial vs binary | **Binary (`open` / `answered`) for v1.** Partial is a v2 UX concern. Noted in preamble. |
| 13 | `fact_stable_at` field | **Added** to schema and populated on questions where stability is non-trivial (mostly damages — MMI, demand_received, settlement). |

# Open questions about the info map itself (meta)

- **Q-META-1:** Per-instance cycle-time overrides — should we model
  that the specific Hillsborough County records office takes 60d
  vs. the FL default 30d? Yes, eventually, when we have outreach
  history to learn from. Not in this version.
- **Q-META-2:** Source-fidelity hierarchy — how do we score
  authoritative vs self-reported? For now: primary/secondary/
  tertiary tags only; numerical fidelity scoring comes when we have
  multi-source conflict cases to ground it.
- **Q-META-3:** Cycle-time citations marked `[ESTIMATE]` — these are
  TODOs to verify in Phase 1 adjuster-workflow research before any
  eval that depends on cycle-time-driven prioritization.
