"""Pydantic schemas for specialist outputs.

The primitives in `contract.py` enforce the contract described in
AGENT_ARCHITECTURE.md §3: every Assessment emitted by a legally-bearing
specialist must carry at least one EvidenceCitation, and every Synthesis
must distribute probability mass that sums to 1.0 over mutually exclusive
outcomes.

The specialist output schemas in `specialists/` compose these primitives.
"""
from argos.schemas.contract import (
    Assessment,
    EvidenceCitation,
    Synthesis,
)

__all__ = [
    "Assessment",
    "EvidenceCitation",
    "Synthesis",
]
