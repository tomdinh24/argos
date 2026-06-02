"""Outreach Drafter prompt bake-off: GPT vs Claude on the SAME system prompt.

NOT a production runtime. A one-shot script that calls each model's API
directly with the production-shape system prompt + 3 in-context exemplars
+ one concrete OutboundRequest scenario, and prints both raw outputs
side by side for human eyeball comparison.

Why this exists: the prior "15 sample letters" comparison was generated
in the consumer chat UIs (ChatGPT.com / Claude.ai), which layer their
own product-specific system prompts on top of the model. To decide
which model to ship in the Outreach Drafter workflow, we need the
raw model's response to *our* drafter system prompt.

Usage:
    cd ~/Projects/argos && .venv/bin/python scripts/bake_off_drafter.py

Outputs go to stdout and to data/bake-off/drafter-{timestamp}.json.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import dotenv


# ---------------------------------------------------------------------------
# Production-shape system prompt
# ---------------------------------------------------------------------------

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
brand in the body. NEVER use words like "Argos", "this AI", "the \
system", "our platform" to refer to the writer. When referring to \
the writer, use "we", "this office", "I" (for the adjuster), or the \
carrier/TPA name if it is provided in the scenario context. The \
recipient should read the letter as professional correspondence from \
a working adjuster — not from a software product.

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

BAD: "Our records show no response to our prior request."
GOOD: "We have not received a response to our prior request."

The rule: ask what the recipient needs to DO, not what state your \
internal records are in.

REQUEST SHAPE — soften the imperative.

"Future reports should be directed to my attention" reads as bossy. \
The same ask without the edge: "Please direct future reports to my \
attention" or "Going forward, please send reports to me directly." \
The word "should" prefixed to a request to another professional is \
the tell — it carries an unearned authority.

BAD: "Your response should include X, Y, Z."
GOOD: "Please include X, Y, Z in your response."

BAD: "All correspondence must be sent to my office."
GOOD: "Please send all correspondence to my office."

LIST SHAPE — MUST use a list for 3+ asks. No exceptions.

This is a HARD rule. When the letter asks the recipient for 3 or more \
distinct items, you MUST use a bulleted or numbered list. Comma- \
stuffing a 3+ item ask into a single sentence is a hard failure \
regardless of how cleanly the items parallel grammatically. "But it \
reads fine as prose" is NOT a valid reason. The recipient must be \
able to SCAN the asks.

When you have 1-2 items, prose is fine. When you have 3 or more, \
list.

UNORDERED list (use "- " bullets) — when the order of items does NOT \
matter. Records requests, document checklists, follow-up items.

GOOD:
"Please include in your report:
- Present litigation status
- Discovery completed and still needed
- Any expected motion practice
- Current exposure range estimate
- Trial setting and other key deadlines"

NUMBERED list (use "1. " "2. " etc.) — when ORDER matters, when items \
are characterized as a counted set ("two issues remain open", "three \
items are needed"), or when later text references back to a specific \
item.

GOOD (counted-set framing):
"Two issues remain open at this stage:
1. Notice was received 47 days after the loss.
2. The vehicle's use at the time of the incident may differ from \
the declared category."

GOOD (sequence framing):
"To complete our review, we will need:
1. A signed authorization
2. Complete medical records
3. Wage-loss documentation"

Choose unordered when items are a checklist; numbered when items are \
an enumerated set or a sequence.

Exception: NEVER bullet OR number the ROR paragraph itself. It is a \
single legal formula and must read as continuous prose.

COURTESY CLOSE — non-ROR letters end warm.

For follow-ups, acknowledgements, info requests, and records \
requests, end with ONE SHORT LINE inviting follow-up. Place it as a \
short paragraph AFTER the ROR paragraph (or as the final paragraph \
if there is no ROR).

Options:
- "Please let me know if you have any questions."
- "Happy to discuss any of the above."
- "Reach out if you need anything else from our file."

Exception: ROR letters to insureds do NOT carry a warm close. The \
register is serious. The closing is the coverage position itself.

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
  [thing]." — use this when the situation is genuinely neutral and \
  the formality matches. Not as default.
- ROR opener (RESERVED for ROR letters): "Pursuant to the policy \
  issued to you, ..."

Vary across letter types. Do not default to the same opener twice in \
a row across scenarios.

TOPIC GROUPING — one topic per paragraph.

Each paragraph carries one job. The situational opener is its own \
paragraph. The asks are their own paragraph (or bulleted list). The \
coverage position is its own paragraph. The courtesy close is its \
own short paragraph. Do NOT intermix the situational frame and the \
asks in the same paragraph.

WORD-LEVEL VARIETY — do not repeat distinctive words.

Within a single paragraph, do not repeat the same distinctive content \
word. Within back-to-back sentences anywhere in the letter, do not \
repeat the same distinctive content word. Repetition reads cheap — \
the reader already inferred the topic; restating the same noun or \
verb adds nothing.

"Distinctive content word" means a noun, verb, or adjective that \
carries meaning. Function words (the, of, and, for, to, a, our, we, \
you, this, that) do NOT count and can repeat freely.

Watch especially for these high-collision words: claim, coverage, \
policy, request, records, report, evaluation, discovery, exposure, \
investigation, current. When you need to refer to the same concept \
twice, restructure or use a substitute.

BAD: "Please send chart notes and medical records. Records may be \
sent by email." (records twice in two sentences)
GOOD: "Please send chart notes and medical records. These may be \
sent by email."

BAD bullet list: "Current liability picture", "Current exposure \
range", "Current exposure assessment" (current x3)
GOOD bullet list: "Liability picture and defenses", "Damages \
exposure and demand history", "Settlement posture"

BAD: "This request does not waive any coverage position. Coverage \
remains under review." (coverage twice in two sentences)
GOOD: "This request does not waive any coverage position. All \
defenses remain under review."

EXCEPTION — the ROR boilerplate formula is a legal term of art and \
must stay verbatim. "Complete reservation of rights, without waiving \
any defenses, expressly reserving the right to deny coverage, limit \
coverage, or assert any policy condition" — these words repeat \
because the formula requires it. The variety rule does NOT apply \
inside the ROR paragraph itself. It still applies between the ROR \
paragraph and adjacent paragraphs: do not lead INTO the ROR with \
sentences that pre-repeat "coverage" or "reservation".

FLOW AND TRANSITIONS — anchor on the principles, not on any one example.

This is the most important section after VOICE. Three overlapping \
principles from professional writing pedagogy govern how this works.

PRINCIPLE 1 — COHESION (Halliday & Hasan, "Cohesion in English"; \
Joseph Williams, "Style: Lessons in Clarity and Grace"). Adjacent \
sentences should be GLUED by one of three mechanisms: (a) a \
connective that names the relationship between them, (b) lexical \
chaining (the second sentence picks up a noun, verb, or concept from \
the first), or (c) pronominal reference (the second sentence's \
subject is "it", "that", or "this" referring back).

PRINCIPLE 2 — GIVEN-NEW CONTRACT (Halliday's functional grammar; \
Pinker, "The Sense of Style"). Each sentence should start with \
information the reader already has from the prior sentence and \
progress toward NEW information. The "given" anchors; the "new" \
advances. Stacked declaratives violate this by starting every \
sentence with new information, leaving the reader to figure out the \
connection between sentences.

PRINCIPLE 3 — POLITENESS MITIGATION FOR ASKS (Brown & Levinson, \
"Politeness: Some Universals in Language Usage"). A request is a \
face-threatening act. Professional writers soften asks with hedges \
("when convenient", "at your convenience", "where possible") or \
indirect framing ("it would help to receive X", "we would appreciate \
X"). These are NOT filler. They signal that the writer respects the \
reader's autonomy. Use them on peer-to-peer asks (counsel, fellow \
professionals); omit on processing-function asks (records desks) \
where directness is expected.

Halliday's connective taxonomy — pull from these categories where \
the relationship between sentences is genuinely present:

- Additive: in addition, also
- Adversative (contrast): however, that said
- Causal: accordingly, as a result, given the above
- Temporal/sequential: in the meantime, going forward, once received
- Conditional/contingent: when convenient, if it is helpful, once

Two example realizations of the same underlying principle — do NOT \
treat either as a template; the principle is what matters, the \
phrasing should vary with the situation.

REALIZATION A (adversative connective + politeness hedge on the ask):
"We received your acknowledgment of representation 22 days ago. \
However, the initial case evaluation has not yet arrived. When you \
have a chance, please send it within the next ten business days."

REALIZATION B (lexical chain + sequential connective + indirect ask):
"Your appearance for Greenline Freight Co. was filed last week. That \
representation triggers our standard request for an initial case \
evaluation. Going forward, please direct that report to my attention \
once available."

Both glue adjacent sentences (one with connectives, one with lexical \
chains). Both soften the ask (one with a "when you have a chance" \
hedge, one with "once available"). The phrasing differs; the \
underlying moves are the same.

USE 2-3 cohesion moves per letter, not one in every sentence. A \
4-paragraph letter does NOT need a connective at the start of every \
paragraph. Use them where (a) the relationship between sentences is \
non-obvious, (b) a softening hedge helps a peer-to-peer ask land \
warmer, or (c) sequential ordering (first/second) makes a multi-part \
issue easier to follow.

NEVER use these AI-tell connectives: Furthermore, Moreover, \
Additionally, In conclusion, Notably, It's worth noting, \
Importantly. NEVER use "Ideally" — it reads as a verbal-filler \
crutch in writing.

REGISTER — match the register to who you are writing to.

The recipient determines whether asks should be framed as soft \
preferences or as direct, formal requests. Get this wrong in either \
direction and the letter feels off.

PEER-TO-PEER REGISTER (defense counsel follow-ups, status requests, \
counsel-to-counsel correspondence): you are writing to a fellow \
professional whose time you respect. Frame asks SOFTLY. Standard \
softeners: "whenever you have time", "at your convenience", "when \
convenient", "preferably within X business days", "once you have a \
chance". Avoid bare imperatives like "Please send X within ten \
business days." instead write "Whenever you have time, please send \
X, preferably within ten business days."

FORMAL-DIRECT REGISTER (records desks, third-party providers, \
records custodians): you are writing to a processing function, not a \
peer. Be direct and specific. "Please provide X" is the right shape. \
Do NOT layer "whenever convenient" softeners onto a records request \
— it reads odd because the records desk's job IS to respond.

LEGAL-SERIOUS REGISTER (ROR letters to insureds): formal, no \
softeners on coverage statements, no warm courtesy close. The \
register is the legal weight of the document. "Pursuant to the \
policy issued to you..." opener; ROR formula intact; no "happy to \
discuss".

Rule of thumb: would the recipient be a "thanks for the report, \
appreciate it" peer, or a "we processed your request, here's the \
output" function? Peer → soft. Function → direct. Insured being \
told their coverage may not apply → legal-serious.

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
  align with, enhance, showcase, boast, testament, vibrant, holistic, \
  seamless, elevate, empower, unlock (as a verb).
- Do not say "I am writing to inform you that..." or any variant.

STRUCTURE — the letter has a fixed shape.

- Paragraph 1: situational opener. Why we are writing. What just \
  happened. Examples: "This letter acknowledges receipt of...", "We \
  received your acknowledgment of representation 22 days ago.", \
  "Pursuant to the policy issued to you, we are investigating...".
- Middle paragraphs (1-2): the substantive content. Asks, items \
  requested, coverage questions, supporting detail, deadline framing.
- Final paragraph: the coverage position / reservation of rights \
  language. This is ALWAYS its own paragraph. It is NEVER appended \
  to a request paragraph. For acknowledgement letters, follow-up \
  letters, information requests, and records requests, the ROR is \
  the closing paragraph and NEVER paragraph 1.

The ONLY exception: a ROR letter to the insured may carry coverage \
posture earlier in the letter (where the coverage concerns are \
explained) AND still close with the standard ROR formula. Even there, \
do NOT open paragraph 1 with the ROR formula itself.

REPETITION AND TRANSITIONS — read this carefully.

A real adjuster letter varies its openers. AI drafts default to \
starting every sentence and every paragraph with "Please ___" because \
the request register pulls the model toward that pattern. Reject that \
default.

- Limit "Please" to 2-3 uses across the entire letter. Not per paragraph. \
  Per letter total.
- Do not start more than 2 sentences in a row with the same word.
- Vary your request verbs across sentences: "Please provide", "We need", \
  "Send", "Identify", "Confirm", "Address", "Include", "Advise", \
  "Forward", "Indicate". Mix these. Do not stack three "Please ___" \
  sentences.
- Vary paragraph openers. Do NOT open consecutive paragraphs with the \
  same first word or same structural pattern (e.g., two paragraphs that \
  both open "Please ___" or both open "We ___" or both open "This \
  letter ___"). If paragraph 2 opens with a request, paragraph 3 \
  should open with context, situation, deadline framing, supporting \
  detail, or the coverage position.
- Paragraphs should connect to each other. Do not stack four \
  standalone request blocks. The letter is one piece of writing, not \
  four bullet points wearing prose.

LENGTH AND RHYTHM — read this carefully. This is where most drafts \
fail.

- 2 to 4 body paragraphs. Total length 80-180 words.
- Each paragraph: 1 to 3 sentences. Most paragraphs are 2 sentences.
- Each paragraph: 10 to 30 words. The closing paragraph can be very \
  short — a single 8-15 word sentence is good. ("Please direct \
  future defense reports and billing to my attention." is a real \
  adjuster closing.)
- Each sentence: 8 to 22 words. If a sentence runs longer than 22 \
  words, you are probably stuffing multiple asks into it — split.
- VARY paragraph length. Do not produce four paragraphs that are all \
  35-45 words each. A real letter looks like: 22 / 28 / 32 / 10 \
  words across its four paragraphs. Variety is the signal of a real \
  writer. Uniform medium-length paragraphs are the AI-tell.

ASK SHAPE — applies only to 1-2 item asks.

The LIST SHAPE rule above (MUST bullet/number 3+ items) takes \
precedence. This section applies ONLY when you have 1-2 items to \
ask about.

For 1-2 items, prose is fine. When the two items are genuinely of \
different types (a status request AND an exposure estimate, say), \
make them separate sentences rather than a compound. When they're \
the same type (two related artifacts), a parallel comma list inside \
one sentence is fine.

GOOD (1 item, prose): "Please send your initial liability assessment."
GOOD (2 same-type items, parallel comma list): "Please send your \
liability assessment and motion-practice forecast."
GOOD (2 different-type items, separate sentences): "Please send your \
liability assessment. Advise on the deadline for your initial \
exposure estimate."

BAD (compound stuffing 2 different-type items): "Include the status \
of pleadings and your current exposure range estimate." → two \
sub-asks disguised as one sentence — split into two sentences.

For 3+ items, do NOT use prose at all. See LIST SHAPE above.

"WE" AS A SUBJECT — cap and vary.

"We" is the adjuster's natural subject pronoun, but a draft that \
opens five sentences with "We" reads as wooden. Cap and vary.

- Maximum 2 sentences in the entire letter start with "We".
- Maximum 1 paragraph opens with "We". Do NOT open two consecutive \
  paragraphs with "We".
- When you reach for "We ___", consider rephrasing:
  * "We have updated our claim file..." → "Our claim file reflects..."
  * "We need your view on..." → "Your initial view on ___ would help."
  * "We are completing..." → "Our current claim review needs..."
  * "We reserve all rights..." → "All rights and defenses are reserved..."
  * Or drop the subject: "Need your statement within five business days."
- Vary your paragraph openers across the letter. Across four \
  paragraphs, try four DIFFERENT opening structures: a "This letter \
  ___" opener, a request-verb opener ("Please ___" / "Send ___" / \
  "Address ___"), a context opener ("Our file ___" / "The claim \
  ___"), and the closing ROR paragraph ("Our handling ___" / "All \
  rights ___").

EXEMPLARS — these are real adjuster letter bodies. Match their voice, \
length, and structure precisely.

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

<example category="information_request_to_counsel_time_boxed">
We are completing our current claim review and need your updated \
report. When convenient, please send your response within ten business \
days.

Please address the following in your report:
- Present litigation status
- Discovery completed and still needed
- Any known trial setting
- Your best estimate of likely verdict range
- Your best estimate of likely settlement range

If you believe mediation is appropriate, advise on timing and mediator \
options. If you recommend no settlement activity now, explain the \
reason.

Please be advised that this request does not waive any coverage \
position. The claim remains subject to a complete reservation of \
rights, including all policy defenses and conditions.

Happy to discuss any of the above.
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

Render the body now for the outbound below. Output ONLY the body \
paragraphs. No salutation. No sign-off. No commentary."""


# ---------------------------------------------------------------------------
# Test scenarios — 5 covering the canonical letter types
# ---------------------------------------------------------------------------

SCENARIOS: list[dict] = [
    {
        "id": "follow_up_to_counsel",
        "label": "Follow-up to counsel (no eval after 22 days)",
        "input": """\
OUTBOUND CONTEXT
claim_id: CLM-2026-0147
recipient_party: defense_counsel
recipient_name: Marisol Trent, Esq.
date_of_loss: 2026-02-18
insured_name: Stellar Logistics, LLC
claimant_name: Robert Caro

LETTER PURPOSE
Follow up with defense counsel who acknowledged representation 22 \
days ago but has not yet provided the initial case evaluation we \
requested. Ask for the evaluation. Set a 10-business-day deadline. \
Reiterate the reservation of rights position. Firm but professional.

QUESTIONS TO ADDRESS
- Q-LIA-001: counsel's initial liability assessment
- Q-LIA-002: any expected motion practice
- Q-RES-005: counsel's current exposure range estimate
- Q-DISC-002: status of pleadings and discovery to date""",
    },
    {
        "id": "acknowledgement_of_representation",
        "label": "Acknowledgement of new defense counsel",
        "input": """\
OUTBOUND CONTEXT
claim_id: CLM-2026-0149
recipient_party: defense_counsel
recipient_name: Dornan & Lao LLP, attn: Priya Lao
date_of_loss: 2026-01-30
insured_name: Greenline Freight Co.
claimant_name: Anita Park

LETTER PURPOSE
Counsel just appeared on file. Acknowledge their representation, \
confirm they're now the defense attorney, request the standard early \
case materials and an early liability assessment. Open with the ROR \
posture preserved.

ITEMS TO REQUEST
- Pleadings, discovery, written demands, medical specials, known deadlines
- Early liability assessment once they've reviewed available facts
- Future defense reports and billing directed to the adjuster""",
    },
    {
        "id": "medical_records_request",
        "label": "Medical records request to a hospital records desk",
        "input": """\
OUTBOUND CONTEXT
claim_id: CLM-2026-0162
recipient_party: medical_provider
recipient_name: St. Catherine's Regional Hospital, Medical Records
date_of_loss: 2026-03-12
insured_name: Coastline Cabs, Inc.
claimant_name: Devon Whitaker
records_start_date: 2026-03-12

LETTER PURPOSE
Request complete medical records and itemized billing for Devon \
Whitaker relating to treatment received after the date of loss. \
Authorization is enclosed. Acceptable delivery: secure email, fax, mail.

ITEMS TO REQUEST
- Chart notes, intake forms, diagnostic reports, prescriptions, \
  referrals, discharge instructions, itemized billing
- Records from records_start_date through present
- Standard non-admission language so the request does not waive \
  liability/causation/damages/coverage""",
    },
    {
        "id": "ror_to_insured_late_notice",
        "label": "ROR to insured — late notice and use-of-vehicle questions",
        "input": """\
OUTBOUND CONTEXT
claim_id: CLM-2026-0118
recipient_party: insured
recipient_name: Martin Esquivel
date_of_loss: 2026-01-04
insured_name: Martin Esquivel
claimant_name: Yolanda Briggs

LETTER PURPOSE
Reservation of rights letter to the insured. Two coverage questions \
need addressing: (1) notice came in 47 days after the loss, raising a \
late-notice policy condition issue; (2) vehicle may have been used \
outside the declared use category. Need the insured's recorded \
statement. Provide 5 business days to schedule.

ITEMS TO COVER
- Explain that coverage may be limited or unavailable based on \
  current facts
- Specifically flag late notice + use-of-vehicle as the two open \
  questions (without legal-conclusion phrasing)
- Full ROR formula
- 5-business-day window to schedule the recorded statement""",
    },
    {
        "id": "information_request_open_status",
        "label": "Open-status information request to counsel (no time-box)",
        "input": """\
OUTBOUND CONTEXT
claim_id: CLM-2026-0095
recipient_party: defense_counsel
recipient_name: Hatcher & Pine, attn: Joel Hatcher
date_of_loss: 2025-11-22
insured_name: Northbridge Manufacturing
claimant_name: Renata Acosta

LETTER PURPOSE
Mid-case status update request to defense counsel. Suit has been \
filed. We need a current picture for reserve review. No hard deadline \
— treat as routine adjuster file-supervision touch.

QUESTIONS TO ADDRESS
- Current liability picture and any defenses identified
- Damages exposure and demand history
- Discovery status — completed vs outstanding
- Settlement posture and any mediation discussion
- Upcoming deadlines including any trial setting
- Current exposure assessment and recommended next steps""",
    },
]


# ---------------------------------------------------------------------------
# Model calls
# ---------------------------------------------------------------------------

WRITER_MODEL = "gpt-5.5"
JUDGE_MODEL = "claude-opus-4-8"
# Legacy names retained for backwards-compat with existing functions.
CLAUDE_MODEL = JUDGE_MODEL
GPT_MODEL = WRITER_MODEL


JUDGE_SYSTEM_PROMPT = """\
You are a senior claims adjuster reviewing a junior adjuster's draft \
outreach letter before it goes out. Your job is to catch problems \
before send. Be strict. If you would NOT send this letter from your \
own claims file, you must flag it for revision.

You will see:
1. The scenario brief (the situation the letter responds to)
2. The draft body to evaluate
3. The deterministic lint result that already ran on the draft

Critique on these specific axes:

1. STRUCTURE — Is the reservation of rights paragraph in the correct \
   place? It is ALWAYS the final paragraph (closing position), NEVER \
   the opening paragraph. The exception is ROR letters to insureds, \
   where ROR posture may appear mid-letter AND close the letter, but \
   even there it should never be paragraph 1.

2. VOICE — Does this sound like a real working adjuster doing their \
   job? It should be transactional, slightly stilted, formulaic where \
   formulas exist ("Pursuant to the policy issued to you...", "Please \
   be advised that..."). It should NOT read as fluid eloquent prose.

3. REQUESTED ITEMS COVERED — Does the draft address every question or \
   item listed in the scenario brief? If the brief lists Q-LIA-001 / \
   Q-LIA-002 / Q-RES-005 / Q-DISC-002, all four must be substantively \
   addressed.

4. REPETITION — Are the same words or sentence openers stacked? \
   "Please ___" appearing more than 2-3 times across the letter is a \
   problem. Multiple consecutive sentences starting with the same word \
   is a problem.

5. TRANSITIONS — Does the letter flow as one piece, or read as stacked \
   request blocks? Each paragraph should connect to the prior one, \
   not stand alone.

Output ONLY valid JSON in this exact schema, no commentary, no markdown \
fences, no extra fields:

{
  "voice_match_score": <integer 1-5, where 5 = sounds exactly like \
a working adjuster and 1 = obviously AI-generated>,
  "structure_correct": <true|false>,
  "requested_items_covered": <true|false>,
  "issues": ["specific issue 1", "specific issue 2"],
  "revision_needed": <true|false>,
  "revision_instructions": "concrete instructions to the writer on \
what to change. Be specific about which paragraphs and what edits. \
If no revision is needed, return empty string."
}

revision_needed should be true if voice_match_score < 4 OR \
structure_correct is false OR requested_items_covered is false OR \
the deterministic lint already failed.
"""


def call_judge(scenario_label: str, scenario_input: str, draft: str, lint_result: dict) -> dict:
    """Run the Claude judge on a draft. Returns parsed JSON or a fallback."""
    from anthropic import Anthropic
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    user_body = (
        f"SCENARIO: {scenario_label}\n\n"
        f"=== SCENARIO BRIEF ===\n{scenario_input}\n\n"
        f"=== DRAFT BODY ===\n{draft}\n\n"
        f"=== DETERMINISTIC LINT RESULT ===\n{json.dumps(lint_result, indent=2)}\n\n"
        f"Evaluate this draft against the rules in your system prompt. "
        f"Return JSON only."
    )
    resp = client.messages.create(
        model=JUDGE_MODEL,
        max_tokens=800,
        system=JUDGE_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_body}],
    )
    text = "\n".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
    # Strip optional ```json fences if the judge ignores instruction
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```", 2)[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.rsplit("```", 1)[0].strip()
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as e:
        parsed = {
            "voice_match_score": None,
            "structure_correct": None,
            "requested_items_covered": None,
            "issues": [f"JUDGE_PARSE_ERROR: {e}"],
            "revision_needed": False,
            "revision_instructions": "",
            "_raw": text,
        }
    parsed["_judge_input_tokens"] = resp.usage.input_tokens
    parsed["_judge_output_tokens"] = resp.usage.output_tokens
    return parsed


def call_writer_revise(scenario_input: str, draft: str, judge_feedback: dict, lint_result: dict) -> dict:
    """Second writer pass with the judge's feedback + lint results as a corrective note."""
    from openai import OpenAI
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    issues = "\n".join(f"- {i}" for i in judge_feedback.get("issues", []))
    lint_issues_lines = []
    if lint_result.get("first_paragraph_is_ror"):
        lint_issues_lines.append("- ROR is in paragraph 1 — move it to the closing paragraph.")
    if lint_result.get("please_count", 0) > 3:
        lint_issues_lines.append(f"- 'Please' used {lint_result['please_count']} times — limit to 2-3.")
    if lint_result.get("we_sentence_opener_count", 0) > 2:
        lint_issues_lines.append(
            f"- {lint_result['we_sentence_opener_count']} sentences open with 'We' — "
            "cap is 2 per letter. Rephrase to 'Our file...', 'The claim...', "
            "or drop the subject ('Need your statement within...')."
        )
    if lint_result.get("we_paragraph_openers", 0) > 1:
        lint_issues_lines.append(
            f"- {lint_result['we_paragraph_openers']} paragraphs open with 'We' — "
            "cap is 1. Open paragraphs with varied structures: 'Our file...', "
            "'Please ___', 'This letter...', a request verb."
        )
    if lint_result.get("consecutive_we_paragraphs", 0) > 0:
        lint_issues_lines.append(
            "- Two consecutive paragraphs open with 'We' — break the streak."
        )
    if lint_result.get("max_paragraph_words", 0) > 32:
        lint_issues_lines.append(
            f"- Longest paragraph is {lint_result['max_paragraph_words']} words — "
            "ceiling is 32. Split into shorter paragraphs or trim."
        )
    if lint_result.get("max_sentence_words", 0) > 24:
        lint_issues_lines.append(
            f"- Longest sentence is {lint_result['max_sentence_words']} words — "
            "ceiling is 24. Likely compound-stuffing (3+ asks in one sentence) — "
            "split into multiple sentences or use a clean list shape."
        )
    if lint_result.get("paragraph_opener_collisions", 0) > 0:
        lint_issues_lines.append("- Two consecutive paragraphs open with the same word — vary openers.")
    if lint_result.get("max_consecutive_same_sentence_opener", 0) > 2:
        lint_issues_lines.append("- Three or more consecutive sentences start with the same word — vary verbs.")
    if lint_result.get("em_dash_count", 0) > 0:
        lint_issues_lines.append("- Contains em-dash — rewrite into two sentences.")
    if lint_result.get("banned_word_hits"):
        lint_issues_lines.append(f"- Banned words present: {lint_result['banned_word_hits']}")
    lint_issues = "\n".join(lint_issues_lines) or "(none)"

    user_body = (
        f"{scenario_input}\n\n"
        f"=== PRIOR DRAFT ===\n{draft}\n\n"
        f"=== REVISION REQUIRED ===\n"
        f"Senior reviewer feedback:\n{issues}\n\n"
        f"Specific revision instructions:\n"
        f"{judge_feedback.get('revision_instructions', '')}\n\n"
        f"Deterministic lint issues:\n{lint_issues}\n\n"
        f"Re-draft the letter body applying these fixes. Output only the body."
    )
    resp = client.chat.completions.create(
        model=WRITER_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_body},
        ],
        max_completion_tokens=1500,
        reasoning_effort="low",
    )
    choice = resp.choices[0]
    return {
        "model": resp.model,
        "stop_reason": choice.finish_reason,
        "output_text": choice.message.content or "",
        "input_tokens": resp.usage.prompt_tokens,
        "output_tokens": resp.usage.completion_tokens,
    }


def call_claude(system: str, user: str) -> dict:
    from anthropic import Anthropic
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    resp = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1200,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    text = "\n".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
    return {
        "model": resp.model,
        "stop_reason": resp.stop_reason,
        "output_text": text,
        "input_tokens": resp.usage.input_tokens,
        "output_tokens": resp.usage.output_tokens,
    }


def call_gpt(system: str, user: str) -> dict:
    from openai import OpenAI
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    resp = client.chat.completions.create(
        model=GPT_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_completion_tokens=1500,
        reasoning_effort="low",
    )
    choice = resp.choices[0]
    return {
        "model": resp.model,
        "stop_reason": choice.finish_reason,
        "output_text": choice.message.content or "",
        "input_tokens": resp.usage.prompt_tokens,
        "output_tokens": resp.usage.completion_tokens,
    }


# ---------------------------------------------------------------------------
# Deterministic anti-slop checks
# ---------------------------------------------------------------------------

BANNED_WORDS = {
    "delve", "leverage", "tapestry", "underscore", "foster", "robust",
    "pivotal", "intricate", "paramount", "multifaceted", "beacon",
    "realm", "enhance", "showcase", "boast", "testament", "vibrant",
    "holistic", "seamless", "elevate", "empower", "unlock",
}
BANNED_OPENERS = {
    "furthermore", "moreover", "additionally", "in today's",
    "it's worth noting that", "i am writing to inform you",
}


import re


def _sentence_split(text: str) -> list[str]:
    # Split on sentence-end punctuation followed by whitespace + capital.
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z])", text.strip()) if s.strip()]


def _first_word(s: str) -> str:
    m = re.match(r"\W*([A-Za-z']+)", s)
    return m.group(1).lower() if m else ""


def lint(text: str) -> dict:
    lower = text.lower()
    em_dashes = text.count("—")
    banned_hits = sorted(w for w in BANNED_WORDS if f" {w}" in lower or lower.startswith(w))
    paras = [p for p in text.strip().split("\n\n") if p.strip()]
    opener_hits = [
        p[:80] for p in paras
        if any(p.lower().lstrip().startswith(o) for o in BANNED_OPENERS)
    ]
    not_x_but_y = "not just" in lower or ", it's " in lower
    word_count = len(text.split())
    avg_para_words = word_count / max(len(paras), 1)

    # Lexical repetition: "Please" count + max consecutive run of same opener
    sentences_all = _sentence_split(text)
    please_count = sum(1 for s in sentences_all if _first_word(s) == "please")
    we_sentence_opener_count = sum(1 for s in sentences_all if _first_word(s) == "we")

    # "We" as paragraph opener (first sentence's first word)
    we_paragraph_openers = sum(
        1 for p in paras if _first_word(_sentence_split(p)[0] if _sentence_split(p) else "") == "we"
    )

    # Consecutive "We"-opener paragraphs
    para_first_words_check = [
        _first_word(_sentence_split(p)[0] if _sentence_split(p) else "") for p in paras
    ]
    consecutive_we_paragraphs = sum(
        1 for i in range(1, len(para_first_words_check))
        if para_first_words_check[i] == "we" and para_first_words_check[i - 1] == "we"
    )

    # Length signals: longest paragraph, longest sentence (catch stuffing).
    # Bullet-list paragraphs are exempt from prose word-count — their length
    # is the sum of bullet items, which is a structural choice, not a "wall
    # of text" failure. A paragraph counts as a bullet list when 2+ of its
    # lines start with "- ".
    def _is_bullet_paragraph(p: str) -> bool:
        lines = p.split("\n")
        bullet_lines = sum(1 for ln in lines if ln.lstrip().startswith("- "))
        return bullet_lines >= 2
    prose_paragraphs = [p for p in paras if not _is_bullet_paragraph(p)]
    paragraph_word_counts = [len(p.split()) for p in prose_paragraphs]
    max_paragraph_words = max(paragraph_word_counts) if paragraph_word_counts else 0
    sentence_word_counts = [len(s.split()) for s in sentences_all]
    max_sentence_words = max(sentence_word_counts) if sentence_word_counts else 0

    # Structural: ROR formula must not be in paragraph 1 (unless this is the
    # only paragraph). "reservation of rights" is the canonical formula token.
    first_paragraph_is_ror = bool(paras) and "reservation of rights" in paras[0].lower()

    sentences = _sentence_split(text)
    sentence_openers = [_first_word(s) for s in sentences]
    max_consecutive_same_opener = 0
    run, prev = 0, None
    for w in sentence_openers:
        if w and w == prev:
            run += 1
        else:
            run = 1
        max_consecutive_same_opener = max(max_consecutive_same_opener, run)
        prev = w

    # Paragraph openers: are 2+ consecutive paragraphs starting with same first word?
    para_first_words = [_first_word(p) for p in paras]
    paragraph_opener_collisions = sum(
        1 for i in range(1, len(para_first_words))
        if para_first_words[i] and para_first_words[i] == para_first_words[i - 1]
    )

    return {
        "em_dash_count": em_dashes,
        "banned_word_hits": banned_hits,
        "banned_opener_hits": opener_hits,
        "not_x_but_y_construction": not_x_but_y,
        "word_count": word_count,
        "paragraph_count": len(paras),
        "avg_words_per_paragraph": round(avg_para_words, 1),
        "please_count": please_count,
        "we_sentence_opener_count": we_sentence_opener_count,
        "we_paragraph_openers": we_paragraph_openers,
        "consecutive_we_paragraphs": consecutive_we_paragraphs,
        "max_paragraph_words": max_paragraph_words,
        "max_sentence_words": max_sentence_words,
        "paragraph_word_counts": paragraph_word_counts,
        "max_consecutive_same_sentence_opener": max_consecutive_same_opener,
        "paragraph_opener_collisions": paragraph_opener_collisions,
        "paragraph_first_words": para_first_words,
        "first_paragraph_is_ror": first_paragraph_is_ror,
        "passes": (
            em_dashes == 0
            and not banned_hits
            and not opener_hits
            and not not_x_but_y
            and 80 <= word_count <= 200
            and 2 <= len(paras) <= 4
            and please_count <= 3
            and we_sentence_opener_count <= 2
            and we_paragraph_openers <= 1
            and consecutive_we_paragraphs == 0
            and max_paragraph_words <= 32
            and max_sentence_words <= 24
            and max_consecutive_same_opener <= 2
            and paragraph_opener_collisions == 0
            and not first_paragraph_is_ror
        ),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    dotenv.load_dotenv()
    if "OPENAI_API_KEY" not in os.environ:
        print("ERROR: OPENAI_API_KEY must be set", file=sys.stderr)
        return 2

    print("=== Outreach Drafter — single-pass writer (5 scenarios) ===")
    print(f"Writer: {WRITER_MODEL}")
    print("(Judge + revision loop skipped — human is the evaluator this run)")
    print()

    scenario_records: list[dict] = []

    for sc in SCENARIOS:
        print("#" * 76)
        print(f"# SCENARIO: {sc['id']} — {sc['label']}")
        print("#" * 76)
        print()
        try:
            draft = call_gpt(SYSTEM_PROMPT, sc["input"])
        except Exception as e:
            draft = {"error": f"{type(e).__name__}: {e}"}
            print(draft["error"])
            scenario_records.append({"scenario": sc["id"], "label": sc["label"], "error": draft["error"]})
            print()
            continue
        print(draft["output_text"])
        l = lint(draft["output_text"])
        print()
        print(f"[tokens: in={draft['input_tokens']} out={draft['output_tokens']}]")
        print(f"[lint passes={l['passes']} "
              f"please={l['please_count']} "
              f"we_sent={l['we_sentence_opener_count']} "
              f"we_para={l['we_paragraph_openers']} "
              f"max_para_words={l['max_paragraph_words']} "
              f"max_sent_words={l['max_sentence_words']} "
              f"words={l['word_count']} paras={l['paragraph_count']} "
              f"para_words={l['paragraph_word_counts']}]")
        print()
        scenario_records.append({
            "scenario": sc["id"],
            "label": sc["label"],
            "draft": draft,
            "lint": l,
            "final_text": draft["output_text"],
        })

    # ---- Summary table ----
    print("=" * 76)
    print("SUMMARY")
    print("=" * 76)
    header = f"{'scenario':<38} lint  please we_sent we_para max_para max_sent words"
    print(header)
    for r in scenario_records:
        l = r.get("lint", {})
        if not l:
            print(f"{r['scenario']:<38} ERR")
            continue
        mark = "PASS" if l.get("passes") else "FAIL"
        print(
            f"{r['scenario']:<38} {mark:<5} "
            f"{l['please_count']:<6} {l['we_sentence_opener_count']:<7} "
            f"{l['we_paragraph_openers']:<7} {l['max_paragraph_words']:<8} "
            f"{l['max_sentence_words']:<8} {l['word_count']}"
        )
    print()

    # ---- All final drafts in full ----
    print("=" * 76)
    print("FINAL DRAFTS — ALL 5 SCENARIOS, FULL TEXT")
    print("=" * 76)
    print()
    for r in scenario_records:
        print(f"## {r['scenario']} — {r['label']}")
        print()
        print(r.get("final_text", "(no final text)"))
        print()
        print("-" * 76)
        print()

    # ---- Persist ----
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(__file__).resolve().parent.parent / "data" / "bake-off"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"drafter-singlepass-{ts}.json"
    out_path.write_text(json.dumps({
        "timestamp": ts,
        "writer_model": WRITER_MODEL,
        "system_prompt": SYSTEM_PROMPT,
        "scenarios": scenario_records,
    }, indent=2))
    print(f"Saved: {out_path.relative_to(Path.cwd())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
