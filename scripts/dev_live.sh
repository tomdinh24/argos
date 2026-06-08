#!/usr/bin/env bash
# Boot the cockpit LIVE end-to-end: FastAPI backend on :8071 + Next.js cockpit
# on :3007, wired together via web/.env.local (NEXT_PUBLIC_API_BASE).
#
# "Live" is otherwise an undocumented two-terminal ritual; this is the single
# command. Ctrl-C stops both.
#
# Foundry writes: set ARGOS_FOUNDRY_BRIDGE_ENABLED=1 before running to mirror
# decisions into the ontology — but note the OSDK must be regenerated/pinned to
# ontology 88f01e1f-… first (see docs/DECISIONS.md 2026-06-07), or every bridge
# returns ActionTypeNotFound (the local audit trail still commits regardless).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

cleanup() { echo "stopping…"; kill 0; }
trap cleanup EXIT INT TERM

echo "→ backend  http://localhost:8071  (FastAPI)"
ARGOS_DATA_ROOT="${ARGOS_DATA_ROOT:-data}" \
  uv run uvicorn argos.api.app:app --port 8071 --reload --log-level info &

echo "→ cockpit  http://localhost:3007  (Next.js)"
( cd web && npm run dev -- --port 3007 ) &

wait
