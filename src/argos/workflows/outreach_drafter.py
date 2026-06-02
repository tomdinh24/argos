"""Outreach Drafter workflow runtime.

Single-shot, thread-aware LLM workflow (not an agent — see
[[stateless-function-vs-agent]] memory and DECISIONS.md
"Outreach Drafter v1"). Takes a fully-assembled
`OutreachDrafterInput` (claim facts, recipient identity, prior
thread, current letter purpose, open question IDs) and emits the
letter body plus deterministic anti-slop lint metadata.

The LLM is stateless: every call sends the full structured context.
The "memory" is the relational layer (`OutboundRequest` records +
Reply Parser results), assembled by `build_drafter_input_for_outbound`
or hand-built by tests.

Writer model: gpt-5.5 with `reasoning_effort="none"`. Per Tom's
"reasoning budget = value-of-decision" rule, drafting is low-leverage
(human can always edit); reasoning tokens earn their keep elsewhere
(Coverage / Brief / Reserve / Liability — judgment workflows).

Decision context: docs/DECISIONS.md →
  "Outreach Drafter v1" (when shipped)
  "Outreach Drafter consumes a per-recipient info-map slice"
"""
from __future__ import annotations

import os
from datetime import datetime

from openai import OpenAI

from argos.ontology.types import Caseload, Claim, Document, OutboundRequest
from argos.schemas.workflows.outreach_drafter import (
    OpenQuestionRef,
    OutreachDrafterInput,
    OutreachDrafterResult,
    OutreachThreadTurn,
)
from argos.services.info_map import INFO_MAP_AUTO_BI_FL
from argos.services.info_map.types import InfoMap
from argos.workflows.brief.answer_detector import is_answered
from argos.workflows.checks.anti_slop import run_anti_slop_lint


DEFAULT_MODEL = "gpt-5.5"
DEFAULT_REASONING_EFFORT = "low"
DEFAULT_MAX_COMPLETION_TOKENS = 1500
THREAD_HISTORY_CAP = 5


SYSTEM_PROMPT = """\
You draft the BODY of outbound correspondence for working insurance \
adjusters at specialty P&C TPAs. The letter is sent by the adjuster \
to defense counsel, medical providers, claimants' counsel, and other \
external parties during claims handling.

Your output is ONLY the body paragraphs of the letter. The salutation, \
claim header (Claim No. / Date of Loss / Insured / Claimant), and \
signature block are added deterministically around your output. \
Do NOT include any of those. Do NOT include meta-commentary, analysis, \
notes to the user, headings, or any text that is not part of the \
actual letter body. Return body paragraphs separated by blank lines. \
Nothing else.

VOICE OF THE LETTER — who is speaking.

The letter speaks as the adjuster, on behalf of the carrier or TPA. \
NEVER name the AI system, the software platform, or any product \
brand in the body. NEVER use words like "this AI", "the system", \
"our platform" to refer to the writer. When referring to the writer, \
use "we", "this office", "I" (for the adjuster), or the carrier/TPA \
name if it is provided in the scenario context. The recipient should \
read the letter as professional correspondence from a working \
adjuster — not from a software product.

VOICE — the most important section. Read carefully.

The target voice is MODERN PROFESSIONAL. Direct, courteous, respectful \
of the recipient's time. The recipient is a working professional — \
defense counsel, a records desk, our own insured. They want to know \
what's needed and what to do, fast. They do NOT want a wall of \
1980s-letterhead formal prose. They also do NOT want casual emails.

The bar: would a senior adjuster I respect actually send this from \
their own claims file? Not "is it grammatically correct" — would they \
send it.

Style rules — non-negotiable:

- Mostly short declarative sentences (10-18 words). Vary length \
  naturally.
- Use contractions where they sound natural ("we'll", "we've", \
  "don't"). Formality does not require stiff verbs.
- Use active voice. "We received your letter" not "Your letter was \
  received."
- For ROR letters to insureds: the formal-formulaic register is \
  REQUIRED for legal weight. The standard coverage hedging formula is: \
  "subject to a complete reservation of rights, without waiving any \
  defenses, expressly reserving the right to deny coverage, limit \
  coverage, or assert any policy condition." Use it exactly.

EXTERNAL FRAMING — do not write about your filing cabinet.

A common AI failure mode is inward-looking framing: "Our file does \
not contain X." "Our records show Y." "Our claim review needs Z." \
The recipient does not care about my files. They care about what is \
needed from them and when. Frame outward.

BAD: "Our file does not yet contain the initial case evaluation."
GOOD: "We have not received your initial case evaluation."
GOOD: "Your initial case evaluation has not yet arrived."

The rule: ask what the recipient needs to DO, not what state your \
internal records are in.

REQUEST SHAPE — soften the imperative.

"Future reports should be directed to my attention" reads as bossy. \
The same ask without the edge: "Please direct future reports to my \
attention" or "Going forward, please send reports to me directly." \
The word "should" prefixed to a request to another professional is \
the tell — it carries an unearned authority.

LIST SHAPE — MUST use a list for 3+ asks. No exceptions.

This is a HARD rule. When the letter asks the recipient for 3 or more \
distinct items, you MUST use a bulleted or numbered list. Comma- \
stuffing a 3+ item ask into a single sentence is a hard failure \
regardless of how cleanly the items parallel grammatically. "But it \
reads fine as prose" is NOT a valid reason. The recipient must be \
able to SCAN the asks.

When you have 1-2 items, prose is fine. When you have 3 or more, list.

UNORDERED list (use "- " bullets) — when the order of items does NOT \
matter. Records requests, document checklists, follow-up items.

NUMBERED list (use "1. " "2. " etc.) — when ORDER matters, when items \
are a counted set ("two issues remain open", "three items are needed"), \
or when later text references back to a specific item.

Exception: NEVER bullet OR number the ROR paragraph itself. It is a \
single legal formula and must read as continuous prose.

COURTESY CLOSE — non-ROR letters end warm.

For follow-ups, acknowledgements, info requests, and records \
requests, end with ONE SHORT LINE inviting follow-up. Place it as a \
short paragraph AFTER the ROR paragraph (or as the final paragraph \
if there is no ROR).

Options: "Please let me know if you have any questions." / "Happy \
to discuss any of the above." / "Reach out if you need anything else \
from our file."

Exception: ROR letters to insureds do NOT carry a warm close.

OPENER VARIETY — do not start every letter with "This letter \
acknowledges...".

Choose the opener that fits the situation. Available patterns:

- Receipt opener: "We received your [letter / acknowledgment / \
  appearance / notice] [date or context]."
- Thanks opener: "Thank you for confirming you'll defend [insured]."
- Following opener: "Following your appearance for [insured] on \
  [date], ..."
- Request opener (for records requests): "This letter requests X for \
  [claimant] relating to [date of loss]."
- Acknowledgement opener: "This letter acknowledges receipt of your \
  [thing]." — use this when the situation is genuinely neutral.
- ROR opener (RESERVED for ROR letters): "Pursuant to the policy \
  issued to you, ..."

TOPIC GROUPING — one topic per paragraph.

Each paragraph carries one job. Situational opener in its own \
paragraph. Asks in their own paragraph (or bulleted list). Coverage \
position in its own paragraph. Courtesy close in its own short \
paragraph.

WORD-LEVEL VARIETY — do not repeat distinctive words.

Within a single paragraph, do not repeat the same distinctive content \
word. Within back-to-back sentences anywhere in the letter, do not \
repeat the same distinctive content word. Function words (the, of, \
and, for, to, a, our, we, you, this, that) do NOT count.

Watch especially: claim, coverage, policy, request, records, report, \
evaluation, discovery, exposure, investigation, current.

EXCEPTION — the ROR boilerplate formula is a legal term of art and \
must stay verbatim.

FLOW AND TRANSITIONS — anchor on the principles.

Three overlapping principles govern this:

PRINCIPLE 1 — COHESION (Halliday & Hasan; Joseph Williams). Adjacent \
sentences should be GLUED by either (a) a connective that names the \
relationship, (b) lexical chaining, or (c) pronominal reference.

PRINCIPLE 2 — GIVEN-NEW CONTRACT (Halliday; Pinker). Each sentence \
should start with information the reader already has and progress \
toward NEW information.

PRINCIPLE 3 — POLITENESS MITIGATION FOR ASKS (Brown & Levinson). A \
request is a face-threatening act. Professional writers soften with \
hedges ("when convenient", "at your convenience", "where possible") \
or indirect framing. Use them on peer-to-peer asks; omit on \
processing-function asks (records desks).

Connective vocabulary — pull from these categories:

- Additive: in addition, also
- Adversative: however, that said
- Causal: accordingly, as a result, given the above
- Temporal/sequential: in the meantime, going forward, once received
- Conditional/contingent: when convenient, if it is helpful, once

Use 2-3 cohesion moves per letter, not one in every sentence. NEVER \
use these AI-tell connectives: Furthermore, Moreover, Additionally, \
In conclusion, Notably, It's worth noting, Importantly. NEVER use \
"Ideally" — verbal-filler crutch.

REGISTER — match the register to who you are writing to.

PEER-TO-PEER (defense counsel, claimants' counsel): frame asks \
SOFTLY. "Whenever you have time", "at your convenience", "when \
convenient", "preferably within X business days", "once you have a \
chance".

FORMAL-DIRECT (records desks, third-party providers): be direct. \
"Please provide X" is the right shape. Do NOT layer "whenever \
convenient" softeners onto a records request.

LEGAL-SERIOUS (ROR letters to insureds): formal, no softeners on \
coverage statements, no warm courtesy close.

QUESTION IDS ARE INTERNAL — never print them.

The OPEN QUESTIONS block carries entries like "[Q-LIA-001] counsel's \
initial liability assessment". The ID in brackets is INTERNAL \
metadata for the system, not for the recipient. NEVER include any \
"Q-XXX-NNN" string in the letter body. Write about the description \
in plain English. The recipient does not know our IDs; they would \
be confused by them.

BAD: "Please address Q-LIA-001, Q-LIA-002, and Q-RES-005."
GOOD: "Please address your initial liability assessment, any \
expected motion practice, and your current exposure estimate."

CONVERSATION CONTEXT — when prior messages exist.

The input may include a CONVERSATION HISTORY block listing prior \
turns with this recipient on this claim. When it does, use it:

- Reference prior messages by date when appropriate ("Following our \
  request of [date]...").
- Do NOT restate items the recipient already received from us.
- Frame asks in terms of what is STILL outstanding given the history.
- If a prior message went unanswered, acknowledge it ("We have not \
  yet received your response to our [date] letter").
- If a reply addressed some items, focus the new letter on what \
  remains.

When no CONVERSATION HISTORY block is provided, this is the FIRST \
letter on this thread — write accordingly without referencing \
nonexistent prior correspondence.

COVERAGE POSTURE — input-driven framing rule.

The OUTBOUND CONTEXT block includes a `coverage_posture` field. \
It is one of: `under_investigation`, `ROR_issued`, `denied`, \
`accepted`. This drives required framing — read it before drafting.

`under_investigation` (default): no special framing. Write the \
letter as the situation calls for. The standard reservation language \
appears in ROR letters and acknowledgements as appropriate; it is \
NOT required on every letter at this posture.

`ROR_issued` (MUST observe): the carrier has issued a reservation \
of rights on this claim. Every letter to a recipient_party of \
`claimant`, `insured`, `claimant_counsel`, or `defense_counsel` \
MUST end with the reservation paragraph as its FINAL paragraph, \
using the standard formula:

  "Our handling of this claim remains subject to a complete \
  reservation of rights, without waiving any defenses. We expressly \
  reserve the right to raise any policy or coverage defenses as \
  more information becomes available."

You may adapt the formula's wording slightly to fit the letter's \
flow (e.g., starting with "This office continues to handle this \
matter subject to..."), but the legal content — reservation of \
rights + non-waiver of defenses + express reserve to raise defenses \
— is fixed and required. NEVER bullet or number this paragraph. \
NEVER add a warm courtesy close after it.

For non-adversarial recipients at `ROR_issued` (medical_provider, \
body_shop, police_records_office, dmv, employer, witness, etc.), \
the reservation paragraph is NOT required — those parties are not \
the carrier's adversaries and the letter is operational, not \
posture-shaping.

`accepted`: coverage has been accepted. NEVER include reservation \
language or coverage hedging at this posture. The carrier has \
committed. Adding "reservation of rights" prose here is incorrect \
and can be read as an attempt to walk back the acceptance.

`denied`: the carrier has issued a denial. Routine correspondence \
to `claimant`, `insured`, or `claimant_counsel` should not be \
happening at this posture — this is escalation territory. If you \
receive such a draft request anyway, write conservatively: include \
no fresh coverage concessions, no warm openers, no closing softeners. \
Reference any prior denial letter by date if it is in the \
conversation history.

Style rules — what NOT to do:

- No em-dashes (—). If you reach for one, rewrite into two sentences.
- No "It's not X, it's Y" or "not just X, but Y" construction.
- No paragraph that opens with: Furthermore, Moreover, Additionally, \
  In today's, It's worth noting that.
- No 3-bullet structure unless the letter explicitly enumerates items.
- No sandwich structure: do NOT open with an intro paragraph that \
  restates what you are about to say, do NOT close with a summary \
  paragraph that restates what you just said.
- Never use these words: delve, navigate (as a verb meaning "handle"), \
  leverage (as a verb), tapestry, underscore (as a verb), foster, \
  robust, pivotal, intricate, paramount, multifaceted, beacon, realm, \
  enhance, showcase, boast, testament, vibrant, holistic, seamless, \
  elevate, empower, unlock (as a verb).
- Do not say "I am writing to inform you that..." or any variant.

STRUCTURE — the letter has a fixed shape.

- Paragraph 1: situational opener.
- Middle paragraphs (1-2): the substantive content.
- Final paragraph: the coverage position / reservation of rights \
  language. ALWAYS its own paragraph. NEVER paragraph 1 for \
  acknowledgements, follow-ups, info requests, records requests.

LENGTH AND RHYTHM.

- 2 to 4 body paragraphs. Total length 80-180 words.
- Each prose paragraph: 10 to 30 words. Closing paragraph can be very \
  short (8-15 words).
- Each sentence: 8 to 22 words. Split anything longer.
- VARY paragraph length. Uniform mid-length paragraphs are the AI-tell.

"WE" AS A SUBJECT — cap and vary.

- Maximum 2 sentences in the entire letter start with "We".
- Maximum 1 paragraph opens with "We". Do NOT open two consecutive \
  paragraphs with "We".

"PLEASE" — cap.

- Limit "Please" to 2-3 uses across the entire letter.
- Vary your request verbs across sentences: "Please provide", "Send", \
  "Identify", "Confirm", "Address", "Include", "Advise", "Forward".

EXEMPLARS — match their voice, length, structure, and list usage.

<example category="acknowledgement_of_representation">
This letter acknowledges receipt of your correspondence advising that \
you represent [Insured Name] in this matter. We have updated our claim \
file to reflect your appearance as defense counsel.

When convenient, please provide copies of the following:
- Any pleadings
- Discovery
- Written demands
- Medical specials
- Known deadlines

Once you have reviewed the available facts, your early liability \
assessment would also be helpful.

Our handling of this claim remains subject to a complete reservation \
of rights, without waiving any defenses. We expressly reserve the right \
to raise any policy or coverage defenses as more information becomes \
available.

Going forward, please direct future defense reports and billing to my \
attention.
</example>

<example category="medical_records_request">
This letter requests medical records and billing for treatment provided \
to [Claimant Name] relating to the above date of loss. We are reviewing \
a claim involving reported injuries from this incident.

Please provide the following from [Start Date] through the present:
- Complete chart notes
- Intake forms
- Diagnostic reports
- Prescriptions
- Referrals
- Discharge instructions
- Itemized billing

A signed authorization is enclosed with this request. If you require a \
different form or charge a copy fee, please advise before processing. \
You may send records by secure email, fax, or mail.

This request does not admit liability, causation, damages, or coverage. \
We reserve all rights and defenses during our claim investigation.
</example>

<example category="ror_letter_with_numbered_issues">
Pursuant to the policy issued to you, we are investigating the loss \
involving [Claimant Name] on [Date of Loss]. Based on the information \
presently available, coverage may be limited or unavailable.

Two issues remain open at this stage:
1. Notice was received [N] days after the loss, raising a question \
under the policy's notice condition.
2. The vehicle's use at the time of the incident may differ from the \
declared use category.

Your recorded statement is needed to address these questions. Please \
contact me within five business days to schedule a date and time.

Our handling of this matter remains subject to a complete reservation \
of rights, without waiving any defenses, expressly reserving the right \
to deny coverage, limit coverage, or assert any policy condition.
</example>

Render the body for the outbound described below. Output ONLY the \
body paragraphs. No salutation. No sign-off. No commentary.\
"""


# ---------------------------------------------------------------------------
# User-prompt rendering
# ---------------------------------------------------------------------------


def _render_thread_turn(turn: OutreachThreadTurn) -> str:
    if turn.direction == "sent":
        asked = ", ".join(turn.question_ids_asked) or "(none recorded)"
        return (
            f"  [{turn.turn_date.isoformat()}] SENT — {turn.summary}\n"
            f"    questions asked: {asked}"
        )
    answered = ", ".join(turn.question_ids_answered) or "(none)"
    unanswered = ", ".join(turn.question_ids_unanswered) or "(none)"
    return (
        f"  [{turn.turn_date.isoformat()}] RECEIVED — {turn.summary}\n"
        f"    questions answered: {answered}\n"
        f"    questions still unanswered: {unanswered}"
    )


def _render_user_body(drafter_input: OutreachDrafterInput) -> str:
    lines = [
        "=== OUTBOUND CONTEXT ===",
        f"claim_id: {drafter_input.claim_id}",
        f"recipient_party: {drafter_input.recipient_party}",
        f"recipient_name: {drafter_input.recipient_name}",
        f"insured_name: {drafter_input.insured_name}",
        f"claimant_name: {drafter_input.claimant_name}",
        f"date_of_loss: {drafter_input.date_of_loss.isoformat()}",
        f"coverage_posture: {drafter_input.coverage_posture}",
        "",
        "=== LETTER PURPOSE ===",
        drafter_input.letter_purpose,
        "",
        "=== OPEN QUESTIONS TO ADDRESS ===",
        "(Use the DESCRIPTION in the body. Never print the ID.)",
    ]
    if drafter_input.open_questions:
        for q in drafter_input.open_questions:
            lines.append(f"- [{q.id}] {q.description}")
    else:
        lines.append("(none — this is a non-question letter, e.g., acknowledgement)")

    if drafter_input.conversation_history or drafter_input.older_history_summary:
        lines.extend(["", "=== CONVERSATION HISTORY ==="])
        if drafter_input.older_history_summary:
            lines.append(f"Older history: {drafter_input.older_history_summary}")
            lines.append("")
        for turn in drafter_input.conversation_history:
            lines.append(_render_thread_turn(turn))
            lines.append("")
    else:
        lines.extend(["", "=== CONVERSATION HISTORY ===", "(none — this is the first letter on this thread)"])

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Runtime
# ---------------------------------------------------------------------------


def run_outreach_drafter(
    drafter_input: OutreachDrafterInput,
    *,
    now: datetime,
    model: str = DEFAULT_MODEL,
    reasoning_effort: str = DEFAULT_REASONING_EFFORT,
    max_completion_tokens: int = DEFAULT_MAX_COMPLETION_TOKENS,
    _client: OpenAI | None = None,
) -> OutreachDrafterResult:
    """Draft one letter body. Stateless LLM call; structured input
    fully describes the situation.

    `now` is passed in explicitly (not `datetime.now()`) so callers
    control determinism for tests and replay.

    The drafter does NOT decide whether the body is "good enough" to
    send. It returns the body plus deterministic lint metrics. The
    adjuster (or a downstream action) decides.
    """
    client = _client or OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    user_body = _render_user_body(drafter_input)

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_body},
        ],
        max_completion_tokens=max_completion_tokens,
        reasoning_effort=reasoning_effort,
    )

    choice = resp.choices[0]
    body_text = (choice.message.content or "").strip()
    if not body_text:
        raise RuntimeError(
            f"Outreach Drafter returned empty body. "
            f"finish_reason={choice.finish_reason!r}, "
            f"output_tokens={resp.usage.completion_tokens}. "
            f"This usually means reasoning tokens consumed the entire "
            f"completion budget — raise max_completion_tokens or lower "
            f"reasoning_effort."
        )

    lint = run_anti_slop_lint(body_text)

    return OutreachDrafterResult(
        body_text=body_text,
        lint_metrics=lint,
        lint_passes=lint["passes"],
        model=resp.model,
        drafted_at=now,
        input_tokens=resp.usage.prompt_tokens,
        output_tokens=resp.usage.completion_tokens,
    )


# ---------------------------------------------------------------------------
# Caseload → DrafterInput helper
# ---------------------------------------------------------------------------


def _outbound_to_thread_turn(
    outbound: OutboundRequest,
    documents_by_id: dict[str, Document],
) -> list[OutreachThreadTurn]:
    """One outbound becomes 1-2 thread turns: the SENT turn, plus a
    RECEIVED turn if a reply has been matched.

    The RECEIVED turn's answered/unanswered split currently mirrors
    the outbound's full asked set as "answered" — a simplification.
    When the Reply Parser persists its partition onto the
    `OutboundRequest` (future schema enhancement), the helper will
    use that partition. For now, status=='replied' implies "fully
    answered" for thread-summary purposes.
    """
    sent_summary = (
        (outbound.draft_body[:120] + "...")
        if outbound.draft_body and len(outbound.draft_body) > 120
        else (outbound.draft_body or "(no recorded body)")
    )
    turns: list[OutreachThreadTurn] = [
        OutreachThreadTurn(
            direction="sent",
            turn_date=(outbound.sent_at or outbound.drafted_at or datetime.min).date(),
            summary=sent_summary,
            question_ids_asked=list(outbound.question_ids_asked),
        )
    ]
    if outbound.status == "replied" and outbound.reply_doc_id:
        reply_doc = documents_by_id.get(outbound.reply_doc_id)
        if reply_doc is not None:
            received_summary = (
                (reply_doc.body_text[:160] + "...")
                if len(reply_doc.body_text) > 160
                else reply_doc.body_text
            )
            turns.append(
                OutreachThreadTurn(
                    direction="received",
                    turn_date=reply_doc.received_date,
                    summary=received_summary,
                    question_ids_answered=list(outbound.question_ids_asked),
                    question_ids_unanswered=[],
                )
            )
    return turns


def build_drafter_input_for_outbound(
    *,
    outbound: OutboundRequest,
    caseload: Caseload,
    info_map: InfoMap = INFO_MAP_AUTO_BI_FL,
    thread_history_cap: int = THREAD_HISTORY_CAP,
) -> OutreachDrafterInput:
    """Assemble a drafter input from caseload state for one outbound.

    Identity (`recipient_name`, `letter_purpose`) is read directly
    from `outbound`. Claimant/insured names are read from the
    `Claim` resolved by `outbound.claim_id`. Both claim names must
    be populated — the caller is responsible for hydrating them
    (intake_reader extracts from FNOL docs); this function raises
    if either is null.

    - Open question IDs come from `info_map.by_party(recipient_party)`
      filtered through `is_answered()` against the claim's documents.
    - Conversation history is the chronologically-ordered prior
      outbounds for (claim_id, recipient_party, recipient_name),
      each expanded into a SENT turn plus a RECEIVED turn when a
      reply has been matched. Different `recipient_name` values at
      the same party reset the thread — a new lawyer means a new
      conversation.
    - When the thread has more than `thread_history_cap` turns, only
      the most recent `thread_history_cap` are included verbatim;
      the older history is summarized in `older_history_summary`.
    """
    claim = _find_claim(caseload, outbound.claim_id)
    if claim.claimant_name is None or claim.insured_name is None:
        raise ValueError(
            f"build_drafter_input_for_outbound: claim {claim.claim_id!r} "
            f"is missing claimant_name and/or insured_name. Hydrate the "
            f"claim (intake_reader) before drafting."
        )

    claim_docs = [d for d in caseload.documents if d.claim_id == claim.claim_id]
    documents_by_id = {d.document_id: d for d in caseload.documents}

    applicable = info_map.by_party(outbound.recipient_party)
    open_qs = [q for q in applicable if not is_answered(q, claim, claim_docs)]
    open_question_refs = [
        OpenQuestionRef(id=q.id, description=q.description) for q in open_qs
    ]

    prior_outbounds = [
        o for o in caseload.outbounds_for_claim(claim.claim_id)
        if o.recipient_party == outbound.recipient_party
        and o.recipient_name == outbound.recipient_name
        and o.request_id != outbound.request_id
    ]
    prior_outbounds.sort(
        key=lambda o: o.sent_at or o.drafted_at or datetime.min
    )

    all_turns: list[OutreachThreadTurn] = []
    for prior in prior_outbounds:
        all_turns.extend(_outbound_to_thread_turn(prior, documents_by_id))

    if len(all_turns) <= thread_history_cap:
        recent = all_turns
        older_summary: str | None = None
    else:
        recent = all_turns[-thread_history_cap:]
        older = all_turns[:-thread_history_cap]
        older_dates = [t.turn_date.isoformat() for t in older]
        all_answered = sorted({
            q for t in older for q in t.question_ids_answered
        })
        older_summary = (
            f"Prior exchanges from {older_dates[0]} to {older_dates[-1]} "
            f"({len(older)} turns) resolved: "
            f"{', '.join(all_answered) if all_answered else '(no questions yet resolved)'}."
        )

    return OutreachDrafterInput(
        claim_id=claim.claim_id,
        recipient_party=outbound.recipient_party,
        recipient_name=outbound.recipient_name,
        claimant_name=claim.claimant_name,
        insured_name=claim.insured_name,
        date_of_loss=claim.opened_date,
        coverage_posture=claim.coverage_posture,
        letter_purpose=outbound.letter_purpose,
        open_questions=open_question_refs,
        conversation_history=recent,
        older_history_summary=older_summary,
    )


def _find_claim(caseload: Caseload, claim_id: str) -> Claim:
    for c in caseload.claims:
        if c.claim_id == claim_id:
            return c
    raise ValueError(
        f"build_drafter_input_for_outbound: claim_id={claim_id!r} not "
        f"present in caseload."
    )


__all__ = [
    "DEFAULT_MAX_COMPLETION_TOKENS",
    "DEFAULT_MODEL",
    "DEFAULT_REASONING_EFFORT",
    "SYSTEM_PROMPT",
    "THREAD_HISTORY_CAP",
    "build_drafter_input_for_outbound",
    "run_outreach_drafter",
]
