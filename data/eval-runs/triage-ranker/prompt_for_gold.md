You are an experienced claims adjuster sitting down at 9 AM on Friday, May 29, 2026. The caseload below is your open queue — 20 active coverage requests across your book. Your job, right now, is to rank them top-to-bottom by what you should work on today.

Use your judgment. The fields below are the cross-claim state the system tracks for each request. There is no single correct answer — you are producing the human-priority reference that a deterministic ranker will be benchmarked against. The ranker reads the same fields. You may apply adjuster judgment the ranker cannot (e.g., "litigation + statute = no matter what else, this is top-3").

Field glossary:
- `severity`: minor / standard / serious / catastrophic
- `sla_hours`: hours until a carrier/TPA service deadline (24h-contact, 30-day-decision, etc.) — `none` means no SLA is currently firing
- `statute_days`: days until a statute-of-limitations or legal deadline — `none` means no statute is approaching
- `hours_since_touch`: hours since the last system or human action on the claim
- `open_diary`: count of overdue follow-up tasks
- `incurred`: paid_to_date + current_reserve (dollars)
- `days_since_claimant_contact`: days since the last outbound/inbound communication with the claimant
- `unread_docs`: documents received since the last system touch on the claim (deterministic shadow of "new evidence arrived" — does not tell you whether the doc is material)
- `litigation` / `rep` / `complaint`: boolean escalation flags

Return your ranking as CSV with the exact header below, 20 rows, no extra commentary outside the CSV block:

```csv
rank,request_id,reason_short
1,REQ-XXX,one-line reason
2,REQ-XXX,one-line reason
...
20,REQ-XXX,one-line reason
```

Caseload (20 requests):

### REQ-001
- severity: serious
- opened_date: 2026-04-14
- sla_hours: 1.0
- statute_days: none
- hours_since_touch: 24.0
- open_diary: 0
- incurred: $80,000
- days_since_claimant_contact: 7.0
- unread_docs: 0
- litigation: False
- rep: False
- complaint: False

### REQ-002
- severity: standard
- opened_date: 2026-04-14
- sla_hours: 4.0
- statute_days: none
- hours_since_touch: 24.0
- open_diary: 0
- incurred: $25,000
- days_since_claimant_contact: 7.0
- unread_docs: 0
- litigation: False
- rep: False
- complaint: False

### REQ-003
- severity: standard
- opened_date: 2026-04-14
- sla_hours: 6.0
- statute_days: none
- hours_since_touch: 24.0
- open_diary: 0
- incurred: $15,000
- days_since_claimant_contact: 7.0
- unread_docs: 0
- litigation: False
- rep: False
- complaint: False

### REQ-004
- severity: serious
- opened_date: 2026-04-14
- sla_hours: none
- statute_days: 3
- hours_since_touch: 24.0
- open_diary: 0
- incurred: $120,000
- days_since_claimant_contact: 7.0
- unread_docs: 0
- litigation: False
- rep: False
- complaint: False

### REQ-005
- severity: standard
- opened_date: 2026-04-14
- sla_hours: none
- statute_days: 7
- hours_since_touch: 24.0
- open_diary: 0
- incurred: $40,000
- days_since_claimant_contact: 7.0
- unread_docs: 0
- litigation: False
- rep: False
- complaint: False

### REQ-006
- severity: standard
- opened_date: 2026-04-14
- sla_hours: none
- statute_days: 14
- hours_since_touch: 24.0
- open_diary: 0
- incurred: $30,000
- days_since_claimant_contact: 7.0
- unread_docs: 0
- litigation: False
- rep: False
- complaint: False

### REQ-007
- severity: catastrophic
- opened_date: 2026-01-29
- sla_hours: none
- statute_days: none
- hours_since_touch: 24.0
- open_diary: 0
- incurred: $1,750,000
- days_since_claimant_contact: 7.0
- unread_docs: 0
- litigation: False
- rep: False
- complaint: False

### REQ-008
- severity: serious
- opened_date: 2026-04-14
- sla_hours: none
- statute_days: none
- hours_since_touch: 24.0
- open_diary: 0
- incurred: $585,000
- days_since_claimant_contact: 7.0
- unread_docs: 0
- litigation: False
- rep: False
- complaint: False

### REQ-009
- severity: serious
- opened_date: 2026-04-14
- sla_hours: none
- statute_days: none
- hours_since_touch: 24.0
- open_diary: 0
- incurred: $875,000
- days_since_claimant_contact: 7.0
- unread_docs: 0
- litigation: False
- rep: False
- complaint: False

### REQ-010
- severity: standard
- opened_date: 2026-04-14
- sla_hours: none
- statute_days: none
- hours_since_touch: 360.0
- open_diary: 0
- incurred: $20,000
- days_since_claimant_contact: 20.0
- unread_docs: 0
- litigation: False
- rep: False
- complaint: False

### REQ-011
- severity: standard
- opened_date: 2026-04-14
- sla_hours: none
- statute_days: none
- hours_since_touch: 504.0
- open_diary: 0
- incurred: $35,000
- days_since_claimant_contact: 25.0
- unread_docs: 0
- litigation: False
- rep: False
- complaint: False

### REQ-012
- severity: serious
- opened_date: 2026-04-14
- sla_hours: none
- statute_days: none
- hours_since_touch: 720.0
- open_diary: 0
- incurred: $60,000
- days_since_claimant_contact: 30.0
- unread_docs: 0
- litigation: False
- rep: False
- complaint: False

### REQ-013
- severity: standard
- opened_date: 2026-04-14
- sla_hours: none
- statute_days: none
- hours_since_touch: 36.0
- open_diary: 0
- incurred: $18,000
- days_since_claimant_contact: 7.0
- unread_docs: 1
- litigation: False
- rep: False
- complaint: False

### REQ-014
- severity: serious
- opened_date: 2026-04-14
- sla_hours: none
- statute_days: none
- hours_since_touch: 36.0
- open_diary: 0
- incurred: $55,000
- days_since_claimant_contact: 7.0
- unread_docs: 2
- litigation: False
- rep: False
- complaint: False

### REQ-015
- severity: serious
- opened_date: 2026-04-14
- sla_hours: none
- statute_days: none
- hours_since_touch: 36.0
- open_diary: 0
- incurred: $90,000
- days_since_claimant_contact: 7.0
- unread_docs: 3
- litigation: False
- rep: False
- complaint: False

### REQ-016
- severity: serious
- opened_date: 2026-04-14
- sla_hours: none
- statute_days: none
- hours_since_touch: 24.0
- open_diary: 1
- incurred: $200,000
- days_since_claimant_contact: 7.0
- unread_docs: 0
- litigation: True
- rep: True
- complaint: False

### REQ-017
- severity: serious
- opened_date: 2026-04-14
- sla_hours: none
- statute_days: 45
- hours_since_touch: 24.0
- open_diary: 0
- incurred: $350,000
- days_since_claimant_contact: 7.0
- unread_docs: 0
- litigation: True
- rep: True
- complaint: False

### REQ-018
- severity: standard
- opened_date: 2026-04-14
- sla_hours: none
- statute_days: none
- hours_since_touch: 24.0
- open_diary: 0
- incurred: $15,000
- days_since_claimant_contact: 2.0
- unread_docs: 0
- litigation: False
- rep: True
- complaint: True

### REQ-019
- severity: minor
- opened_date: 2026-04-14
- sla_hours: none
- statute_days: none
- hours_since_touch: 12.0
- open_diary: 0
- incurred: $3,500
- days_since_claimant_contact: 2.0
- unread_docs: 0
- litigation: False
- rep: False
- complaint: False

### REQ-020
- severity: minor
- opened_date: 2026-04-14
- sla_hours: none
- statute_days: none
- hours_since_touch: 8.0
- open_diary: 0
- incurred: $1,250
- days_since_claimant_contact: 1.0
- unread_docs: 0
- litigation: False
- rep: False
- complaint: False

