---
tags:
  - project/argos
  - type/data-exploration
  - dataset/nhtsa-fars
  - status/draft
created: 2026-05-28
aliases:
  - FARS Notes
---

# FARS 2023 — exploration notes

## What it is

NHTSA Fatality Analysis Reporting System. A census (not a sample) of every police-reported motor vehicle traffic crash on a US public road that resulted in at least one death within 30 days. Public, free, federally maintained, refreshed annually with ~12-month lag.

Source: `https://www.nhtsa.gov/file-downloads` → FARS → 2023. Loaded via [scripts/load_fars.py](../../scripts/load_fars.py) into `data/fars.duckdb` under schema `fars2023`.

## Shape

- 33 tables, ~400MB CSV input
- Headline tables: `accident` (37,769 rows), `vehicle` (58,508), `person` (92,768)
- Other useful tables: `damage`, `factor`, `maneuver`, `pbtype` (pedestrian/bicyclist), `parkwork`, `violatn`, `vsoe` (sequence of events), `drugs`, `distract`

## Grain

| Table | One row = | Key |
|---|---|---|
| `accident` | one crash | `ST_CASE` |
| `vehicle` | one vehicle involved in a crash | `(ST_CASE, VEH_NO)` |
| `person` | one person involved in a crash, occupant or non-occupant | `(ST_CASE, VEH_NO, PER_NO)` |

A triple-join `accident ⨝ vehicle ⨝ person` yields the canonical "one person, in one vehicle, in one crash, with one injury outcome" row. That row is the **loss event** — the thing a claim is built on top of.

Non-occupant rows (pedestrians, cyclists) have `VEH_NO = 0` and won't join to vehicle. Separate code path required for pedestrian claims.

## What's actually in there (signal)

- Crash circumstances: date, time, day of week, state, county, city, lat/long, route type, road function, weather, light condition, atmospheric conditions
- Vehicle: make/model/year, body type, registration state, owner type, travel speed, posted speed limit
- Person: age, sex, seating position, restraint use, injury severity (KABCO scale), airbag deployment, ejection, alcohol/drug indicators
- Sequence: maneuvers, factors contributing to crash, sequence-of-events per vehicle

## The real-vs-synthetic gap

FARS captures the **loss event**. A claim is the **business artifact** built on top. The synthetic layer has to produce:

| FARS gives us | Synthetic layer must add |
|---|---|
| Loss event (who/what/where/when/severity) | Parties cast as policyholders, claimants, witnesses |
| Vehicle ID, body type, make/model | Vehicle ACV, repair estimate, total-loss decision |
| Injury severity (KABCO) | Medical bills, treatment timeline, provider |
| Crash conditions (weather, road, light) | Liability allocation % between parties |
| — | Coverages, deductibles, policy limits per party |
| — | Reserves over time (bitemporal — what we thought it was worth at each point) |
| — | The claim lifecycle (states: opened → reserved → adjusted → paid → closed → reopened) |
| — | **All unstructured documents** — police report, recorded statements, repair estimates, medical bills, adjuster notes, photos |
| — | Fraud signals |
| — | Subrogation flow (intra-carrier vs inter-carrier) |
| — | Salvage recovery on total losses |
| — | Litigation flag, attorney representation |

The **unstructured documents** row is the entire reason LLM extraction exists in this product. Without it, there is no AI story.

## Severity bias (the catch)

FARS is fatality-only. Every accident in this dataset killed someone. Real claim books are ~70% PDO / 23% non-fatal injury / 0.6% fatal (see [CRSS notes](./nhtsa-crss.md)). Building a synthetic claim book on FARS alone would produce an unrealistically catastrophic distribution. Use CRSS to calibrate severity skew; use FARS for the geographic + fatal-detail layer.

## Role in the demo

**Primary source for auto-line loss events.** Provides the structural backbone — incident, vehicle, persons, environmental conditions — that the synthetic generator dresses up into claims. Geographic precision (lat/long, route, milepost) makes the SQL transforms feel non-contrived.

## Cut criteria

| Criterion | Answer |
|---|---|
| Is the structured data real enough that SQL transforms feel non-contrived? | **Yes.** Real federal census data, real composite keys, real referential integrity, real messiness. |
| Does the workflow it implies match the LMM buyer profile? | **TBD Phase 3.** Auto FNOL → triage → investigation maps cleanly to a TPA or regional carrier. Not to a flood-only program. |
| What synthetic layer do we need to add for the LLM extraction story to be meaningful? | The full set in the gap table above. Headline: parties, coverages, reserves, lifecycle, unstructured documents. |

**Verdict:** Keep. Primary auto-line foundation.
