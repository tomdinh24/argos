"""Extended N=20 caseload with realistic document bodies.

Wraps `build_caseload()` and replaces placeholder document bodies on
the unread-doc claims (REQ-013/014/015), plus adds 2 unread docs to
REQ-007 (catastrophic) and 1 unread doc to REQ-008 (serious) so the
Reader integration has both promote and demote signal.

Used only by the Reader-integration benchmark
(`scripts/run_triage_policy_with_reader_benchmark.py`). The v3 fixture
(`build_caseload()`) is unchanged — v3 thresholds, gold, and tests
remain valid.

Pinned by `docs/evals/triage-policy-engine-with-reader-integrated-thresholds.md`.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from argos.ontology.synthetic_caseload import DEFAULT_AS_OF, build_caseload
from argos.ontology.types import Caseload, Document


@dataclass(frozen=True)
class PinnedDoc:
    """One realistic doc inserted into the extended fixture.

    `expected_material` and `expected_posture` are pinned in the
    integration thresholds doc and used by the benchmark to verify
    Reader output against the locked predictions.
    """

    document_id: str
    claim_id: str
    document_type: str
    source: str
    body_text: str
    expected_material: bool
    expected_posture: str | None  # "reserve" | "liability" | "coverage" | "damages" | None


# ---------------------------------------------------------------------------
# Pinned document bodies for the extended fixture
# ---------------------------------------------------------------------------

# REQ-007 — catastrophic auto BI, $1.75M reserve
_DOC_007_01 = PinnedDoc(
    document_id="DOC-007-01",
    claim_id="CLM-007",
    document_type="correspondence",
    source="adjuster_internal",
    body_text=(
        "Internal correspondence — file note 2026-05-30.\n\n"
        "Received voicemail from claimant counsel's office requesting a "
        "status update on the matter. Returned the call within the hour; "
        "left a return voicemail with my direct line and email. "
        "Available for a call any time this week or next. No new "
        "documents or substantive content to log at this time."
    ),
    expected_material=False,
    expected_posture=None,
)

_DOC_007_02 = PinnedDoc(
    document_id="DOC-007-02",
    claim_id="CLM-007",
    document_type="medical_records",
    source="treating_provider",
    body_text=(
        "PATIENT VISIT SUMMARY\n"
        "Patient: [Claimant]\n"
        "Date of visit: 2026-05-22\n"
        "Provider: Dr. Andrea Kim, MD — Orthopedic Spine Specialist\n\n"
        "Chief complaint: Follow-up for cervical and thoracic pain "
        "status post motor vehicle accident.\n\n"
        "ASSESSMENT AND PLAN: MRI dated 2026-05-15 reveals C5-C6 disc "
        "herniation with nerve root impingement. Patient has been "
        "referred to neurosurgical consultation. Surgical intervention "
        "may be indicated if conservative treatment fails over the next "
        "60 days. Estimated cost of cervical discectomy and fusion: "
        "$85,000–$120,000. Patient is also being evaluated for possible "
        "thoracic involvement; additional imaging pending."
    ),
    expected_material=True,
    expected_posture="reserve",
)

# REQ-008 — serious auto BI, $585K reserve
_DOC_008_01 = PinnedDoc(
    document_id="DOC-008-01",
    claim_id="CLM-008",
    document_type="correspondence",
    source="other_carrier_counsel",
    body_text=(
        "RE: Tender of Defense — Plaintiff v. our insured\n"
        "Our Reference: ACME-26-TND-2204\n\n"
        "Dear Claims Manager,\n\n"
        "Thank you for your correspondence dated last month regarding "
        "the above matter. We acknowledge receipt of your tender of "
        "defense and are coordinating with our coverage team on a "
        "response. We will revert to you within thirty (30) days with "
        "our coverage position.\n\n"
        "Very truly yours,\n/s/ R. Patel\nCoverage Counsel"
    ),
    expected_material=False,
    expected_posture=None,
)

# REQ-013 — standard auto BI, $18K reserve (1 unread)
_DOC_013_01 = PinnedDoc(
    document_id="DOC-013-01",
    claim_id="CLM-013",
    document_type="correspondence",
    source="claimant_counsel",
    body_text=(
        "Dear Adjuster,\n\n"
        "Following up on the above-referenced matter. Our client "
        "continues to receive treatment and we will update you as "
        "matters progress. Please let us know if you require anything "
        "further from our office at this time.\n\n"
        "Best regards,\n/s/ J. Nguyen, Esq."
    ),
    expected_material=False,
    expected_posture=None,
)

# REQ-014 — serious auto BI, $55K reserve (2 unread)
_DOC_014_01 = PinnedDoc(
    document_id="DOC-014-01",
    claim_id="CLM-014",
    document_type="correspondence",
    source="claimant_counsel",
    body_text=(
        "Dear Claims Representative,\n\n"
        "We continue to represent the claimant in the above matter and "
        "remain available to discuss the file at your convenience. "
        "Please confirm receipt of the medical authorizations we "
        "provided last month so our records are aligned.\n\n"
        "Sincerely,\n/s/ M. Reyes, Esq."
    ),
    expected_material=False,
    expected_posture=None,
)

_DOC_014_02 = PinnedDoc(
    document_id="DOC-014-02",
    claim_id="CLM-014",
    document_type="correspondence",
    source="claimant_counsel",
    body_text=(
        "RE: Settlement Discussion — claimant v. your insured\n\n"
        "Dear Claims Representative,\n\n"
        "Per our prior correspondence, we are now in a position to make "
        "the following settlement demand: our client demands $175,000.00 "
        "to fully resolve all claims against your insured. This demand "
        "is open for thirty (30) days from the date of this letter, "
        "after which our client reserves the right to proceed with "
        "formal litigation.\n\n"
        "Sincerely,\n/s/ M. Reyes, Esq."
    ),
    expected_material=True,
    expected_posture="damages",
)

# REQ-015 — serious auto BI, $90K reserve (3 unread)
_DOC_015_01 = PinnedDoc(
    document_id="DOC-015-01",
    claim_id="CLM-015",
    document_type="correspondence",
    source="claimant_counsel",
    body_text=(
        "Dear Adjuster,\n\n"
        "Brief note to follow up on our prior call. Please advise on "
        "scheduling for the IME we discussed. Our office can accommodate "
        "most weekday windows in the next two weeks. Best,\n"
        "/s/ T. Olsen, Esq."
    ),
    expected_material=False,
    expected_posture=None,
)

_DOC_015_02 = PinnedDoc(
    document_id="DOC-015-02",
    claim_id="CLM-015",
    document_type="correspondence",
    source="claimant_counsel",
    body_text=(
        "Dear Claims Representative,\n\n"
        "Confirming receipt of your last status letter. Our office has "
        "no new updates to provide at this time. We will revert when "
        "we have additional information.\n\n"
        "Regards,\n/s/ T. Olsen, Esq."
    ),
    expected_material=False,
    expected_posture=None,
)

_DOC_015_03 = PinnedDoc(
    document_id="DOC-015-03",
    claim_id="CLM-015",
    document_type="correspondence",
    source="other_carrier_counsel",
    body_text=(
        "RE: Tender of Defense — co-defendant matter\n"
        "Your Reference: REQ-015\n\n"
        "Dear Claims Manager,\n\n"
        "After review of the underlying contract and policy language, "
        "Northstar Casualty declines your tender of defense and "
        "indemnity. Our position is that the cooperative-defense "
        "obligations in the underlying agreement do not extend to "
        "claims arising from your insured's independent acts. We will "
        "not be participating in defense or indemnity.\n\n"
        "Very truly yours,\n/s/ S. Wright, Coverage Counsel"
    ),
    expected_material=True,
    expected_posture="coverage",
)


PINNED_DOCS: list[PinnedDoc] = [
    _DOC_007_01, _DOC_007_02,
    _DOC_008_01,
    _DOC_013_01,
    _DOC_014_01, _DOC_014_02,
    _DOC_015_01, _DOC_015_02, _DOC_015_03,
]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def build_caseload_with_realistic_docs(
    as_of: datetime = DEFAULT_AS_OF,
) -> Caseload:
    """Return the v3 N=20 caseload extended with realistic document
    bodies on REQ-007/008/013/014/015.

    The v3 fixture (`build_caseload()`) is called first; this function
    only mutates the `documents` list:

    1. Removes the placeholder Documents for REQ-013/014/015 (the v3
       fixture inserts `body_text="(synthetic placeholder body)"`
       documents for those claims).
    2. Inserts the 9 pinned realistic documents.

    Pinned doc set: see `PINNED_DOCS` above. Pre-registered Reader
    output for each is captured in the integration thresholds doc.
    """
    caseload = build_caseload(as_of)

    # Remove placeholder docs (claim_ids whose docs we're replacing).
    claims_with_replacements = {
        d.claim_id for d in PINNED_DOCS if d.claim_id in {"CLM-013", "CLM-014", "CLM-015"}
    }
    caseload.documents = [
        d for d in caseload.documents if d.claim_id not in claims_with_replacements
    ]

    # Pick a received_date that's strictly after every AgentAction
    # timestamp in the caseload so the new docs always count as unread.
    # Last AgentAction is at most `as_of - 1 hour` for these claims;
    # `as_of.date()` is safely after that.
    received = as_of.date()

    for pinned in PINNED_DOCS:
        caseload.documents.append(
            Document(
                document_id=pinned.document_id,
                claim_id=pinned.claim_id,
                document_type=pinned.document_type,
                received_date=received,
                source=pinned.source,
                body_text=pinned.body_text,
            )
        )

    return caseload


def pinned_doc_predictions() -> dict[str, PinnedDoc]:
    """Return pinned docs keyed by `document_id` for the benchmark's
    Reader-output verification."""
    return {d.document_id: d for d in PINNED_DOCS}
