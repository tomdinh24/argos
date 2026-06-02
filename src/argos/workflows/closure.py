"""Closure workflow runtime — LLM extractor + Python policy engine +
assessment calculator + diligence ledger + templated rationale.

Architecture (locked 2026-06-02, see docs/DECISIONS.md):

  1. Extractor: Anthropic tool_use forces a ClosureInputs-shaped output
     from SyntheticClaim + Claim meta + all upstream snapshots
     (Coverage/Liability/Reserve/Recovery/Brief). Bounded to extraction;
     emits no gate evaluation, no recommendation, no rationale.
  2. Policy engine: apply_fl_closure_gates consumes ClosureInputs +
     ClosureUpstreamContext and produces a DoctrineResolution
     (26 gates + variance flags + OIR classification + preservation
     until-date).
  3. Calculator: build_closure_assessment composes inputs + upstream +
     doctrine + ProgramConfig into a ClosureAssessment with
     11-literal recommendation, tier-capped ready_probability, ranked
     blocking defects, bifurcated indemnity/defense status, preservation
     plan, authority routing.
  4. Diligence ledger: enrich_diligence_ledger fills per-lien /
     per-CRN / per-notice records the calculator skeleton left empty.
     Boecher/Ruiz-discoverable artifact, co-equal with recommendation.
  5. Rationale: finalize_assessment stamps the templated rationale text
     onto both the assessment and the ledger.

Only step 1 talks to an LLM. Steps 2-5 are reproducible byte-for-byte.

Spec: docs/specs/closure-workflow.md.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from anthropic import Anthropic
from pydantic import ValidationError

from argos.ontology.types import Claim, SyntheticClaim
from argos.schemas.workflows.closure import (
    ClosureAssessment,
    ClosureInputs,
    ClosureProgramConfig,
    ClosureUpstreamContext,
)
from argos.services.closure import (
    DEFAULT_PROGRAM,
    apply_fl_closure_gates,
    build_closure_assessment,
    enrich_diligence_ledger,
    finalize_assessment,
)


DEFAULT_MODEL = "claude-sonnet-4-6"
TOOL_NAME = "emit_closure_inputs"
DEFAULT_TRIGGER = "INITIAL_CLOSURE_EVALUATION"


SYSTEM_PROMPT = """\
You are the Closure extractor for Argos, an AI-native claims operations \
layer for specialty property and casualty TPAs.

Your role is narrow and bounded: read the policy, the claim record, every \
document provided, and the upstream Coverage/Liability/Reserve/Recovery/Brief \
snapshots, and emit a structured `ClosureInputs` payload via the \
`emit_closure_inputs` tool.

What you DO:

1. Extract `loss_date` and `claim_first_actual_notice_date`. These anchor \
HB 837 safe-harbor windows and the preservation-floor SOL calculation.
2. Set `intended_closure_intent`: `with_payment` when there is settlement \
activity or paid indemnity, `without_payment` when the file points to a \
declination, `tbd` when neither posture is asserted in the record.
3. Set `coverage_decision` exactly: `granted`, `ror`, `denied`, or \
`uncommitted`. Mirror the upstream Coverage snapshot when available; only \
override on documented evidence newer than the snapshot.
4. Populate `denial_letter_audit` only when the file shows a denial letter \
on file. Verbatim-check that the letter cites the specific policy \
provision, the facts giving rise to denial, and the applicable law. \
Conservative defaults: leave `cites_*` false when the citation is not in \
the letter body.
5. Set `liability_apportionment_committed` to mirror the upstream \
Liability snapshot. Do not re-extract fault percentages.
6. Populate `boston_old_colony_diligence`. Each of the five preconditions \
flips true ONLY when the record documents the act: insured notified of \
settlement opportunities, insured warned of excess exposure, facts \
investigated, settlement offers received fair consideration, decision \
reflects a reasonable prudent person. Defaults to false on undocumented \
preconditions.
7. Populate `powell_analysis`. `liability_clear` and \
`damages_plausibly_exceed_limits` are factual reads from the file. \
`affirmative_policy_limits_offer_made` requires documented evidence of a \
sua-sponte limits tender by the carrier. \
`why_powell_does_not_apply_memo_on_file` requires a memo expressly \
arguing why Powell does not apply (disputed coverage, etc.).
8. Populate `macola_signals` only when all three are documented: Powell \
duty arguably triggered earlier, tender came only after suit/demand \
pressure, close memo treats payment as resolution.
9. Populate `harvey_communication_log` with `received_count`, \
`answered_count`, `relayed_to_insured_count`. Count claimant \
communications in the documents list; default to 0 when none.
10. Populate `open_crns`. Each CRN: crn_id (the DFS filing number), \
dfs_filing_date, days_since_dfs_filing, alleged_statutory_violations \
(list of citation strings extracted verbatim), cure_status \
(`no_open_crn`, `cured`, `uncured`, `partial_cure`).
11. Set `third_party_safe_harbor_tender_made` true ONLY when the file \
documents a §624.155(4) policy-limits tender within the 90-day window. \
Default false.
12. Populate `multi_claimant_state`. `is_multi_claimant` is true when the \
occurrence shows >1 claimant. `competing_demands_exceed_aggregate` \
requires documented aggregate erosion. `interpleader_filed` and \
`binding_arbitration_submitted` require documented procedural artifacts. \
`global_tender_letter_sent_to_all_claimants` / \
`per_claimant_responses_logged` / `priority_memo_on_file` / \
`insured_notice_of_strategy_on_file` each flip true only on documented \
artifact.
13. Populate `section_627_4137_state` from the affidavit-of-coverage \
correspondence chain.
14. Populate `pip_bill_ledger` from PIP bills in the file. Each PIP bill: \
bill_id, billed_amount (Decimal), received_date, status \
(`paid_within_30`, `denied_within_30`, `open_within_30`, \
`open_past_30`, `eob_issued`), days_since_received.
15. Populate `settlement` from any signed settlement / release / tender \
correspondence. agreement_date, agreement_amount (Decimal), \
release_executed_date, release_includes_hold_harmless_for_liens, \
check_tendered_date, check_amount (Decimal).
16. Populate `exposure_status` per the per-coverage-section closure \
ledger. True means the exposure is closed/denied/paid OR structurally \
absent from the policy; false means the exposure is open.
17. Populate `liens`. Each lien record: kind (one of the LienKind \
literals), payer_name, claimed_amount (Decimal), notice_sent_date, \
notice_sent_certified_mail, response_received_date, \
release_letter_on_file, release_letter_doc_id, satisfaction_amount \
(Decimal), status (one of LienResolutionStatus literals), county (for \
hospital_county_specific).
18. Populate `section_111_log` only when a Section 111 TPOC transmit has \
been attempted. Each: tpoc_date, tpoc_amount (Decimal), \
transmit_success, transmit_confirmation_id, transmit_date.
19. Set the Medicare/Medicaid/employment/ERISA/VA-TRICARE eligibility \
booleans from documented evidence (CMS Section 111 query response, \
state Medicaid card, employer wage statements, SPD, VA/TRICARE \
correspondence). Defaults to false when no evidence is in the file.
20. Populate `hospital_lien_county_search_status` per the per-county \
search artifact (Shands v. Mercury). `searched_clean` requires a dated \
recorded-lien search by county of treatment. `searched_lien_found` \
requires a recorded-lien hit.
21. Populate `collateral_source_notice_sent_date` and \
`collateral_source_responses_logged` from the §768.76 notice correspondence \
chain.
22. Populate `open_obrs`. Each OutboundRequest: obr_id, legal_weight \
(`legally_required` / `informational` / `n_a`), cite, days_open.
23. Set `agent_action_ledger_complete` per the upstream Brief snapshot. \
v1: false → warning only, not blocker.
24. Set `interpleader_indemnity_deposited` and \
`underlying_tort_actions_unresolved` from the file's litigation posture.
25. Populate `last_cms_cpn_date`, `last_phi_authorization_end_date`, \
`tpa_contract_termination_date`, `sol_outer_bound_date` when documented. \
These compose the preservation-until-date.

What you DO NOT do:

- You do NOT evaluate the closure gates. The policy engine owns all 26 \
gate evaluations.
- You do NOT decide the OIR classification, the recommendation, the \
ready_probability, or the authority tier. The calculator owns all of \
that.
- You do NOT compute the preservation-until-date. The policy engine + \
calculator derive it from your extracted anchors.
- You do NOT fabricate dates, dollar amounts, CRN IDs, or doc IDs. Leave \
nullable fields null when not in the file.
- You do NOT re-extract fault percentages, reserve breakdowns, or \
liability regime — those come from the upstream snapshots.

FL-SPECIFIC NOTES:

- HB 837 (effective 2023-03-24): §624.155(4) 90-day third-party safe \
harbor; §624.155(6) multi-claimant 90-day safe harbor.
- §627.4265: 20-day post-settlement tender window. 12% statutory \
interest accrues after.
- §627.736(4)(b): each PIP bill has its own 30-day pay-or-deny clock.
- §768.76: 30-day collateral-source-notice waiver window.
- Shands Teaching Hosp. v. Mercury: county-of-treatment hospital-lien \
search required (§713.50 struck down).
- 42 U.S.C. §1395y(b)(8): Section 111 TPOC report required when \
settlement ≥ $750 and claimant Medicare-eligible.
- Gallardo v. Marstiller (2022): FL Medicaid lien attaches to past + \
future medicals.
- US Airways v. McCutchen / Sereboff: self-funded ERISA preempts \
§768.76 waiver and FL common-fund.

Emit via `emit_closure_inputs`. The tool's input_schema is the contract \
— outputs that violate it are rejected upstream.
"""


def _render_for_extractor(
    claim: SyntheticClaim,
    claim_meta: Claim | None,
    upstream: ClosureUpstreamContext,
) -> str:
    """Render claim + upstream snapshots for the extractor user-message body."""
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
    if upstream.coverage is not None:
        c2 = upstream.coverage
        lines += [
            "Coverage:",
            f"  decision_committed: {c2.decision_committed}",
            f"  decision: {c2.decision}",
            f"  denial_letter_on_file: {c2.denial_letter_on_file}",
            f"  denial_letter_cites_policy_provision: "
            f"{c2.denial_letter_cites_policy_provision}",
            f"  denial_letter_cites_facts: {c2.denial_letter_cites_facts}",
            f"  denial_letter_cites_law: {c2.denial_letter_cites_law}",
            f"  omnibus_roster_size: {c2.omnibus_roster_size}",
        ]
    else:
        lines.append("Coverage: (no upstream snapshot)")
    if upstream.liability is not None:
        u = upstream.liability
        lines += [
            "Liability:",
            f"  apportionment_committed: {u.apportionment_committed}",
            f"  regime_statute: {u.regime_statute}",
            f"  insured_fault_pct: {u.insured_fault_pct}",
            f"  claimant_fault_pct: {u.claimant_fault_pct}",
            f"  multi_claimant_occurrence: {u.multi_claimant_occurrence}",
            f"  competing_demands_exceed_aggregate: "
            f"{u.competing_demands_exceed_aggregate}",
            f"  first_actual_notice_date: {u.first_actual_notice_date}",
            f"  powell_duty_potentially_triggered: {u.powell_duty_potentially_triggered}",
            f"  tender_made: {u.tender_made}",
        ]
    else:
        lines.append("Liability: (no upstream snapshot)")
    if upstream.reserve is not None:
        r = upstream.reserve
        lines += [
            "Reserve:",
            f"  total_paid: {r.total_paid}",
            f"  reserve_balance: {r.reserve_balance}",
            f"  paid_indemnity_by_component: {dict(r.paid_indemnity_by_component)}",
            f"  outstanding_indemnity_by_component: "
            f"{dict(r.outstanding_indemnity_by_component)}",
            f"  pip_bill_ledger_count: {len(r.pip_bill_ledger)}",
        ]
    else:
        lines.append("Reserve: (no upstream snapshot)")
    if upstream.recovery is not None:
        rc = upstream.recovery
        lines += [
            "Recovery:",
            f"  pursuit_decision_committed: {rc.pursuit_decision_committed}",
            f"  decision: {rc.decision}",
            f"  subro_only_file_state: {rc.subro_only_file_state}",
        ]
    else:
        lines.append("Recovery: (no upstream snapshot)")
    if upstream.brief is not None:
        b = upstream.brief
        lines += [
            "Brief:",
            f"  open_obrs_with_legal_weight: {b.open_obrs_with_legal_weight}",
            f"  open_obrs_informational: {b.open_obrs_informational}",
            f"  agent_action_count: {b.agent_action_count}",
            f"  claim_first_notice_date: {b.claim_first_notice_date}",
        ]
    else:
        lines.append("Brief: (no upstream snapshot)")
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


def _closure_inputs_tool_schema() -> dict[str, Any]:
    """JSON schema that forces ClosureInputs-shaped tool_use output."""
    return {
        "name": TOOL_NAME,
        "description": (
            "Emit the structured ClosureInputs payload for this claim, "
            "extracted from documents, structured claim state, and "
            "upstream Coverage/Liability/Reserve/Recovery/Brief "
            "snapshots. Do not evaluate gates, classify OIR, or pick "
            "recommendation; those belong to the policy engine and "
            "calculator. Conservative defaults when a field is not in "
            "the file — leave nullable fields null rather than guessing."
        ),
        "input_schema": ClosureInputs.model_json_schema(),
    }


@dataclass
class ClosureRunResult:
    """What `run_closure` returns: validated assessment + extraction metadata."""

    assessment: ClosureAssessment
    extractor_model: str
    extractor_attempts: int
    raw_inputs: ClosureInputs


def extract_closure_inputs(
    claim: SyntheticClaim,
    *,
    upstream: ClosureUpstreamContext,
    claim_meta: Claim | None = None,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 16_000,
    max_retries: int = 1,
    anthropic_client: Anthropic | None = None,
) -> tuple[ClosureInputs, str, int]:
    """LLM-extract ClosureInputs from claim docs + upstream context.

    Returns (inputs, model, attempts).
    """
    client = anthropic_client or Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    tool = _closure_inputs_tool_schema()
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
            inputs = ClosureInputs.model_validate(tool_input)
        except ValidationError as e:
            last_error = str(e)
            continue

        return inputs, resp.model, attempt + 1

    raise RuntimeError(
        f"Closure extractor failed validation after {max_retries + 1} attempts. "
        f"Last error:\n{last_error}",
    )


def run_closure(
    claim: SyntheticClaim,
    *,
    upstream: ClosureUpstreamContext | None = None,
    claim_meta: Claim | None = None,
    program_config: ClosureProgramConfig = DEFAULT_PROGRAM,
    request_id: str | None = None,
    reviewed_as_of: datetime | None = None,
    extractor_model: str = DEFAULT_MODEL,
    max_retries: int = 1,
    anthropic_client: Anthropic | None = None,
    inputs_override: ClosureInputs | None = None,
    today: date | None = None,
    agent_action_ledger_complete: bool | None = None,
) -> ClosureRunResult:
    """End-to-end Closure workflow.

    Extractor → policy engine → calculator → ledger → rationale. The
    ClosureAssessment carries a templated rationale_text and an enriched
    diligence ledger.

    `inputs_override` short-circuits the extractor — useful for tests
    and the demo runner when ClosureInputs is hand-constructed.
    """
    rid = request_id or f"CLO-{claim.request.request_id}"
    review_dt = reviewed_as_of or datetime.now(timezone.utc)
    today_date = today or review_dt.date()
    upstream_ctx = upstream or ClosureUpstreamContext()

    if inputs_override is not None:
        inputs = inputs_override
        model_used = "(override — no LLM call)"
        attempts = 0
    else:
        inputs, model_used, attempts = extract_closure_inputs(
            claim,
            upstream=upstream_ctx,
            claim_meta=claim_meta,
            model=extractor_model,
            max_retries=max_retries,
            anthropic_client=anthropic_client,
        )

    # The runner-level audit-log probe is authoritative over whatever
    # the extractor guessed about ledger completeness. Pass-through `None`
    # keeps the extractor's value (used by direct callers without a log).
    if agent_action_ledger_complete is not None:
        inputs = inputs.model_copy(update={
            "agent_action_ledger_complete": agent_action_ledger_complete,
        })

    doctrine = apply_fl_closure_gates(
        inputs, upstream_ctx, program_config, today=today_date,
    )

    assessment = build_closure_assessment(
        inputs,
        upstream_ctx,
        program_config,
        doctrine,
        request_id=rid,
        today=today_date,
        reviewed_as_of=review_dt,
    )

    enriched_ledger = enrich_diligence_ledger(assessment, inputs)
    assessment = assessment.model_copy(update={"diligence_ledger": enriched_ledger})

    final = finalize_assessment(assessment)

    return ClosureRunResult(
        assessment=final,
        extractor_model=model_used,
        extractor_attempts=attempts,
        raw_inputs=inputs,
    )
