---
tags:
  - project/argos
  - type/foundry-specs
  - status/draft
created: 2026-05-28
aliases:
  - Foundry Specs README
---

# Foundry specs (preparation material)

This directory holds **draft specifications** for the Foundry ontology and Action Types, prepared locally before importing into the Foundry Developer Tier tenant during Weekend 1.

## What's here

```
foundry/
  README.md                      # this file
  ontology/
    object-types.yaml            # all 26 object types from data-layer.md §5
    link-types.yaml              # link types connecting object types
    property-types.yaml          # shared property type definitions
  action-types/
    record-financial-transaction.ts   # the ledger write Action Type
    update-exposure-status.ts          # status changes with illegal-combination matrix
    register-document.ts                # document ingestion
    emit-agent-action.ts                # specialist recommendation surface
    # ... 8 more (stubbed in v0.1)
    _shared/
      illegal-combinations.ts      # the matrix used by UpdateExposureStatus
      posting-rules.ts             # the rules used by RecordFinancialTransaction
      types.ts                      # shared TS types
```

## Important: format vs Foundry's actual import path

Foundry's Ontology Manager is a browser UI. There is no single "import this YAML and the ontology appears" path documented in the public docs. The YAML files in `ontology/` are **specs that map field-by-field to Ontology Manager form fields** — they reduce Weekend 1 to "paste from spec to UI" rather than "design from scratch in UI."

The TypeScript files in `action-types/` are **drafts of the validator logic** that gets pasted into Code Repositories during Weekend 1. They use placeholder types (`ObjectType`, `LinkedObject<T>`) that resolve to Foundry's actual generated types once the ontology exists in the tenant.

## Weekend 1 import sequence

1. Sign up Foundry Developer Tier
2. Create the ontology in Ontology Manager:
   - Property types first (`property-types.yaml`)
   - Object types next (`object-types.yaml`) — paste field-by-field
   - Link types last (`link-types.yaml`)
3. Create the Code Repositories repo for ontology Functions
4. Paste the Action Type validators into Code Repositories, fix imports to point to Foundry's generated types
5. Run the §14 acceptance gate from TECH_PLAN.md

## What to do when something doesn't map

The specs were drafted from data-layer.md §5 + TECH_PLAN.md §5. If a Foundry UI field doesn't exist for something in the spec, or vice versa:
- Update the spec to reflect Foundry's actual model
- Note the divergence in the file's header comment
- If material, surface it in TECH_PLAN.md v0.3
