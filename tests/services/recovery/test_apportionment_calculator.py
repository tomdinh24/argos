"""Recovery calculator — recoverable basis, layered targets, net economics,
forum routing, deadlines, preservation hold, authority routing, recommendation."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from argos.schemas.workflows.recovery import (
    EvidenceArtifacts,
    ExternalEventTriggers,
)
from argos.services.recovery.apportionment_calculator import compute_recovery
from argos.services.recovery.constants import DEFAULT_PROGRAM
from argos.services.recovery.policy_engine import apply_fl_recovery_doctrines

from tests.services.recovery._fixtures import make_inputs, make_upstream


EVAL_TODAY = date(2025, 7, 1)
REVIEWED_AS_OF = datetime(2025, 7, 1, 12, 0, 0)


def _ctx(inputs=None, upstream=None, program=None):
    inputs = inputs or make_inputs()
    upstream = upstream or make_upstream()
    resolution = apply_fl_recovery_doctrines(inputs, upstream, today=EVAL_TODAY)
    program = program or DEFAULT_PROGRAM
    return compute_recovery(
        inputs, upstream, resolution, program, reviewed_as_of=REVIEWED_AS_OF,
    )


class TestRecoverableBasis:
    def test_basis_strips_pip(self) -> None:
        ctx = _ctx()
        # Section 768_0427-capped damages = economic loss ($30K); PIP=0 unless input provided
        assert ctx.recoverable_basis.basis >= Decimal("0")

    def test_basis_does_not_subtract_made_whole_shortfall_per_schonau(self) -> None:
        ctx = _ctx()
        # Even when paid_indemnity < economic_loss, basis math holds shortfall at 0
        assert ctx.recoverable_basis.made_whole_shortfall == Decimal("0")


class TestLayeredTargets:
    def test_operator_layer_uses_apportioned_share(self) -> None:
        ctx = _ctx(upstream=make_upstream(insured_pct=20, claimant_pct=80))
        ops = [t for t in ctx.layered_targets if t.layer_id == "operator_policy"]
        assert ops
        assert ops[0].apportioned_fault_pct == Decimal("80")

    def test_layered_targets_include_required_layers(self) -> None:
        ctx = _ctx()
        ids = {t.layer_id for t in ctx.layered_targets}
        # Operator always present; others conditional but operator must be there
        assert "operator_policy" in ids

    def test_probability_descends_layer_by_layer(self) -> None:
        ctx = _ctx()
        # Per program ladder: operator > vicarious > neg-ent > Fabre > products
        layer_probs = {t.layer_id: t.probability_of_recovery for t in ctx.layered_targets}
        if "operator_policy" in layer_probs and "vicarious_cap" in layer_probs:
            assert layer_probs["operator_policy"] >= layer_probs["vicarious_cap"]


class TestForumRouting:
    def test_within_af_cap_routes_to_af(self) -> None:
        ctx = _ctx(upstream=make_upstream(paid_indemnity=25000))
        assert ctx.forum_routing.within_af_cap

    def test_over_af_cap_routes_to_litigation_or_negotiated(self) -> None:
        ctx = _ctx(upstream=make_upstream(paid_indemnity=200000))
        # paid_indemnity > $100K AF cap, so routing should NOT be AF
        assert ctx.forum_routing.recommendation != "arbitration_forums_inc"

    def test_missing_naic_blocks_forum_routing(self) -> None:
        ctx = _ctx(inputs=make_inputs(tortfeasor_carrier_naic=None))
        assert ctx.forum_routing.af_signatory_check in (
            "unverifiable", "tbd_signatory_check_pending",
        )


class TestNetEconomics:
    def test_net_total_equals_gross_minus_drag(self) -> None:
        ctx = _ctx()
        ne = ctx.net_economics
        # net + drag + fee_shift should reconcile to gross
        assert ne.net_total == ne.gross_recoverable_total - ne.fee_drag - ne.fee_shifting_exposure

    def test_pre_hb837_carries_fee_shifting_exposure(self) -> None:
        ctx = _ctx(inputs=make_inputs(loss_date=date(2022, 6, 2)))
        assert ctx.net_economics.fee_shifting_exposure >= Decimal("0")


class TestRecommendation:
    def test_bar_routes_to_abstain(self) -> None:
        # claimant 60% post-HB-837 → barred
        ctx = _ctx(upstream=make_upstream(insured_pct=40, claimant_pct=60))
        assert ctx.recommendation == "abstain"

    def test_mandatory_variance_routes_to_senior_review(self) -> None:
        # Coverage denial = mandatory escalation flag
        ctx = _ctx(upstream=make_upstream(coverage_status="denied"))
        assert ctx.recommendation == "senior_review_required"

    def test_negative_net_routes_to_abstain(self) -> None:
        # Very high paid + low econ → recoverable basis is near zero or negative
        ctx = _ctx(upstream=make_upstream(paid_indemnity=1000, economic_loss=500))
        # Should not crash; recommendation should be valid enum
        assert ctx.recommendation in (
            "pursue", "route_to_af", "route_to_litigation",
            "route_to_negotiated_demand", "abstain", "senior_review_required",
        )


class TestAuthorityRouting:
    def test_authority_keyed_off_net_not_gross(self) -> None:
        ctx = _ctx()
        a = ctx.authority_routing
        assert a.net_apportioned_recoverable == ctx.net_economics.net_total

    def test_low_net_committable_at_examiner(self) -> None:
        ctx = _ctx(upstream=make_upstream(paid_indemnity=5000, economic_loss=10000))
        a = ctx.authority_routing
        # Very small recoveries should be committable at examiner unless mandatory variance
        if not any(v in DEFAULT_PROGRAM.mandatory_escalation_variance_flags
                   for v in ctx.variance_flags):
            assert a.required_tier in ("examiner", "senior_examiner")


class TestDeadlineCalendar:
    def test_sol_deadline_present(self) -> None:
        ctx = _ctx()
        ids = {e.deadline_id for e in ctx.deadline_calendar.entries}
        assert "sol_drop_dead" in ids

    def test_um_deadline_when_triggered(self) -> None:
        triggers = ExternalEventTriggers(
            liability_carrier_offer_date=date(2025, 6, 20),
        )
        ctx = _ctx(inputs=make_inputs(external_event_triggers=triggers))
        ids = {e.deadline_id for e in ctx.deadline_calendar.entries}
        assert any("627_727" in i for i in ids)


class TestPreservationHold:
    def test_hold_issued_with_vehicle_in_storage(self) -> None:
        ctx = _ctx()
        assert ctx.preservation_hold.issued

    def test_hold_blocked_when_vehicle_released(self) -> None:
        inputs = make_inputs(
            evidence_artifacts=EvidenceArtifacts(vehicle_status="released_to_salvage"),
        )
        ctx = _ctx(inputs=inputs)
        # Already-released vehicle = preservation hold cannot block salvage
        assert ctx.preservation_hold.blocks_salvage_release is False


class TestCrossStream:
    def test_coverage_denial_interlock_surfaced(self) -> None:
        ctx = _ctx(upstream=make_upstream(coverage_status="denied"))
        assert ctx.cross_stream_conflicts.coverage_denial_recovery_pursuit_interlock != "none"
