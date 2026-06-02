"""Closure workflow — deterministic core (policy engine + calculator + ledger + rationale).

Spec: docs/specs/closure-workflow.md.
"""
from argos.services.closure.closure_calculator import build_closure_assessment
from argos.services.closure.constants import (
    DEFAULT_PROGRAM,
    FL_CLOSURE_GATE_REGISTRY_V1,
    MANDATORY_ESCALATION_VARIANCE_FLAGS,
    TIER_FAILURE_PROBABILITY_CAP,
    VERSION,
)
from argos.services.closure.diligence_ledger import enrich_diligence_ledger
from argos.services.closure.policy_engine import apply_fl_closure_gates
from argos.services.closure.rationale import (
    finalize_assessment,
    render_ledger_rationale,
    render_rationale,
)


__all__ = [
    "VERSION",
    "DEFAULT_PROGRAM",
    "FL_CLOSURE_GATE_REGISTRY_V1",
    "MANDATORY_ESCALATION_VARIANCE_FLAGS",
    "TIER_FAILURE_PROBABILITY_CAP",
    "apply_fl_closure_gates",
    "build_closure_assessment",
    "enrich_diligence_ledger",
    "render_rationale",
    "render_ledger_rationale",
    "finalize_assessment",
]
