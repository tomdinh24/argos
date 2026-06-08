# Argos — Claude Code Instructions

## Conductor worktree model

This repo runs under Conductor: each agent works inside a git worktree at
`~/conductor/workspaces/<repo>/<name>` — that worktree IS the repo and is your
cwd (`$CONDUCTOR_WORKSPACE_PATH`). The matching `~/Projects/<repo>` is the
shared **root checkout** (`$CONDUCTOR_ROOT_PATH`), normally on `main`.

- **Never `cd ~/Projects/<repo>` to do feature work — edit, build, or test there.**
  You're already in the repo — stay in your worktree. Feature work in the root
  checkout lands on the wrong branch and leaves your workspace diff empty.
- Use `$CONDUCTOR_ROOT_PATH` only as read-only reference for feature work. The
  cockpit `web/` source is now **tracked**, so cockpit edits happen in your
  worktree like any other source — not in the root.
- **One named exception:** the root checkout is the cockpit's **deploy box**. Its
  node_modules / `.next` / `.vercel/` build artifacts live only there (worktrees
  don't share untracked files), so `vercel --prod` and the commit-to-`main` flow
  Railway builds from must run in the root. The *only* writes allowed there are
  those deploy / commit-to-main flows — never feature work. Before deploying,
  fast-forward the root to the reviewed `main` and confirm it's clean
  (`git -C "$CONDUCTOR_ROOT_PATH" switch main && git pull`); you deploy reviewed
  state, never ad-hoc edits made in the root.

## Required reading

Before architectural, naming, flow, or "what should we build next" work:

1. **[docs/DECISIONS.md](./docs/DECISIONS.md)** — the load-bearing decisions
   log. Append-only. Read newest first. If you're about to make a
   suggestion, check no prior entry already settled it.
2. **[docs/SYSTEM_ARCHITECTURE.md](./docs/SYSTEM_ARCHITECTURE.md)** —
   deployment topology, request flow, security model.
3. **[docs/AGENT_ARCHITECTURE.md](./docs/AGENT_ARCHITECTURE.md)** —
   workflow + agent topology, runtime, eval wiring, failure modes.

For implementation details, the canonical specs live in `docs/specs/`.

## Mandatory re-read after context compaction

When the conversation has been compacted (you see a "summary" wrapping
prior turns) **and** the user asks any of:

- "what's next" / "what should we build next" / "what's the next problem"
- "what's missing" / "what's the gap" / "is this the gap"
- "did we already solve X" / "is X built" / "does X exist"
- "what's the current state of X" / "how does X work today"

**you MUST re-read `docs/AGENT_ARCHITECTURE.md` §2 and scan
`docs/DECISIONS.md` titles before answering.** Compaction summaries
capture what the recent session built — they do not carry the rest of
the system map. Answering from the summary alone produces confident,
plausible-sounding gas-lighting where you propose work that already
shipped or call something unbuilt that exists.

This rule overrides any temptation to "just answer from context."
The architecture doc is corrective; recent context is biased.

If `docs/AGENT_ARCHITECTURE.md` itself looks stale relative to a spec
status (e.g., spec says "KILLED" but the architecture doc still
describes the killed approach as live), append a rejection entry to
`docs/DECISIONS.md` and update the architecture doc to match.
Rejection entries are as load-bearing as ship entries.

## Source-of-truth rule

`docs/DECISIONS.md` is authoritative for what we're building and why.
**Code and plans must align with what's recorded there.** If a
suggestion would contradict an entry, surface the conflict — don't
silently re-litigate.

When a load-bearing decision is made in a session, append a new entry
to `docs/DECISIONS.md` using the format documented in its "How to use
this file" section. Newest on top. Don't edit history; supersede via
a new entry.

Skip the log for: variable renames driven by style, lint cleanup,
fixture tweaks, doc-only edits. Anything that affects architecture,
an LLM-facing surface, an eval baseline, the build plan, or workflow/agent
composition belongs in the log.

## Repo conventions

- Python: `from __future__ import annotations`; Pydantic v2 schemas; workflows/agents return result objects, not bare dicts.
- **Policy-engine-first**: deterministic policy gates + within-bucket scoring decide; the LLM does extraction / materiality only — never free-form ranking. ("Workflow" = stateless LLM call; "agent" = tool loop. Don't say "specialist".)
- LLM-facing surfaces (system prompts, tool names, JSON schema field names) are sealed against locked anchor-pair evals in `docs/evals/`. Touching them invalidates thresholds → don't do it without a documented re-run plan.
- Python-internal names should be human-readable English. Use Pydantic field aliases when the wire format must stay different (see the `RelevanceCall` pattern at `src/argos/schemas/specialists/document_reader.py`).
- Tests: `pytest -q` runs the full suite. Targeted: `pytest tests/services/info_map/`.

## What lives where

- Active development: `src/argos/`
- Locked specs: `docs/specs/`
- Eval thresholds (locked): `docs/evals/*-thresholds.md`
- Eval procedures: `docs/evals/*-procedure.md`
- Run logs: `docs/evals/<eval>-runs/`
- Fixtures + synthetic data: `src/argos/ontology/`, `data/`

## Hard rules

- **Never** rename or re-version an LLM-facing surface without a documented eval re-run.
- **Never** edit a `status/locked` doc's frontmatter without explicit user confirmation.
- **Never** add new top-level directories at the repo root.
- **Never** commit credentials. `.env` is gitignored.
