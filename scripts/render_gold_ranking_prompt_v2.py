"""Render a less-biased gold-ranking prompt for cross-model validation.

Differences from `render_gold_ranking_prompt.py`:
  - Block order is shuffled with a fixed seed (kills the request_id clustering
    leakage Codex flagged: REQ-001..003 = SLA, REQ-004..006 = statute, etc.).
  - Preamble drops "the ranker reads the same fields" and similar pointers
    that bias the model toward a feature-weighted-sum interpretation.
  - Field glossary uses adjuster-shop domain language, not the scorer's
    internal feature names where possible.

The CSV format requested back is identical so it loads through the same
`load_gold()` in the benchmark script.

Run:
    .venv/bin/python scripts/render_gold_ranking_prompt_v2.py
"""
from __future__ import annotations

import random

from argos.ontology.synthetic_caseload import DEFAULT_AS_OF, build_caseload
from argos.services.triage.features import extract_raw


# Deterministic shuffle — different seed than the tuner so the two procedures
# are independent.
SHUFFLE_SEED = 17


PREAMBLE = """\
You are an experienced claims adjuster. It is 9 AM on Friday, May 29, 2026.

Below is your open queue: 20 active coverage requests. Your job, right now, \
is to rank them top-to-bottom by what you should work on today.

There is no one correct answer. Use adjuster judgment. The fields shown for \
each request are the cross-claim state your shop tracks. Apply the kind of \
reasoning a senior adjuster would: which clocks are firing, what cannot be \
recovered if missed, what exposure could escalate, what is genuinely urgent \
vs what only looks busy.

Field glossary:
- `severity`: minor / standard / serious / catastrophic
- `service_deadline_hours`: hours until a carrier or TPA service deadline \
(24-hour contact, 30-day decision, etc.); `none` if none is firing
- `legal_deadline_days`: days until a statute of limitations or other legal \
deadline; `none` if none is approaching
- `hours_since_last_activity`: hours since anyone or anything last \
touched the file
- `overdue_tasks`: count of follow-up tasks past their fire date
- `total_incurred`: paid to date + current reserve, in dollars
- `days_since_last_claimant_contact`: days since the last claimant-side \
communication
- `new_documents`: documents received since the last file activity
- `litigation` / `claimant_represented` / `complaint`: escalation flags

Return your ranking as CSV with the exact header below, 20 rows, no extra \
commentary outside the CSV block:

```csv
rank,request_id,reason_short
1,REQ-XXX,one-line reason
2,REQ-XXX,one-line reason
...
20,REQ-XXX,one-line reason
```

Caseload (20 requests, listed in arbitrary order):
"""


def _fmt(v: float, kind: str) -> str:
    if kind == "hours_or_none":
        return f"{v:.1f}" if v < 24 * 14 else "none"
    if kind == "days_or_none":
        return f"{int(v)}" if v < 365 else "none"
    if kind == "money":
        return f"${v:,.0f}"
    if kind == "int":
        return str(int(v))
    if kind == "days1":
        return f"{v:.1f}"
    if kind == "hours1":
        return f"{v:.1f}"
    return str(v)


def render() -> str:
    cs = build_caseload(as_of=DEFAULT_AS_OF)
    raw = extract_raw(cs)

    requests = list(cs.requests)
    rng = random.Random(SHUFFLE_SEED)
    rng.shuffle(requests)

    blocks = []
    for request in requests:
        rid = request.request_id
        rf = raw[rid]
        claim = cs.claim_for(request)
        block = (
            f"### {rid}\n"
            f"- severity: {request.severity_tier}\n"
            f"- opened_date: {claim.opened_date.isoformat()}\n"
            f"- service_deadline_hours: {_fmt(rf.hours_until_sla_breach, 'hours_or_none')}\n"
            f"- legal_deadline_days: {_fmt(rf.days_until_statute, 'days_or_none')}\n"
            f"- hours_since_last_activity: {_fmt(rf.hours_since_last_touch, 'hours1')}\n"
            f"- overdue_tasks: {_fmt(rf.open_diary_count, 'int')}\n"
            f"- total_incurred: {_fmt(rf.incurred_amount, 'money')}\n"
            f"- days_since_last_claimant_contact: {_fmt(rf.days_since_claimant_contact, 'days1')}\n"
            f"- new_documents: {_fmt(rf.unread_document_count, 'int')}\n"
            f"- litigation: {bool(rf.litigation_flag)}\n"
            f"- claimant_represented: {bool(rf.rep_flag)}\n"
            f"- complaint: {bool(rf.complaint_flag)}\n"
        )
        blocks.append(block)

    return PREAMBLE + "\n" + "\n".join(blocks)


if __name__ == "__main__":
    print(render())
