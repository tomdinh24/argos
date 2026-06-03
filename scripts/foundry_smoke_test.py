"""Foundry vertical-slice smoke test.

Proves the Dataset -> Object Type -> Action Type -> OSDK round-trip by:
  1. Reading CLM-001's current coverage_posture via OSDK
  2. Invoking apply_coverage_decision(CLM-001, ROR_issued) via OSDK
  3. Re-reading CLM-001 and asserting the property flipped

If this passes, the write leg is proven via the channel Argos's production
code on Railway will use. Replaces the broken Foundry Preview-panel path.

Usage:
    export FOUNDRY_TOKEN=...   # user bearer token from Developer Console
    /Users/tomlam/miniconda3/bin/python scripts/foundry_smoke_test.py

Cleanup TODO (post-slice):
    Re-install argos_osdk_sdk into argos/.venv (it currently lives in
    miniconda base because Tom's pip install targeted the wrong env).
"""
from __future__ import annotations

import os
import sys

from argos_osdk_sdk import FoundryClient, UserTokenAuth

HOSTNAME = "argos.usw-17.palantirfoundry.com"
TARGET_CLAIM = "CLM-001"
NEW_POSTURE = "ROR_issued"


def main() -> int:
    token = os.environ.get("FOUNDRY_TOKEN")
    if not token:
        print("ERROR: FOUNDRY_TOKEN not set in environment.", file=sys.stderr)
        return 2

    client = FoundryClient(auth=UserTokenAuth(token=token), hostname=HOSTNAME)

    print(f"READ  {TARGET_CLAIM} (before)...")
    before = client.ontology.objects.ClaimsV1.get(TARGET_CLAIM)
    print(f"  coverage_posture = {before.coverage_posture!r}")

    print(f"INVOKE apply_coverage_decision({TARGET_CLAIM}, {NEW_POSTURE!r})...")
    result = client.ontology.actions.apply_coverage_decision(
        claims_v1=TARGET_CLAIM,
        new_parameter=NEW_POSTURE,
    )
    print(f"  result = {result!r}")

    print(f"READ  {TARGET_CLAIM} (after)...")
    after = client.ontology.objects.ClaimsV1.get(TARGET_CLAIM)
    print(f"  coverage_posture = {after.coverage_posture!r}")

    if after.coverage_posture == NEW_POSTURE:
        print(f"\nSLICE CLOSED: {TARGET_CLAIM}.coverage_posture flipped to {NEW_POSTURE}.")
        return 0

    print(
        f"\nWRITE DID NOT LAND. Expected {NEW_POSTURE!r}, got {after.coverage_posture!r}.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
