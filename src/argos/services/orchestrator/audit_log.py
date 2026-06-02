"""AgentAction audit log — append-only JSONL per claim.

Every workflow run (Coverage / Liability / Reserve / Recovery / Closure /
Brief) and every extractor retry appends a typed `AgentAction` row.
The log is:

  - **Append-only** — rows never mutate. A correction = new row.
  - **Per-claim** — one JSONL file per claim_id under `log_root/`.
  - **Boecher/Ruiz-discoverable** — the trail of "what the AI agents
    did, when, and whether it succeeded" must survive discovery in a
    bad-faith case. This module IS that trail.

This addresses the Closure workflow's Tier-D gate
`agent_action_ledger_incomplete`: once a claim has rows, Closure can
treat the ledger as complete and promote the gate from a warning to
a blocker (D1 in the closure gate registry).

Cross-workflow lineage: a single claim_id ties together every
`analysis_emitted` row, so the Brief assembler (and the cockpit) can
render "what specialists touched this claim, in what order, with what
result" without re-deriving from the workflow-results JSON.

The store is intentionally dumb: filesystem JSONL. Promotion to a
typed Caseload field or a Postgres table is §0.2 item #7
(`pending_recommendations` collection) — orthogonal to this log.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from argos.ontology.types import AgentAction


# Action-type literals — kept aligned with AgentAction.action_type.
ANALYSIS_EMITTED = "analysis_emitted"
VALIDATOR_PASS = "validator_pass"
VALIDATOR_FAIL = "validator_fail"
SPECIALIST_INVOKED = "specialist_invoked"


def _log_path(log_root: Path, claim_id: str) -> Path:
    """One JSONL file per claim, parented under log_root."""
    return log_root / f"{claim_id}.jsonl"


def append_agent_action(
    action: AgentAction,
    *,
    log_root: Path,
) -> Path:
    """Append one AgentAction row to the per-claim JSONL log.

    Creates `log_root` if missing. Returns the log-file path written
    to. Append-only — never reads or rewrites existing rows.
    """
    log_root.mkdir(parents=True, exist_ok=True)
    path = _log_path(log_root, action.claim_id)
    line = action.model_dump_json()
    with path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    return path


def load_agent_actions(
    claim_id: str,
    *,
    log_root: Path,
) -> list[AgentAction]:
    """Load all AgentAction rows for one claim, in append order.

    Returns an empty list when no log file exists. Silently skips
    malformed lines (the trail is operational; one bad row should
    not block reading the rest).
    """
    path = _log_path(log_root, claim_id)
    if not path.exists():
        return []
    rows: list[AgentAction] = []
    with path.open("r", encoding="utf-8") as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            try:
                rows.append(AgentAction.model_validate_json(raw))
            except (ValueError, json.JSONDecodeError):
                continue
    return rows


def count_workflow_actions(
    claim_id: str,
    workflow: str,
    *,
    log_root: Path,
    action_type: str | None = None,
) -> int:
    """How many AgentAction rows match (claim_id, workflow [, action_type])?

    Used by Closure's policy engine to decide whether the per-claim
    ledger is "complete" for the upstream workflows it consumed.
    """
    return sum(
        1
        for a in load_agent_actions(claim_id, log_root=log_root)
        if a.workflow == workflow
        and (action_type is None or a.action_type == action_type)
    )


def has_workflow_evidence(
    claim_id: str,
    workflows: list[str],
    *,
    log_root: Path,
) -> bool:
    """True iff EVERY workflow in `workflows` has at least one
    `analysis_emitted` row for this claim.

    Closure's D1 gate calls this against its upstream set
    (coverage/liability/reserve/recovery) to decide whether the ledger
    is complete enough to promote from warning → blocker.
    """
    rows = load_agent_actions(claim_id, log_root=log_root)
    seen = {
        a.workflow for a in rows if a.action_type == ANALYSIS_EMITTED
    }
    return all(w in seen for w in workflows)


def build_agent_action(
    *,
    claim_id: str,
    workflow: str,
    action_type: str,
    summary: str,
    success: bool = True,
    timestamp: datetime | None = None,
    action_id: str | None = None,
) -> AgentAction:
    """Construct an AgentAction with sensible defaults.

    `action_id` defaults to a uuid4 hex; `timestamp` defaults to now
    in UTC. Callers (the runner + writebacks) use this helper so the
    audit-log call sites stay one line.
    """
    return AgentAction(
        action_id=action_id or uuid.uuid4().hex,
        claim_id=claim_id,
        timestamp=timestamp or datetime.now(timezone.utc),
        workflow=workflow,
        action_type=action_type,  # type: ignore[arg-type]
        summary=summary,
        success=success,
    )


__all__ = [
    "ANALYSIS_EMITTED",
    "SPECIALIST_INVOKED",
    "VALIDATOR_FAIL",
    "VALIDATOR_PASS",
    "append_agent_action",
    "build_agent_action",
    "count_workflow_actions",
    "has_workflow_evidence",
    "load_agent_actions",
]
