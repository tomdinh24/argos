---
tags:
  - project/argos
  - type/architecture
  - status/living
created: 2026-06-02
updated: 2026-06-04
---

# Foundry bridge pattern

Argos's writeback layer (`services/orchestrator/*_actions.py`) mutates
Pydantic state in-process. To mirror those mutations into the Foundry
ontology, each workflow has a **bridge module** under
`services/foundry/<workflow>_bridge.py` that wraps the OSDK call.

This doc is the contract every workflow bridge follows. **Read this
before adding a Reserve / Liability / Recovery / Closure bridge.**
The Coverage bridge ([`coverage_bridge.py`](../../src/argos/services/foundry/coverage_bridge.py))
is the canonical reference implementation.

## Why a bridge layer (and not "call OSDK from the action directly")

1. **Argos's analytical workflows must run without OSDK installed.**
   The OSDK (`argos_osdk_sdk`) is a private Foundry-pypi package; CI
   without secrets and contributor laptops without Foundry access
   won't have it. The bridge lazy-imports OSDK; the analytical
   workflows never touch the bridge.
2. **One place to swap auth when the tier bumps.** Today: `UserTokenAuth`
   (14-day expiry). After tier-bump: `ConfidentialClientAuth`
   (auto-refresh). One-line diff in [`client.py`](../../src/argos/services/foundry/client.py).
3. **One place to handle the broad OSDK exception family.** OSDK raises
   `UnauthorizedError`, `BadRequestError`, `ValidationFailed`, network
   errors. Bridges re-wrap into a single `<Workflow>BridgeError` so
   callers have one type to catch.
4. **Feature-flag the whole layer.** `ARGOS_FOUNDRY_BRIDGE_ENABLED=1`
   to actually propagate. Default off so unit tests, contributors,
   and CI stay hermetic.

## Contract every bridge must implement

```python
# services/foundry/<workflow>_bridge.py

from argos.services.foundry.client import (
    bridge_is_enabled,
    get_foundry_client,
    raise_if_action_invalid,
)

class <Workflow>BridgeError(RuntimeError):
    """Re-wrapper for OSDK-level failures."""

def propagate_<workflow>_decision_to_foundry(
    claim_id: str,
    *,  # named-only for everything else — keep callsites readable
    <decision_args>,
) -> str | None:
    if not bridge_is_enabled():
        return None
    client = get_foundry_client()
    try:
        result = client.ontology.actions.<foundry_action_name>(
            claim=claim_id,
            <foundry_param_mapping>,
        )
    except Exception as e:
        raise <Workflow>BridgeError(
            f"Foundry <foundry_action_name> failed for claim_id={claim_id!r}: {e}"
        ) from e
    # MANDATORY: HTTP 200 + validation=INVALID happens (e.g. unknown enum
    # value); without this check the bridge silently returns None and the
    # caller can't tell "flag off" from "Foundry rejected the write."
    raise_if_action_invalid(
        result, <Workflow>BridgeError, "<foundry_action_name>",
        claim_id=claim_id, <param_diagnostics>,
    )
    return getattr(result, "operation_id", None)
```

**Return value semantics:**

| Return | Meaning |
|---|---|
| `None` | Bridge skipped by design (flag off). Caller treats as "Pydantic-side committed, Foundry-side intentionally not attempted." |
| `str` (RID) | Foundry write committed. RID is suitable for `AgentAction.foundry_operation_id` audit field. |
| `<Workflow>BridgeError` raised | Pydantic-side already committed, Foundry-side failed. Caller's choice: retry, queue, or surface to operator. **Do not roll back the Pydantic mutation.** |

## Contract every caller must implement

In `services/orchestrator/<workflow>_actions.py`:

```python
new_caseload = caseload.model_copy(...)  # Pydantic-side commit FIRST

try:
    operation_id = propagate_<workflow>_decision_to_foundry(...)
    if operation_id is not None:
        logger.info("propagated to Foundry: operation_id=%s ...", operation_id)
except <Workflow>BridgeError as e:
    logger.error("Foundry propagation failed: %s", e)
except Exception as e:
    logger.exception("unexpected bridge error: %s", e)

return new_caseload
```

**Rules:**

- **Pydantic-side commit comes FIRST.** Foundry is the secondary
  substrate; the in-process Caseload is what every downstream Argos
  consumer (Drafter, Reader, dispatcher) reads. A bridge failure does
  not invalidate the Pydantic write.
- **Errors are logged, not raised.** The caller never crashes on
  Foundry failure. The in-process state stayed coherent; recovery is a
  separate concern.
- **`source_recommendation_id` (or equivalent) goes into the log
  message.** When AgentAction projection lands in Foundry, the Foundry
  operation_id + Argos recommendation_id pair lets us reconstruct the
  full audit trail.

## Why errors are logged, not raised

An adjuster commits a Coverage decision. The Pydantic substrate flips
to `ROR_issued`; the Drafter immediately starts generating an ROR
letter. The Foundry bridge call fails (token expired). Options:

- **Raise.** The orchestrator sees the exception, rolls back, the
  adjuster's commit reverts. **Bad** — the Drafter already started
  drafting, the user sees a flapping state.
- **Log and continue.** The Pydantic substrate is correct, the
  Drafter does its job, a sweep later reconciles Foundry. **Good** —
  the in-process state stays coherent; the Foundry divergence is
  recoverable.

The cost of raising is a worse user-facing experience. The cost of
logging is a known divergence window that a reconciliation job clears.
We pick the latter.

## What goes in the bridge, what doesn't

### Goes in the bridge

- The OSDK call (`client.ontology.actions.<name>(...)`).
- The parameter-name translation (snake_case Argos → kebab/camel
  Foundry). Example: `new_posture: "ROR_issued"` →
  `new_parameter: "ROR_issued"` because Foundry's wizard left the
  parameter named `new_parameter`.
- Error re-wrapping (`<Workflow>BridgeError`).
- The feature-flag check (delegated to `bridge_is_enabled()`).

### Does NOT go in the bridge

- **Transition validation.** Argos's action enforces "no
  `ROR_issued` → `under_investigation`". Foundry's Action Type does
  not duplicate this check. By the time the bridge is called, Argos
  has already validated. (Foundry's Action Type validator IS allowed
  to reject — e.g., for unrecognized posture values — and the bridge
  surfaces that as `<Workflow>BridgeError`.)
- **Read-back verification.** The smoke test ([`scripts/foundry_smoke_test.py`](../../scripts/foundry_smoke_test.py))
  does that. Production bridges are invocation-only; verification is a
  separate concern handled by reconciliation sweeps.
- **AgentAction emission to Foundry.** Until `AgentAction` exists as a
  Foundry Object Type (TODO), audit rows stay in Argos's local
  [`audit_log.py`](../../src/argos/services/orchestrator/audit_log.py)
  substrate. When `AgentAction` lands in Foundry, extend the bridge
  with a paired emission per [`data-layer.md §6`](../data-layer.md).

## Status table — bridges built vs to-build

| Workflow | Bridge module | Foundry Action Type | Status |
|---|---|---|---|
| Coverage | [`coverage_bridge.py`](../../src/argos/services/foundry/coverage_bridge.py) | `apply-coverage-decision-v2` | live-verified 2026-06-04 |
| Reserve | [`reserve_bridge.py`](../../src/argos/services/foundry/reserve_bridge.py) | `apply-reserve-decision` | live-verified 2026-06-04 |
| Liability | [`liability_bridge.py`](../../src/argos/services/foundry/liability_bridge.py) | `apply-liability-decision` | live-verified 2026-06-04 |
| Recovery | [`recovery_bridge.py`](../../src/argos/services/foundry/recovery_bridge.py) | `apply-recovery-decision` | live-verified 2026-06-04 |
| Closure | [`closure_bridge.py`](../../src/argos/services/foundry/closure_bridge.py) | `apply-closure-decision`, `apply-reopen-decision` | live-verified 2026-06-04 |
| AgentAction emission | [`agent_action_bridge.py`](../../src/argos/services/foundry/agent_action_bridge.py) | `emit-agent-action` | shipped 2026-06-04 — wired into [`audit_log.py::append_agent_action`](../../src/argos/services/orchestrator/audit_log.py); integration test pending OSDK regen to v0.2.0 |

## Deferred: function-backed `emit-agent-action` for atomic citation materialization

The shipped `emit-agent-action` Action Type uses Foundry's declarative
rule, which materializes the `AgentAction` object but **ignores the
parallel citation arrays** (Foundry's declarative rules can't iterate
arrays to create N child objects). The bridge call signature already
accepts citation parameters, so the OSDK invocation doesn't change
when the rule upgrades — only the Foundry-side execution does.

Local `EvidenceCitation` rows remain first-class in
[`audit_log.py`](../../src/argos/services/orchestrator/audit_log.py)
JSONL. This satisfies the discovery-survivable record and the
cockpit's "show me the receipts" pane. Cross-claim SQL on citations
("across all AgentActions claiming P=80%, what fraction resolved?")
is what the upgrade unlocks — not yet load-bearing.

When calibration eval becomes real work, run a fresh AI FDE session
with the prompt: "Take the TypeScript source below, create a Foundry
TypeScript Functions repo, publish v0.1.0, swap `emit-agent-action`'s
rule from declarative to ontologyEditFunction referencing the
published function." Pre-baked source (drafted by AI FDE in the
2026-06-04 session, ready to paste):

```typescript
import { OntologyEditFunction, Edits } from "@foundry/functions-api";
import { Objects } from "@foundry/ontology-api";

export class EmitAgentActionFunction {
  @OntologyEditFunction()
  public emitAgentAction(
    // AgentAction fields
    agentActionId: string,
    specialist: string,
    claim: Objects.Claim,
    promptVersion: string,
    modelId: string,
    inputHash: string,
    inputSnapshotPath: string,
    outputJson: string,
    reasoningTrace: string,
    triggeredBy: string,
    triggeredAt: Timestamp,
    status: string,
    escalationOutcome: string,
    requestId: string | undefined,
    approvedByPartyId: string | undefined,
    approvedAt: Timestamp | undefined,
    // Citation parallel arrays
    citationIds: string[],
    documentIds: string[],
    sourcedRuleIds: string[],
    ledgerEntryIds: string[],
    locators: string[],
    textExcerpts: string[],
    citationRelations: string[],
    claimTexts: string[],
    probabilities: number[],
  ): void {
    const n = citationIds.length;
    const arrays = [documentIds, sourcedRuleIds, ledgerEntryIds, locators, textExcerpts, citationRelations, claimTexts, probabilities];
    for (const arr of arrays) {
      if (arr.length !== n) {
        throw new Error(`All citation arrays must be same length. Expected ${n}, got ${arr.length}`);
      }
    }

    const agentAction = Objects.create().agentAction(agentActionId);
    agentAction.specialist = specialist;
    agentAction.claimId = claim.claimId;
    agentAction.promptVersion = promptVersion;
    agentAction.modelId = modelId;
    agentAction.inputHash = inputHash;
    agentAction.inputSnapshotPath = inputSnapshotPath;
    agentAction.outputJson = outputJson;
    agentAction.reasoningTrace = reasoningTrace;
    agentAction.triggeredBy = triggeredBy;
    agentAction.triggeredAt = triggeredAt;
    agentAction.status = status;
    agentAction.escalationOutcome = escalationOutcome;
    agentAction.approvedByPartyId = approvedByPartyId;
    agentAction.approvedAt = approvedAt;

    for (let i = 0; i < n; i++) {
      const hasDoc = documentIds[i] !== "";
      const hasRule = sourcedRuleIds[i] !== "";
      const hasLedger = ledgerEntryIds[i] !== "";
      const setCount = [hasDoc, hasRule, hasLedger].filter(Boolean).length;

      if (setCount !== 1) {
        throw new Error(
          `Citation row ${i}: exactly one of (document_id, sourced_rule_id, ledger_entry_id) must be set. Got ${setCount}.`
        );
      }

      const citation = Objects.create().evidenceCitation(citationIds[i]);
      citation.agentActionId = agentActionId;
      citation.documentId = hasDoc ? documentIds[i] : undefined;
      citation.sourcedRuleId = hasRule ? sourcedRuleIds[i] : undefined;
      citation.ledgerEntryId = hasLedger ? ledgerEntryIds[i] : undefined;
      citation.locator = locators[i];
      citation.textExcerpt = textExcerpts[i];
      citation.citationRelation = citationRelations[i];
      citation.claimText = claimTexts[i];
      citation.probability = probabilities[i] !== 0 ? probabilities[i] : undefined;
    }
  }
}
```
| AgentAction emission | TODO | TODO (`emit-agent-action`) | unblocked 2026-06-03 — `AgentAction` + `EvidenceCitation` Object Types exist in main ontology (poc-1 merged); needs an action-type definition + bridge module |

## How to add a new bridge

1. **Confirm the Foundry Action Type exists.** Same setup as the
   ClaimsV1 / apply-coverage-decision slice from 2026-06-02. If it
   doesn't, that's UI-clicks work (Ontology Manager wizard).
2. **Regenerate the OSDK.** Developer Console → re-generate, capture
   the new install command, re-run install command (both miniconda
   for scripts AND `.venv/bin/pip install` for the repo).
3. **Write the bridge module.** Copy `coverage_bridge.py`, rename
   types, rename action name, adjust parameter mapping.
4. **Wire the caller.** Same try/except in `services/orchestrator/<workflow>_actions.py`.
5. **Test stack.** Unit tests (flag-off no-op, flag-on env-missing
   raise) + integration test (gated by `foundry_integration` marker
   + `FOUNDRY_TOKEN` skipif).
6. **Update this doc's status table + SYSTEM_ARCHITECTURE.md §0.1.**

Total cost per bridge after this one: ~30 lines of bridge code + ~50
lines of test, given the harness already exists. The expensive part
(harness, client builder, doc) is one-time.
