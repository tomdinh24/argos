---
tags:
  - project/argos
  - type/research
  - status/draft
created: 2026-06-01
---

# Reserve estimation methods — how claims professionals actually compute the number

> Input to the Reserve workflow design
> ([docs/specs/reserve-workflow.md](../specs/reserve-workflow.md)). The
> workflow's prompt has to embed real methodology, not generic "estimate
> reasonably." This doc captures the methods adjusters and claims
> examiners actually use, so the prompt can mirror them.

## Reality check — what auto BI claims actually cost

Before diving into per-component math: **most auto BI claims close
for far less than the surgical/litigated examples you see in
training materials**. The distribution is heavily right-skewed.

| Closing band | % of auto BI claims | What's in this band |
|---|---|---|
| **< $30K** | ~60% | Soft tissue + minor moderate, conservative care, no litigation |
| **$30K – $100K** | ~25% | Moderate to severe-recovering, sometimes light litigation |
| **$100K – $500K** | ~12% | Litigated severe injuries, surgical, permanent impairment |
| **$500K +** | ~3% | Catastrophic, wrongful death, nuclear verdicts (trucking inflates this band) |

**Average auto BI claim severity (US, 2024):** ~$26K–29K incurred.
**Median:** roughly $8K–12K — much lower than the average because the
distribution is so right-skewed. Source: Insurance Information
Institute, NAIC Profitability Reports, Insurance Research Council
closed-claim studies.

**Trucking / commercial inflates everything.** Average commercial
auto BI claim severity runs $80K–150K, not $26K, because (a)
commercial limits are higher so policy-limit reserves are higher,
(b) juries hit deep-pocket commercial defendants harder, and (c)
trucks tend to cause worse injuries than passenger vehicles. A
truck-hit-pedestrian or truck-hit-passenger-car BI claim sits in a
different distribution than a fender-bender.

**Reserve ≠ final paid.** Carriers reserve conservatively. A claim
reserved at $100K might settle for $60K–80K once the file matures.
The reserve covers the downside; the settlement reflects negotiation,
liability haircuts, and the carrier's appetite for trial. So when
the workflow recommends a reserve, that number is the "if this goes
badly, here's what we're exposed to" number — not a prediction of
final paid.

The numbers below build to a recommendation that sits in the same
distribution. A $100K+ recommendation should be reserved for cases
whose evidence actually supports the severe-or-above tier, not
applied to every fender-bender by default.

---

## The shape of the answer

Per-component reserves for auto BI / GL claims roll up like this:

```
Total exposure on a claim
= INDEMNITY (specials + generals, × fault probability)
+ ALAE       (defense + experts + investigation)
+ ULAE       (carrier overhead allocation)
+ ALE        (property displacement, if applicable)
+ expert_fees (IME, recon, valuation)
+ defense    (counsel fees — sometimes broken from ALAE)
+ mitigation (post-loss preservation)
```

Each line uses a different method. The workflow needs to know all of
them.

---

## INDEMNITY — bodily injury (the largest single line)

Industry decomposes indemnity into two parts: **specials** (economic,
quantifiable) and **generals** (non-economic, judgment-based).

### Specials (economic damages)

These are the receipts. The math is straightforward:

```
specials = past_medicals + future_medicals + past_wage_loss
         + future_wage_loss + out_of_pocket
```

**Past medicals** read directly from medical bills in the file.

**Future medicals** project from the treatment plan + impairment
rating:

- **Conservative method:** sum the line items the treating physician has
  prescribed (PT sessions, follow-up MRIs, planned injections).
- **Life-care plan method (severe injuries):** a certified life-care
  planner builds a year-by-year projection of future medical needs
  through life expectancy. Total can run mid-six to seven figures for
  permanent injuries. Citation: any treating-physician deposition
  estimating future treatment cost, or a formal life-care plan
  document.
- **Impairment-rating-driven method:** for permanent partial impairment
  (PPI), some states attach statutory weekly values per percentage of
  impairment (WC context, but the rating itself influences BI generals
  multipliers — see below).

**Past wage loss** = (weekly_wage × weeks_out_of_work). Sourced from
W-2s, paystubs, employer wage verification.

**Future wage loss** projection for permanent disability cases:

- Loss of earning capacity = (pre-injury earning capacity − post-injury
  earning capacity) × remaining work-life expectancy, discounted to
  present value.
- Common discount rates: 3–5%. Common work-life expectancy tables:
  US BLS or Skoog-Ciecka tables.

**Out-of-pocket** = mileage to medical appointments, prescriptions,
durable medical equipment.

### Generals (non-economic damages)

Generals are pain and suffering, loss of consortium, hedonic damages,
emotional distress. No receipt method works. Three industry methods:

#### 1. Multiplier method (most common in adjuster reserve-setting)

```
generals = specials × M
```

Where `M` (the multiplier) ranges by injury severity. **Defense-side
reserve multipliers — calibrated to what carriers actually reserve,
not what plaintiff counsel demands.** Plaintiff demand letters
routinely use 4–10× even on soft tissue; that's posturing, not
reserve practice.

| Tier | Typical injury profile | Defense M range | % of auto BI claims | Typical total exposure (specials + generals + LAE) |
|---|---|---|---|---|
| **Minor** | Soft tissue (whiplash, sprain/strain), conservative care, full recovery < 3 months | 1.5 – 2.5 | ~50% | $3K – $15K |
| **Moderate** | Imaging + PT, possible injection, lingering symptoms < 12 months, no surgery, full recovery | 2 – 3.5 | ~30% | $15K – $50K |
| **Severe — recovering** | Single-system surgical repair (e.g., ORIF of fracture), 6–18 month recovery, no permanent impairment | 2.5 – 4 | ~10% | $50K – $150K |
| **Severe — permanent** | Surgical repair WITH permanent partial impairment rating, ongoing symptoms past MMI | 4 – 6 | ~5% | $150K – $500K |
| **Catastrophic** | Multi-system trauma, TBI, spinal cord injury, amputation, paralysis, wrongful death | 8 – 15 (sometimes higher in nuclear-verdict jurisdictions) | <5% | $500K – policy limits |

**Why these ranges differ from plaintiff-side multipliers.** The
1.5–25 ranges floating around the internet conflate (a) what
plaintiff counsel demands in opening letters, (b) what cases settle
at, and (c) what carriers reserve at. Reserves are
covering-the-downside numbers, not midpoints — but they're not
worst-case-plaintiff-demand either. Defense reserves sit between
median jury verdicts and the carrier's appetite for adverse
development.

**Sources for the multiplier ranges:** the tier-anchored ranges
above are calibrated against Insurance Research Council closed-claim
studies + Insurance Information Institute averages (US auto BI
severity hovering ~$26K–29K average through 2024) + AIC / CPCU
curriculum methodology. Specific carrier histories vary; v1 uses
these defaults, v2 recalibrates against a real customer's book.

**For the workflow:** the prompt picks M based on the documented
injury profile, NOT generic severity tier. Severity tier from the
caseload is the prior; specific evidence (diagnosis codes, MMI date,
impairment rating, surgical reports) is the posterior. The rationale
field must reference the specific documents that justified the
chosen M.

#### 2. Per-diem method (alternative, common in demand letters)

```
generals = days_of_suffering × $rate_per_day
```

`$rate_per_day` ranges $50–500 in industry pleadings. The injury
duration is from injury date to either MMI (maximum medical
improvement) date or settlement date. Plaintiff counsel often pleads
high per-diem; defense reserves often use mid-range.

#### 3. Verdict-search method (litigation/trial preparation)

Pull comparable jury verdicts from databases (Westlaw Jury Verdicts,
JuryVerdictResearch.com, VerdictSearch). Index by jurisdiction +
injury type + plaintiff demographics + liability percentage. Use the
distribution of comparable verdicts as the band.

This is the most defensible method for litigated claims but requires
database access. For Argos v1 the multiplier method is the right
default; verdict-search is a v2 hook once we have a database
integration.

### Liability adjustment (the fault haircut)

If liability is contested, indemnity exposure is weighted by P(we pay):

```
indemnity_recommended = (specials + generals) × P(we_pay)
                      = (specials + generals) × P(defendant_at_fault)
                                              × jurisdictional_recovery_factor
```

Jurisdictional recovery factor depends on the comparative negligence
rule:

| Rule | Effect on recovery |
|---|---|
| **Pure comparative** (CA, FL pre-2023, NY) | Plaintiff recovers (1 − plaintiff_fault%) of damages, regardless of fault % |
| **Modified 50%** (CO, ME, others) | Plaintiff recovers (1 − plaintiff_fault%) ONLY if plaintiff < 50% at fault; else $0 |
| **Modified 51%** (TX, IL, FL post-2023-03, NJ) | Plaintiff recovers (1 − plaintiff_fault%) ONLY if plaintiff ≤ 50% at fault; else $0 |
| **Pure contributory** (AL, MD, NC, VA, DC) | Plaintiff 1% at fault → $0 recovery |

Florida specifically moved from pure to modified 51% on
**March 24, 2023** (HB 837 tort reform). Big shift in Florida BI
exposure — for loss dates after that, plaintiff 51%+ at fault means
no recovery. Loss date matters for which rule applies.

**For the workflow:** the jurisdiction comes from
`policy.jurisdiction_state`. The fault % is contested — v1 assumes
100% defendant (no liability haircut applied inside the Reserve
workflow). The adjuster applies the haircut at commit time. v2 may
chain Liability's fault distribution as input.

---

## ALAE — allocated loss adjustment expense

Costs tied to this specific claim, not carrier overhead. Three
sub-pieces:

### Defense counsel

```
defense = sum across phases of (phase_hours × hourly_rate)
```

**Hourly rates** vary by jurisdiction and counsel tier. Industry
ranges in 2025–2026 dollars:

| Tier | Hourly rate range |
|---|---|
| Junior associate | $150 – 300 |
| Senior associate | $300 – 500 |
| Partner | $400 – 800+ |
| Coverage / specialty counsel | $500 – 1000+ |

**Phase-based budgets** for routine civil litigation (auto BI as the
canonical example):

| Phase | Typical total cost | Notes |
|---|---|---|
| Pre-suit investigation + initial demand response | $2K – 15K | Records review, initial defense letter |
| Pleadings + early motions | $10K – 30K | Answer, motion to dismiss, initial discovery requests |
| Discovery | $20K – 80K | Depositions, expert disclosures, written discovery |
| Mediation prep + mediation | $5K – 15K | Often pre-trial settlement venue |
| Trial prep | $30K – 100K | Pretrial motions, jury instructions, witness prep |
| Trial | $50K – 300K+ | Multi-day trials add fast |
| Post-trial / appeal | $20K – 100K+ | If applicable |

**Source:** widely-cited industry benchmarks (defense-counsel
marketing materials, carrier internal budgets, ALAE benchmarking
studies). Actual costs vary 2–3× depending on jurisdiction, counsel
quality, claim complexity, and aggressive opposing counsel.

**For the workflow:** the recommendation depends on what phase the
claim is likely to reach. The prompt should reason about: is suit
filed? Is there a demand letter? What's the likelihood of trial vs
settlement? Then sum estimated costs from current phase through
likely end phase.

### Investigation

Sub-rosa surveillance, accident reconstruction, witness statements,
recorded statements. Typical ranges $2K–$20K per claim depending on
investigation depth.

### Routine ALAE

Document copying, court filings, mediator fees, court reporter fees.
Usually $1K–10K per litigated claim.

---

## ULAE — unallocated loss adjustment expense

Carrier overhead allocation — adjuster salaries, claims system, office
overhead. Computed as a % of indemnity at the book level, then
allocated to claims for accounting purposes.

Industry ranges: 5–15% of indemnity. Specialty TPAs often use a flat
fee model with the client carrier, so per-claim ULAE may be a fixed
amount rather than a percentage.

**For the workflow:** ULAE is the most formulaic component. Either
apply a configured percentage (5–15% of recommended indemnity p50)
OR pass through a fixed fee from the TPA's client agreement. v1 can
default to 10% of indemnity p50 with a config override.

---

## expert_fees, defense (separated from ALAE in some frameworks)

Some carriers break expert fees and defense counsel into separate
components from ALAE for cleaner accounting. The schema allows both.
Typical usage:

- `defense` line: counsel fees only
- `expert_fees` line: IME (independent medical exam) $1K–5K, accident
  reconstructionist $5K–25K, vocational expert $3K–10K, life-care
  planner $5K–20K, economic expert (for wage loss) $5K–15K

Multiple experts can fire on a single claim (BI + permanent injury
typically uses IME + life-care planner + economist).

---

## ALE — additional living expense (property only)

For property claims where the insured is displaced. Hotel + food +
incidentals during displacement period.

```
ALE = displacement_days × (hotel_per_diem + food_allowance + incidentals)
```

Policy typically caps ALE at 20–40% of dwelling coverage. Adjuster
reads displacement timeline from contractor estimate (how long
repairs will take).

---

## mitigation — post-loss preservation costs

Property claims: tarp + board-up after fire/water/wind. Auto claims:
emergency tow + storage.

Industry ranges $500–10K per claim. Sourced from contractor invoices
in the file. The reserve here is typically very tight (these costs
have already been incurred and invoiced by the time the workflow
runs).

---

## Notice obligation thresholds

For each `NoticeType`, the trigger condition:

### excess_carrier

Industry standard: notify when primary reserves cross **50% of
primary policy limits** (often called the "50% rule"). Some excess
policies specify a different threshold (25%, 33%, or notice on any
reserve set above primary self-insured retention). Read the excess
policy form to confirm.

### reinsurer

Treaty-specific. Common: notify when reserves cross **50% of cession
layer attachment point**. For pro-rata treaties, notify on initial
reserve set above threshold. For excess-of-loss treaties, notify
when reserves cross attachment.

### client (TPA-specific)

Specialty TPAs administer claims FOR a client carrier. The TPA
service agreement defines reporting triggers — common: monthly
status report, immediate notice on reserves above $X, immediate
notice on litigation, immediate notice on regulatory action.

### DOI (state department of insurance)

Jurisdiction-specific. Examples:

- **California:** SIR fund contribution on certain UM/UIM payments
- **Florida:** PIP fraud reporting requirements
- **New York:** Frauds Bureau notice on certain claim types
- Statewide annual reporting on aggregate paid losses (not per-claim)

The workflow recognizes the high-frequency triggers; rare ones
escalate as "possible obligation, confirm with compliance."

### Medicare_Section_111

MMSEA Section 111 reporting: when a claimant is a Medicare
beneficiary (or has applied within 6 months), the carrier must
report the claim to CMS within specific deadlines. Two triggers:

- Initial ORM (ongoing responsibility for medicals) when carrier
  accepts medical payment responsibility
- TPOC (total payment obligation to claimant) when claim closes
  with a settlement

Penalty for failure to report: $1K/day per claim under the
Strengthening Medicare and Repaying Taxpayers Act. Carriers take
this seriously.

The workflow needs to identify: is the claimant a Medicare
beneficiary? Look for Social Security disability evidence, age 65+,
ESRD diagnosis, or explicit Medicare card in the file.

---

## Authority routing

Carriers structure adjuster authority around reserve and settlement
amounts. Typical bands (varies by carrier and TPA agreement):

| Authority level | Typical reserve / settlement cap |
|---|---|
| Handler | $25K – $50K |
| Supervisor | $50K – $250K |
| Manager | $250K – $1M |
| Client (carrier sign-off required) | $1M+ |

**For the workflow:** match the recommended band's p50 against
configured authority bands. The workflow emits the level required;
the writeback enforces it.

---

## What the prompt actually needs to contain

The Reserve workflow's SYSTEM_PROMPT should embed these methods
explicitly, not assume the model "knows reserve setting." Specifically:

1. **The decomposition** — per-component breakdown above. The model
   should know which components apply to which claim type (auto BI
   activates indemnity + ALAE + defense + expert_fees; property
   activates indemnity + ALAE + ALE + mitigation).
2. **The methods per component** — multiplier ranges for generals,
   phase-based budgets for defense, percentage defaults for ULAE,
   threshold rules for notice obligations.
3. **The jurisdiction handles** — comparative negligence rule,
   non-economic damage caps if any, jurisdiction-specific notice
   triggers. Pull from `policy.jurisdiction_state` and
   `SpecialistConfig.sourced_legal_rules`.
4. **The coverage posture framing** — per the producer/consumer
   pattern: denied → zero indemnity, defense only; ROR → full bands
   with uncertainty flagged; clean → standard exposure-weighted bands.
5. **The citation discipline** — every band must cite at least one
   document. Every multiplier choice must reference documented injury
   severity. Every notice obligation must cite the policy clause or
   statute that triggers it.

## What we DON'T have yet (and what to do about it)

- **Carrier-internal closed-claim history** to anchor multipliers
  against. Generic multiplier ranges (1.5–25) are wide; carrier-
  specific anchors would be tighter. v1 uses generic ranges with the
  understanding that v2 (when we have a real carrier customer)
  recalibrates against their book.
- **Verdict-search database integration.** Real defense counsel use
  Westlaw Jury Verdicts or VerdictSearch. v1 skips this; v2 adds it
  as a tool.
- **Life-care planner integration** for severe injuries. v1 reads the
  life-care plan from documents in the file; if no plan exists, the
  prompt flags this as "severe injury without life-care plan —
  recommend obtaining one."

## Sources cited inline above

- Florida HB 837 tort reform, March 24, 2023 — moved Florida from pure
  to modified-51% comparative negligence
- MMSEA Section 111 (Medicare Secondary Payer reporting)
- Strengthening Medicare and Repaying Taxpayers Act (SMART Act)
- BLS Skoog-Ciecka work-life expectancy tables (economic damages
  projection)
- Adjuster certification curricula: AIC (Associate in Claims), IIA
  Insurance Institute, CPCU
- Westlaw Jury Verdicts / VerdictSearch (commercial databases)

The multiplier ranges, phase budgets, hourly rates, and authority
bands are industry rules of thumb cited across many secondary sources
(adjuster training materials, plaintiff/defense attorney content,
carrier internal benchmarks). Range estimates are conservative
mid-market; specialty TPAs handling severity-tier-skewed books will
have tighter internal anchors. v1 of the Reserve workflow uses the
generic ranges; v2 recalibrates once we have a carrier's
closed-claim history to fit against.
