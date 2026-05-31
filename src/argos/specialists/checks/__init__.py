"""Post-runtime checks the schema can't enforce on its own.

The Pydantic contract in `argos.schemas.contract` catches structural violations
(probabilities outside [0,1], synthesis outcomes that don't sum to 1.0, missing
citations). It does not catch:

- citation hallucination — citation points at a real document but the
  `text_excerpt` does not appear in that document's body.
- recommendation-creep — schema enforces no `recommended_*` field, but the
  drafted memo/letter prose can still contain recommendation language.
- premise inventiveness — model invents facts in `reasoning` that aren't in
  any document.

These checks run after the specialist returns a schema-valid result, and
either pass or fail the eval independently of the structural contract.
"""

from argos.specialists.checks.citation_verifier import (
    CitationVerifierResult,
    verify_citations,
)
from argos.specialists.checks.recommendation_regex import (
    RecommendationRegexResult,
    check_recommendation_prose,
)
from argos.specialists.checks.premise_grounding import (
    PremiseGroundingResult,
    check_premise_grounding,
)


__all__ = [
    "CitationVerifierResult",
    "PremiseGroundingResult",
    "RecommendationRegexResult",
    "check_premise_grounding",
    "check_recommendation_prose",
    "verify_citations",
]
