"""Liability workflow runtime — LLM extractor + Python policy engine +
apportionment calculator + diligence ledger + templated rationale.

Architecture (locked 2026-06-01, see docs/DECISIONS.md):

  1. Extractor: Anthropic tool_use forces a LiabilityInputs-shaped output
     from SyntheticClaim + Claim meta. Bounded to extraction; emits no
     percentages, no doctrine resolution, no apportionment.
  2. Policy engine: pure-Python apply_fl_doctrines consumes LiabilityInputs
     + ProgramConfig and produces a DoctrineResolution (regime, ceiling).
  3. Apportionment calculator: pure-Python compute_apportionment consumes
     LiabilityInputs + DoctrineResolution + ProgramConfig and produces a
     CalculationContext with apportionment, variance flags, authority
     routing, evidence pack classification, optional subro referral.
  4. Diligence ledger: build_diligence_ledger renders the Ruiz-discoverable
     artifact. Co-equal with apportionment, not a side effect.
  5. Rationale: render_liability_rationale interpolates everything above
     into a byte-reproducible audit-trail string.

Only step 1 talks to an LLM. Steps 2-5 are reproducible byte-for-byte.

Spec: docs/specs/liability-workflow.md.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from anthropic import Anthropic
from pydantic import ValidationError

from argos.ontology.types import Claim, SyntheticClaim
from argos.schemas.workflows.liability import (
    LiabilityAssessment,
    LiabilityInputs,
    ProgramConfig,
)
from argos.services.liability.apportionment_calculator import compute_apportionment
from argos.services.liability.constants import DEFAULT_PROGRAM
from argos.services.liability.diligence_ledger import build_diligence_ledger
from argos.services.liability.policy_engine import apply_fl_doctrines
from argos.services.liability.rationale import render_liability_rationale


DEFAULT_MODEL = "claude-sonnet-4-6"
TOOL_NAME = "emit_liability_inputs"
DEFAULT_TRIGGER = "INITIAL_APPORTIONMENT"


SYSTEM_PROMPT = """\
You are the Liability extractor for Argos, an AI-native claims operations \
layer for specialty property and casualty TPAs.

Your role is narrow and bounded: read the policy, the claim record, and \
every document provided, and emit a structured `LiabilityInputs` payload \
via the `emit_liability_inputs` tool.

What you DO:

1. Classify the `fact_pattern` from the documents into one of the controlled \
literals (rear_end, left_turn_across_traffic, lane_change, controlled_intersection, \
uncontrolled_intersection, parked_pullout, sideswipe, chain_reaction, \
pedestrian_in_crosswalk, pedestrian_mid_block, cyclist, parking_lot, other). \
The fact_pattern drives the anchor — pick the closest match. Use `other` \
only when none of the named patterns fit; that routes to human review.
2. Identify every party with a `party_id` (use document-stable identifiers) \
and a role. FL is several-only; identify Fabre non-parties as `fabre_non_party` \
when evidence supports their fault. Each party MUST have an \
`identity_evidence_cite` pointing to the source document.
3. Extract `owner_relationship` precisely. `owner_type` is one of \
`natural_person`, `commercial_lessor_graves` (commercial vehicle lessor — \
Graves-eligible), `business_not_in_leasing`, `self_insured_fleet`. \
`driver_is_owner` is true when the named driver IS the title-holding owner. \
`permissive_use_evidence_cite` quotes the source establishing permission.
4. Populate `evidence_items` for every load-bearing factual datum. Each \
item is: kind, source_doc_id, verbatim `quoted_span` (≥1 sentence from the \
source — Ruiz discoverability), contemporaneity in hours from loss, \
`fl_admissibility` (admissible / privileged_316_066 / physical_evidence_carveout \
/ chemical_test_carveout), `fault_direction` (insured_more_fault / \
claimant_more_fault / neutral), `weight_class` (hard_data / independent / \
party_admission / rebuttable_signal / credibility_only). \
Police-report STATEMENTS are privileged_316_066. Skid marks, debris, \
measurements are physical_evidence_carveout. BAC results are \
chemical_test_carveout. Most other evidence is admissible.
5. Populate `intoxication_evidence` if any BAC or impairment-observation \
appears in the file. `bac_value` as Decimal. `causation_to_fault_evidence_cites` \
ONLY if there is evidence linking impairment to the fault — the §768.36 \
second prong requires causation.
6. Populate `rear_end_rebuttal_evidence.category` only when the file \
documents one of the four Birge categories (mechanical_failure, \
sudden_stop_unexpected_place, sudden_lane_change_by_lead, \
illegal_improper_stop_by_lead). Otherwise category=none.
7. Populate `police_report_structured_fields` (FL HSMV 90010S) when a \
police report is on file. driver_action_codes_per_party is the list of \
integer codes per party_id. citation_issued_to is the party_ids cited.
8. Run `consistency_checks` over what is in the file: er_mechanism vs \
claimant statement, damage pattern vs claimed mechanism, police POI vs \
claimant statement. Use `gap` when a check can't run; `contradiction` \
ONLY when the file plainly shows contradiction (not inference). \
Contradictions widen the band and route to SIU — they are NOT a fault \
adjustment.
9. Populate `demand_received` if a demand letter / time-limit demand / \
policy-limits demand is in the file. `sufficient_evidence_assessment` is \
your call from the §624.155(4) totality — sufficient / insufficient / \
borderline. Provide reasoning. Do NOT set safe_harbor_clock_start_date \
unless a Notice of Filing CRN is on file or the file explicitly starts \
the 90-day clock.
10. Populate `ror_and_crn_state` when a Reservation of Rights, Civil \
Remedy Notice, or non-waiver / independent counsel correspondence is on \
file. cure_deadline is ror_sent_date + 60 days per §624.155(3) if a CRN \
exists.
11. Populate `prior_posture_history` with any prior apportionment \
postures the claim file shows (e.g. prior reserve memos, prior \
roundtable notes). This drives delta detection.

What you DO NOT do:

- You do NOT emit fault percentages. The calculator owns apportionment math.
- You do NOT decide which FL regime applies. The policy engine handles \
HB 837 vs pre-HB-837 vs med-mal carve-out from accrual_date + \
line_of_business.
- You do NOT decide whether vicarious cap or Graves preemption applies. \
You extract the structured facts; the policy engine resolves the doctrines.
- You do NOT silently weight contradictions as fault adjustments. \
Contradiction signals route to SIU via consistency_checks.
- You do NOT fabricate quoted_spans. Quote verbatim from the source.
- You do NOT classify §316.066(4) admissibility wrong. Statements made \
to the investigating officer on the accident report = privileged. \
Physical observations = carveout. BAC test results = chemical-test \
carveout. When in doubt on a per-datum classification, default to \
privileged_316_066.

FL-SPECIFIC NOTES:

- `accrual_date` is the loss date (or the date the cause of action accrued \
where different). This gates HB 837 (2023-03-24 effective).
- `line_of_business` is `auto_bi` for third-party bodily injury under an \
auto policy. `med_mal` keeps pure comparative.
- `owner_type=commercial_lessor_graves` is for rental/leasing companies \
where the lessor is not the driver. Graves preempts vicarious liability \
unless negligent maintenance / negligent rental.
- For chain-reaction or multi-claimant scenarios, list every party \
including drivers, passengers, owners, and Fabre non-parties.

Emit via `emit_liability_inputs`. The tool's input_schema is the contract \
— outputs that violate it are rejected upstream.
"""


def _render_for_extractor(claim: SyntheticClaim, claim_meta: Claim | None) -> str:
    """Render the SyntheticClaim and Claim meta for the extractor user-message body."""
    lines: list[str] = []

    if claim_meta is not None:
        lines += [
            "=== CLAIM RECORD ===",
            f"claim_id: {claim_meta.claim_id}",
            f"opened_date: {claim_meta.opened_date}",
            f"status: {claim_meta.status}",
            f"severity_tier_summary: {claim_meta.severity_tier_summary}",
            f"litigation_flag: {claim_meta.litigation_flag}",
            f"rep_flag: {claim_meta.rep_flag}",
            f"complaint_flag: {claim_meta.complaint_flag}",
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
    lines += ["", "=== LOSS ===", f"loss_date: {claim.loss_date}", "", "loss_facts:", claim.loss_facts, ""]

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


def _liability_inputs_tool_schema() -> dict[str, Any]:
    """JSON schema that forces LiabilityInputs-shaped tool_use output."""
    return {
        "name": TOOL_NAME,
        "description": (
            "Emit the structured LiabilityInputs payload for this claim, "
            "extracted from documents and structured claim state. Do not "
            "emit fault percentages; the calculator handles apportionment "
            "math. Conservative defaults when a field is not in the file."
        ),
        "input_schema": LiabilityInputs.model_json_schema(),
    }


@dataclass
class LiabilityRunResult:
    """What `run_liability` returns: validated assessment + extraction metadata."""

    assessment: LiabilityAssessment
    extractor_model: str
    extractor_attempts: int
    raw_inputs: LiabilityInputs


def extract_liability_inputs(
    claim: SyntheticClaim,
    *,
    claim_meta: Claim | None = None,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 16_000,
    max_retries: int = 1,
    anthropic_client: Anthropic | None = None,
) -> tuple[LiabilityInputs, str, int]:
    """LLM-extract LiabilityInputs from claim documents. Returns (inputs, model, attempts)."""
    client = anthropic_client or Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    tool = _liability_inputs_tool_schema()
    user_body = _render_for_extractor(claim, claim_meta)

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
            inputs = LiabilityInputs.model_validate(tool_input)
        except ValidationError as e:
            last_error = str(e)
            continue

        return inputs, resp.model, attempt + 1

    raise RuntimeError(
        f"Liability extractor failed validation after {max_retries + 1} attempts. "
        f"Last error:\n{last_error}"
    )


def run_liability(
    claim: SyntheticClaim,
    *,
    claim_meta: Claim | None = None,
    program_config: ProgramConfig = DEFAULT_PROGRAM,
    request_id: str | None = None,
    reviewed_as_of: datetime | None = None,
    eval_seq: int = 1,
    trigger_name: str = DEFAULT_TRIGGER,
    trigger_event_date: date | None = None,
    examiner_id: str = "system",
    gross_exposure: Decimal = Decimal("0"),
    extractor_model: str = DEFAULT_MODEL,
    max_retries: int = 1,
    anthropic_client: Anthropic | None = None,
    inputs_override: LiabilityInputs | None = None,
) -> LiabilityRunResult:
    """End-to-end Liability workflow.

    Extractor → policy engine → calculator → ledger → rationale. The
    LiabilityAssessment has a templated audit-trail rationale_text
    interpolated from the CalculationContext + DiligenceLedger.

    `inputs_override` short-circuits the extractor — useful for tests and
    the demo runner when LiabilityInputs is hand-constructed from a fixture.
    """
    rid = request_id or f"LIA-{claim.request.request_id}"
    review_dt = reviewed_as_of or datetime.now(timezone.utc)
    trigger_dt = trigger_event_date or review_dt.date()
    claim_id = claim_meta.claim_id if claim_meta is not None else claim.request.claim_id

    if inputs_override is not None:
        inputs = inputs_override
        model_used = "(override — no LLM call)"
        attempts = 0
    else:
        inputs, model_used, attempts = extract_liability_inputs(
            claim,
            claim_meta=claim_meta,
            model=extractor_model,
            max_retries=max_retries,
            anthropic_client=anthropic_client,
        )

    # Policy engine pre-pass (regime + ceiling, no apportionment yet)
    apply_fl_doctrines(inputs, program_config)

    # Apportionment calculator runs the policy engine internally a second
    # time with computed fault percentages to detect bar conditions.
    ctx = compute_apportionment(
        inputs,
        program_config,
        request_id=rid,
        reviewed_as_of=review_dt,
        gross_exposure=gross_exposure,
    )

    ledger = build_diligence_ledger(ctx, trigger_name=trigger_name)

    rationale_text = render_liability_rationale(
        ctx,
        ledger,
        claim_id=claim_id,
        eval_seq=eval_seq,
        trigger_name=trigger_name,
        trigger_event_date=trigger_dt,
        examiner_id=examiner_id,
    )

    assessment = LiabilityAssessment(
        request_id=rid,
        reviewed_as_of=review_dt,
        apportionment=ctx.apportionment,
        applicable_regime=ctx.resolution.applicable_regime,
        exposure_ceiling=ctx.resolution.exposure_ceiling,
        rationale=ctx.rationale,
        diligence_ledger=ledger,
        rationale_text=rationale_text,
        variance_flags=ctx.variance_flags,
        authority_tier_required=ctx.authority_routing,
        evidence_pack_classification=ctx.evidence_pack,
        subro_referral=ctx.subro_referral,
    )

    return LiabilityRunResult(
        assessment=assessment,
        extractor_model=model_used,
        extractor_attempts=attempts,
        raw_inputs=inputs,
    )
