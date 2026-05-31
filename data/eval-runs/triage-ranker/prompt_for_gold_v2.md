You are an experienced claims adjuster. It is 9 AM on Friday, May 29, 2026.

Below is your open queue: 20 active coverage requests. Your job, right now, is to rank them top-to-bottom by what you should work on today.

There is no one correct answer. Use adjuster judgment. The fields shown for each request are the cross-claim state your shop tracks. Apply the kind of reasoning a senior adjuster would: which clocks are firing, what cannot be recovered if missed, what exposure could escalate, what is genuinely urgent vs what only looks busy.

Field glossary:
- `severity`: minor / standard / serious / catastrophic
- `service_deadline_hours`: hours until a carrier or TPA service deadline (24-hour contact, 30-day decision, etc.); `none` if none is firing
- `legal_deadline_days`: days until a statute of limitations or other legal deadline; `none` if none is approaching
- `hours_since_last_activity`: hours since anyone or anything last touched the file
- `overdue_tasks`: count of follow-up tasks past their fire date
- `total_incurred`: paid to date + current reserve, in dollars
- `days_since_last_claimant_contact`: days since the last claimant-side communication
- `new_documents`: documents received since the last file activity
- `litigation` / `claimant_represented` / `complaint`: escalation flags

Return your ranking as CSV with the exact header below, 20 rows, no extra commentary outside the CSV block:

```csv
rank,request_id,reason_short
1,REQ-XXX,one-line reason
2,REQ-XXX,one-line reason
...
20,REQ-XXX,one-line reason
```

Caseload (20 requests, listed in arbitrary order):

### REQ-008
- severity: serious
- opened_date: 2026-04-14
- service_deadline_hours: none
- legal_deadline_days: none
- hours_since_last_activity: 24.0
- overdue_tasks: 0
- total_incurred: $585,000
- days_since_last_claimant_contact: 7.0
- new_documents: 0
- litigation: False
- claimant_represented: False
- complaint: False

### REQ-007
- severity: catastrophic
- opened_date: 2026-01-29
- service_deadline_hours: none
- legal_deadline_days: none
- hours_since_last_activity: 24.0
- overdue_tasks: 0
- total_incurred: $1,750,000
- days_since_last_claimant_contact: 7.0
- new_documents: 0
- litigation: False
- claimant_represented: False
- complaint: False

### REQ-016
- severity: serious
- opened_date: 2026-04-14
- service_deadline_hours: none
- legal_deadline_days: none
- hours_since_last_activity: 24.0
- overdue_tasks: 1
- total_incurred: $200,000
- days_since_last_claimant_contact: 7.0
- new_documents: 0
- litigation: True
- claimant_represented: True
- complaint: False

### REQ-015
- severity: serious
- opened_date: 2026-04-14
- service_deadline_hours: none
- legal_deadline_days: none
- hours_since_last_activity: 36.0
- overdue_tasks: 0
- total_incurred: $90,000
- days_since_last_claimant_contact: 7.0
- new_documents: 3
- litigation: False
- claimant_represented: False
- complaint: False

### REQ-006
- severity: standard
- opened_date: 2026-04-14
- service_deadline_hours: none
- legal_deadline_days: 14
- hours_since_last_activity: 24.0
- overdue_tasks: 0
- total_incurred: $30,000
- days_since_last_claimant_contact: 7.0
- new_documents: 0
- litigation: False
- claimant_represented: False
- complaint: False

### REQ-004
- severity: serious
- opened_date: 2026-04-14
- service_deadline_hours: none
- legal_deadline_days: 3
- hours_since_last_activity: 24.0
- overdue_tasks: 0
- total_incurred: $120,000
- days_since_last_claimant_contact: 7.0
- new_documents: 0
- litigation: False
- claimant_represented: False
- complaint: False

### REQ-011
- severity: standard
- opened_date: 2026-04-14
- service_deadline_hours: none
- legal_deadline_days: none
- hours_since_last_activity: 504.0
- overdue_tasks: 0
- total_incurred: $35,000
- days_since_last_claimant_contact: 25.0
- new_documents: 0
- litigation: False
- claimant_represented: False
- complaint: False

### REQ-001
- severity: serious
- opened_date: 2026-04-14
- service_deadline_hours: 1.0
- legal_deadline_days: none
- hours_since_last_activity: 24.0
- overdue_tasks: 0
- total_incurred: $80,000
- days_since_last_claimant_contact: 7.0
- new_documents: 0
- litigation: False
- claimant_represented: False
- complaint: False

### REQ-002
- severity: standard
- opened_date: 2026-04-14
- service_deadline_hours: 4.0
- legal_deadline_days: none
- hours_since_last_activity: 24.0
- overdue_tasks: 0
- total_incurred: $25,000
- days_since_last_claimant_contact: 7.0
- new_documents: 0
- litigation: False
- claimant_represented: False
- complaint: False

### REQ-005
- severity: standard
- opened_date: 2026-04-14
- service_deadline_hours: none
- legal_deadline_days: 7
- hours_since_last_activity: 24.0
- overdue_tasks: 0
- total_incurred: $40,000
- days_since_last_claimant_contact: 7.0
- new_documents: 0
- litigation: False
- claimant_represented: False
- complaint: False

### REQ-009
- severity: serious
- opened_date: 2026-04-14
- service_deadline_hours: none
- legal_deadline_days: none
- hours_since_last_activity: 24.0
- overdue_tasks: 0
- total_incurred: $875,000
- days_since_last_claimant_contact: 7.0
- new_documents: 0
- litigation: False
- claimant_represented: False
- complaint: False

### REQ-019
- severity: minor
- opened_date: 2026-04-14
- service_deadline_hours: none
- legal_deadline_days: none
- hours_since_last_activity: 12.0
- overdue_tasks: 0
- total_incurred: $3,500
- days_since_last_claimant_contact: 2.0
- new_documents: 0
- litigation: False
- claimant_represented: False
- complaint: False

### REQ-020
- severity: minor
- opened_date: 2026-04-14
- service_deadline_hours: none
- legal_deadline_days: none
- hours_since_last_activity: 8.0
- overdue_tasks: 0
- total_incurred: $1,250
- days_since_last_claimant_contact: 1.0
- new_documents: 0
- litigation: False
- claimant_represented: False
- complaint: False

### REQ-013
- severity: standard
- opened_date: 2026-04-14
- service_deadline_hours: none
- legal_deadline_days: none
- hours_since_last_activity: 36.0
- overdue_tasks: 0
- total_incurred: $18,000
- days_since_last_claimant_contact: 7.0
- new_documents: 1
- litigation: False
- claimant_represented: False
- complaint: False

### REQ-003
- severity: standard
- opened_date: 2026-04-14
- service_deadline_hours: 6.0
- legal_deadline_days: none
- hours_since_last_activity: 24.0
- overdue_tasks: 0
- total_incurred: $15,000
- days_since_last_claimant_contact: 7.0
- new_documents: 0
- litigation: False
- claimant_represented: False
- complaint: False

### REQ-018
- severity: standard
- opened_date: 2026-04-14
- service_deadline_hours: none
- legal_deadline_days: none
- hours_since_last_activity: 24.0
- overdue_tasks: 0
- total_incurred: $15,000
- days_since_last_claimant_contact: 2.0
- new_documents: 0
- litigation: False
- claimant_represented: True
- complaint: True

### REQ-012
- severity: serious
- opened_date: 2026-04-14
- service_deadline_hours: none
- legal_deadline_days: none
- hours_since_last_activity: 720.0
- overdue_tasks: 0
- total_incurred: $60,000
- days_since_last_claimant_contact: 30.0
- new_documents: 0
- litigation: False
- claimant_represented: False
- complaint: False

### REQ-010
- severity: standard
- opened_date: 2026-04-14
- service_deadline_hours: none
- legal_deadline_days: none
- hours_since_last_activity: 360.0
- overdue_tasks: 0
- total_incurred: $20,000
- days_since_last_claimant_contact: 20.0
- new_documents: 0
- litigation: False
- claimant_represented: False
- complaint: False

### REQ-014
- severity: serious
- opened_date: 2026-04-14
- service_deadline_hours: none
- legal_deadline_days: none
- hours_since_last_activity: 36.0
- overdue_tasks: 0
- total_incurred: $55,000
- days_since_last_claimant_contact: 7.0
- new_documents: 2
- litigation: False
- claimant_represented: False
- complaint: False

### REQ-017
- severity: serious
- opened_date: 2026-04-14
- service_deadline_hours: none
- legal_deadline_days: 45
- hours_since_last_activity: 24.0
- overdue_tasks: 0
- total_incurred: $350,000
- days_since_last_claimant_contact: 7.0
- new_documents: 0
- litigation: True
- claimant_represented: True
- complaint: False

