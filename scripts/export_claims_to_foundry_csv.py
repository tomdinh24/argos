"""One-shot export: synthetic Argos caseload → claims.csv for Foundry upload.

Path B (Pydantic-faithful): the CSV mirrors `argos.ontology.types.Claim`,
NOT the `foundry/ontology/object-types.yaml` Foundry-spec shape. This is
the transitional v1 shape used to prove the vertical slice
(Dataset → Object Type → Action Type → OSDK round-trip). The canonical
data-layer.md §5 shape is the second pass.

Usage:
    uv run python scripts/export_claims_to_foundry_csv.py

Output:
    data/foundry-uploads/claims_v1.csv  (20 rows, deterministic)
"""
from __future__ import annotations

import csv
from pathlib import Path

from argos.ontology.synthetic_caseload import build_caseload


OUT = Path("data/foundry-uploads/claims_v1.csv")

# Column order = Pydantic field order. Foundry will infer types from values;
# we'll re-type the literal-enum columns and the date column in Ontology
# Manager (they land as strings on first ingest).
COLUMNS = [
    "claim_id",
    "policy_period_id",
    "opened_date",
    "status",
    "severity_tier_summary",
    "litigation_flag",
    "rep_flag",
    "complaint_flag",
    "claimant_name",
    "insured_name",
    "coverage_posture",
    "reserve_decision_committed",
    "liability_apportionment_committed",
    "recovery_pursuit_decision_committed",
    "recovery_pursuit_decision",
]


def _bool(value: bool) -> str:
    # Explicit "true"/"false" so Foundry infers bool, not nullable string.
    return "true" if value else "false"


def _str_or_blank(value: str | None) -> str:
    return "" if value is None else value


def main() -> None:
    caseload = build_caseload()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(COLUMNS)
        for claim in caseload.claims:
            writer.writerow([
                claim.claim_id,
                claim.policy_period_id,
                claim.opened_date.isoformat(),
                claim.status,
                claim.severity_tier_summary,
                _bool(claim.litigation_flag),
                _bool(claim.rep_flag),
                _bool(claim.complaint_flag),
                _str_or_blank(claim.claimant_name),
                _str_or_blank(claim.insured_name),
                claim.coverage_posture,
                _bool(claim.reserve_decision_committed),
                _bool(claim.liability_apportionment_committed),
                _bool(claim.recovery_pursuit_decision_committed),
                claim.recovery_pursuit_decision,
            ])
    print(f"Wrote {len(caseload.claims)} claims → {OUT}")


if __name__ == "__main__":
    main()
