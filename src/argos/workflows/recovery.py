"""Recovery workflow runtime — LLM extractor + Python policy engine +
recoverable-basis calculator + diligence ledger + templated rationale.

Architecture (locked 2026-06-02, see docs/DECISIONS.md):

  1. Extractor: Anthropic tool_use forces a RecoveryInputs-shaped output
     from SyntheticClaim + Claim meta + upstream snapshots. Bounded to
     extraction; emits no doctrine resolution, no layered targets, no
     recommendation.
  2. Policy engine: apply_fl_recovery_doctrines consumes RecoveryInputs +
     RecoveryUpstreamContext and produces a DoctrineResolution
     (SOL regime + 15 gates + variance flags + bar status).
  3. Calculator: compute_recovery consumes RecoveryInputs + upstream +
     resolution + ProgramConfig and produces a CalculationContext with
     5 layered targets, net economics, forum routing, deadline calendar,
     preservation hold, recommendation, authority routing.
  4. Diligence ledger: build_diligence_ledger renders the
     Boecher/Ruiz-discoverable artifact. Co-equal with recommendation.
  5. Rationale: render_recovery_rationale interpolates everything above
     into a byte-reproducible audit-trail string.

Only step 1 talks to an LLM. Steps 2-5 are reproducible byte-for-byte.

Spec: docs/specs/recovery-workflow.md.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from anthropic import Anthropic
from pydantic import ValidationError

from argos.ontology.types import Claim, SyntheticClaim
from argos.schemas.workflows.recovery import (
    ProgramConfig,
    RecoveryAssessment,
    RecoveryInputs,
    RecoveryUpstreamContext,
)
from argos.services.recovery.apportionment_calculator import compute_recovery
from argos.services.recovery.constants import DEFAULT_PROGRAM
from argos.services.recovery.diligence_ledger import build_diligence_ledger
from argos.services.recovery.policy_engine import apply_fl_recovery_doctrines
from argos.services.recovery.rationale import render_recovery_rationale


DEFAULT_MODEL = "claude-sonnet-4-6"
TOOL_NAME = "emit_recovery_inputs"
DEFAULT_TRIGGER = "INITIAL_RECOVERY_EVALUATION"


SYSTEM_PROMPT = """\
You are the Recovery extractor for Argos, an AI-native claims operations \
layer for specialty property and casualty TPAs.

Your role is narrow and bounded: read the policy, the claim record, every \
document provided, and the upstream Liability/Reserve/Coverage snapshots, \
and emit a structured `RecoveryInputs` payload via the \
`emit_recovery_inputs` tool.

What you DO:

1. Extract `loss_date`, `loss_state` (FL or other), and `claim_filing_date` \
when a suit has been filed. These gate HB 837 SOL regime selection and \
§768.0427 paid-not-billed.
2. Classify `tortfeasor_vehicle_classification` precisely: \
`private_passenger` (PIP-required), `commercial` (PIP carve-out under \
§627.7405), `motorcycle`, `out_of_state`, `unknown`. Wrong classification \
on a PIP lane bars recovery.
3. Extract `tortfeasor_carrier_naic` — the 5-digit NAIC code of the \
tortfeasor's liability carrier. This drives Arbitration Forums signatory \
lookup. If the carrier is named but NAIC is not in the file, leave NAIC \
null; do NOT guess. The extractor gap routes to senior review.
4. Populate `tortfeasor_policy_limits` when limits are documented \
(declaration page on file, demand letter that quotes limits, recorded \
statement that names limits). Leave null otherwise.
5. Populate `owner_operator_split`. `are_same` is true when the driver IS \
the title-holding owner. `owner_type` is one of `natural_person`, \
`commercial_lessor_graves`, `business_not_in_leasing`, `government`. \
Vicarious-cap exposure under §324.021(9)(b)3 hinges on this field.
6. Populate `owner_knowledge_indicators` when the file documents owner \
knowledge of operator unfitness — license suspension, prior incidents, \
intoxication patterns. Each indicator is: kind, source_doc_id, verbatim \
quoted_span ≥1 sentence, and date_known if available.
7. Populate `named_insured_and_omnibus_roster` — every party the insured's \
policy covers, with their role (named_insured / permissive / resident_relative) \
and `coverage_section_paid_under` (collision, comp, med_pay, pip, um). \
Anti-subrogation overlap is computed per coverage section, NOT \
policy-wide.
8. Set `policy_subrogation_language`. `has_made_whole_waiver` is true \
when the policy expressly waives the made-whole doctrine in writing. \
`waiver_text` quotes the exact subrogation/transfer-of-rights clause. \
Leave waiver_status `not_waived` when no waiver is present.
9. Pick `subrogation_lane` precisely: `627_7405_pip_commercial` (PIP \
subrogating against a commercial tortfeasor), `627_736_2_pip_other_carve_out`, \
`legal` (third-party negligence), `physical_damage` (collision/comp \
recovery), `contractual` (rental/loaner agreement), `wcs_lien` (WC lien \
recovery), `other`. Wrong lane drives wrong doctrinal gates.
10. Populate `release_or_settlement_signals` if the file documents any \
release, settlement, or pre-tender resolution with the tortfeasor or \
any §627.727(6) party. Each signal: type (release_executed / \
pending_settlement / consent_to_settle_request / um_offer_made / \
ucfra_violation_signal), party, signal_date, source_doc_id, verbatim \
quoted_span. Releases bar recovery per WQBA.
11. Populate `collateral_source_payments` for every paid-source payment \
that touches the recoverable basis — PIP, Medicare, Medicaid, WC, \
employer-provided LTD, ACA-marketplace coverage. Each payment: type, \
amount (Decimal), source_doc_id, date_paid. §768.76(7) collateral source \
notice runs 30 days from when the payment posts.
12. Populate `verbal_threshold_evidence` if the underlying tort claim is \
non-economic damages from auto BI — §627.737 requires permanent injury, \
significant scarring, or significant/permanent loss of important bodily \
function. If economic-only or property-damage recovery, leave null.
13. Populate `evidence_artifacts`. `vehicle_status` is one of \
`in_storage_yard`, `totaled_held`, `released_to_salvage`, `with_insured`, \
`unknown`. `edr_pulled` is true if event data recorder data has been \
pulled. `accident_recon_completed` is true if an accident reconstruction \
expert has been retained. Vehicle status drives spoliation risk under \
Valcin/Martino — released-to-salvage breaks the preservation chain.
14. Populate `external_event_triggers` for any deadline anchor: \
`liability_carrier_offer_date` (starts §627.727(6) UM 30-day clock), \
`section_768_76_notice_date` (collateral source 30-day clock), \
`underlying_dismissal_date_if_af` (starts §624.155(4) 60-day AF refile clock).
15. Populate `fabre_candidate_nonparties` when the file documents \
non-party fault candidates (e.g. a road-maintenance entity, a product \
defect, a separate driver). Each: party_id, identity_evidence_cite, \
basis_for_inclusion. Fabre apportionment under §768.81(3) reduces \
recoverable basis layer-by-layer.
16. Populate `rental_fleet_loaner_agreement` if the tortfeasor was in a \
rental, fleet vehicle, or loaner. `contract_type` is one of \
`rental_consumer`, `rental_commercial`, `fleet_owned`, `loaner_dealer`. \
Indemnification language, if present, opens the contractual lane.
17. Populate `coverage_denial_status` if the upstream Coverage workflow \
denied or reserved rights. denied=true + basis (e.g. late_notice, \
material_misrepresentation) triggers the Harvey deny+subrogate interlock.

What you DO NOT do:

- You do NOT decide the SOL regime. The policy engine resolves HB 837 \
post/pre based on accrual_date.
- You do NOT decide which gates fire or which gates bar recovery. The \
policy engine owns all 15 doctrine evaluations.
- You do NOT compute layered targets, net economics, or the \
recommendation. The calculator owns that math.
- You do NOT fabricate quoted_spans, NAIC codes, or VIN numbers. Quote \
verbatim from the source. Leave null when not in the file.
- You do NOT silently downgrade signals — a pre-tender consent-to-settle \
request goes in `release_or_settlement_signals` even when ambiguous; \
the policy engine surfaces the variance flag.

FL-SPECIFIC NOTES:

- HB 837 effective 2023-03-24 compresses SOL from 4yr→2yr for negligence \
losses. The accrual_date / loss_date drives regime selection.
- §627.7405 PIP commercial carve-out is the ONLY PIP subrogation lane. \
Private-passenger tortfeasor on a PIP lane = barred.
- Arbitration Forums compulsory jurisdiction applies to AF-signatory \
carrier vs AF-signatory carrier under $100K. Non-signatory carriers \
route to litigation or negotiated demand.
- §768.81(6) modified comparative bar: claimant >50% fault is barred. \
The upstream Liability snapshot drives this; you don't re-extract fault.

Emit via `emit_recovery_inputs`. The tool's input_schema is the contract \
— outputs that violate it are rejected upstream.
"""


def _render_for_extractor(
    claim: SyntheticClaim,
    claim_meta: Claim | None,
    upstream: RecoveryUpstreamContext,
) -> str:
    """Render the SyntheticClaim + Claim meta + upstream snapshots for the
    extractor user-message body."""
    lines: list[str] = []

    if claim_meta is not None:
        lines += [
            "=== CLAIM RECORD ===",
            f"claim_id: {claim_meta.claim_id}",
            f"opened_date: {claim_meta.opened_date}",
            f"status: {claim_meta.status}",
            f"severity_tier_summary: {claim_meta.severity_tier_summary}",
            f"litigation_flag: {claim_meta.litigation_flag}",
            f"coverage_posture: {claim_meta.coverage_posture}",
            f"claimant_name: {claim_meta.claimant_name or '(not yet extracted)'}",
            f"insured_name: {claim_meta.insured_name or '(not yet extracted)'}",
            "",
        ]

    p = claim.policy
    lines += [
        "=== POLICY ===",
        f"policy_id: {p.policy_id}",
        f"policy_number: {p.policy_number}",
        f"policy_form: {p.policy_form}",
        f"jurisdiction_state: {p.jurisdiction_state}",
        "",
        "=== COVERAGES ===",
    ]
    for c in claim.coverages:
        lines += [
            f"- coverage_id: {c.coverage_id}",
            f"  type: {c.coverage_type}",
            f"  per_occurrence: ${c.limit_per_occurrence:,.0f}",
            (
                f"  per_person: ${c.limit_per_person:,.0f}"
                if c.limit_per_person is not None else "  per_person: (none)"
            ),
            f"  deductible: ${c.deductible:,.0f}",
        ]
    lines += [
        "",
        "=== LOSS ===",
        f"loss_date: {claim.loss_date}",
        "",
        "loss_facts:",
        claim.loss_facts,
        "",
    ]

    lines += ["=== UPSTREAM CONTEXT ==="]
    if upstream.liability is not None:
        u = upstream.liability
        lines += [
            "Liability:",
            f"  regime_statute: {u.regime_statute}",
            f"  insured_fault_pct: {u.insured_fault_pct}",
            f"  claimant_fault_pct: {u.claimant_fault_pct}",
            f"  operator_party_id: {u.operator_party_id}",
            f"  owner_party_id: {u.owner_party_id}",
            f"  recovery_bar_triggered: {u.recovery_bar_triggered}",
            f"  bar_basis: {u.bar_basis}",
            f"  apportionment_by_party_id: {dict(u.apportionment_by_party_id)}",
        ]
    else:
        lines.append("Liability: (no upstream snapshot — extractor should NOT infer fault)")
    if upstream.reserve is not None:
        r = upstream.reserve
        lines += [
            "Reserve:",
            f"  paid_indemnity_by_component: {dict(r.paid_indemnity_by_component)}",
            f"  outstanding_indemnity_by_component: {dict(r.outstanding_indemnity_by_component)}",
            f"  total_economic_loss: {r.total_economic_loss}",
        ]
    else:
        lines.append("Reserve: (no upstream snapshot)")
    if upstream.coverage is not None:
        c2 = upstream.coverage
        lines += [
            "Coverage:",
            f"  status: {c2.status}",
            f"  denial_basis: {c2.denial_basis}",
            f"  omnibus_roster_count: {len(c2.omnibus_roster)}",
            f"  cooperation_defense_window_open: {c2.cooperation_defense_window_open}",
        ]
    else:
        lines.append("Coverage: (no upstream snapshot)")
    lines.append("")

    lines += ["=== DOCUMENTS ==="]
    for d in claim.documents:
        lines += [
            f"--- document_id: {d.document_id} ---",
            f"type: {d.document_type}",
            f"received_date: {d.received_date}",
            f"source: {d.source}",
            "body:",
            d.body_text,
            "",
        ]

    return "\n".join(lines)


def _recovery_inputs_tool_schema() -> dict[str, Any]:
    """JSON schema that forces RecoveryInputs-shaped tool_use output."""
    return {
        "name": TOOL_NAME,
        "description": (
            "Emit the structured RecoveryInputs payload for this claim, "
            "extracted from documents, structured claim state, and "
            "upstream Liability/Reserve/Coverage snapshots. Do not emit "
            "doctrine resolution, layered targets, or recommendation; "
            "those belong to the policy engine and calculator. "
            "Conservative defaults when a field is not in the file — "
            "leave nullable fields null rather than guessing."
        ),
        "input_schema": RecoveryInputs.model_json_schema(),
    }


@dataclass
class RecoveryRunResult:
    """What `run_recovery` returns: validated assessment + extraction metadata."""

    assessment: RecoveryAssessment
    extractor_model: str
    extractor_attempts: int
    raw_inputs: RecoveryInputs


def extract_recovery_inputs(
    claim: SyntheticClaim,
    *,
    upstream: RecoveryUpstreamContext,
    claim_meta: Claim | None = None,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 16_000,
    max_retries: int = 1,
    anthropic_client: Anthropic | None = None,
) -> tuple[RecoveryInputs, str, int]:
    """LLM-extract RecoveryInputs from claim docs + upstream context.

    Returns (inputs, model, attempts)."""
    client = anthropic_client or Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    tool = _recovery_inputs_tool_schema()
    user_body = _render_for_extractor(claim, claim_meta, upstream)

    last_error: str | None = None
    for attempt in range(max_retries + 1):
        system_text = SYSTEM_PROMPT
        if last_error is not None:
            system_text = (
                SYSTEM_PROMPT
                + "\n\n--- PRIOR ATTEMPT REJECTED ---\n"
                + "Your previous output failed schema validation with this "
                + "error. Re-emit the tool call with the issue fixed.\n\n"
                + last_error
            )

        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system_text,
            tools=[tool],
            tool_choice={"type": "tool", "name": TOOL_NAME},
            messages=[{"role": "user", "content": user_body}],
        )

        tool_blocks = [b for b in resp.content if b.type == "tool_use"]
        if not tool_blocks:
            last_error = "Model did not emit a tool_use block. Emit the tool."
            continue

        tool_input = tool_blocks[0].input
        try:
            inputs = RecoveryInputs.model_validate(tool_input)
        except ValidationError as e:
            last_error = str(e)
            continue

        return inputs, resp.model, attempt + 1

    raise RuntimeError(
        f"Recovery extractor failed validation after {max_retries + 1} attempts. "
        f"Last error:\n{last_error}"
    )


def run_recovery(
    claim: SyntheticClaim,
    *,
    upstream: RecoveryUpstreamContext | None = None,
    claim_meta: Claim | None = None,
    program_config: ProgramConfig = DEFAULT_PROGRAM,
    request_id: str | None = None,
    reviewed_as_of: datetime | None = None,
    eval_seq: int = 1,
    trigger_name: str = DEFAULT_TRIGGER,
    trigger_event_date: date | None = None,
    examiner_id: str = "system",
    extractor_model: str = DEFAULT_MODEL,
    max_retries: int = 1,
    anthropic_client: Anthropic | None = None,
    inputs_override: RecoveryInputs | None = None,
) -> RecoveryRunResult:
    """End-to-end Recovery workflow.

    Extractor → policy engine → calculator → ledger → rationale. The
    RecoveryAssessment carries a templated rationale_text interpolated
    from the CalculationContext + DiligenceLedger.

    `inputs_override` short-circuits the extractor — useful for tests and
    the demo runner when RecoveryInputs is hand-constructed from a fixture.
    """
    rid = request_id or f"REC-{claim.request.request_id}"
    review_dt = reviewed_as_of or datetime.now(timezone.utc)
    trigger_dt = trigger_event_date or review_dt.date()
    claim_id = claim_meta.claim_id if claim_meta is not None else claim.request.claim_id
    upstream_ctx = upstream or RecoveryUpstreamContext()

    if inputs_override is not None:
        inputs = inputs_override
        model_used = "(override — no LLM call)"
        attempts = 0
    else:
        inputs, model_used, attempts = extract_recovery_inputs(
            claim,
            upstream=upstream_ctx,
            claim_meta=claim_meta,
            model=extractor_model,
            max_retries=max_retries,
            anthropic_client=anthropic_client,
        )

    resolution = apply_fl_recovery_doctrines(
        inputs, upstream_ctx, today=review_dt.date(),
    )

    ctx = compute_recovery(
        inputs, upstream_ctx, resolution, program_config, reviewed_as_of=review_dt,
    )

    ledger = build_diligence_ledger(ctx, trigger_name=trigger_name)

    rationale_text = render_recovery_rationale(
        ctx,
        ledger,
        claim_id=claim_id,
        eval_seq=eval_seq,
        trigger_name=trigger_name,
        trigger_event_date=trigger_dt,
        examiner_id=examiner_id,
    )

    assessment = RecoveryAssessment(
        request_id=rid,
        reviewed_as_of=review_dt,
        recommendation=ctx.recommendation,
        subrogation_lane=ctx.subrogation_lane,
        doctrinal_gates=resolution.gates,
        sol_regime=resolution.sol_regime,
        layered_targets=ctx.layered_targets,
        recoverable_basis=ctx.recoverable_basis,
        net_economics=ctx.net_economics,
        forum_routing=ctx.forum_routing,
        deadline_calendar=ctx.deadline_calendar,
        preservation_hold=ctx.preservation_hold,
        diligence_ledger=ledger,
        rationale_text=rationale_text,
        variance_flags=ctx.variance_flags,
        authority_tier_required=ctx.authority_routing,
        cross_stream_conflicts=ctx.cross_stream_conflicts,
    )

    return RecoveryRunResult(
        assessment=assessment,
        extractor_model=model_used,
        extractor_attempts=attempts,
        raw_inputs=inputs,
    )
