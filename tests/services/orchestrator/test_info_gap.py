"""Tests for the InfoGap detector — the upstream policy that turns
a claim's open-question set into fresh pending_draft outbounds.

Covers:
- Happy path: open questions on the claim → pending_draft proposals
  bundled by (party, recipient_name).
- Dependency blocking: Q-X depends on Q-Y, both open → only Q-Y
  proposed; Q-X recorded in `skipped`.
- Source selection: highest-fidelity deliverable source wins;
  internal-only sources skip with `no_deliverable_source`.
- Missing recipient directory entry → `no_recipient_in_directory`
  skip; question is preserved in audit trail.
- In-flight blocking: pending_draft/drafted/sent/overdue outbound
  on same party blocks re-asking; `replied` does NOT block.
- apply_outcome: appends to caseload.outbound_requests, input
  unmutated, empty proposals are a no-op.
- End-to-end loop closure: propose → ingest doc that satisfies a
  question → propose again sees fewer open questions.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from argos.ontology.types import (
    Caseload,
    Claim,
    CoverageRequest,
    Document,
    OutboundRequest,
)
from argos.services.orchestrator.info_gap import (
    apply_outcome,
    propose_pending_outbounds,
)


_NOW = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _claim(
    *,
    claimant_name: str | None = "Robert Caro",
    insured_name: str | None = "Stellar Logistics, LLC",
) -> Claim:
    return Claim(
        claim_id="CLM-007",
        policy_period_id="PP-1",
        opened_date=date(2026, 5, 10),
        claimant_name=claimant_name,
        insured_name=insured_name,
    )


def _caseload(
    *,
    documents: list[Document] | None = None,
    outbounds: list[OutboundRequest] | None = None,
) -> Caseload:
    return Caseload(
        as_of=_NOW,
        claims=[_claim()],
        requests=[CoverageRequest(
            request_id="REQ-007", claim_id="CLM-007", coverage_id="COV-1",
        )],
        documents=documents or [],
        outbound_requests=outbounds or [],
    )


def _directory() -> dict[str, str]:
    """A reasonably-populated recipient directory covering parties
    that appear in INFO_MAP_AUTO_BI_FL with deliverable channels."""
    return {
        "broker": "BrokerCo Underwriting Desk",
        "insured": "Stellar Logistics, LLC",
        "police_records_office": "FL Highway Patrol Records",
        "medical_provider": "St. Anthony's Medical Records",
        "claimant_counsel": "Marisol Trent, Esq.",
        "dmv": "Florida DMV Portal",
        "body_shop": "Premier Auto Body",
        "employer": "Stellar Logistics HR",
        "cms_msprp": "CMS MSPRP Portal",
        "iso_claim_search": "ISO ClaimSearch API Desk",
        "court_records": "Hillsborough County Clerk",
        "carrier_uw": "Carrier Underwriting",
        "fnol_system": "FNOL System Operator",
        "witness": "Witness on file",
        "pip_carrier": "PIP Carrier Claims Desk",
    }


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestProposeHappyPath:
    def test_open_questions_produce_proposals(self):
        """An empty claim (no documents, no outbounds) should yield
        proposals for every open question the info map can route to
        a deliverable party."""
        outcome = propose_pending_outbounds(
            _claim(),
            _caseload(),
            recipient_directory=_directory(),
        )
        assert outcome.claim_id == "CLM-007"
        assert outcome.proposals, "Expected at least one proposal on an empty claim"
        for o in outcome.proposals:
            assert o.status == "pending_draft"
            assert o.draft_body is None
            assert o.recipient_name  # populated from directory
            assert o.question_ids_asked  # non-empty
            assert o.letter_purpose  # non-empty

    def test_proposals_bundle_by_party_and_recipient(self):
        """Multiple questions routed to the same (party, recipient_name)
        end up on ONE outbound, not one per question."""
        outcome = propose_pending_outbounds(
            _claim(),
            _caseload(),
            recipient_directory=_directory(),
        )
        # Group proposals by (party, recipient_name) and assert each
        # group has exactly one OutboundRequest.
        seen = set()
        for o in outcome.proposals:
            key = (o.recipient_party, o.recipient_name)
            assert key not in seen, (
                f"Duplicate outbound for {key!r} — bundling failed"
            )
            seen.add(key)

    def test_request_ids_use_prefix_and_counter(self):
        outcome = propose_pending_outbounds(
            _claim(),
            _caseload(),
            recipient_directory=_directory(),
            request_id_prefix="OBR-CLM007-",
            request_id_start=42,
        )
        assert outcome.proposals
        ids = [o.request_id for o in outcome.proposals]
        # First id uses the start counter; subsequent ones increment.
        assert ids[0] == "OBR-CLM007-042"
        if len(ids) > 1:
            assert ids[1] == "OBR-CLM007-043"


# ---------------------------------------------------------------------------
# Dependency blocking
# ---------------------------------------------------------------------------


class TestDependencyBlocking:
    def test_dependent_question_skipped_when_dependency_open(self):
        """Q-COV-002 depends_on=['Q-COV-001']. Both are open on an
        empty claim → Q-COV-002 must be skipped, not bundled."""
        outcome = propose_pending_outbounds(
            _claim(),
            _caseload(),
            recipient_directory=_directory(),
        )
        proposed_qs = {q for o in outcome.proposals for q in o.question_ids_asked}
        assert "Q-COV-002" not in proposed_qs, (
            "Q-COV-002 should be blocked while Q-COV-001 is open"
        )
        # And it should appear in skipped with the right reason.
        blocked = [s for s in outcome.skipped if s.question_id == "Q-COV-002"]
        assert blocked, "Q-COV-002 should be in skipped"
        assert blocked[0].reason == "blocked_on_dependency"
        assert "Q-COV-001" in blocked[0].detail


# ---------------------------------------------------------------------------
# Source selection
# ---------------------------------------------------------------------------


class TestSourceSelection:
    def test_internal_only_question_skipped(self):
        """If we synthesize a tiny info map where a question only has
        internal_lookup sources, it must skip with
        no_deliverable_source."""
        from argos.services.info_map.types import (
            InfoMap,
            OpenQuestion,
            Source,
        )
        tiny_map = InfoMap(
            lob="auto_BI",
            jurisdiction="FL",
            phase="test",
            revision="r0",
            source_spec="docs/test",
            questions=[OpenQuestion(
                id="Q-TEST-001",
                description="Internal-only fact.",
                blocks_end_state="coverage",
                gating="required",
                sources=[Source(
                    party="carrier_uw", channel="internal_lookup",
                    cycle_time_days_min=0, cycle_time_days_max=0,
                    fidelity="authoritative",
                )],
                best_case_cycle_time_days_min=0,
                best_case_cycle_time_days_max=0,
                requirement_citation="test",
                cycle_time_citation="test",
            )],
        )
        outcome = propose_pending_outbounds(
            _claim(),
            _caseload(),
            recipient_directory=_directory(),
            info_map=tiny_map,
        )
        assert outcome.proposals == []
        assert len(outcome.skipped) == 1
        assert outcome.skipped[0].reason == "no_deliverable_source"

    def test_highest_fidelity_deliverable_source_wins(self):
        """When multiple deliverable sources exist, the one with the
        highest fidelity rank picks first."""
        from argos.services.info_map.types import (
            InfoMap,
            OpenQuestion,
            Source,
        )
        tiny_map = InfoMap(
            lob="auto_BI", jurisdiction="FL", phase="test", revision="r0",
            source_spec="docs/test",
            questions=[OpenQuestion(
                id="Q-TEST-002",
                description="Pickable.",
                blocks_end_state="coverage",
                gating="required",
                sources=[
                    Source(
                        party="insured", channel="phone",
                        cycle_time_days_min=1, cycle_time_days_max=3,
                        fidelity="tertiary",
                    ),
                    Source(
                        party="dmv", channel="portal",
                        cycle_time_days_min=7, cycle_time_days_max=14,
                        fidelity="authoritative",
                    ),
                ],
                best_case_cycle_time_days_min=1,
                best_case_cycle_time_days_max=3,
                requirement_citation="test",
                cycle_time_citation="test",
            )],
        )
        outcome = propose_pending_outbounds(
            _claim(),
            _caseload(),
            recipient_directory=_directory(),
            info_map=tiny_map,
        )
        assert len(outcome.proposals) == 1
        # DMV (authoritative) beats insured (tertiary).
        assert outcome.proposals[0].recipient_party == "dmv"


# ---------------------------------------------------------------------------
# Recipient directory
# ---------------------------------------------------------------------------


class TestRecipientDirectory:
    def test_missing_directory_entry_skips_with_reason(self):
        """An empty directory means every question routes to a party
        we don't have a name for. Every survivor should be skipped
        with no_recipient_in_directory."""
        outcome = propose_pending_outbounds(
            _claim(),
            _caseload(),
            recipient_directory={},  # empty
        )
        assert outcome.proposals == []
        assert outcome.skipped, "Empty directory should produce skips"
        reasons = {s.reason for s in outcome.skipped}
        # Some will be blocked_on_dependency or no_deliverable_source;
        # at least one should be no_recipient_in_directory.
        assert "no_recipient_in_directory" in reasons


# ---------------------------------------------------------------------------
# In-flight blocking
# ---------------------------------------------------------------------------


def _existing_outbound(
    *,
    request_id: str = "OBR-OLD",
    recipient_party: str = "police_records_office",
    question_ids: list[str] | None = None,
    status: str = "sent",
) -> OutboundRequest:
    base = dict(
        request_id=request_id,
        claim_id="CLM-007",
        recipient_party=recipient_party,
        recipient_name="FL Highway Patrol Records",
        letter_purpose="Earlier outbound on file.",
        question_ids_asked=question_ids or ["Q-LIA-001"],
        status=status,
    )
    if status in ("sent", "overdue", "replied"):
        base["sent_at"] = _NOW
        base["channel"] = "mail"
        base["drafted_at"] = _NOW
        base["draft_body"] = "Existing body."
    if status == "drafted":
        base["drafted_at"] = _NOW
        base["draft_body"] = "Existing body."
    if status == "replied":
        base["replied_at"] = _NOW
        base["reply_doc_id"] = "DOC-X"
    return OutboundRequest(**base)


class TestInFlightBlocking:
    def test_in_flight_outbound_blocks_re_ask(self):
        """A `sent` outbound covering Q-LIA-001 should prevent the
        detector from proposing it again."""
        cs = _caseload(outbounds=[
            _existing_outbound(question_ids=["Q-LIA-001"], status="sent"),
        ])
        outcome = propose_pending_outbounds(
            _claim(),
            cs,
            recipient_directory=_directory(),
        )
        proposed_qs = {q for o in outcome.proposals for q in o.question_ids_asked}
        assert "Q-LIA-001" not in proposed_qs
        blocked = [s for s in outcome.skipped if s.question_id == "Q-LIA-001"]
        assert blocked
        assert blocked[0].reason == "already_in_flight"
        assert "OBR-OLD" in blocked[0].detail

    def test_pending_draft_outbound_also_blocks(self):
        cs = _caseload(outbounds=[
            _existing_outbound(question_ids=["Q-LIA-001"], status="pending_draft"),
        ])
        outcome = propose_pending_outbounds(
            _claim(), cs, recipient_directory=_directory(),
        )
        proposed_qs = {q for o in outcome.proposals for q in o.question_ids_asked}
        assert "Q-LIA-001" not in proposed_qs

    def test_replied_outbound_does_not_block(self):
        """If the prior outbound is `replied` but the question is still
        open (deterministic check says no answering doc), re-asking
        is correct."""
        cs = _caseload(outbounds=[
            _existing_outbound(question_ids=["Q-LIA-001"], status="replied"),
        ])
        outcome = propose_pending_outbounds(
            _claim(), cs, recipient_directory=_directory(),
        )
        proposed_qs = {q for o in outcome.proposals for q in o.question_ids_asked}
        # The deterministic detector still says Q-LIA-001 is open
        # (no police_report on file) → we should re-ask.
        assert "Q-LIA-001" in proposed_qs

    def test_cancelled_outbound_does_not_block(self):
        cs = _caseload(outbounds=[
            _existing_outbound(question_ids=["Q-LIA-001"], status="cancelled"),
        ])
        outcome = propose_pending_outbounds(
            _claim(), cs, recipient_directory=_directory(),
        )
        proposed_qs = {q for o in outcome.proposals for q in o.question_ids_asked}
        assert "Q-LIA-001" in proposed_qs


# ---------------------------------------------------------------------------
# apply_outcome
# ---------------------------------------------------------------------------


class TestApplyOutcome:
    def test_apply_appends_proposals_to_caseload(self):
        cs = _caseload()
        outcome = propose_pending_outbounds(
            _claim(), cs, recipient_directory=_directory(),
        )
        new_cs = apply_outcome(cs, outcome)
        assert len(new_cs.outbound_requests) == len(outcome.proposals)
        # Every proposed id is now in the caseload.
        new_ids = {o.request_id for o in new_cs.outbound_requests}
        assert new_ids == {o.request_id for o in outcome.proposals}

    def test_apply_preserves_existing_outbounds(self):
        existing = _existing_outbound(request_id="OBR-LEGACY", status="sent")
        cs = _caseload(outbounds=[existing])
        outcome = propose_pending_outbounds(
            _claim(), cs, recipient_directory=_directory(),
        )
        new_cs = apply_outcome(cs, outcome)
        assert len(new_cs.outbound_requests) == 1 + len(outcome.proposals)
        assert any(o.request_id == "OBR-LEGACY" for o in new_cs.outbound_requests)

    def test_apply_with_no_proposals_is_noop(self):
        cs = _caseload()
        outcome = propose_pending_outbounds(
            _claim(), cs, recipient_directory={},  # nothing routes → no proposals
        )
        assert outcome.proposals == []
        new_cs = apply_outcome(cs, outcome)
        assert new_cs.outbound_requests == cs.outbound_requests

    def test_apply_does_not_mutate_input(self):
        cs = _caseload()
        outcome = propose_pending_outbounds(
            _claim(), cs, recipient_directory=_directory(),
        )
        new_cs = apply_outcome(cs, outcome)
        assert new_cs is not cs
        assert cs.outbound_requests == []


# ---------------------------------------------------------------------------
# End-to-end loop closure
# ---------------------------------------------------------------------------


class TestEndToEndLoopClosure:
    def test_ingesting_an_answering_doc_reduces_next_proposal_set(self):
        """The full Drafter↔Parser↔InfoGap loop: propose initial
        outbounds → ingest a doc that answers some questions →
        propose again sees fewer open questions."""
        # Round 1: empty claim, propose everything routable.
        cs = _caseload()
        outcome1 = propose_pending_outbounds(
            _claim(), cs, recipient_directory=_directory(),
        )
        round1_questions = {
            q for o in outcome1.proposals for q in o.question_ids_asked
        }
        assert "Q-LIA-001" in round1_questions, (
            "Sanity: empty claim should have Q-LIA-001 (police_report) open"
        )

        # Apply: outbounds are now in flight (status=pending_draft).
        cs2 = apply_outcome(cs, outcome1)

        # Ingest a police_report → Q-LIA-001 satisfied by is_answered.
        police_report = Document(
            document_id="DOC-PR-1",
            claim_id="CLM-007",
            document_type="police_report",
            received_date=date(2026, 5, 30),
            source="FHP",
            body_text="Officer arrived 14:12; complete crash narrative ...",
        )
        cs3 = cs2.model_copy(update={"documents": [police_report]})

        # Round 2: now propose again — Q-LIA-001 should be gone from
        # the open set entirely (answered by the doc) AND any prior
        # in-flight outbound for it would block re-asking anyway.
        # Most importantly, the police_report ALSO answers Q-LIA-002
        # through Q-LIA-007, so they should drop too.
        outcome2 = propose_pending_outbounds(
            _claim(), cs3, recipient_directory=_directory(),
        )
        round2_questions = {
            q for o in outcome2.proposals for q in o.question_ids_asked
        }
        # Load-bearing assertions:
        # (a) The police_report-satisfied questions don't reappear.
        for qid in ("Q-LIA-001", "Q-LIA-002", "Q-LIA-003"):
            assert qid not in round2_questions, (
                f"{qid} should be answered by police_report and no longer proposed"
            )
        # (b) Every question newly proposed in round 2 was either NOT in
        #     round 1 (a freshly-unblocked dependency — desirable) or was
        #     never satisfied. NONE of the police_report-satisfied
        #     questions should drift back in.
        satisfied_by_police_report = {
            "Q-LIA-001", "Q-LIA-002", "Q-LIA-003",
            "Q-LIA-004", "Q-LIA-006", "Q-LIA-007",
        }
        assert satisfied_by_police_report.isdisjoint(round2_questions), (
            "Police-report-satisfied questions must not be re-proposed"
        )
