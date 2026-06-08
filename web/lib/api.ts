import type { ClaimDetail, ClaimDossier, ClaimSummary, DashboardMetrics, ExampleClaim, NewInfoItem, PendingRecommendation, StageKey, Workflow } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") ?? "";
const TOKEN = process.env.NEXT_PUBLIC_DEMO_TOKEN ?? "";

export const usingLiveApi = !!API_BASE;

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "content-type": "application/json",
      ...(TOKEN ? { authorization: `Bearer ${TOKEN}` } : {}),
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`${path} → ${res.status}`);
  return res.json() as Promise<T>;
}

export async function getClaims(): Promise<ClaimSummary[]> {
  if (!API_BASE) return FIXTURE_CLAIMS.map(withActivity);
  try {
    return await call<ClaimSummary[]>("/api/claims");
  } catch {
    return FIXTURE_CLAIMS.map(withActivity);
  }
}

// The activity recency + unread count a caseload row needs, derived from the
// claim's new-info log so the list and the detail page never disagree.
function newInfoFor(claimId: string): NewInfoItem[] {
  return NEW_INFO_BY_CLAIM[claimId] ?? SHARED_DOSSIER.new_info;
}

function deriveActivity(
  items: NewInfoItem[],
): { unread_count: number; unread_stages: StageKey[]; last_activity?: string } {
  const unread = items.filter((n) => n.is_new);
  return {
    unread_count: unread.length,
    unread_stages: unread.map((n) => n.stage).filter((s): s is StageKey => s != null),
    last_activity: items[0]?.when, // newest-first, so [0] is the latest
  };
}

function withActivity(c: ClaimSummary): ClaimSummary {
  return { ...c, ...deriveActivity(newInfoFor(c.claim_id)) };
}

export async function getClaim(id: string): Promise<ClaimDetail | null> {
  if (!API_BASE) return FIXTURE_DETAIL[id] ?? null;
  try {
    return await call<ClaimDetail>(`/api/claims/${encodeURIComponent(id)}`);
  } catch {
    return FIXTURE_DETAIL[id] ?? null;
  }
}

// Run a single workflow synchronously to materialize/refresh its draft on the
// backend. No-op offline (fixtures already carry a full dossier).
export async function runWorkflow(
  claimId: string,
  workflow: Workflow,
): Promise<PendingRecommendation | null> {
  if (!API_BASE) return null;
  return await call<PendingRecommendation | null>(
    `/api/claims/${encodeURIComponent(claimId)}/run/${workflow}`,
    { method: "POST" },
  );
}

export type DecisionOutcome = "approved" | "modified" | "rejected";

export type DecisionResponse = {
  ok: boolean;
  decision_id: string;
  next_workflow: Workflow | null;
};

// Commit a human decision on a stage. The backend logs the audit row, routes to
// the orchestrator action handler (which mutates the claim + fires the Foundry
// bridge), and advances the chain on approve/modify. No-op offline.
export async function postDecision(
  claimId: string,
  body: {
    recommendation_id: string;
    workflow: Workflow;
    outcome: DecisionOutcome;
    final_title: string;
    reason?: string;
  },
): Promise<DecisionResponse | null> {
  if (!API_BASE) return null;
  return await call<DecisionResponse>(
    `/api/claims/${encodeURIComponent(claimId)}/decisions`,
    { method: "POST", body: JSON.stringify(body) },
  );
}

export async function getExamples(): Promise<ExampleClaim[]> {
  if (!API_BASE) return FIXTURE_EXAMPLES;
  try {
    return await call<ExampleClaim[]>("/api/demo/examples");
  } catch {
    return FIXTURE_EXAMPLES;
  }
}

export async function getDashboardMetrics(): Promise<DashboardMetrics> {
  if (!API_BASE) return FIXTURE_METRICS;
  try {
    return await call<DashboardMetrics>("/api/metrics");
  } catch {
    return FIXTURE_METRICS;
  }
}

export async function seedExampleClaim(exampleId: string): Promise<ClaimSummary> {
  if (!API_BASE) {
    const ex = FIXTURE_EXAMPLES.find((e) => e.example_id === exampleId);
    return {
      claim_id: `CLM-${Math.floor(Math.random() * 9000 + 1000)}`,
      insured_name: ex?.label ?? "New Claim",
      loss_type: ex?.loss_type ?? "auto-bi",
      reported_at: new Date().toISOString(),
      triage_band: ex?.triage_band ?? "amber",
      next_workflow: "coverage",
      rationale: "Example claim seeded; auto-triage pending.",
      reserve_total: null,
      status: "triaging",
    };
  }
  return await call<ClaimSummary>("/api/demo/seed-claim", {
    method: "POST",
    body: JSON.stringify({ example_id: exampleId }),
  });
}

// Fixtures so the cockpit renders against an unbuilt backend.
const FIXTURE_CLAIMS: ClaimSummary[] = [
  {
    claim_id: "CLM-1042",
    insured_name: "Northbridge Logistics",
    loss_type: "auto-bi",
    reported_at: "2026-05-31T14:12:00Z",
    triage_band: "red",
    next_workflow: "reserve",
    rationale: "Specials $84k with prior surgery — reserve outside band.",
    reserve_total: 92000,
    status: "open",
  },
  {
    claim_id: "CLM-1041",
    insured_name: "Sierra Cement",
    loss_type: "property",
    reported_at: "2026-05-30T18:40:00Z",
    triage_band: "amber",
    next_workflow: "coverage",
    rationale: "Two endorsements cross-cite; posture analysis pending.",
    reserve_total: 38500,
    status: "open",
  },
  {
    claim_id: "CLM-1038",
    insured_name: "Atlas Freight",
    loss_type: "auto-bi",
    reported_at: "2026-05-29T09:05:00Z",
    triage_band: "green",
    next_workflow: "liability",
    rationale: "Clear comparative fault; recovery candidate on subro.",
    reserve_total: 12000,
    status: "open",
  },
];

const COMMON_CITATIONS = [
  { citation_id: "C-01", index: 1, source_type: "medical" as const, document: "ED record · AMC, p.4",
    excerpt: "Pt. presented with cervical pain 8/10; MRI ordered; admitted overnight.",
    body: `ALPINE MEDICAL CENTER — EMERGENCY DEPARTMENT NOTE
MRN 44192 · Date of service 2026-05-22 · Page 4

Chief complaint: Neck pain following motor-vehicle collision.

History: 41-year-old restrained driver, rear-ended while stopped at a signal. Ambulatory at the scene, transported for evaluation.

Exam: Cervical paraspinal tenderness with limited range of motion. Neurologic exam intact.

Assessment / Plan: Pt. presented with cervical pain 8/10; MRI ordered; admitted overnight. Observation and pain control initiated.

Disposition: Admit to observation.` },
  { citation_id: "C-02", index: 2, source_type: "medical" as const, document: "Ortho consult · Dr. Marin, 2026-05-28",
    excerpt: "C4-C5 disc herniation; surgical consult pending; conservative tx exhausted.",
    body: `ORTHOPEDIC CONSULTATION — A. Marin, MD
Date 2026-05-28

Reason for consult: Persistent cervical radiculopathy following MVC of 2026-05-22.

Imaging: MRI of the cervical spine reviewed this date.

Impression: C4-C5 disc herniation; surgical consult pending; conservative tx exhausted.

Recommendation: Refer to spine surgery for operative evaluation; continue activity modification in the interim.` },
  { citation_id: "C-03", index: 3, source_type: "scene" as const, document: "Police report · CHP-2026-0814, line 12",
    excerpt: "Vehicle 2 driver admits inattention; vehicle 1 stopped at red signal.",
    body: `CALIFORNIA HIGHWAY PATROL — TRAFFIC COLLISION REPORT
Report CHP-2026-0814 · Date 2026-05-22

Parties: Vehicle 1 (insured), Vehicle 2 (third party).

Narrative (line 12): Vehicle 2 driver admits inattention; vehicle 1 stopped at red signal.

Primary collision factor: Vehicle 2 — failure to maintain a safe following distance.` },
  { citation_id: "C-04", index: 4, source_type: "liability" as const, document: "Comparative fault memo · 2026-05-26",
    excerpt: "100% allocation to vehicle 2; no contributory factors documented.",
    body: `LIABILITY ANALYSIS — Comparative Fault Memo
Date 2026-05-26

Facts: Rear-end collision. Vehicle 1 stopped at a signal; Vehicle 2 admits inattention per CHP-2026-0814.

Analysis: No evidence of contributory negligence by the insured. No sudden-stop or brake-light defense supported by the record.

Conclusion: 100% allocation to vehicle 2; no contributory factors documented.` },
  { citation_id: "C-05", index: 5, source_type: "policy" as const, document: "Endorsement 3 · POL-2026-0093",
    excerpt: "Specialty BI sublimit raised to $100k; defense within limits.",
    body: `POLICY POL-2026-0093 — ENDORSEMENT 3
Effective 2026-01-01

This endorsement amends the Specialty Bodily Injury coverage part.

Terms: Specialty BI sublimit raised to $100k; defense within limits.

All other terms, conditions, and exclusions of the policy remain unchanged.` },
  { citation_id: "C-06", index: 6, source_type: "policy" as const, document: "Reserve schedule · tier B, band 2",
    excerpt: "Auto BI tier B reserve range $75k–$110k for documented surgical specials.",
    body: `RESERVE SCHEDULE — Auto Bodily Injury
Tier B · Band 2

Guidance: Auto BI tier B reserve range $75k–$110k for documented surgical specials.

Apply the severity multiplier per treatment posture; escalate to supervisor authority above program handling limits.` },
  { citation_id: "C-07", index: 7, source_type: "other" as const, document: "Defense estimate · phase-aligned, 2026-05-30",
    excerpt: "Pre-litigation phase: $11k allocation; mediation phase: +$18k contingent.",
    body: `DEFENSE COST ESTIMATE — Phase-Aligned
Prepared 2026-05-30

Estimate by litigation phase:
Pre-litigation phase: $11k allocation; mediation phase: +$18k contingent.

Trial phase: re-estimate upon scheduling order.` },
];

// Shared per-stage dossier — demo content for the Overview / Workflow / Sources
// tabs. Bracketed [n] markers in prose resolve against COMMON_CITATIONS by index.
const SHARED_DOSSIER: ClaimDossier = {
  brief:
    "Rear-end collision at a signaled intersection. The insured driver was stopped at a red signal when the third-party vehicle struck them from behind [3]. The third-party driver admits inattention on the scene report; no contributory factors are documented for the insured [4]. The claimant reports cervical injury and is in active treatment [1].",
  new_info: [
    {
      when: "2d ago",
      what: "Ortho consult added: C4-C5 disc herniation; surgical consult pending, conservative care exhausted.",
      cite: 2,
      note: "moved the reserve recommendation up.",
      is_new: true,
      stage: "reserve",
    },
    {
      when: "5d ago",
      what: "ED record received: cervical pain 8/10, MRI ordered, admitted overnight.",
      cite: 1,
      is_new: true,
      stage: "reserve",
    },
    {
      when: "8d ago",
      what: "Police report filed: third-party admits inattention; insured stopped at red signal.",
      cite: 3,
      stage: "liability",
    },
  ],
  coverage: {
    map: {
      accident: "Auto BI loss; specialty bodily-injury exposure from the rear-end collision.",
      provision:
        "Endorsement 3 — specialty BI sublimit raised to $100k; defense within limits; loss falls within enumerated perils, no exclusion triggers.",
      cite: 5,
    },
    distribution: [
      { label: "Clean coverage", p: 0.92 },
      { label: "Reservation of rights", p: 0.06 },
      { label: "Denial", p: 0.02 },
    ],
    decided_label: "Affirmed by you · 9:42 AM",
  },
  reserve: {
    findings: [
      { text: "Surgical specials documented — ER admit, cervical pain 8/10, MRI ordered.", cite: 1, doc: "ED record" },
      { text: "C4-C5 disc herniation; surgical consult pending, conservative care exhausted.", cite: 2, doc: "Ortho consult" },
      { text: "$92k sits inside the tier-B range of $75k–$110k for documented surgical specials.", cite: 6, doc: "Reserve schedule" },
    ],
    bands: [
      { name: "Indemnity", recommend: 76000, low: 60000, high: 98000, carried: 72000 },
      { name: "Defense costs", recommend: 13000, low: 11000, high: 19000, carried: 12000 },
    ],
    checks: [
      {
        label: "Sign-off",
        status: "need",
        title: "Needs a supervisor's sign-off",
        detail: "$92k is above your $80k handling authority for this program.",
        action: "Request →",
      },
      {
        label: "Notice",
        status: "need",
        title: "Excess carrier notice owed",
        detail: "The reserve crosses the notice band.",
        due: "due Jun 20",
      },
      {
        label: "Done",
        status: "ok",
        title: "Specials substantiated",
        detail: "Objective MRI on file [2].",
      },
    ],
    amount: 92000,
  },
  liability: {
    allocation: [
      { party: "Third party — Vehicle 2 driver", pct: 100, meta: "band 92–100 · conf 0.94", primary: true },
      { party: "Insured driver", pct: 0, meta: "no contributory factors" },
    ],
    evidence: [
      { text: "Vehicle 2 driver admits inattention; vehicle 1 stopped at red signal.", cite: 3, doc: "Police report, line 12" },
      { text: "100% allocation to vehicle 2; no contributory factors documented.", cite: 4, doc: "Fault memo" },
    ],
  },
  recovery: {
    status: "Pursue",
    lane: "subrogation lane · third-party carrier · 6 citations",
    todo: [
      {
        text: "Preservation hold acknowledgment",
        sub: "scope: vehicle · scene photos · witness statements — acknowledgment pending",
      },
      { text: "Adverse carrier policy limits", sub: "requested from third-party carrier · open 6 days" },
      {
        text: "Demand package draft",
        sub: "specials + liability evidence assembled, demand letter not yet drafted",
        action: "Draft →",
      },
      { text: "Statute of limitations clear", sub: "SOL drop-dead well out", done: true, due: "412 days" },
    ],
    econ: { gross: "$92,000", drag: "−$13,800", net: "$78,200" },
  },
  closure: {
    status: "Ready to close — with payment",
    readiness: 0.88,
    recap: [
      { stage: "Coverage", outcome: "Affirmed on Endorsement 3 ($100k sublimit)" },
      { stage: "Reserve", outcome: "Set to $92,000 (supervisor signed off)" },
      { stage: "Liability", outcome: "100% comparative fault to third party" },
      { stage: "Recovery", outcome: "Subrogation opened; referred to recovery vendor" },
    ],
    amount: 84500,
  },
};

// Per-claim activity logs. Only CLM-1042 (the priority claim) has unread docs,
// so the caseload shows contrast — most rows are quiet, one says "2 new docs".
// The rest of the dossier is shared demo content (see SHARED_DOSSIER).
const NEW_INFO_BY_CLAIM: Record<string, NewInfoItem[]> = {
  "CLM-1042": SHARED_DOSSIER.new_info,
  "CLM-1041": [
    { when: "5d ago", what: "Coverage endorsements cross-cited; posture analysis queued.", stage: "coverage" },
  ],
  "CLM-1038": [
    { when: "1w ago", what: "Comparative-fault memo filed; subrogation candidate flagged.", stage: "liability" },
  ],
};

const FIXTURE_DETAIL: Record<string, ClaimDetail> = Object.fromEntries(
  FIXTURE_CLAIMS.map((c) => [
    c.claim_id,
    {
      ...withActivity(c),
      policy_number: "POL-2026-0093",
      date_of_loss: "2026-05-22",
      jurisdiction: "CA",
      severity: "Serious",
      description:
        "Rear-end collision at signaled intersection. Insured driver stopped. Third-party admits fault on scene report.",
      pending_recommendations: [
        {
          recommendation_id: "REC-A1",
          workflow: c.next_workflow,
          title:
            c.next_workflow === "reserve"
              ? "Set reserve to $92,000"
              : c.next_workflow === "coverage"
              ? "Affirm coverage on Endorsement 3"
              : "Open subrogation on third-party carrier",
          posture: c.next_workflow === "reserve" ? "set" : "affirm",
          rationale:
            "Specials documented in ED + ortho records; multiplier 2.1 on tier B; +$11k phase-aligned defense.",
          citations: 7,
          awaiting_approval: true,
        },
      ],
      citations: COMMON_CITATIONS,
      dossier: { ...SHARED_DOSSIER, new_info: newInfoFor(c.claim_id) },
    } satisfies ClaimDetail,
  ]),
);

const FIXTURE_METRICS: DashboardMetrics = {
  adjuster_first_name: "Tom",
  active_claims: 32,
  active_delta_label: "+4 this week",
  awaiting_approval: 2,
  cycle_time_days: 9.4,
  cycle_band_days: 12,
  reserve_accuracy_pct: 94,
  reserve_target_pct: 90,
  approved_7d: 18,
  approved_avg_citations: 6.2,
};

const FIXTURE_EXAMPLES: ExampleClaim[] = [
  {
    example_id: "EX-AUTO-MOD",
    label: "Moderate auto BI — surgical specials",
    loss_type: "auto-bi",
    triage_band: "red",
    description: "Single-vehicle rear-end, surgical specials, prior MRI.",
  },
  {
    example_id: "EX-PROP-WATER",
    label: "Commercial property — water intrusion",
    loss_type: "property",
    triage_band: "amber",
    description: "Roof-flashing failure with two cross-citing endorsements.",
  },
  {
    example_id: "EX-AUTO-SOFT",
    label: "Soft-tissue auto BI",
    loss_type: "auto-bi",
    triage_band: "green",
    description: "Two-vehicle, clear fault, soft-tissue only.",
  },
];
