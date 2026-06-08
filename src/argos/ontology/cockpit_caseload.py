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
    9: _COVERAGE_BI,     # Pinnacle Steel — auto BI (injured-driver subrogation archetype;
                         # base fixture pins this to property, which the auto/flood-only
                         # PolicyCoverage type can't model — override to auto-BI)
    11: _COVERAGE_PD,    # Goldman Produce — auto PD
    13: _COVERAGE_PROP,  # Lakeshore Retail — property
    17: _COVERAGE_PROP,  # Coastal Pipe — property
}

# The caseload's five always-top (red-band) rows are each a distinct point in the
# policy engine's range, so scrolling the top of the desk walks the lifecycle:
#
#   CLM-007 (cat)  → injury, payable      → $255k reserve, client authority  (escalate)
#   CLM-001 (ser)  → injury, barred       → $0, comparative-fault bar        (no — liability)
#   CLM-004 (ser)  → injury, payable      → $159.6k reserve                  (pay)
#   CLM-008 (ser)  → mild injury + open coverage question → ROR              (no/maybe — coverage)
#   CLM-009 (ser)  → insured-victim BI, PIP paid, commercial tortfeasor → subrogation (pursue)
#
# The "injury heroes" share one bundle (ED note, ortho, police report, endorsement,
# demand); the police-report fault-flip swings barred vs payable. CLM-008 and
# CLM-009 get their own bundles below so coverage-ROR and recovery-pursue land.
_HERO_CLAIMS = {1, 4, 7}
# Payable = insured at fault → the claimant has a clean BI claim, so the reserve
# models real indemnity. CLM-004 (serious) and CLM-007 (catastrophic) are the two
# payable injury heroes — 007 is the high-reserve / escalated-authority archetype
# the caseload's #1 row needs (catastrophic exposure can't read as a barred $0).
_PAYABLE_HEROES = {4, 7}

# CLM-008 — coverage-dispute (ROR) archetype: a MILD injury (so the computed
# reserve stays small and the coverage question, not the money, is the headline)
# plus a legible open coverage question (unlisted driver / business use) that the
# coverage workflow surfaces as a reservation of rights.
_ROR_CLAIM = 8

# CLM-009 — subrogation archetype: the insured's own driver is injured by an
# identified third-party COMMERCIAL truck (insured 0% at fault). The insurer pays
# PIP / med-pay, then subrogates against the trucking company's carrier under the
# §627.7405 PIP-commercial lane — the one PIP subrogation lane FL allows. PIP paid
# + commercial tortfeasor + clear liability + documented medical basis + no release
# → the recovery calculator prices a real recoverable basis and recommends pursuit.
# (Framed as insured-victim BI rather than first-party physical damage: the recovery
# calculator prices BI/medical recoverable basis — §768.0427 damages, collateral
# sources — and returns $0 on a pure property loss.)
_SUBRO_CLAIM = 9


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


def _ror_documents(claim_id: str, n: str, received) -> list[Document]:
    """CLM-008 — coverage-dispute (ROR) bundle.

    A minor soft-tissue injury (small specials → modest reserve) so the open
    *coverage* question is the headline, not the money. The coverage question:
    at the time of loss the insured vehicle was driven by someone not listed on
    the policy and apparently in commercial delivery use — both potentially
    outside the personal-use terms — so the carrier acknowledges the claim but
    reserves rights pending investigation. That ambiguity (not a clean grant, not
    a clean exclusion) is what pushes the coverage synthesis toward ROR.
    """
    return [
        Document(
            document_id=f"DOC-{n}-ED",
            claim_id=claim_id,
            document_type="medical_records",
            received_date=received,
            source="treating_provider",
            body_text=(
                "RIVERSIDE URGENT CARE — VISIT NOTE\n"
                "MRN 70213 · Date of service 2026-05-22 · Page 1\n\n"
                "Chief complaint: Neck and shoulder soreness after a low-speed "
                "motor-vehicle collision earlier today.\n\n"
                "Exam: Mild left cervical paraspinal tenderness. Full range of "
                "motion. Neurologic exam intact. No midline tenderness. Cervical "
                "X-ray obtained — no acute fracture or malalignment.\n\n"
                "Assessment: Cervical strain (whiplash), minor. No red-flag "
                "findings.\n\n"
                "Plan: OTC analgesics, home exercises, return if symptoms persist. "
                "Discharged same day in stable condition. No imaging beyond X-ray "
                "indicated. Estimated treatment to date: $2,400."
            ),
        ),
        Document(
            document_id=f"DOC-{n}-CHP",
            claim_id=claim_id,
            document_type="police_report",
            received_date=received,
            source="law_enforcement",
            body_text=(
                "CALIFORNIA HIGHWAY PATROL — TRAFFIC COLLISION REPORT\n"
                "Report CHP-2026-1188 · Date 2026-05-22\n\n"
                "Parties: Vehicle 1 (insured), Vehicle 2 (claimant).\n\n"
                "Narrative (line 9): Vehicle 1 (insured) failed to stop in time and "
                "struck Vehicle 2 (claimant), which was stopped in traffic. Vehicle 1 "
                "operator identified as J. Alvarez. Vehicle 1 displayed magnetic "
                "signage reading 'QuickRoute Deliveries.'\n\n"
                "Primary collision factor: Vehicle 1 (insured) — following too "
                "closely. Low speed; minor property damage to both vehicles."
            ),
        ),
        Document(
            document_id=f"DOC-{n}-COVMEMO",
            claim_id=claim_id,
            document_type="correspondence",
            received_date=received,
            source="adjuster_internal",
            body_text=(
                "COVERAGE INVESTIGATION MEMO — internal\n"
                "Re: open coverage questions before any payment\n\n"
                "Two open questions prevent an unconditional coverage grant:\n\n"
                "1) Listed-driver question. The named insured is the policyholder, "
                "but the operator at the time of loss was J. Alvarez, who does not "
                "appear on the policy's listed-driver schedule. Whether Alvarez was a "
                "permissive user within the omnibus clause is not yet established.\n\n"
                "2) Use question. The vehicle bore 'QuickRoute Deliveries' signage at "
                "the scene, suggesting possible commercial/delivery use. The policy is "
                "rated for personal and non-commercial business use; a livery or "
                "for-hire delivery use at the time of loss may fall outside the "
                "covered use. This is unconfirmed — Alvarez may have been off-shift.\n\n"
                "Neither question is resolved on the current record. Recommend "
                "acknowledging the claim and reserving rights pending a recorded "
                "statement and confirmation of the vehicle's use and the operator's "
                "permission. No grounds for outright denial on the present facts."
            ),
        ),
        Document(
            document_id=f"DOC-{n}-ROR",
            claim_id=claim_id,
            document_type="correspondence",
            received_date=received,
            source="adjuster_internal",
            body_text=(
                "DRAFT — RESERVATION OF RIGHTS\n"
                "Re: claim under POL-2026-0093\n\n"
                "The Company acknowledges receipt of this claim and is proceeding "
                "with its investigation. The Company reserves all rights and defenses "
                "under the policy, including but not limited to questions regarding "
                "(a) whether the operator at the time of loss was a permissive user "
                "within the policy's omnibus clause, and (b) whether the vehicle was "
                "being used for commercial delivery or for-hire purposes outside the "
                "policy's covered-use terms.\n\n"
                "No coverage position is final. This communication is not a denial "
                "and not a waiver of any term, condition, or exclusion."
            ),
        ),
    ]


def _subro_documents(claim_id: str, n: str, received) -> list[Document]:
    """CLM-009 — subrogation bundle.

    The insured's own driver (Pinnacle Steel Works fleet) is injured when an
    identified third-party COMMERCIAL tractor-trailer strikes the insured vehicle.
    The insured driver is the stationary victim (0% at fault). The insurer pays
    PIP / med-pay on the insured's behalf and holds a clean subrogation claim
    against the trucking company's commercial-auto carrier under the §627.7405
    PIP-commercial lane. Injured insured + documented medical specials + PIP paid
    (collateral source) + identified commercial tortfeasor + carrier NAIC +
    documented limits + clear liability + no release → the recovery calculator
    prices a real recoverable basis and recommends pursuit (not abstain)."""
    return [
        Document(
            document_id=f"DOC-{n}-ED",
            claim_id=claim_id,
            document_type="medical_records",
            received_date=received,
            source="treating_provider",
            body_text=(
                "VALLEY GENERAL HOSPITAL — EMERGENCY DEPARTMENT NOTE\n"
                "MRN 88431 · Date of service 2026-05-22 · Page 3\n\n"
                "Patient: insured's commercial driver (Pinnacle Steel Works fleet).\n\n"
                "History: Belted driver of a box truck struck on the driver side by a "
                "tractor-trailer while stopped. Significant intrusion to the cab.\n\n"
                "Exam: Left shoulder deformity, cervical tenderness, seatbelt "
                "bruising. Imaging: left clavicle fracture confirmed on X-ray; "
                "cervical MRI shows C5-C6 disc protrusion.\n\n"
                "Assessment / Plan: Displaced clavicle fracture — orthopedic fixation "
                "scheduled; cervical injury managed conservatively with PT.\n\n"
                "Medical specials to date: $38,500 (ED, imaging, orthopedic surgery "
                "estimate, physical therapy). Permanent impairment likely given "
                "operative fracture."
            ),
        ),
        Document(
            document_id=f"DOC-{n}-INCIDENT",
            claim_id=claim_id,
            document_type="police_report",
            received_date=received,
            source="law_enforcement",
            body_text=(
                "POLICE INCIDENT REPORT — commercial-vehicle collision\n"
                "Report PD-2026-3071 · Date 2026-05-23\n\n"
                "Parties: Vehicle 1 (insured). Vehicle 2 (third party).\n\n"
                "Narrative (line 8): Vehicle 1 (insured) was fully stopped, waiting "
                "to enter the yard, when Vehicle 2 struck it from the rear. Vehicle 1 "
                "took no evasive action because none was available; it was stationary "
                "and lawfully stopped. The injured party is the insured's own driver.\n\n"
                "Primary collision factor: Vehicle 2 — failure to maintain a safe "
                "following distance. No contributing factor attributed to Vehicle 1.\n\n"
                "Citation: the Vehicle 2 driver was cited. Vehicle 2 is a commercial "
                "tractor-trailer (a commercial motor carrier, not a private-passenger "
                "vehicle), operated for Brightway Freight Carriers, Inc. Liability "
                "insurer identified at scene as Continental Freight Indemnity Co. The "
                "carrier's NAIC code is not stated in the file. DOT# 2204417.\n\n"
                "Fault allocation: Vehicle 2 — 100%. Vehicle 1 (insured) — 0%."
            ),
        ),
        Document(
            document_id=f"DOC-{n}-PIP",
            claim_id=claim_id,
            document_type="ledger",
            received_date=received,
            source="adjuster_internal",
            body_text=(
                "PIP / MED-PAY PAYMENT RECORD — first-party benefits\n"
                "Claim under POL-2026-0093 · Personal Injury Protection\n\n"
                "The Company has paid Personal Injury Protection benefits on behalf "
                "of the injured insured driver: $10,000 PIP exhausted (80% of "
                "documented medical to the statutory cap), plus $5,000 med-pay. Total "
                "first-party benefits paid to date: $15,000. These payments are a "
                "collateral source posted 2026-06-01.\n\n"
                "The Company is subrogated to the insured's rights of recovery "
                "against the responsible third party to the extent of PIP/med-pay "
                "paid. No release has been given to the tortfeasor or its carrier; no "
                "settlement reached; the statute of limitations has not run."
            ),
        ),
        Document(
            document_id=f"DOC-{n}-SUBRO",
            claim_id=claim_id,
            document_type="correspondence",
            received_date=received,
            source="adjuster_internal",
            body_text=(
                "SUBROGATION REFERRAL — third-party recovery\n"
                "Re: Pinnacle Steel Works injured-driver loss of 2026-05-22\n\n"
                "Tortfeasor: Brightway Freight Carriers, Inc. — a COMMERCIAL motor "
                "carrier (not a private-passenger vehicle), so the §627.7405 PIP "
                "commercial subrogation carve-out applies. Liability carrier: "
                "Continental Freight Indemnity Co. The carrier's NAIC code is not in "
                "the file, so its Arbitration Forums signatory status cannot be "
                "verified — the forum decision (compulsory arbitration vs. litigation "
                "vs. negotiated demand) needs senior signoff. Policy limits "
                "documented at $1,000,000 per occurrence on the carrier's "
                "declarations page in file.\n\n"
                "Recoverable basis: $15,000 PIP/med-pay paid plus the insured "
                "driver's $38,500 medical specials and BI damages, pursued under the "
                "PIP-commercial lane. Liability is clear (police report assigns 100% "
                "to the carrier's driver; driver cited). No anti-subrogation overlap "
                "— the tortfeasor is not an insured under our policy.\n\n"
                "Recommend opening recovery against Continental Freight Indemnity."
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
      3. Scenario document bundles on the five always-top rows so the live
         workflows cite real document_ids with highlightable bodies, and each
         row pre-bakes a distinct policy-engine archetype (see the module-level
         table by _HERO_CLAIMS): the injury heroes (ED note, ortho, police
         report, endorsement, demand — barred/payable via the fault-flip), the
         ROR bundle (mild injury + open coverage question), and the subrogation
         bundle (insured-victim BI + commercial tortfeasor + PIP paid).
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

    # Scenario document bundles. Received date is strictly after every
    # AgentAction so they read as freshly-arrived evidence; drop any placeholder
    # docs on the same claim first so the bundle is the whole story.
    received = (as_of + timedelta(hours=1)).date()
    authored_ids = {f"CLM-{i:03d}" for i in _HERO_CLAIMS} | {
        f"CLM-{_ROR_CLAIM:03d}", f"CLM-{_SUBRO_CLAIM:03d}",
    }
    caseload.documents = [
        d for d in caseload.documents if d.claim_id not in authored_ids
    ]
    for i in sorted(_HERO_CLAIMS):
        cid = f"CLM-{i:03d}"
        caseload.documents.extend(
            _hero_documents(cid, f"{i:03d}", received, payable=i in _PAYABLE_HEROES)
        )
    ror_id = f"CLM-{_ROR_CLAIM:03d}"
    caseload.documents.extend(
        _ror_documents(ror_id, f"{_ROR_CLAIM:03d}", received)
    )
    subro_id = f"CLM-{_SUBRO_CLAIM:03d}"
    caseload.documents.extend(
        _subro_documents(subro_id, f"{_SUBRO_CLAIM:03d}", received)
    )

    return caseload


def _claim_index(claim_id: str) -> int:
    """CLM-007 → 7. Returns -1 for anything that doesn't match."""
    try:
        return int(claim_id.rsplit("-", 1)[1])
    except (IndexError, ValueError):
        return -1
