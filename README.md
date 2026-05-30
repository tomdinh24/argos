---
tags:
  - project/argos
  - type/readme
  - status/draft
created: 2026-05-30
aliases:
  - Argos README
---

# Argos

> Argos is an AI-native claims operations layer for specialty property and casualty TPAs. It turns fragmented claim files into structured evidence, calibrated probabilities, and draft work product across the full claim lifecycle, with validators that require every AI output to be sourced before it reaches the adjuster workspace.

---

## What this is

A portfolio project building Argos. Six specialists watch every claim — Brief, Coverage, Liability, Reserve, Recovery, Closure — and surface evidence + probability + drafted work product to the adjuster's workspace. The adjuster picks the path. The vault enforces every write.

The architecture answers two interview loops:

- **Palantir FDE** — ontology design over messy real data, SQL-on-messy-data, configuration-as-moat, system decomposition
- **AI PM** — problem framing, multi-agent architecture, evals, calibration, the legally-bearing-claim contract

## Design docs (read in this order)

1. [THESIS](docs/THESIS.md) — what we believe, who the buyer is, why the wedge is structured this way
2. [MARKET_ANALYSIS](docs/MARKET_ANALYSIS.md) — sourced market sizing, competitive landscape, vendor profiles
3. [STRATEGY](docs/STRATEGY.md) — six specialists, two services, the demo moment, the moat
4. [data-layer](docs/data-layer.md) — synthesis pipeline, ontology, four-layer truth model, calibration
5. [SYSTEM_ARCHITECTURE](docs/SYSTEM_ARCHITECTURE.md) — Foundry + Railway + Vercel three-layer architecture
6. [AGENT_ARCHITECTURE](docs/AGENT_ARCHITECTURE.md) — specialist runtime, the LegallyBearingClaim contract, eval wiring
7. [TECH_PLAN](docs/TECH_PLAN.md) — per-component decisions, build sequence, validation gates
8. [research/specialty-tpa-auto-property-workflow](docs/research/specialty-tpa-auto-property-workflow.md) — workflow ground truth

## Core architectural commitments

- **Three layers.** Foundry holds typed semantic state and validates every write; Railway runs the specialists; Vercel renders the cockpit.
- **Six specialists.** Brief, Coverage, Liability, Reserve, Recovery, Closure — each emits `Assessment` and `Synthesis` outputs (probability + reasoning + cited evidence) or, in Brief's case, a structured view with citations on every diff item.
- **No recommendations.** Specialists surface evidence and quantify uncertainty; humans pick the path. The schemas are tested to reject `recommended_*` fields. This is what makes the output calibratable.
- **The deterministic spine.** Specialists never mutate state directly. Every write flows through a Foundry Action Type validator. Illegal state combinations and unbalanced financial postings are rejected at the door.
- **Configuration as moat.** The same specialist code behaves differently per client because `SpecialistConfig` drives material-event triggers, authority matrices, notice deadlines, sourced legal rules.

## Repo layout

```
docs/                 # Design docs (the meat — read these)
foundry/              # Foundry-ready ontology YAML + Action Type TypeScript drafts
  ontology/           # 28 object types from data-layer.md §5
  action-types/       # Validator skeletons (in progress)
src/argos/            # Python package
  schemas/            # Pydantic v2 schemas — the Assessment + Synthesis contract
    contract.py               # EvidenceCitation, Assessment, Synthesis
    specialists/              # One file per specialist's output schema
  specialists/        # Specialist runtimes (in progress)
  services/           # Priority Scorer + Correspondence (in progress)
  vault/              # OSDK client + Foundry Function wrappers (in progress)
  synthesis/          # Three-pass synthesis pipeline (in progress)
tests/                # pytest; 26 passing on the schema contract
scripts/              # Data exploration scripts (FARS, CRSS loaders)
data/                 # DuckDB + raw datasets (gitignored)
```

## Running tests

```bash
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
```

26 tests pass on the Assessment + Synthesis contract and the six specialist schemas, including structural assertions that the Coverage and Liability schemas contain no `recommended_path` field (the "no recommendation" rule enforced by the test suite).

## Status

Weekend 1 in progress. See [TECH_PLAN §8](docs/TECH_PLAN.md) for the four-weekend build sequence.

## License

No license attached yet. Portfolio project; reach out before copying.
