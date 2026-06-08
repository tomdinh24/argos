# Deploying the Argos backend to Railway

The FastAPI backend (`argos.api.app:app`) hosts the cockpit's live data + decision
API. The Vercel-hosted cockpit (`https://project-argos.vercel.app`) talks to it over
HTTPS. This is the runbook for the hosted half of the "live end-to-end" path
(Phase 5 of the cockpit-live plan; see `docs/DECISIONS.md` 2026-06-07).

## Live deployment

- **Backend:** `https://argos-backend-production-0121.up.railway.app` (deployed
  2026-06-07; auth ON via `ARGOS_DEMO_TOKEN`, Foundry bridge OFF).
- **Railway project:** `argos-backend` (`b268fc55-eede-4099-b256-5a9a3fd8b567`).
- `ANTHROPIC_API_KEY` is **not yet set** on the host → the two pre-baked hero
  claims (CLM-001, CLM-004) render fully, but opening a *fresh* claim that needs a
  cold chain run will fail until the key is added.

## What's already wired (repo-side, no action needed)

- **`Dockerfile`** — the builder (set in `railway.json` as `DOCKERFILE`). Builds
  from `python:3.11-slim`, `pip install`s `requirements.txt`, copies `src/` + `data/`,
  runs uvicorn on `$PORT`. Replaced Nixpacks, whose build-time fetch of the NixOS
  package archive from GitHub failed intermittently with HTTP 504 (2026-06-08). The
  Docker base is Docker-Hub-cached, so builds are deterministic.
- **`railway.json`** — `DOCKERFILE` builder + a `/healthz` health check. Railway
  injects `$PORT`; the Dockerfile `CMD` owns the start command.
- **`requirements.txt`** — pinned dependency install (mirrors `pyproject.toml`). The
  `argos` package is importable via `PYTHONPATH=/app/src` (set in the Dockerfile),
  so no `pip install .` step is needed.
- **`.python-version`** → `3.11` (matches the local venv all evals/tests ran on).
- **`Procfile`** — aligned with the same start command (Heroku-style fallback).
- **CORS** already allows `https://project-argos.vercel.app`
  (`src/argos/api/app.py`). For any other domain, set `ARGOS_CORS_EXTRA`
  (comma-separated) rather than editing code.
- **Pre-run dossiers ship in the build.** `data/workflow-results/CLM-001` and
  `CLM-004` (full 5-stage results) are committed, so the two hero claims render
  rich dossiers immediately on a fresh deploy — no cold LLM run required.

## One-time setup

You're already logged in (`railway whoami` → Tom Lam). From the repo root
(`~/Projects/argos`):

```bash
railway init            # create a new project (or `railway link` to an existing one)
```

### Set environment variables (Railway → service → Variables)

| Variable | Value | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | *(your real key)* | **You set this** — I can't enter credentials. Needed only when a claim's chain is run on-host (the two heroes are pre-baked). |
| `ARGOS_DEMO_TOKEN` | *(a shared secret)* | Generate with `openssl rand -hex 24`. Gates the API; must match Vercel's `NEXT_PUBLIC_DEMO_TOKEN`. Without it the API is **open**. |
| `ARGOS_DATA_ROOT` | `data` | Default; lets the committed pre-run results load. |
| `ARGOS_CORS_EXTRA` | *(optional)* | Only if the cockpit serves from a domain other than `project-argos.vercel.app`. |
| `ARGOS_FOUNDRY_BRIDGE_ENABLED` | **leave UNSET** | Keep the Foundry write OFF until the OSDK is re-pinned to ontology `88f01e1f` (blocker logged 2026-06-07). The local audit trail still commits. |

`PORT` is injected by Railway — do not set it.

### Deploy

```bash
railway up              # uploads the working tree, builds via Nixpacks, deploys
railway domain          # generate / print the public HTTPS URL
```

Verify the backend:

```bash
curl https://<your-railway-domain>/healthz          # -> {"status":"ok"}
curl -H "Authorization: Bearer $ARGOS_DEMO_TOKEN" \
     https://<your-railway-domain>/api/claims | head # -> the caseload JSON
curl -s https://<your-railway-domain>/api/claims     # -> 401 (auth enforced)
```

## Point the Vercel cockpit at it

In the Vercel project (Settings → Environment Variables), set for Production:

| Variable | Value |
|---|---|
| `NEXT_PUBLIC_API_BASE` | `https://<your-railway-domain>` |
| `NEXT_PUBLIC_DEMO_TOKEN` | *(the same `ARGOS_DEMO_TOKEN` secret)* |

Redeploy the cockpit. Then load `https://project-argos.vercel.app` → the caseload
and the CLM-001 / CLM-004 dossiers should render from Railway, not fixtures.

## Caveats

- **Ephemeral disk.** Railway's filesystem resets on every redeploy. The committed
  pre-run hero results survive (they're in the build image), but *new* decisions
  written at runtime (`data/agent-actions/*.jsonl`, freshly run chains) are lost on
  redeploy. For durable demo state, attach a Railway volume at `ARGOS_DATA_ROOT`.
- **Cold-claim latency.** Opening a non-hero claim triggers up to five sequential
  LLM workflow runs (~2 min each). Pre-run more claims locally and commit their
  `data/workflow-results/<id>/` dirs to make them instant on-host.
- **Foundry stays local-only** until the OSDK blocker is resolved. Hosted decisions
  append to the local JSONL audit log; they do **not** yet mirror to the ontology.
