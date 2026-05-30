"""Pydantic schemas for specialist outputs.

The primitives in `legally_bearing.py` enforce the contract described in
AGENT_ARCHITECTURE.md §3: every probabilistic claim emitted by a legally-bearing
specialist must carry at least one EvidenceCitation, and outcome-path
distributions must sum to 1.0.

The specialist output schemas in `specialists/` compose these primitives.
"""
from argos.schemas.legally_bearing import (
    EvidenceCitation,
    OutcomePathDistribution,
    ProbabilisticClaim,
)

__all__ = [
    "EvidenceCitation",
    "OutcomePathDistribution",
    "ProbabilisticClaim",
]
