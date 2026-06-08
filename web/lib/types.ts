export type Workflow =
  | "coverage"
  | "reserve"
  | "liability"
  | "recovery"
  | "closure"
  | "reopen";

export type TriageBand = "green" | "amber" | "red";

export type ClaimSummary = {
  claim_id: string;
  insured_name: string;
  loss_type: string;
  reported_at: string;
  triage_band: TriageBand;
  next_workflow: Workflow;
  rationale: string;
  reserve_total: number | null;
  status: string;
  // Relative recency of the last thing that happened on the claim (e.g.
  // "2d ago"), shown in the caseload subtext — more useful to a returning
  // adjuster than the reported date. Derived from new_info in the fixture.
  last_activity?: string;
  // Count of unreviewed new documents since the adjuster last looked. Drives
  // the caseload "● N new docs" badge. Derived from new_info.filter(is_new).
  unread_count?: number;
  // The lifecycle stage each unread doc bears on (one entry per unread doc, may
  // repeat). Lets the caseload badge drop as the adjuster reviews those stages.
  unread_stages?: StageKey[];
};

export type ClaimDetail = ClaimSummary & {
  policy_number: string;
  date_of_loss: string;
  jurisdiction: string;
  severity: string;
  description: string;
  pending_recommendations: PendingRecommendation[];
  citations: Citation[];
  // Structured content behind the detail page's Overview / Workflow / Sources
  // tabs. Several surfaces here are schema-backed but not yet emitted by the
  // backend (tagged `proposed` in the UI); fixtures carry demo content so the
  // page renders end to end. Optional so a thin claim still renders.
  dossier?: ClaimDossier;
};

// ── Claim dossier — the per-stage detail content (lifecycle accordion) ──

export type StageKey = "coverage" | "reserve" | "liability" | "recovery" | "closure";

export type NewInfoItem = {
  when: string;
  what: string;
  cite?: number;
  note?: string;
  // Unreviewed since the adjuster last looked — surfaced with a notification tag.
  is_new?: boolean;
  // Which lifecycle stage this change bears on. Lets a Recent-activity item
  // route the adjuster straight to the workflow stage that needs re-review,
  // not just to the source document (`cite`).
  stage?: StageKey;
};

export type Finding = { text: string; cite: number; doc: string };

export type CoverageMap = { accident: string; provision: string; cite: number };
export type DistRow = { label: string; p: number };

// Reserve component band — modelled range with a recommended point and the
// number currently carried. All dollars; the UI formats + positions on a scale.
export type ReserveBand = {
  name: string;
  recommend: number;
  low: number;
  high: number;
  carried: number;
};

export type StageCheck = {
  label: string; // "Sign-off" | "Notice" | "Done"
  status: "need" | "ok";
  title: string;
  detail: string;
  due?: string;
  action?: string;
};

export type AllocRow = { party: string; pct: number; meta: string; primary?: boolean };

export type TodoItem = { text: string; sub: string; done?: boolean; due?: string; action?: string };

export type Econ = { gross: string; drag: string; net: string };

export type RecapRow = { stage: string; outcome: string };

export type ClaimDossier = {
  brief: string;
  new_info: NewInfoItem[];
  coverage: { map: CoverageMap; distribution: DistRow[]; decided_label: string };
  reserve: { findings: Finding[]; bands: ReserveBand[]; checks: StageCheck[]; amount: number };
  liability: { allocation: AllocRow[]; evidence: Finding[] };
  recovery: { status: string; lane: string; todo: TodoItem[]; econ: Econ };
  closure: { status: string; readiness: number; recap: RecapRow[]; amount: number };
};

export type CitationSourceType = "medical" | "policy" | "scene" | "liability" | "other";

export type Citation = {
  citation_id: string;
  index: number;
  source_type: CitationSourceType;
  document: string;
  excerpt: string;
  // Full document text. The viewer renders this with `excerpt` highlighted in
  // context — clicking a citation opens the document, not a bare quote.
  body?: string;
};

export type DashboardMetrics = {
  adjuster_first_name: string;
  active_claims: number;
  active_delta_label: string;
  awaiting_approval: number;
  cycle_time_days: number;
  cycle_band_days: number;
  reserve_accuracy_pct: number;
  reserve_target_pct: number;
  approved_7d: number;
  approved_avg_citations: number;
};

export type PendingRecommendation = {
  recommendation_id: string;
  workflow: Workflow;
  title: string;
  posture: string;
  rationale: string;
  citations: number;
  awaiting_approval: boolean;
  // Structured dollar value for recommendations that turn on an amount
  // (reserve, closure paid total). Editable on Modify as its own field so the
  // adjuster doesn't have to retype a full sentence to change the number.
  amount?: number;
  // Structured findings derived from the model's claim_text (e.g. "policy in
  // force", "coverage type matched"). Rendered above the rationale prose as
  // scan-able bullets so the recommendation reads as evidence, not paragraph.
  findings?: string[];
};

export type ExampleClaim = {
  example_id: string;
  label: string;
  loss_type: string;
  triage_band: TriageBand;
  description: string;
};
