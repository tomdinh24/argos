"""Foundry vertical-slice smoke test.

Proves the Dataset -> Object Type -> Action Type -> OSDK round-trip by:
  1. Reading <claim>'s current coverage_posture via OSDK
  2. Invoking apply_coverage_decision(<claim>, <new posture>) via OSDK
  3. Re-reading <claim> and asserting the property flipped

If this passes, the write leg is proven via the channel Argos's production
code on Railway will use. Replaces the broken Foundry Preview-panel path.

Auth: UserTokenAuth via FOUNDRY_TOKEN env var (Developer Console bearer).
Bearer tokens expire (~14d for Developer-Console-issued tokens); rotate
by regenerating in Developer Console -> Tokens. The Developer Tier blocks
the client_credentials grant (Application permissions are greyed out in
Developer Console), so ConfidentialClientAuth is NOT available without a
tier upgrade. When the tier is bumped, swap UserTokenAuth here for
ConfidentialClientAuth(client_id, client_secret) using FOUNDRY_CLIENT_ID
/ FOUNDRY_CLIENT_SECRET (already in .env).

Usage:
    uv run python scripts/foundry_smoke_test.py
    uv run python scripts/foundry_smoke_test.py --posture denied
    uv run python scripts/foundry_smoke_test.py --claim CLM-007 --posture accepted
"""
from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv

from argos_live_sdk import FoundryClient, UserTokenAuth


VALID_POSTURES = ("under_investigation", "ROR_issued", "denied", "accepted")


def main() -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--claim", default="CLM-001", help="Claim ID to mutate")
    parser.add_argument(
        "--posture",
        default="ROR_issued",
        choices=VALID_POSTURES,
        help="New coverage_posture value",
    )
    args = parser.parse_args()

    hostname = os.environ["FOUNDRY_HOSTNAME"]
    token = os.environ.get("FOUNDRY_TOKEN")
    if not token:
        print(
            "ERROR: FOUNDRY_TOKEN not set. Export it in your shell or add to .env.",
            file=sys.stderr,
        )
        return 2

    client = FoundryClient(auth=UserTokenAuth(token=token), hostname=hostname)

    print(f"READ  {args.claim} (before)...")
    before = client.ontology.objects.ClaimsV1.get(args.claim)
    print(f"  coverage_posture = {before.coverage_posture!r}")

    print(f"INVOKE apply_coverage_decision({args.claim}, {args.posture!r})...")
    result = client.ontology.actions.apply_coverage_decision(
        claims_v1=args.claim,
        new_parameter=args.posture,
    )
    print(f"  result = {result!r}")

    print(f"READ  {args.claim} (after)...")
    after = client.ontology.objects.ClaimsV1.get(args.claim)
    print(f"  coverage_posture = {after.coverage_posture!r}")

    if after.coverage_posture == args.posture:
        print(f"\nSLICE CLOSED: {args.claim}.coverage_posture is now {args.posture!r}.")
        return 0

    print(
        f"\nWRITE DID NOT LAND. Expected {args.posture!r}, got {after.coverage_posture!r}.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
