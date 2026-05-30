---
tags:
  - project/argos
  - type/data-exploration
  - dataset/fema-nfip
  - status/draft
created: 2026-05-28
aliases:
  - NFIP Notes
---

# FEMA NFIP Redacted Claims — exploration notes

## What it is

OpenFEMA's redacted dataset of every claim filed under the National Flood Insurance Program. Public, federal, refreshed periodically. The "redacted" version rounds lat/long, omits policyholder identity, and drops some fields the non-redacted version retains.

Source: `https://www.fema.gov/api/open/v2/FimaNfipClaims.csv` (574MB direct download). Dataset metadata: `https://www.fema.gov/openfema-data-page/fima-nfip-redacted-claims-v2`. Loaded into `data/nfip.duckdb` under schema `main_nfip` as a single table `claims`.

## Shape

- 1 table, 1,541,714 rows, 73 columns
- Coverage: 1978-01-01 → 2026-04-28 (date of loss range)
- 57 distinct values in `state` (50 states + DC + territories)

## Grain

One row = one **closed claim** filed under an NFIP policy after a flood loss. Not a loss-event sample — this is the actual claim record as reported to FEMA after the file closed.

## What's actually in there (signal — the money side)

This is where NFIP earns its place. **FARS has zero dollars; NFIP has $41B.**

| Field | Value |
|---|---|
| Rows with non-null `amountPaidOnBuildingClaim` | 1,219,906 |
| Rows with paid building claim > $0 | 1,134,605 (93% of populated) |
| Rows with paid contents claim > $0 | 561,138 |
| Rows with paid ICC (Increased Cost of Compliance) > $0 | 23,348 |
| Median paid building amount (where > 0) | **$12,000** |
| P95 paid building amount | **$144,860** |
| Max paid building amount | $10.7M |
| **Total paid across file** | **$41.3B** |

Top states by total paid: LA $9.4B, FL $9.4B, TX $7.6B, NJ $3.0B, NY $2.8B.

## Catastrophe tagging

Named storm events tagged directly on claims:

| Event | Claims |
|---|---:|
| Hurricane Katrina | 118K |
| Hurricane Sandy | 82K |
| Hurricane Harvey | 52K |
| Hurricane Helene | 33K |
| Hurricane Ian | 27K |

This unlocks **CAT-event clustering** — adjuster surge during named events, intra-event correlation between claims, the operational reality of property carriers handling 50K claims in a 90-day window after a single storm.

## Coverage structure (the other thing FARS doesn't have)

- Median `totalBuildingInsuranceCoverage` $128,000
- P95 building coverage $250,000 (the **statutory NFIP cap** — natural ceiling visible in the data)
- Median `totalContentsInsuranceCoverage` $14,000
- `buildingDeductibleCode` is a coded enum, not a dollar amount. Top codes: `0` (26%), `1` (21%), `2` (15%), `F` (14%); 10% null. Decoder table needed before this is interpretable.

This gives us real coverage limits, real coverage caps, real deductibles — the structure FARS structurally cannot provide.

## What's NOT in there (the catch)

**No claim lifecycle timing.** The redacted file has `dateOfLoss` and `asOfDate` (data extract date), but **no `dateOfClaimFiled` and no `dateClosed`**. `asOfDate − dateOfLoss` is a meaningless ~20-year gap because `asOfDate` is just the data-refresh stamp.

This means we **cannot** measure:
- Loss-to-file cycle time
- File-to-close cycle time
- Reserve trajectory over the life of the claim

If lifecycle timing matters for the demo, the OpenFEMA `FimaNfipPolicies` companion file may provide the policy-side dates needed to reconstruct it. Pull separately if needed.

## Other notable columns

`causeOfDamage`, `waterDepth`, `floodWaterDuration`, `floodZoneCurrent`, `ratedFloodZone`, `baseFloodElevation`, `elevationDifference`, `latitude` / `longitude` (rounded — that's the "redacted"), `censusTract`, `censusBlockGroupFips`. Strong feature surface for property risk modeling if the demo extends that direction.

## Role in the demo

**Property-line counterpart to auto.** Specifically:

1. **Real dollars.** Anchors the entire money side of the synthetic generator. We can sample payout distributions from real NFIP data instead of inventing them.
2. **Real coverage structure.** Deductibles, limits, caps — visible in the data, not invented.
3. **Real CAT clustering.** Named-event tagging lets us demo the surge-handling workflow that's a real LMM property carrier pain point.
4. **Second LOB on one ontology.** The "asset" story (per [THESIS.md §5](../THESIS.md)) requires the ontology to span LOBs without per-line forks. Auto + property on one ontology is the minimum credible demonstration of that.

## Caveats for the LMM-first thesis

NFIP is **federally underwritten**. The buyer profile we're targeting (LMM TPA or regional carrier) typically doesn't write flood directly — it's a separate program. So NFIP gives us *data*, but the *workflow* it implies is federal-program-specific, not the standard private-property workflow we'd see at a regional carrier.

How to handle this: use NFIP for the data layer (payouts, coverage structure, CAT clustering) while modeling the workflow on standard private-property handling (FNOL → inspection → estimate → settlement → closure), which the research doc [research/adjuster-workflow.md](../research/adjuster-workflow.md) covers. The data is real; the workflow is generic-property.

## Cut criteria

| Criterion | Answer |
|---|---|
| Is the structured data real enough that SQL transforms feel non-contrived? | **Yes.** 1.5M real claims, real dollars, real catastrophe tagging. |
| Does the workflow it implies match the LMM buyer profile? | **Partial.** NFIP workflow is federal-program-specific; we'd model the demo workflow on standard private-property handling, using NFIP for the data layer. |
| What synthetic layer do we need to add for the LLM extraction story to be meaningful? | Unstructured documents (estimates, photos, adjuster notes, statements) and the claim lifecycle timing absent from the redacted file. The structured money + coverage layer is already real. |

**Verdict:** Keep. Anchors the property-line money + coverage structure. Pair with private-property workflow modeling from the research doc.
