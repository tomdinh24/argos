"""Diligence ledger + templated rationale — byte-reproducibility and structure."""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from argos.services.liability.apportionment_calculator import compute_apportionment
from argos.services.liability.constants import DEFAULT_PROGRAM, VERSION
from argos.services.liability.diligence_ledger import (
    build_diligence_ledger,
    render_diligence_ledger,
)
from argos.services.liability.rationale import render_liability_rationale

from tests.services.liability._fixtures import (
    make_evidence,
    make_inputs,
    posture_snapshot,
)


NOW = datetime(2025, 7, 1, 10, 0, 0, tzinfo=timezone.utc)


def _ctx(**overrides):
    return compute_apportionment(
        make_inputs(**overrides),
        DEFAULT_PROGRAM,
        request_id="req-1",
        reviewed_as_of=NOW,
        gross_exposure=Decimal("25000"),
    )


class TestLedgerBuild:
    def test_posture_matches_apportionment(self) -> None:
        ctx = _ctx()
        ledger = build_diligence_ledger(ctx, trigger_name="INITIAL_APPORTIONMENT")
        for pid, ap in ctx.apportionment.items():
            assert ledger.posture_percent_by_party[pid] == ap.fault_pct

    def test_basis_evidence_excludes_credibility_only(self) -> None:
        ctx = _ctx(
            evidence_items=[
                make_evidence("scene_photo", weight_class="hard_data"),
                make_evidence("recorded_statement_insured", weight_class="credibility_only"),
            ],
        )
        ledger = build_diligence_ledger(ctx, trigger_name="INITIAL_APPORTIONMENT")
        weight_classes = [b.weight_class for b in ledger.basis_evidence]
        assert "hard_data" in weight_classes
        assert "credibility_only" not in weight_classes

    def test_rear_end_no_rebuttal_emits_change_condition(self) -> None:
        ctx = _ctx(fact_pattern="rear_end")
        ledger = build_diligence_ledger(ctx, trigger_name="INITIAL_APPORTIONMENT")
        assert any("Birge" in c for c in ledger.change_conditions)

    def test_prior_posture_delta_recorded_when_history_present(self) -> None:
        ctx = _ctx(
            prior_posture=[posture_snapshot(insured_pct=70, claimant_pct=30)],
        )
        ledger = build_diligence_ledger(ctx, trigger_name="EVIDENCE_LANDED_RE_EVAL")
        assert ledger.prior_posture_delta is not None
        assert ledger.prior_posture_delta.prior_pct_by_party["P-insured"] == Decimal("70")

    def test_open_requests_inferred_when_police_report_missing(self) -> None:
        ctx = _ctx(police_report=False)
        ledger = build_diligence_ledger(ctx, trigger_name="FNOL_INITIAL")
        req_types = [r.request_type for r in ledger.open_requests]
        assert "police_report_full_HSMV_90010S" in req_types

    def test_default_next_review_90d_diary(self) -> None:
        ctx = _ctx()
        ledger = build_diligence_ledger(ctx, trigger_name="FNOL_INITIAL")
        # Variance flags fire on default rear_end (powell_duty_clarity) →
        # 30-day VARIANCE_REVIEW, not 90-day
        assert ledger.next_review_trigger.startswith("VARIANCE_REVIEW")
        assert (ledger.next_review_date - NOW.date()).days == 30


class TestLedgerRender:
    def test_render_is_deterministic(self) -> None:
        ctx = _ctx()
        ledger = build_diligence_ledger(ctx, trigger_name="INITIAL_APPORTIONMENT")
        a = render_diligence_ledger(ledger)
        b = render_diligence_ledger(ledger)
        assert a == b

    def test_render_includes_posture_and_basis(self) -> None:
        ctx = _ctx(
            evidence_items=[
                make_evidence("scene_photo", weight_class="hard_data", quoted_span="Skid marks 12 ft."),
            ],
        )
        ledger = build_diligence_ledger(ctx, trigger_name="INITIAL_APPORTIONMENT")
        rendered = render_diligence_ledger(ledger)
        assert "DILIGENCE LEDGER:" in rendered
        assert "Posture by party:" in rendered
        assert "P-insured" in rendered
        assert "Skid marks 12 ft." in rendered


class TestRationaleRender:
    def test_rationale_header_includes_version(self) -> None:
        ctx = _ctx()
        ledger = build_diligence_ledger(ctx, trigger_name="INITIAL_APPORTIONMENT")
        text = render_liability_rationale(
            ctx,
            ledger,
            claim_id="CLM-9",
            eval_seq=2,
            trigger_name="INITIAL_APPORTIONMENT",
            trigger_event_date=date(2025, 6, 5),
        )
        assert f"constants {VERSION}" in text
        assert "Claim CLM-9" in text
        assert "Eval #2" in text

    def test_rationale_includes_all_required_sections(self) -> None:
        ctx = _ctx()
        ledger = build_diligence_ledger(ctx, trigger_name="INITIAL_APPORTIONMENT")
        text = render_liability_rationale(
            ctx, ledger,
            claim_id="CLM-9", eval_seq=1,
            trigger_name="INITIAL_APPORTIONMENT",
            trigger_event_date=date(2025, 6, 5),
        )
        for header in (
            "LIABILITY EVALUATION",
            "PARTIES",
            "FACT PATTERN:",
            "APPLICABLE REGIME:",
            "EXPOSURE CEILING:",
            "APPORTIONMENT WALK",
            "CONFIDENCE BAND:",
            "VARIANCE FLAGS",
            "§316.066(4) EVIDENCE PACK CLASSIFICATION:",
            "DILIGENCE LEDGER:",
            "AUTHORITY:",
            "DOWNSTREAM HANDOFFS:",
        ):
            assert header in text, f"missing section: {header}"

    def test_rationale_is_deterministic(self) -> None:
        inputs = make_inputs()
        ctx_a = compute_apportionment(
            inputs, DEFAULT_PROGRAM,
            request_id="req-1", reviewed_as_of=NOW,
            gross_exposure=Decimal("25000"),
        )
        ctx_b = compute_apportionment(
            inputs, DEFAULT_PROGRAM,
            request_id="req-1", reviewed_as_of=NOW,
            gross_exposure=Decimal("25000"),
        )
        ledger_a = build_diligence_ledger(ctx_a, trigger_name="INITIAL_APPORTIONMENT")
        ledger_b = build_diligence_ledger(ctx_b, trigger_name="INITIAL_APPORTIONMENT")
        text_a = render_liability_rationale(
            ctx_a, ledger_a, claim_id="CLM-9", eval_seq=1,
            trigger_name="INITIAL_APPORTIONMENT", trigger_event_date=date(2025, 6, 5),
        )
        text_b = render_liability_rationale(
            ctx_b, ledger_b, claim_id="CLM-9", eval_seq=1,
            trigger_name="INITIAL_APPORTIONMENT", trigger_event_date=date(2025, 6, 5),
        )
        assert text_a == text_b

    def test_rationale_reflects_recovery_bar_in_regime_section(self) -> None:
        ctx = _ctx(
            fact_pattern="uncontrolled_intersection",
            evidence_items=[
                make_evidence("edr_download", fault_direction="claimant_more_fault", weight_class="hard_data"),
                make_evidence("edr_download", fault_direction="claimant_more_fault", weight_class="hard_data"),
            ],
        )
        ledger = build_diligence_ledger(ctx, trigger_name="EVIDENCE_LANDED_RE_EVAL")
        text = render_liability_rationale(
            ctx, ledger,
            claim_id="CLM-1", eval_seq=3,
            trigger_name="EVIDENCE_LANDED_RE_EVAL",
            trigger_event_date=date(2025, 6, 30),
        )
        if ctx.resolution.applicable_regime.recovery_bar_triggered:
            assert "triggered=True" in text
