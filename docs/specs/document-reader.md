---
tags:
  - project/argos
  - type/spec
  - status/draft
created: 2026-05-31
---

# Document Reader — materiality specialist

The narrow LLM piece the policy-engine triage architecture explicitly
carved out. Reads one document at a time and answers: *does this
document change reserve, liability, coverage, or damages posture?*

This is the spec that closes the architectural loop opened by triage
v3: deterministic gates + within-bucket scoring + LLM only for
extraction and materiality. The policy engine is built; this is the
missing extraction layer.

## What the Reader does

**Input:** one `Document` (body + metadata) + minimal claim context
(severity, current reserves, open coverage status, litigation/rep
flags).

**Output:** a `MaterialityCall`:

- `material: bool` — does this document change adjuster posture?
- `posture_changed: Literal["reserve", "liability", "coverage", "damages", None]` —
  which posture, if any. `None` when `material == False`.
- `reason: str` — one line, ≤ 200 chars, plain-English explanation.
- `text_excerpt: str` — verbatim sentence(s) from the document body
  that support the call. Required when `material == True`; empty when
  `material == False`.

The output is tiny by design. The Reader is one narrow capability
(materiality classification), not a multi-purpose summarizer.

## What the Reader does NOT do

- Does NOT rank claims, prioritize work, or drive triage decisions.
  That is the policy engine's job. The Reader supplies one signal the
  policy engine consumes.
- Does NOT estimate magnitude. "This raises the reserve by ~$120K" is
  the Reserve specialist's job. The Reader only says "this changes
  reserve posture."
- Does NOT infer the new posture. "Coverage tender denial → coverage
  becomes ROR" is the Coverage specialist's job. The Reader only flags
  the change.
- Does NOT write drafts, memos, or letters.
- Does NOT cite multiple documents or do cross-document synthesis.
  One document in, one call out.
- Does NOT invent facts. Every `text_excerpt` must be a verbatim
  quote from the input document body. Hallucinated excerpts fail
  the eval automatically.

This narrowness is the point. The Reader is the smallest LLM unit
the policy engine needs; everything else is downstream specialist
work or downstream policy logic.

## Materiality definition

A document is **material** if a competent adjuster's next required
action on the claim would change after reading it.

- Police report newly assigning fault → liability posture changes
- Demand letter with a specific number → damages posture changes
- Coverage tender denial from co-defendant carrier → coverage posture
  changes
- Medical update showing new diagnosis → reserve posture changes
- Statute notice with deadline → liability/coverage (depending)
- Routine claimant status call note → not material
- Calendar reminder → not material
- Form letter acknowledgment → not material

The line is "would the next action change?" not "is this document
interesting?" An interesting document with no action implication is
not material.

## Architecture role

The Reader is consumed in two places in the policy engine:

1. **Bucket 6 trigger.** Currently: `incurred ≥ $250K AND
   unread_document_count ≥ 1`. Post-Reader integration:
   `incurred ≥ $250K AND material_unread_document_count ≥ 1`. Routine
   status-update letters stop creating false B6 triggers.
2. **Bucket 7 within-bucket score.** Material-doc claims bump above
   non-material-doc claims of similar incurred / aged signal. Same
   linear-scorer math, but with a `material_doc_signal` feature
   replacing the raw `unread_document_count`.

Reader output is also a standalone API for adjusters: "what's new
on my claim?" → list of material docs with one-line reasons.

Integration into the policy engine is **out of scope for this spec**.
The Reader ships standalone first with its own paired-anchor eval.
Wiring into B6/B7 is a follow-up after the Reader's eval passes —
same discipline as triage v3 (built standalone, integrated after the
metric was clean).

## What the Reader sees

The minimum context to make a competent materiality call:

```
DOCUMENT
  document_id, document_type, source, received_date
  body_text (verbatim, full)

CLAIM CONTEXT
  claim_id, severity_tier
  current_reserve_amount (sum of LedgerEntries)
  paid_to_date
  litigation_flag, rep_flag, complaint_flag
  open_coverage_status (pending / clean / ROR / denial)
  loss_facts (one-paragraph intake summary)
```

Not shown: other documents on the claim, full Communications log,
prior AgentActions. The Reader is per-document, not cross-document.
Cross-document synthesis is the per-claim specialist's job.

## Locked design choices

### Model

**Claude Sonnet 4.6** (matches Coverage's default). Sonnet is more
than capable of this narrow classification, and using the same model
across specialists means one cost/latency profile for the per-claim
pipeline.

### Output via Anthropic tool_use

Same pattern as Coverage. `MaterialityCall.model_json_schema()` is
the tool input schema; Pydantic validates the model's output; retry
once on validation failure with the error fed back.

### Schema enforcement

- `text_excerpt` non-empty iff `material == True` (model_validator)
- `posture_changed != None` iff `material == True` (model_validator)
- `text_excerpt` substring of input document body when `material == True`
  (post-call verifier check; hallucinated excerpts fail the eval)

### Prompt — concrete exemplars, not abstract rules

Per the project-level "make decisions in prompts, don't defer to
runtime judgment" rule, the system prompt carries:

- 2 routine-update exemplars labeled NOT MATERIAL
- 4 posture-change exemplars (one per posture) labeled MATERIAL with
  the expected `text_excerpt` shape

Exemplars are short, fictional, and built to be obviously the call
they're labeled as. The point is to nail the decision boundary in
the prompt, not to ask the model to invent one.

## Eval methodology

**Paired anchors with locked deltas, matching Coverage.** Each anchor
pair = same claim context + same document metadata, body differs by
one material event.

- **Variant A (clean):** routine doc body. Expected: `material=False`.
- **Variant B (with-flag):** same body + one added material sentence.
  Expected: `material=True`, `text_excerpt` quoting the new sentence,
  `posture_changed` = whichever posture the new sentence implies.

Initial anchor set: **4 pairs**, one per posture (liability, coverage,
damages, reserve). Locked targets and delta thresholds live in
`docs/evals/document-reader-anchor-pairs-thresholds.md`. Pre-registered
before any model run.

The eval passes only if **all 4 pairs** pass per-variant + paired-delta
+ schema-verifier checks. A single pair failure flips the verdict to
FAIL, regardless of how plausible the other 3 look.

## Implementation surface

| file | purpose |
|---|---|
| `docs/specs/document-reader.md` | this spec |
| `docs/evals/document-reader-anchor-pairs-thresholds.md` | locked thresholds + per-variant targets |
| `src/argos/schemas/specialists/document_reader.py` | `MaterialityCall` Pydantic model |
| `src/argos/specialists/document_reader.py` | runtime: `run_document_reader(doc, ctx) → MaterialityCallResult` |
| `src/argos/ontology/document_reader_anchors.py` | the 4 anchor pairs (claim context + paired document bodies) |
| `scripts/run_document_reader_anchors.py` | runs all 4 pairs once, applies locked thresholds, prints verdict |
| `tests/specialists/test_document_reader.py` | schema tests + retry logic tests; no live API calls in pytest |

## What v1 of the Reader explicitly does NOT prove

- Generalization across carriers (anchors are synthetic, one carrier).
- Latency or cost characteristics at scale.
- Multi-document synthesis.
- Magnitude or posture-inference quality (out of scope by design).
- Integration with policy engine B6/B7 (follow-up after Reader passes).

The Reader's v1 question is narrow: *can a single LLM call reliably
classify document materiality, with verbatim citation, under
pre-registered deltas?* Pass that, then integrate.
