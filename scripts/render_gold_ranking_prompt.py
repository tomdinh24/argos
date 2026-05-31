"""Print the gold-ranking prompt to stdout.

Reads the deterministic caseload + raw features, formats one block per
CoverageRequest (no corner labels exposed — those are the answer key),
and wraps the blocks in a prompt that asks a frontier model to rank the
20 requests top-to-bottom with one-line reasons.

Output is copy-pasteable into any chat UI. The output CSV format the
prompt asks for is exactly what `data/eval-runs/triage-ranker/gold.csv`
expects: `rank,request_id,reason_short`.

Run:
    .venv/bin/python scripts/render_gold_ranking_prompt.py
"""
from __future__ import annotations

from argos.ontology.synthetic_caseload import DEFAULT_AS_OF, build_caseload
from argos.services.triage.features import extract_raw


PREAMBLE = """\
You are an experienced claims adjuster sitting down at 9 AM on Friday, \
May 29, 2026. The caseload below is your open queue — 20 active coverage \
requests across your book. Your job, right now, is to rank them \
top-to-bottom by what you should work on today.

Use your judgment. The fields below are the cross-claim state the system \
tracks for each request. There is no single correct answer — you are \
producing the human-priority reference that a deterministic ranker will \
be benchmarked against. The ranker reads the same fields. You may apply \
adjuster judgment the ranker cannot (e.g., "litigation + statute = no \
matter what else, this is top-3").

Field glossary:
- `severity`: minor / standard / serious / catastrophic
- `sla_hours`: hours until a carrier/TPA service deadline (24h-contact, \
30-day-decision, etc.) — `none` means no SLA is currently firing
- `statute_days`: days until a statute-of-limitations or legal deadline — \
`none` means no statute is approaching
- `hours_since_touch`: hours since the last system or human action on the \
claim
- `open_diary`: count of overdue follow-up tasks
- `incurred`: paid_to_date + current_reserve (dollars)
- `days_since_claimant_contact`: days since the last outbound/inbound \
communication with the claimant
- `unread_docs`: documents received since the last system touch on the \
claim (deterministic shadow of "new evidence arrived" — does not tell \
you whether the doc is material)
- `litigation` / `rep` / `complaint`: boolean escalation flags

Return your ranking as CSV with the exact header below, 20 rows, no \
extra commentary outside the CSV block:

```csv
rank,request_id,reason_short
1,REQ-XXX,one-line reason
2,REQ-XXX,one-line reason
...
20,REQ-XXX,one-line reason
```

Caseload (20 requests):
"""


def _fmt(v: float, kind: str) -> str:
    if kind == "hours_or_none":
        # SLA sentinel is 720h+
        return f"{v:.1f}" if v < 24 * 14 else "none"
    if kind == "days_or_none":
        # statute sentinel is 5*365
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

    blocks = []
    for request in sorted(cs.requests, key=lambda r: r.request_id):
        rid = request.request_id
        rf = raw[rid]
        claim = cs.claim_for(request)
        block = (
            f"### {rid}\n"
            f"- severity: {request.severity_tier}\n"
            f"- opened_date: {claim.opened_date.isoformat()}\n"
            f"- sla_hours: {_fmt(rf.hours_until_sla_breach, 'hours_or_none')}\n"
            f"- statute_days: {_fmt(rf.days_until_statute, 'days_or_none')}\n"
            f"- hours_since_touch: {_fmt(rf.hours_since_last_touch, 'hours1')}\n"
            f"- open_diary: {_fmt(rf.open_diary_count, 'int')}\n"
            f"- incurred: {_fmt(rf.incurred_amount, 'money')}\n"
            f"- days_since_claimant_contact: {_fmt(rf.days_since_claimant_contact, 'days1')}\n"
            f"- unread_docs: {_fmt(rf.unread_document_count, 'int')}\n"
            f"- litigation: {bool(rf.litigation_flag)}\n"
            f"- rep: {bool(rf.rep_flag)}\n"
            f"- complaint: {bool(rf.complaint_flag)}\n"
        )
        blocks.append(block)

    return PREAMBLE + "\n" + "\n".join(blocks)


if __name__ == "__main__":
    print(render())
