"""AgentAction emission bridge.

Mirrors local `audit_log.py` AgentAction rows into the Foundry
ontology via the `emit-agent-action` Action Type. The local
append-only JSONL log remains the canonical, discovery-survivable
record; this bridge produces a queryable Foundry-side projection for
cross-claim SQL (calibration eval, audit dashboards).

Local AgentAction (7 fields) is intentionally simpler than the
Foundry Object Type (16 fields). The bridge maps what's available and
fills the rest with documented defaults. When the workflow runner
starts emitting richer provenance (input hashes, snapshots,
EvidenceCitations), the bridge call signature already accepts those
fields — only the orchestrator's call site changes.

Known limitation: the current Foundry-side rule is declarative and
only materializes the `AgentAction` object. The parallel citation
arrays are accepted by the parameter signature and ignored at
execution time. Foundry-side `EvidenceCitation` materialization
waits on a function-backed upgrade — see
`docs/architecture/foundry-bridge-pattern.md` § "Deferred:
function-backed emit-agent-action". For now, citations stay
first-class in the local JSONL.
"""
from __future__ import annotations

import logging
from datetime import datetime

from argos.ontology.types import AgentAction
from argos.services.foundry.client import (
    bridge_is_enabled,
    get_foundry_client,
    raise_if_action_invalid,
)

logger = logging.getLogger(__name__)


# Map local `action_type` literal → Foundry `status` enum value.
# Local action_type expresses *what kind of row this is*; Foundry status
# expresses *what happened to it in the approval/validation lifecycle*.
# System-emitted rows are treated as auto-applied; validator_fail is the
# only one that maps to a schema-violation status.
_ACTION_TYPE_TO_STATUS: dict[str, str] = {
    "specialist_invoked": "auto_applied",
    "analysis_emitted": "auto_applied",
    "validator_pass": "auto_applied",
    "validator_fail": "schema_violation",
    "draft_created": "auto_applied",
    "ranker_update": "auto_applied",
}

# Default field values for Foundry params the local AgentAction
# doesn't carry. These are documented defaults, not magic numbers —
# when the workflow runner starts populating these for real, the
# bridge accepts richer input via the optional kwargs.
_DEFAULT_PROMPT_VERSION = "v0"
_DEFAULT_MODEL_ID = "claude-sonnet-4-6"
_DEFAULT_TRIGGERED_BY = "system"
_DEFAULT_ESCALATION_OUTCOME = "applied_automatically"


class AgentActionBridgeError(RuntimeError):
    """Re-wrapper for OSDK-level failures emitting AgentAction."""


def propagate_agent_action_to_foundry(
    action: AgentAction,
    *,
    prompt_version: str = _DEFAULT_PROMPT_VERSION,
    model_id: str = _DEFAULT_MODEL_ID,
    input_hash: str = "",
    input_snapshot_path: str = "",
    output_json: str | None = None,
    reasoning_trace: str = "",
    triggered_by: str = _DEFAULT_TRIGGERED_BY,
    escalation_outcome: str = _DEFAULT_ESCALATION_OUTCOME,
    request_id: str | None = None,
    approved_by_party_id: str | None = None,
    approved_at: datetime | None = None,
    # Citation arrays — accepted but Foundry-side ignored until the
    # function-backed upgrade lands. Pass empty for now; signature
    # stable across the upgrade.
    citation_ids: list[str] | None = None,
    document_ids: list[str | None] | None = None,
    sourced_rule_ids: list[str | None] | None = None,
    ledger_entry_ids: list[str | None] | None = None,
    locators: list[str] | None = None,
    text_excerpts: list[str] | None = None,
    citation_relations: list[str] | None = None,
    claim_texts: list[str] | None = None,
    probabilities: list[float | None] | None = None,
) -> str | None:
    """Emit one AgentAction row to Foundry via OSDK.

    Returns the Foundry `operation_id` RID on success, `None` when the
    bridge feature flag is off. Raises `AgentActionBridgeError` on OSDK
    failure or Foundry validation=INVALID.

    The caller owns the local-side write — this bridge is the
    Foundry-side mirror only. Caller should have already appended the
    same AgentAction to its local JSONL via
    `audit_log.py::append_agent_action`.
    """
    if not bridge_is_enabled():
        return None

    # Normalise citation arrays to a common length. Foundry's declarative
    # rule ignores them, but the parameter signature still requires
    # parallel-array-shaped input.
    n = len(citation_ids or [])

    citation_ids = citation_ids or []
    document_ids = document_ids if document_ids is not None else [None] * n
    sourced_rule_ids = sourced_rule_ids if sourced_rule_ids is not None else [None] * n
    ledger_entry_ids = ledger_entry_ids if ledger_entry_ids is not None else [None] * n
    locators = locators if locators is not None else [""] * n
    text_excerpts = text_excerpts if text_excerpts is not None else [""] * n
    citation_relations = citation_relations if citation_relations is not None else [""] * n
    claim_texts = claim_texts if claim_texts is not None else [""] * n
    probabilities = probabilities if probabilities is not None else [None] * n

    status = _ACTION_TYPE_TO_STATUS.get(action.action_type, "auto_applied")

    # Default output_json to the action's summary if not provided.
    # Foundry-side `output_json` is the validated specialist payload;
    # for system-emitted ledger rows we serialise the summary text.
    _output_json = output_json if output_json is not None else action.summary

    # Foundry OSDK uses an Empty.value sentinel for "not set" on nullable
    # params. Passing None explicitly overrides the sentinel with a wire
    # null, which Foundry rejects as NonNullablePropertyContainsNull.
    # Build kwargs dict, omitting nullable fields when None.
    optional_kwargs: dict = {}
    if request_id is not None:
        optional_kwargs["request_id"] = request_id
    if approved_by_party_id is not None:
        optional_kwargs["approved_by_party_id"] = approved_by_party_id
    if approved_at is not None:
        optional_kwargs["approved_at"] = approved_at
    if citation_ids:
        optional_kwargs["citation_ids"] = citation_ids
        optional_kwargs["document_ids"] = [d or "" for d in document_ids]
        optional_kwargs["sourced_rule_ids"] = [r or "" for r in sourced_rule_ids]
        optional_kwargs["ledger_entry_ids"] = [le or "" for le in ledger_entry_ids]
        optional_kwargs["locators"] = locators
        optional_kwargs["text_excerpts"] = text_excerpts
        optional_kwargs["citation_relations"] = citation_relations
        optional_kwargs["claim_texts"] = claim_texts
        optional_kwargs["probabilities"] = [p if p is not None else 0.0 for p in probabilities]

    client = get_foundry_client()
    try:
        result = client.ontology.actions.emit_agent_action(
            agent_action_id=action.action_id,
            specialist=action.workflow,
            claim=action.claim_id,
            prompt_version=prompt_version,
            model_id=model_id,
            input_hash=input_hash,
            input_snapshot_path=input_snapshot_path,
            output_json=_output_json,
            reasoning_trace=reasoning_trace,
            triggered_by=triggered_by,
            triggered_at=action.timestamp,
            status=status,
            escalation_outcome=escalation_outcome,
            **optional_kwargs,
        )
    except Exception as e:
        raise AgentActionBridgeError(
            f"Foundry emit_agent_action failed for "
            f"action_id={action.action_id!r} claim_id={action.claim_id!r}: {e}"
        ) from e

    raise_if_action_invalid(
        result, AgentActionBridgeError, "emit_agent_action",
        action_id=action.action_id, claim_id=action.claim_id,
    )
    operation_id = getattr(result, "operation_id", None)
    logger.info(
        "agent_action emitted to Foundry: action_id=%s claim_id=%s "
        "specialist=%s status=%s operation_id=%s",
        action.action_id,
        action.claim_id,
        action.workflow,
        status,
        operation_id,
    )
    return operation_id


__all__ = [
    "AgentActionBridgeError",
    "propagate_agent_action_to_foundry",
]
