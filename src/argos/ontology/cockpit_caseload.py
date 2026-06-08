"""Cockpit demo caseload — eval-safe enrichment of the triage fixture.

The cockpit FastAPI surface needs a caseload that *looks* like a real
adjuster's desk: named insureds, varied loss types, and claims whose
documents carry real body text so the live workflows cite real
document_ids (and the cockpit's document viewer can highlight the cited
passage in context).

We do NOT mutate `synthetic_caseload.build_caseload()` or
`caseload_with_realistic_docs.py` — both are pinned by locked evals
(triage-ranker, triage-policy-engine-with-reader, brief). Instead this
module *wraps* `build_caseload()` and returns an enriched copy used only
by the cockpit (`api/app.py`). The cockpit triages by severity band, not
the locked ranker, so enrichment here cannot shift any eval baseline.

Determinism is preserved: same `as_of` in → identical caseload out. No
randomness, no wall-clock reads.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from argos.ontology.synthetic_caseload import DEFAULT_AS_OF, build_caseload
from argos.ontology.types import Caseload, Claim, CoverageRequest, Document


# --- display enrichment -----------------------------------------------------

# Named insureds, indexed by 1-based claim number. Commercial auto / property
# carriers skew to business names; a few personal-lines names for variety.
_INSURED_NAMES = [
    "Northbridge Logistics",       # 001
    "Sierra Cement Co.",           # 002
    "Atlas Freight Lines",         # 003
    "Calloway Construction",       # 004
    "Harbor Point Properties",     # 005
    "Meridian Foods Distribution", # 006
    "Vanguard Haulage",            # 007
    "Cedar Ridge Apartments LLC",  # 008
    "Pinnacle Steel Works",        # 009
    "Riverside Transit Group",     # 010
    "Goldman Produce",             # 011
    "Keystone Mechanical",         # 012
    "Lakeshore Retail Partners",   # 013
    "Sunbelt Couriers",            # 014
    "Ironclad Security Services",  # 015
    "Brightway Logistics",         # 016
    "Coastal Pipe & Supply",       # 017
    "Summit Fleet Services",       # 018
    "Delgado Trucking",            # 019
    "Foster & Lane Holdings",      # 020
]

_CLAIMANT_NAMES = [
    "Marcus Webb", "Elena Ramos", "David Okafor", "Priya Nair",
    "Thomas Reilly", "Grace Lin", "Andre Dubois", "Sofia Marini",
    "James Holloway", "Aisha Khan", "Victor Cruz", "Rachel Stein",
    "Daniel Park", "Olivia Bennett", "Samuel Adeyemi", "Nina Castellano",
    "Owen Fletcher", "Leah Goldberg", "Carlos Mendez", "Hannah Whitfield",
]

# Loss-type variety. The triage fixture is almost all auto-BI; spread a few PD
# and property claims across the non-hero rows so the caseload reads like a real
# book. Hero claims (rich injury docs) stay auto-BI so the medical narrative
# holds. Keyed by 1-based claim index; default keeps the fixture's coverage_id.
_COVERAGE_BI = "CP-AUTO-BI-STANDARD"
_COVERAGE_PD = "CP-AUTO-PD-STANDARD"
_COVERAGE_PROP = "CP-PROP-BUILDING"
_COVERAGE_OVERRIDE = {
    2: _COVERAGE_PROP,   # Sierra Cement — property
    3: _COVERAGE_PD,     # Atlas Freight — auto PD
    5: _COVERAGE_PROP,   # Harbor Point — property
    6: _COVERAGE_PD,     # Meridian Foods — auto PD
    11: _COVERAGE_PD,    # Goldman Produce — auto PD
    13: _COVERAGE_PROP,  # Lakeshore Retail — property
    17: _COVERAGE_PROP,  # Coastal Pipe — property
}

# Claims that get the full injury-claim document bundle (the demo heroes the
# presenter opens). All serious/catastrophic auto-BI so the documents cohere
# (idx 1 sla-1h, 4 stat-3d, 7 hi-cat, 8 hi-serious-1 — all auto-BI in the
# fixture; CLM-009 is property, deliberately excluded).
#
# Two scenarios so the demo shows both shapes the policy engine can reach:
#   - "barred": the claimant rear-ended the insured → claimant >50% at fault →
#     reserve $0, recovery abstain (CLM-001 etc.).
#   - "payable": the insured was at fault → claimant has a clean BI claim →
#     reserve models real indemnity, closure ready with payment (CLM-004).
_HERO_CLAIMS = {1, 4, 7, 8}
_PAYABLE_HEROES = {4}


# --- hero document bundle ---------------------------------------------------
# Realistic bodies (ported from the cockpit's reviewed fixture set). The live
# coverage/liability workflows read these and cite the document_ids; the cockpit
# viewer renders the body with the cited excerpt highlighted.

def _hero_documents(claim_id: str, n: str, received, payable: bool = False) -> list[Document]:
    # The police report is what swings liability (and therefore whether the
    # claimant's BI claim is barred). "payable" flips fault onto the insured.
    if payable:
        chp_body = (
            "CALIFORNIA HIGHWAY PATROL — TRAFFIC COLLISION REPORT\n"
            "Report CHP-2026-0931 · Date 2026-05-22\n\n"
            "Parties: Vehicle 1 (insured), Vehicle 2 (claimant).\n\n"
            "Narrative (line 12): Vehicle 1 (insured) driver admits inattention "
            "and failure to stop; Vehicle 2 (claimant) was stopped at a red signal "
            "when struck from behind.\n\n"
            "Primary collision factor: Vehicle 1 (insured) — failure to maintain a "
            "safe following distance. No contributing factors attributed to Vehicle 2."
        )
    else:
        chp_body = (
            "CALIFORNIA HIGHWAY PATROL — TRAFFIC COLLISION REPORT\n"
            "Report CHP-2026-0814 · Date 2026-05-22\n\n"
            "Parties: Vehicle 1 (insured), Vehicle 2 (third party).\n\n"
            "Narrative (line 12): Vehicle 2 driver admits inattention; vehicle 1 "
            "stopped at red signal.\n\n"
            "Primary collision factor: Vehicle 2 — failure to maintain a safe "
            "following distance."
        )
    return [
        Document(
            document_id=f"DOC-{n}-ED",
            claim_id=claim_id,
            document_type="medical_records",
            received_date=received,
            source="treating_provider",
            body_text=(
                "ALPINE MEDICAL CENTER — EMERGENCY DEPARTMENT NOTE\n"
                "MRN 44192 · Date of service 2026-05-22 · Page 4\n\n"
                "Chief complaint: Neck pain following motor-vehicle collision.\n\n"
                "History: 41-year-old restrained driver, rear-ended while stopped "
                "at a signal. Ambulatory at the scene, transported for evaluation.\n\n"
                "Exam: Cervical paraspinal tenderness with limited range of motion. "
                "Neurologic exam intact.\n\n"
                "Assessment / Plan: Pt. presented with cervical pain 8/10; MRI "
                "ordered; admitted overnight. Observation and pain control initiated.\n\n"
                "Disposition: Admit to observation."
            ),
        ),
        Document(
            document_id=f"DOC-{n}-ORTHO",
            claim_id=claim_id,
            document_type="medical_records",
            received_date=received,
            source="treating_provider",
            body_text=(
                "ORTHOPEDIC CONSULTATION — A. Marin, MD\n"
                "Date 2026-05-28\n\n"
                "Reason for consult: Persistent cervical radiculopathy following "
                "MVC of 2026-05-22.\n\n"
                "Imaging: MRI of the cervical spine reviewed this date.\n\n"
                "Impression: C4-C5 disc herniation; surgical consult pending; "
                "conservative tx exhausted.\n\n"
                "Recommendation: Refer to spine surgery for operative evaluation; "
                "continue activity modification in the interim."
            ),
        ),
        Document(
            document_id=f"DOC-{n}-CHP",
            claim_id=claim_id,
            document_type="police_report",
            received_date=received,
            source="law_enforcement",
            body_text=chp_body,
        ),
        Document(
            document_id=f"DOC-{n}-ENDORSE",
            claim_id=claim_id,
            document_type="policy",
            received_date=received,
            source="policy_file",
            body_text=(
                "POLICY POL-2026-0093 — ENDORSEMENT 3\n"
                "Effective 2026-01-01\n\n"
                "This endorsement amends the Specialty Bodily Injury coverage part.\n\n"
                "Terms: Specialty BI sublimit raised to $100k; defense within limits.\n\n"
                "All other terms, conditions, and exclusions of the policy remain "
                "unchanged."
            ),
        ),
        Document(
            document_id=f"DOC-{n}-DEMAND",
            claim_id=claim_id,
            document_type="correspondence",
            received_date=received,
            source="claimant_counsel",
            body_text=(
                "RE: Settlement Demand — claimant v. your insured\n\n"
                "Dear Claims Representative,\n\n"
                "Our client demands $175,000.00 to fully resolve all claims against "
                "your insured. Specials to date total $84,000, including documented "
                "surgical recommendation. This demand is open for thirty (30) days, "
                "after which our client reserves the right to proceed with litigation.\n\n"
                "Sincerely,\n/s/ M. Reyes, Esq."
            ),
        ),
    ]


# --- public entry point -----------------------------------------------------


def build_cockpit_caseload(as_of: datetime = DEFAULT_AS_OF) -> Caseload:
    """Return the triage fixture enriched for the cockpit demo.

    Enrichment (display + documents only — never deadlines, ledger, severity,
    or the corner-mix that the locked evals depend on):
      1. Named insureds + claimants on every claim.
      2. Varied loss types (a spread of auto-PD and property among non-hero
         rows; heroes stay auto-BI).
      3. A coherent injury-claim document bundle (ED note, ortho consult,
         police report, policy endorsement, demand letter) on the hero claims,
         so the live workflows cite real document_ids with highlightable bodies.
    """
    caseload = build_caseload(as_of)

    new_claims: list[Claim] = []
    for claim in caseload.claims:
        idx = _claim_index(claim.claim_id)
        update: dict = {}
        if 1 <= idx <= len(_INSURED_NAMES):
            update["insured_name"] = _INSURED_NAMES[idx - 1]
            update["claimant_name"] = _CLAIMANT_NAMES[idx - 1]
        new_claims.append(claim.model_copy(update=update) if update else claim)
    caseload.claims = new_claims

    new_requests: list[CoverageRequest] = []
    for req in caseload.requests:
        idx = _claim_index(req.claim_id)
        override = _COVERAGE_OVERRIDE.get(idx)
        new_requests.append(
            req.model_copy(update={"coverage_id": override}) if override else req
        )
    caseload.requests = new_requests

    # Hero document bundles. Received date is strictly after every AgentAction
    # so they read as freshly-arrived evidence; drop any placeholder docs on the
    # same claim first so the bundle is the whole story.
    received = (as_of + timedelta(hours=1)).date()
    hero_ids = {f"CLM-{i:03d}" for i in _HERO_CLAIMS}
    caseload.documents = [d for d in caseload.documents if d.claim_id not in hero_ids]
    for i in sorted(_HERO_CLAIMS):
        cid = f"CLM-{i:03d}"
        caseload.documents.extend(
            _hero_documents(cid, f"{i:03d}", received, payable=i in _PAYABLE_HEROES)
        )

    return caseload


def _claim_index(claim_id: str) -> int:
    """CLM-007 → 7. Returns -1 for anything that doesn't match."""
    try:
        return int(claim_id.rsplit("-", 1)[1])
    except (IndexError, ValueError):
        return -1
