---
tags:
  - project/argos
  - type/data-exploration
  - dataset/nhtsa-crss
  - status/draft
created: 2026-05-28
aliases:
  - CRSS Notes
---

# CRSS 2023 — exploration notes

## What it is

NHTSA Crash Report Sampling System. A nationally representative **sample** of police-reported motor vehicle crashes in the US — all severities, not just fatalities. Replaces the older NASS GES program. Public, annual refresh.

Source: `https://static.nhtsa.gov/nhtsa/downloads/CRSS/2023/CRSS2023CSV.zip`. Loaded via [scripts/load_crss.py](../../scripts/load_crss.py) into `data/crss.duckdb` under schema `crss2023`. (Separate DB file from FARS — can be attached at query time with `ATTACH`.)

## Shape

- 28 tables, 47MB CSV input
- Headline tables: `accident` (50,103 sampled crashes), `vehicle` (87,461), `person` (122,388)
- Same table family as FARS, plus sample-design tables

## Grain

Same composite key structure as FARS with **one rename**: `ST_CASE` → `CASENUM`. Otherwise `VEH_NO`, `PER_NO` unchanged. A triple-join on `(CASENUM, VEH_NO)` resolves 116,597 of 122,388 person rows; the 5,381 unmatched are non-occupants with `VEH_NO=0` (same pattern as FARS).

Every row carries a `WEIGHT` column for projecting sample counts to national estimates (~6.1M crashes nationally per year).

## The headline finding — severity distribution

| KABCO severity | Sample rows | Weighted national estimate | Share |
|---|---:|---:|---:|
| No Apparent Injury (O — PDO) | 23,856 | 4.33M | **70.5%** |
| Possible Injury (C) | 9,947 | 824K | 13.4% |
| Suspected Minor (B) | 8,635 | 612K | 10.0% |
| Suspected Serious (A) | 5,495 | 141K | 2.3% |
| Fatal (K) | 1,130 | 37K | **0.6%** |

This is what a real claim book looks like — 70% fender-benders, ~25% moderate, <1% fatal. FARS captures only the bottom row.

## Schema differences vs FARS

**CRSS adds:**
- Sample-design columns: `WEIGHT`, `PSU`, `PSUSTRAT`, `STRATUM`, `REGION`, `URBANICITY`
- Imputed variants of many fields, suffixed `_IM` (e.g. `MAXSEV_IM`, `ALCHL_IM`, `WEATHR_IM`) — NHTSA's hot-deck imputation for missing categorical values
- `MAX_SEV` and `NUM_INJ` aggregations at the accident level

**CRSS drops (privacy-preserving):**
- Geographic precision: no `LATITUDE`, `LONGITUD`, `COUNTY`, `CITY`, `TWAY_ID`, `MILEPT`, `FUNC_SYS`, `ROUTE`
- Arrival / hospital / notification timing: no `ARR_HOUR`, `HOSP_HR`, `NOT_HOUR`
- FARS-only fatal-specific fields: `FATALS`, `PERSONS`

**Tables only in FARS:** `drugs`, `race`, `miacc`, `midrvacc`, `miper`. No tables exclusive to CRSS.

## Role in the demo

**Severity calibration layer.** Not a replacement for FARS; an overlay. Two specific uses:

1. **Synthetic generator weighting** — when generating synthetic claims, sample severity from the CRSS distribution, not the FARS distribution, so the demo claim book reflects what a real adjuster's pending list looks like.
2. **PDO and minor-injury sample** — most of an LMM book is low-severity. CRSS gives us examples of low-severity loss events with realistic surrounding context (weather, road, maneuvers), which a synthetic generator can dress into the bulk of the demo book.

Use FARS for the catastrophic tail (geo-precise, fatal detail). Use CRSS for the body of the distribution.

## Cut criteria

| Criterion | Answer |
|---|---|
| Is the structured data real enough that SQL transforms feel non-contrived? | **Yes**, same schema family as FARS, same join mechanics, same level of messiness. |
| Does the workflow it implies match the LMM buyer profile? | **Yes** — low-severity, high-volume is exactly the LMM workflow shape. |
| What synthetic layer do we need to add for the LLM extraction story to be meaningful? | Same as FARS — see [FARS notes](./nhtsa-fars.md) gap table. CRSS doesn't fix any of those gaps; it fixes the severity distribution. |

**Verdict:** Keep as severity-distribution overlay. Don't query directly for the demo UI; use to weight the synthetic generator.
