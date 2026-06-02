"""Diligence ledger + templated rationale — byte-reproducibility and coverage."""
from __future__ import annotations

from datetime import date, datetime

from argos.services.recovery.apportionment_calculator import compute_recovery
from argos.services.recovery.constants import DEFAULT_PROGRAM, VERSION
from argos.services.recovery.diligence_ledger import (
    build_diligence_ledger, render_diligence_ledger,
)
from argos.services.recovery.policy_engine import apply_fl_recovery_doctrines
from argos.services.recovery.rationale import render_recovery_rationale

from tests.services.recovery._fixtures import make_inputs, make_upstream


EVAL_TODAY = date(2025, 7, 1)
REVIEWED_AS_OF = datetime(2025, 7, 1, 12, 0, 0)


def _ctx_and_ledger():
    inputs = make_inputs()
    upstream = make_upstream()
    resolution = apply_fl_recovery_doctrines(inputs, upstream, today=EVAL_TODAY)
    ctx = compute_recovery(
        inputs, upstream, resolution, DEFAULT_PROGRAM, reviewed_as_of=REVIEWED_AS_OF,
    )
    ledger = build_diligence_ledger(ctx, trigger_name="initial_review")
    return ctx, ledger


class TestLedger:
    def test_ledger_records_all_gates(self) -> None:
        ctx, ledger = _ctx_and_ledger()
        assert len(ledger.gates_evaluated) == len(ctx.resolution.gates)

    def test_af_signatory_check_records_source_and_timestamp(self) -> None:
        ctx, ledger = _ctx_and_ledger()
        c = ledger.af_signatory_check
        assert c is not None
        assert "AF_SIGNATORY_ROSTER_V1" in c.source
        assert c.lookup_timestamp == REVIEWED_AS_OF
        assert c.result == "signatory"  # State Farm seed

    def test_made_whole_computation_present(self) -> None:
        _, ledger = _ctx_and_ledger()
        assert ledger.made_whole_computation is not None

    def test_decision_rationale_includes_recommendation(self) -> None:
        ctx, ledger = _ctx_and_ledger()
        assert ctx.recommendation in ledger.decision_rationale


class TestLedgerRenderReproducibility:
    def test_render_is_byte_reproducible(self) -> None:
        ctx, ledger = _ctx_and_ledger()
        r1 = render_diligence_ledger(ledger)
        r2 = render_diligence_ledger(ledger)
        assert r1 == r2

    def test_render_includes_required_sections(self) -> None:
        _, ledger = _ctx_and_ledger()
        out = render_diligence_ledger(ledger)
        assert "DILIGENCE LEDGER:" in out
        assert "Gates evaluated:" in out
        assert "AF signatory check:" in out
        assert "Made-whole:" in out
        assert "Preservation hold:" in out
        assert "Decision rationale:" in out


class TestRationale:
    def test_rationale_is_byte_reproducible(self) -> None:
        ctx, ledger = _ctx_and_ledger()
        r1 = render_recovery_rationale(
            ctx, ledger,
            claim_id="C-TEST-1", eval_seq=1,
            trigger_name="initial_review",
            trigger_event_date=date(2025, 7, 1),
        )
        r2 = render_recovery_rationale(
            ctx, ledger,
            claim_id="C-TEST-1", eval_seq=1,
            trigger_name="initial_review",
            trigger_event_date=date(2025, 7, 1),
        )
        assert r1 == r2

    def test_rationale_stamps_version(self) -> None:
        ctx, ledger = _ctx_and_ledger()
        out = render_recovery_rationale(
            ctx, ledger,
            claim_id="C-TEST-1", eval_seq=1,
            trigger_name="initial_review",
            trigger_event_date=date(2025, 7, 1),
        )
        assert VERSION in out

    def test_rationale_covers_all_required_sections(self) -> None:
        ctx, ledger = _ctx_and_ledger()
        out = render_recovery_rationale(
            ctx, ledger,
            claim_id="C-TEST-1", eval_seq=1,
            trigger_name="initial_review",
            trigger_event_date=date(2025, 7, 1),
        )
        for section in (
            "RECOVERY EVALUATION",
            "TRIGGER:",
            "LOSS POSTURE:",
            "UPSTREAM CONSUMPTION:",
            "DOCTRINAL GATES",
            "LAYERED TARGETS:",
            "RECOVERABLE BASIS:",
            "NET ECONOMICS:",
            "FORUM ROUTING:",
            "DEADLINE CALENDAR:",
            "PRESERVATION HOLD:",
            "VARIANCE FLAGS",
            "CROSS-STREAM CONFLICTS:",
            "DILIGENCE LEDGER:",
            "RECOMMENDATION:",
            "DOWNSTREAM HANDOFFS:",
        ):
            assert section in out, f"missing section: {section}"
