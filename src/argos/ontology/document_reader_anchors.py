"""Anchor-pair fixtures for the Document Reader eval.

Seven pairs total:
- Pairs 1-4 cover the original postures (liability, coverage, damages, reserve).
- Pairs 5-7 (added 2026-06-02) cover the `subrogation` posture introduced
  when the `PostureChanged` literal was extended from 4 -> 5 values.

Each pair shares: same ClaimContext, same DocumentInput metadata, same
opening body. Variant B adds exactly one material sentence to the body
that Variant A does not have.

Bodies are designed so the **added sentence** is the one a passing
Reader must quote in `text_excerpt` on Variant B. Variant A must
return `material=False` with empty excerpt.

Pinned by:
- v1 (Pairs 1-4 baseline): `docs/evals/document-reader-anchor-pairs-thresholds.md`
- v2 (Pairs 1-4 controls hardened): `docs/evals/document-reader-anchor-pairs-v2-thresholds.md`
- v3 (Pairs 5-7 subrogation): `docs/evals/document-reader-anchor-pairs-v3-subrogation-thresholds.md`
"""
from __future__ import annotations

from dataclasses import dataclass

from argos.workflows.document_reader import ClaimContext, DocumentInput


@dataclass(frozen=True)
class AnchorPair:
    """One paired-anchor case for the Document Reader eval."""

    pair_id: str
    posture: str  # "liability" | "coverage" | "damages" | "reserve"
    context: ClaimContext
    variant_a: DocumentInput
    variant_b: DocumentInput
    added_sentence: str  # the exact sentence that distinguishes B from A


# ---------------------------------------------------------------------------
# Pair 1 — Liability posture (police report)
# ---------------------------------------------------------------------------

_PAIR1_CTX = ClaimContext(
    claim_id="CLM-ANCHOR-LIAB-001",
    severity_tier="serious",
    current_reserve_amount=80_000.0,
    paid_to_date=0.0,
    litigation_flag=False,
    rep_flag=False,
    complaint_flag=False,
    open_coverage_status="pending",
    loss_facts=(
        "Two-vehicle collision at intersection of Causeway Blvd and Bermuda "
        "Ave, Tampa FL on 2026-04-22 at approximately 16:42 EDT. V-1 "
        "(insured, 2019 Freightliner straight truck) was traveling "
        "northbound; V-2 (claimant, 2022 Honda Civic) was traveling "
        "eastbound. Disabling damage to both vehicles. Possible injury to "
        "V-2 driver. Fault ambiguous in initial intake."
    ),
)

# REVISED 2026-05-31: stripped of all physical-evidence content (skid
# marks, post-impact displacement, EMS transport) per v2 thresholds doc
# (docs/evals/document-reader-anchor-pairs-v2-thresholds.md). The
# original v1 body leaked liability-relevant content into the Variant A
# control, causing a false-fail. v2 Variant A is a pure procedural
# shell with no findings.
_PAIR1_OPENING = (
    "TAMPA POLICE DEPARTMENT — TRAFFIC CRASH REPORT\n"
    "Case #: TPD-2026-04-22-3081\n"
    "Date of incident: 04/22/2026 16:42 EDT\n"
    "Location: Causeway Blvd × Bermuda Ave\n\n"
    "Officer responded to dispatch call of a two-vehicle collision. "
    "Two vehicles identified at scene; both drivers present and "
    "cooperative. Driver information, license details, and insurance "
    "information collected from both parties. Vehicle identifiers, "
    "registration, and insurance carrier recorded.\n\n"
    "No injuries claimed at scene by either driver. Vehicles were "
    "moved off the roadway pending tow.\n\n"
    "Investigation ongoing. Supplemental report to follow upon "
    "completion of scene reconstruction."
)

_PAIR1_ADDED = (
    "Officer determined V-1 driver failed to yield right of way at "
    "uncontrolled intersection in violation of Florida Statute "
    "316.123(2); citation issued to V-1 driver at scene."
)

PAIR1_LIABILITY = AnchorPair(
    pair_id="pair-1-liability",
    posture="liability",
    context=_PAIR1_CTX,
    variant_a=DocumentInput(
        document_id="DOC-PAIR1-A",
        document_type="police_report",
        source="law_enforcement",
        received_date="2026-04-25",
        body_text=_PAIR1_OPENING,
    ),
    variant_b=DocumentInput(
        document_id="DOC-PAIR1-B",
        document_type="police_report",
        source="law_enforcement",
        received_date="2026-04-25",
        body_text=_PAIR1_OPENING + "\n\n" + _PAIR1_ADDED,
    ),
    added_sentence=_PAIR1_ADDED,
)


# ---------------------------------------------------------------------------
# Pair 2 — Coverage posture (co-defendant carrier denial of tender)
# ---------------------------------------------------------------------------

_PAIR2_CTX = ClaimContext(
    claim_id="CLM-ANCHOR-COV-002",
    severity_tier="serious",
    current_reserve_amount=200_000.0,
    paid_to_date=15_000.0,
    litigation_flag=True,
    rep_flag=True,
    complaint_flag=False,
    open_coverage_status="pending",
    loss_facts=(
        "Commercial auto bodily injury arising out of a multi-party "
        "intersection collision on 2026-02-10. Our insured (defendant 1) "
        "was operating a commercial vehicle under a logistics contract "
        "with Acme Mutual's insured (defendant 2). Plaintiff alleges "
        "both defendants are jointly liable. Tender of defense and "
        "indemnity to Acme Mutual filed 2026-03-15 pursuant to the "
        "cooperative-defense provisions of the underlying contract; "
        "response pending. Suit filed 2026-04-02 in Hillsborough County, FL."
    ),
)

_PAIR2_OPENING = (
    "RE: Tender of Defense — Plaintiff v. Coastal Logistics, et al.\n"
    "Case No.: 26-CA-3081 (Hillsborough County)\n"
    "Your Reference: COASTAL-2026-441\n"
    "Our Reference: ACME-26-TND-1187\n\n"
    "Dear Claims Manager,\n\n"
    "Thank you for your correspondence dated March 15, 2026 regarding "
    "the above-captioned matter. We acknowledge receipt of your tender "
    "of defense and indemnity on behalf of your insured Coastal "
    "Logistics LLC.\n\n"
    "Our claims and coverage teams are currently reviewing the underlying "
    "contract documentation, the operative pleadings, and the relevant "
    "policy provisions of policy ACM-CGL-2026-44188. We are coordinating "
    "with outside coverage counsel to ensure a thorough analysis."
)

_PAIR2_ADDED = (
    "After review, Acme Mutual declines your tender of defense and "
    "indemnity. Our position is that the cooperative-defense clause in "
    "the underlying contract does not extend to claims arising from "
    "your insured's independent acts. We will not be participating in "
    "defense."
)

PAIR2_COVERAGE = AnchorPair(
    pair_id="pair-2-coverage",
    posture="coverage",
    context=_PAIR2_CTX,
    variant_a=DocumentInput(
        document_id="DOC-PAIR2-A",
        document_type="correspondence",
        source="other_carrier_counsel",
        received_date="2026-04-18",
        body_text=(
            _PAIR2_OPENING
            + "\n\nWe will revert to you within thirty (30) days with our "
            "coverage position. Please direct any questions in the interim "
            "to the undersigned.\n\nVery truly yours,\n/s/ Patricia Chen\n"
            "Patricia Chen, Esq.\nSenior Coverage Counsel, Acme Mutual"
        ),
    ),
    variant_b=DocumentInput(
        document_id="DOC-PAIR2-B",
        document_type="correspondence",
        source="other_carrier_counsel",
        received_date="2026-04-18",
        body_text=(
            _PAIR2_OPENING
            + "\n\n"
            + _PAIR2_ADDED
            + "\n\nVery truly yours,\n/s/ Patricia Chen\n"
            "Patricia Chen, Esq.\nSenior Coverage Counsel, Acme Mutual"
        ),
    ),
    added_sentence=_PAIR2_ADDED,
)


# ---------------------------------------------------------------------------
# Pair 3 — Damages posture (pre-suit demand letter)
# ---------------------------------------------------------------------------

_PAIR3_CTX = ClaimContext(
    claim_id="CLM-ANCHOR-DAM-003",
    severity_tier="serious",
    current_reserve_amount=120_000.0,
    paid_to_date=8_500.0,
    litigation_flag=False,
    rep_flag=True,
    complaint_flag=False,
    open_coverage_status="clean",
    loss_facts=(
        "Auto bodily injury arising from a rear-end collision on "
        "2026-01-08 in which our insured admitted fault. Claimant "
        "(represented since 2026-01-22) has been undergoing chiropractic "
        "and physical therapy for cervical and lumbar strain. Pre-suit "
        "demand period; statute of limitations runs 2028-01-08."
    ),
)

# REVISED 2026-05-31: stripped of all specific medical-specials and
# lost-wages totals per v2 thresholds doc
# (docs/evals/document-reader-anchor-pairs-v2-thresholds.md). The
# original opening leaked damages-relevant numbers into both variants;
# Variant A is now the shared opening + courtesy close, Variant B is
# the shared opening + the policy-limits demand sentence. The pair
# differs by exactly one added material event again.
_PAIR3_OPENING = (
    "RE: [Claimant] v. [Your Insured]\n"
    "Date of Loss: January 8, 2026\n"
    "Your Claim Number: CLM-ANCHOR-DAM-003\n\n"
    "Dear Claims Representative,\n\n"
    "Following up on our prior correspondence regarding the above "
    "matter. We continue to represent the claimant and remain "
    "available to discuss the file at your convenience.\n\n"
    "Please confirm receipt of the medical authorization we provided "
    "last month so that our records are aligned. If anything further "
    "is needed from our office, please let us know."
)

_PAIR3_ADDED = (
    "Accordingly, our client hereby demands the policy limits of "
    "$300,000.00 to fully resolve all claims against your insured. "
    "This demand is open for acceptance through July 15, 2026, after "
    "which date we will proceed with formal litigation."
)

PAIR3_DAMAGES = AnchorPair(
    pair_id="pair-3-damages",
    posture="damages",
    context=_PAIR3_CTX,
    variant_a=DocumentInput(
        document_id="DOC-PAIR3-A",
        document_type="correspondence",
        source="claimant_counsel",
        received_date="2026-05-12",
        body_text=(
            _PAIR3_OPENING
            + "\n\nSincerely,\n/s/ Marcus Reyes\nMarcus Reyes, Esq.\n"
            "Reyes & Patel, P.A."
        ),
    ),
    variant_b=DocumentInput(
        document_id="DOC-PAIR3-B",
        document_type="correspondence",
        source="claimant_counsel",
        received_date="2026-05-12",
        body_text=(
            _PAIR3_OPENING
            + "\n\n"
            + _PAIR3_ADDED
            + "\n\nSincerely,\n/s/ Marcus Reyes\nMarcus Reyes, Esq.\n"
            "Reyes & Patel, P.A."
        ),
    ),
    added_sentence=_PAIR3_ADDED,
)


# ---------------------------------------------------------------------------
# Pair 4 — Reserve posture (medical update with new diagnosis)
# ---------------------------------------------------------------------------

_PAIR4_CTX = ClaimContext(
    claim_id="CLM-ANCHOR-RES-004",
    severity_tier="standard",
    current_reserve_amount=25_000.0,
    paid_to_date=2_180.0,
    litigation_flag=False,
    rep_flag=False,
    complaint_flag=False,
    open_coverage_status="clean",
    loss_facts=(
        "Auto bodily injury arising from a low-speed rear-end collision "
        "on 2026-03-04. Claimant has been undergoing conservative "
        "treatment for cervical strain — physical therapy and "
        "chiropractic care, no surgical involvement to date. Reserve "
        "set at $25,000 reflecting expected continuation of conservative "
        "treatment."
    ),
)

_PAIR4_OPENING = (
    "PATIENT VISIT SUMMARY\n"
    "Patient: [Claimant]\n"
    "DOB: redacted | MRN: redacted\n"
    "Date of visit: 2026-05-22\n"
    "Provider: Dr. Andrea Kim, MD — Orthopedic Spine Specialist\n\n"
    "Chief complaint: Follow-up evaluation for cervical pain status "
    "post motor vehicle accident dated 2026-03-04. Patient has been "
    "compliant with prescribed conservative therapy (physical therapy "
    "two times weekly, chiropractic adjustment as tolerated).\n\n"
    "History of present illness: Patient reports ongoing cervical "
    "discomfort centered at C5-C6 level, radiating intermittently into "
    "the right shoulder and upper arm. Pain rated 5/10 average, worse "
    "with sustained sitting and head rotation. Sleep quality has "
    "improved modestly since initial visit. No bowel or bladder "
    "involvement. No upper-extremity weakness reported.\n\n"
    "Physical examination: Cervical range of motion mildly reduced in "
    "rotation and lateral flexion bilaterally. Spurling's test mildly "
    "positive on right. Upper-extremity strength 5/5 throughout. "
    "Sensation intact. Reflexes 2+ and symmetric.\n\n"
    "Current medications: Ibuprofen 600mg TID PRN; cyclobenzaprine "
    "5mg HS PRN. No medication changes today."
)

_PAIR4_ADDED = (
    "ASSESSMENT AND PLAN: MRI dated 2026-05-15 reveals C5-C6 disc "
    "herniation with nerve root impingement. Patient has been referred "
    "to neurosurgical consultation. Surgical intervention may be "
    "indicated if conservative treatment fails over the next 60 days. "
    "Estimated cost of cervical discectomy and fusion: $85,000–$120,000."
)

PAIR4_RESERVE = AnchorPair(
    pair_id="pair-4-reserve",
    posture="reserve",
    context=_PAIR4_CTX,
    variant_a=DocumentInput(
        document_id="DOC-PAIR4-A",
        document_type="medical_records",
        source="treating_provider",
        received_date="2026-05-25",
        body_text=(
            _PAIR4_OPENING
            + "\n\nASSESSMENT AND PLAN: Continue current conservative "
            "regimen. Re-evaluate in four weeks. No new diagnostic "
            "studies indicated at this time."
        ),
    ),
    variant_b=DocumentInput(
        document_id="DOC-PAIR4-B",
        document_type="medical_records",
        source="treating_provider",
        received_date="2026-05-25",
        body_text=_PAIR4_OPENING + "\n\n" + _PAIR4_ADDED,
    ),
    added_sentence=_PAIR4_ADDED,
)


# ---------------------------------------------------------------------------
# Pair 5 — Subrogation posture (ERISA consent-to-settle)
# ---------------------------------------------------------------------------

_PAIR5_CTX = ClaimContext(
    claim_id="CLM-ANCHOR-SUB-005",
    severity_tier="serious",
    current_reserve_amount=200_000.0,
    paid_to_date=0.0,
    litigation_flag=False,
    rep_flag=True,
    complaint_flag=False,
    open_coverage_status="clean",
    loss_facts=(
        "Auto bodily injury arising from a 2026-02-18 collision in "
        "which our insured was not at fault. Claimant is an active "
        "participant in an ERISA-governed employer health plan that "
        "has paid conditional medical benefits and asserted a "
        "first-dollar reimbursement right against any third-party "
        "recovery. Subrogation file is open with the plan trustees."
    ),
)

_PAIR5_OPENING = (
    "RE: Plan Participant — [Claimant Name]\n"
    "Plan ID: TRUSTEE-2026-PP-0042\n"
    "Your File: ARG-SUB-005-A\n\n"
    "Dear Claims Representative,\n\n"
    "This office acknowledges receipt of your correspondence dated "
    "May 8, 2026 regarding the above-referenced plan participant. "
    "Your inquiry has been logged and assigned to the appropriate "
    "recovery analyst for review.\n\n"
    "Please confirm that we have the most current contact information "
    "on file for your claims department, and we will respond "
    "substantively within our standard review window."
)

_PAIR5_ADDED = (
    "Per the terms of the underlying ERISA-governed plan, the Trustees "
    "consent to your insured's settlement with the third-party "
    "tortfeasor in the amount of $150,000.00, subject to the plan's "
    "first-dollar reimbursement right of $42,318.74 in conditional "
    "payments under 29 U.S.C. §1132(a)(3) and US Airways v. McCutchen."
)

PAIR5_SUBROGATION = AnchorPair(
    pair_id="pair-5-subrogation",
    posture="subrogation",
    context=_PAIR5_CTX,
    variant_a=DocumentInput(
        document_id="DOC-PAIR5-A",
        document_type="correspondence",
        source="erisa_plan_administrator",
        received_date="2026-05-28",
        body_text=(
            _PAIR5_OPENING
            + "\n\nSincerely,\n/s/ Trustee Services Group"
        ),
    ),
    variant_b=DocumentInput(
        document_id="DOC-PAIR5-B",
        document_type="correspondence",
        source="erisa_plan_administrator",
        received_date="2026-05-28",
        body_text=(
            _PAIR5_OPENING
            + "\n\n"
            + _PAIR5_ADDED
            + "\n\nSincerely,\n/s/ Trustee Services Group"
        ),
    ),
    added_sentence=_PAIR5_ADDED,
)


# ---------------------------------------------------------------------------
# Pair 6 — Subrogation posture (Arbitration Forums signatory notice)
# ---------------------------------------------------------------------------

_PAIR6_CTX = ClaimContext(
    claim_id="CLM-ANCHOR-SUB-006",
    severity_tier="standard",
    current_reserve_amount=45_000.0,
    paid_to_date=12_400.0,
    litigation_flag=False,
    rep_flag=False,
    complaint_flag=False,
    open_coverage_status="clean",
    loss_facts=(
        "Auto property-damage-plus-soft-tissue claim arising from a "
        "2026-03-30 rear-end collision. Recovery target is the adverse "
        "driver's auto carrier. Intercompany arbitration under the "
        "Arbitration Forums (AF) Auto Subrogation Arbitration Agreement "
        "is under consideration in lieu of litigation."
    ),
)

_PAIR6_OPENING = (
    "Arbitration Forums, Inc.\n"
    "Member Services Notice\n"
    "Account: ARG-MS-2026-1147\n\n"
    "Dear Member,\n\n"
    "This notice confirms your member account remains active and in "
    "good standing. Recent administrative updates to our case "
    "submission portal have been deployed; documentation is available "
    "in the member portal under \"Resources → Portal Updates.\"\n\n"
    "For any account-level questions, contact Member Services."
)

_PAIR6_ADDED = (
    "Per our records, the adverse carrier identified in your inquiry "
    "— Mercury Casualty Group, NAIC 27553 — is a current signatory "
    "to the Auto Subrogation Arbitration Agreement and the dispute as "
    "described falls within compulsory jurisdiction; you may proceed "
    "with filing under Rule 2-1."
)

PAIR6_SUBROGATION = AnchorPair(
    pair_id="pair-6-subrogation",
    posture="subrogation",
    context=_PAIR6_CTX,
    variant_a=DocumentInput(
        document_id="DOC-PAIR6-A",
        document_type="correspondence",
        source="arbitration_forums",
        received_date="2026-05-29",
        body_text=(
            _PAIR6_OPENING
            + "\n\nArbitration Forums, Inc. — Member Services"
        ),
    ),
    variant_b=DocumentInput(
        document_id="DOC-PAIR6-B",
        document_type="correspondence",
        source="arbitration_forums",
        received_date="2026-05-29",
        body_text=(
            _PAIR6_OPENING
            + "\n\n"
            + _PAIR6_ADDED
            + "\n\nArbitration Forums, Inc. — Member Services"
        ),
    ),
    added_sentence=_PAIR6_ADDED,
)


# ---------------------------------------------------------------------------
# Pair 7 — Subrogation posture (made-whole waiver)
# ---------------------------------------------------------------------------

_PAIR7_CTX = ClaimContext(
    claim_id="CLM-ANCHOR-SUB-007",
    severity_tier="serious",
    current_reserve_amount=120_000.0,
    paid_to_date=18_600.0,
    litigation_flag=False,
    rep_flag=True,
    complaint_flag=False,
    open_coverage_status="clean",
    loss_facts=(
        "Auto bodily injury arising from a 2026-01-24 collision. "
        "Claimant is in active recovery negotiation with a health "
        "insurer that has asserted a §768.76 lien notice for paid "
        "medical benefits. Made-whole doctrine has been the live "
        "question in correspondence between claimant counsel and the "
        "health insurer."
    ),
)

_PAIR7_OPENING = (
    "RE: [Claimant Name] — Lien Coordination\n"
    "Your File: CLM-SUB-007\n\n"
    "Dear Claims Representative,\n\n"
    "Enclosed please find a copy of the cover page for our client's "
    "file as previously requested. This is provided for your records "
    "only and is not intended to alter any prior positions taken in "
    "this matter.\n\n"
    "We will follow up separately on remaining outstanding items."
)

_PAIR7_ADDED = (
    "Our client has executed the enclosed Made-Whole Waiver, expressly "
    "waiving the protections of the made-whole doctrine under "
    "§768.76(2)(b) and acknowledging the health insurer's first-dollar "
    "reimbursement right against any third-party recovery; the executed "
    "waiver is attached as Exhibit A."
)

PAIR7_SUBROGATION = AnchorPair(
    pair_id="pair-7-subrogation",
    posture="subrogation",
    context=_PAIR7_CTX,
    variant_a=DocumentInput(
        document_id="DOC-PAIR7-A",
        document_type="executed_agreement",
        source="claimant_counsel",
        received_date="2026-05-30",
        body_text=(
            _PAIR7_OPENING
            + "\n\nSincerely,\n/s/ Reyes & Patel, P.A."
        ),
    ),
    variant_b=DocumentInput(
        document_id="DOC-PAIR7-B",
        document_type="executed_agreement",
        source="claimant_counsel",
        received_date="2026-05-30",
        body_text=(
            _PAIR7_OPENING
            + "\n\n"
            + _PAIR7_ADDED
            + "\n\nSincerely,\n/s/ Reyes & Patel, P.A."
        ),
    ),
    added_sentence=_PAIR7_ADDED,
)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def all_pairs() -> list[AnchorPair]:
    """Return all seven anchor pairs, in the order pinned by the
    thresholds docs (v1/v2: 1-4; v3: 5-7)."""
    return [
        PAIR1_LIABILITY,
        PAIR2_COVERAGE,
        PAIR3_DAMAGES,
        PAIR4_RESERVE,
        PAIR5_SUBROGATION,
        PAIR6_SUBROGATION,
        PAIR7_SUBROGATION,
    ]
