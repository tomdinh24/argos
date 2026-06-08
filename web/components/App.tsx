"use client";

import { useEffect, useMemo, useState } from "react";
import { getClaim, getClaims, getDashboardMetrics, getExamples, postDecision, seedExampleClaim } from "@/lib/api";
import type {
  Citation,
  CitationSourceType,
  ClaimDetail,
  ClaimDossier,
  ClaimSummary,
  DashboardMetrics,
  ExampleClaim,
  Finding,
  StageCheck,
  StageKey,
} from "@/lib/types";
import { useWide } from "@/lib/useWide";
import Preload from "./Preload";
import ClaimSweep from "./ClaimSweep";

// Access code is configured per-deploy via NEXT_PUBLIC_ACCESS_CODE (Vercel env).
// No committed fallback: an unconfigured deploy fails closed (see login()).
const ACCESS_CODE = process.env.NEXT_PUBLIC_ACCESS_CODE ?? "";

// Session persistence — adjuster expects to refresh + come back later without
// re-entering the code. Idle TTL keeps the access gate meaningful: a session
// that's been quiet for >TTL has to re-auth.
const SESSION_KEY = "argos.session_at";
const SESSION_TTL_MS = 30 * 60 * 1000;

function readSessionAt(): number | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(SESSION_KEY);
  if (!raw) return null;
  const n = parseInt(raw, 10);
  return Number.isFinite(n) ? n : null;
}

function writeSessionAt(ts: number): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(SESSION_KEY, String(ts));
}

function clearSession(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(SESSION_KEY);
}

type View = "home" | "claim";

// Caseload shows the top priority claims collapsed; the rest sit behind "Show more".
const CASELOAD_COLLAPSED = 5;

export default function App() {
  const [authed, setAuthed] = useState(false);
  const [token, setToken] = useState("");
  const [err, setErr] = useState(false);
  const [view, setView] = useState<View>("home");
  const [activeClaimId, setActiveClaimId] = useState<string | null>(null);
  // Stages the adjuster has reviewed this session, per claim. Clearing a stage's
  // unread here closes the new-info loop across screens — the workflow flag, the
  // Recent-activity dot, and the caseload badge all read from this. (Client-side
  // for the demo; a real backend would track last_viewed_at per user.)
  const [readByClaim, setReadByClaim] = useState<Record<string, StageKey[]>>({});
  const [booting, setBooting] = useState(true);
  const wide = useWide();

  // Rehydrate auth from localStorage on mount. If the last activity stamp is
  // within TTL, skip the access gate. Otherwise the gate shows as normal.
  useEffect(() => {
    const at = readSessionAt();
    if (at != null && Date.now() - at < SESSION_TTL_MS) {
      setAuthed(true);
      writeSessionAt(Date.now());
    } else if (at != null) {
      clearSession();
    }
  }, []);

  // While authed, bump the activity stamp on real interaction (throttled to
  // once a minute — no need to write to localStorage on every mousemove). Also
  // poll every 60s to auto-sign-out if the user steps away past TTL.
  useEffect(() => {
    if (!authed) return;
    let lastWrite = Date.now();
    writeSessionAt(lastWrite);
    function touch() {
      const now = Date.now();
      if (now - lastWrite > 60_000) {
        lastWrite = now;
        writeSessionAt(now);
      }
    }
    const events: Array<keyof WindowEventMap> = [
      "mousedown", "keydown", "touchstart", "scroll", "focus",
    ];
    events.forEach((e) => window.addEventListener(e, touch, { passive: true }));
    const interval = window.setInterval(() => {
      const at = readSessionAt();
      if (at == null || Date.now() - at >= SESSION_TTL_MS) {
        clearSession();
        setAuthed(false);
        setView("home");
        setActiveClaimId(null);
      }
    }, 60_000);
    return () => {
      events.forEach((e) => window.removeEventListener(e, touch));
      window.clearInterval(interval);
    };
  }, [authed]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setBooting(false);
      return;
    }
    const t = setTimeout(() => setBooting(false), 2200);
    return () => clearTimeout(t);
  }, []);

  function login() {
    // Fail closed when no access code is configured for this deploy.
    if (!ACCESS_CODE || token !== ACCESS_CODE) {
      setErr(true);
      return;
    }
    setErr(false);
    writeSessionAt(Date.now());
    setAuthed(true);
  }
  function signOut() {
    clearSession();
    setAuthed(false);
    setToken("");
    setView("home");
    setActiveClaimId(null);
  }

  return (
    <div className={`app${wide ? " app--wide" : ""}`}>
      {booting ? <Preload /> : null}
      {!authed ? (
        <Landing token={token} setToken={setToken} err={err} setErr={setErr} onSubmit={login} />
      ) : view === "home" ? (
        <Home
          onOpenClaim={(id) => {
            setActiveClaimId(id);
            setView("claim");
          }}
          readByClaim={readByClaim}
          onSignOut={signOut}
        />
      ) : (
        <ClaimDetailScreen
          claimId={activeClaimId}
          read={(activeClaimId && readByClaim[activeClaimId]) || []}
          onMarkRead={(stage) =>
            setReadByClaim((prev) => {
              if (!activeClaimId) return prev;
              const cur = prev[activeClaimId] ?? [];
              if (cur.includes(stage)) return prev;
              return { ...prev, [activeClaimId]: [...cur, stage] };
            })
          }
          onBack={() => setView("home")}
        />
      )}
    </div>
  );
}

function Landing({
  token,
  setToken,
  err,
  setErr,
  onSubmit,
}: {
  token: string;
  setToken: (v: string) => void;
  err: boolean;
  setErr: (v: boolean) => void;
  onSubmit: () => void;
}) {
  return (
    <div className="screen">
      <div className="vlogin">
        <div className="corner">ARGOS / ACCESS</div>
        <div className="lside">
          <div className="ltop">
            <div className="wm">
              <span className="mk" />
              ARGOS
            </div>
            <span className="lidx">001 / ACCESS</span>
          </div>
          <div className="lmid">
            <div className="lhero">
              <h1>
                Sourced claims operations for <em>specialty TPAs.</em>
              </h1>
              <p>
                Argos drafts coverage, reserve, liability, recovery, and closure work product from the
                claim file. Every recommendation cites the documents it rests on.
              </p>
            </div>
            <div className="csweep-wrap">
              <ClaimSweep />
            </div>
          </div>
          <div className="lfoot">Private demo · by invitation</div>
        </div>
        <div className="rside">
          <div className="rtop">
            <span>002 / AUTH</span>
            <span>v0</span>
          </div>
          <form
            className="lform"
            onSubmit={(e) => {
              e.preventDefault();
              onSubmit();
            }}
          >
            {err ? (
              <div className="banner err">
                <span className="bk">Denied</span>
                <span>Access code did not match.</span>
              </div>
            ) : null}
            <label className="fl" htmlFor="access">Access code</label>
            <input
              id="access"
              className={`inp${err ? " bad" : ""}`}
              type="password"
              autoComplete="off"
              value={token}
              onChange={(e) => {
                setToken(e.target.value);
                if (err) setErr(false);
              }}
              placeholder="••••••••"
            />
            <button className="btn" type="submit">Enter cockpit</button>
          </form>
          <div className="rfoot">
            <span>argos claims</span>
            <span>2026</span>
          </div>
        </div>
        <div className="foot">Private demo · by invitation</div>
      </div>
    </div>
  );
}

function Home({
  onOpenClaim,
  readByClaim,
  onSignOut,
}: {
  onOpenClaim: (id: string) => void;
  readByClaim: Record<string, StageKey[]>;
  onSignOut: () => void;
}) {
  const [claims, setClaims] = useState<ClaimSummary[] | null>(null);
  const [examples, setExamples] = useState<ExampleClaim[]>([]);
  const [metrics, setMetrics] = useState<DashboardMetrics | null>(null);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [triaging, setTriaging] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);

  useEffect(() => {
    getClaims().then(setClaims).catch(() => setClaims([]));
    getExamples().then(setExamples).catch(() => setExamples([]));
    getDashboardMetrics().then(setMetrics).catch(() => setMetrics(null));
  }, []);

  async function addExample(ex: ExampleClaim) {
    setSheetOpen(false);
    const seeded = await seedExampleClaim(ex.example_id);
    setTriaging(seeded.claim_id);
    setClaims((prev) => [seeded, ...(prev ?? [])]);
    // Auto-triage settles after a short hold so the rationale field can populate.
    setTimeout(() => {
      setClaims((prev) =>
        (prev ?? []).map((c) =>
          c.claim_id === seeded.claim_id
            ? { ...c, rationale: c.rationale || "Auto-triage complete.", status: "open" }
            : c,
        ),
      );
      setTriaging(null);
    }, 1400);
  }

  return (
    <div className="screen">
      <div className="vtop">
        <div className="brand">
          <span className="mk" />
          ARGOS
        </div>
        <button className="menu" onClick={onSignOut} aria-label="Sign out">
          <span style={{ fontFamily: "var(--mono)", fontSize: 11, letterSpacing: ".08em", textTransform: "uppercase", color: "var(--muted)" }}>
            Sign out
          </span>
        </button>
      </div>
      <div className="scroll">
        {metrics ? <Dashboard metrics={metrics} /> : null}
        <div className="caseload-head">
          <div className="caseload-l">
            <span className="caseload-title">Caseload</span>
            <span className="caseload-meta">Sorted by priority</span>
          </div>
          <button className="ghost-btn" onClick={() => setSheetOpen(true)} aria-label="Add example claim">
            <span className="plus">+</span>Add example
          </button>
        </div>
        <div className="pad">
        {claims === null ? (
          <div className="muted" style={{ padding: "18px 0", fontSize: 13 }}>Loading caseload…</div>
        ) : claims.length === 0 ? (
          <div className="muted" style={{ padding: "18px 0", fontSize: 13 }}>
            No open claims. Add an example to see the workflow chain run end to end.
          </div>
        ) : (
          <>
            {(showAll ? claims : claims.slice(0, CASELOAD_COLLAPSED)).map((c) => (
              <ClaimRow
                key={c.claim_id}
                claim={c}
                read={readByClaim[c.claim_id] ?? []}
                triaging={triaging === c.claim_id}
                onClick={() => onOpenClaim(c.claim_id)}
              />
            ))}
            {claims.length > CASELOAD_COLLAPSED ? (
              <button className="showmore" onClick={() => setShowAll((v) => !v)}>
                {showAll ? "Show less" : `Show ${claims.length - CASELOAD_COLLAPSED} more`}
              </button>
            ) : null}
          </>
        )}
        </div>
      </div>
      {sheetOpen ? (
        <ExampleSheet examples={examples} onPick={addExample} onClose={() => setSheetOpen(false)} />
      ) : null}
    </div>
  );
}

function ClaimRow({
  claim,
  read,
  triaging,
  onClick,
}: {
  claim: ClaimSummary;
  read: StageKey[];
  triaging: boolean;
  onClick: () => void;
}) {
  const date = useMemo(() => formatDate(claim.reported_at), [claim.reported_at]);
  // Unread docs minus the stages the adjuster has already reviewed — so the
  // badge drops once they've worked the new info, closing the loop.
  const unread = (claim.unread_stages ?? []).filter((s) => !read.includes(s)).length;
  return (
    <button className="crow" onClick={onClick}>
      <span className="cid">{claim.claim_id}</span>
      <span className="cmain">
        <h3>{claim.insured_name}</h3>
        <div className="csub">
          {labelForLossType(claim.loss_type)} · {claim.last_activity ?? date}
          {unread ? (
            <span className="newbadge">
              <span className="d" aria-hidden />
              {unread} new doc{unread === 1 ? "" : "s"}
            </span>
          ) : null}
        </div>
        {triaging ? (
          <div className="crat">
            <span className="tchip"><span className="d" />Auto-triaging</span>
          </div>
        ) : (
          <div className="crat">{claim.rationale}</div>
        )}
      </span>
      <span className="cright">
        {labelForBand(claim.triage_band) && (
          <div className={`cband ${claim.triage_band}`}>{labelForBand(claim.triage_band)}</div>
        )}
        <div className="cresv">
          {claim.reserve_total != null ? `$${claim.reserve_total.toLocaleString()}` : "—"}
        </div>
      </span>
    </button>
  );
}

function ExampleSheet({
  examples,
  onPick,
  onClose,
}: {
  examples: ExampleClaim[];
  onPick: (ex: ExampleClaim) => void;
  onClose: () => void;
}) {
  return (
    <div className="sheet" onClick={onClose}>
      <div className="sheetbody" onClick={(e) => e.stopPropagation()}>
        <div className="sheethead">
          <h2>Pick an example claim</h2>
          <button className="x" onClick={onClose}>Close</button>
        </div>
        {examples.length === 0 ? (
          <div className="muted" style={{ fontSize: 13 }}>No examples available.</div>
        ) : (
          examples.map((ex) => (
            <button key={ex.example_id} className="exrow" onClick={() => onPick(ex)}>
              <div className={`exl ${labelForBand(ex.triage_band) ? ex.triage_band : ""}`}>
                {labelForBand(ex.triage_band) ? `${labelForBand(ex.triage_band)} · ` : ""}
                {labelForLossType(ex.loss_type)}
              </div>
              <h3>{ex.label}</h3>
              <p>{ex.description}</p>
            </button>
          ))
        )}
      </div>
    </div>
  );
}

function Dashboard({ metrics }: { metrics: DashboardMetrics }) {
  const greeting = useMemo(() => {
    const h = new Date().getHours();
    if (h < 5) return "Working late";
    if (h < 12) return "Good morning";
    if (h < 17) return "Good afternoon";
    return "Good evening";
  }, []);
  return (
    <div className="dash">
      <div className="greet">
        <h2>{greeting}, {metrics.adjuster_first_name}.</h2>
        <p>
          {metrics.active_claims} active · {metrics.awaiting_approval} awaiting your approval
        </p>
      </div>
      <div className="metric-grid">
        <Metric
          label="Active"
          value={String(metrics.active_claims)}
          note={metrics.active_delta_label}
          tone="neutral"
        />
        <Metric
          label="Cycle time"
          value={`${metrics.cycle_time_days}d`}
          note={`band ${metrics.cycle_band_days}d`}
          tone={metrics.cycle_time_days <= metrics.cycle_band_days ? "good" : "warn"}
        />
        <Metric
          label="Reserve accuracy"
          value={`${metrics.reserve_accuracy_pct}%`}
          note={`target ${metrics.reserve_target_pct}%`}
          tone={metrics.reserve_accuracy_pct >= metrics.reserve_target_pct ? "good" : "warn"}
        />
        <Metric
          label="Approved (7d)"
          value={String(metrics.approved_7d)}
          note={`avg ${metrics.approved_avg_citations} citations`}
          tone="accent"
        />
      </div>
    </div>
  );
}

function Metric({
  label,
  value,
  note,
  tone,
}: {
  label: string;
  value: string;
  note: string;
  tone: "good" | "warn" | "accent" | "neutral";
}) {
  return (
    <div className={`metric metric--${tone}`}>
      <div className="metric-l">{label}</div>
      <div className="metric-v">{value}</div>
      <div className="metric-n">{note}</div>
    </div>
  );
}

// Lifecycle stages, in order. The detail page's Workflow tab renders these as a
// stacked accordion: stages before the active one are accepted, the active one
// needs the adjuster, the rest are upcoming drafts.
const STAGE_CHAIN: StageKey[] = ["coverage", "reserve", "liability", "recovery", "closure"];

// Per-stage display copy for the accordion summary row.
const STAGE_META: Record<StageKey, { name: string; summary: string }> = {
  coverage: { name: "Coverage", summary: "Affirmed on Endorsement 3" },
  reserve: { name: "Reserve", summary: "Set reserve to $92,000" },
  liability: { name: "Liability", summary: "Draft: allocate 100% fault to third party" },
  recovery: { name: "Recovery", summary: "Subrogation viable — items still needed" },
  closure: { name: "Closure", summary: "Ready to close with payment" },
};

function formatAmount(n: number): string {
  return `$${n.toLocaleString()}`;
}

function parseAmount(s: string): number | null {
  const cleaned = s.replace(/[^0-9.]/g, "");
  if (!cleaned) return null;
  const n = parseFloat(cleaned);
  return Number.isFinite(n) ? Math.round(n) : null;
}

// Compact dollar label for band scales — $76k, $110k.
function shortAmount(n: number): string {
  return `$${Math.round(n / 1000)}k`;
}

// Position (0–100%) of a value on a [low, high] scale, clamped.
function scalePct(value: number, low: number, high: number): number {
  if (high <= low) return 0;
  return Math.max(0, Math.min(100, ((value - low) / (high - low)) * 100));
}

type DetailTab = "overview" | "workflow" | "sources";

function ClaimDetailScreen({
  claimId,
  read,
  onMarkRead,
  onBack,
}: {
  claimId: string | null;
  read: StageKey[];
  onMarkRead: (stage: StageKey) => void;
  onBack: () => void;
}) {
  const [claim, setClaim] = useState<ClaimDetail | null>(null);
  const [tab, setTab] = useState<DetailTab>("overview");
  // Stages the adjuster has settled. Stages before the claim's next workflow
  // start settled; the first unsettled stage is the one that needs them.
  const [accepted, setAccepted] = useState<Set<StageKey>>(new Set());
  const [activeCitation, setActiveCitation] = useState<Citation | null>(null);
  // Stage the adjuster routed to from Recent activity — overrides which
  // accordion card opens, so the changed stage is what they land on.
  const [openStage, setOpenStage] = useState<StageKey | null>(null);

  useEffect(() => {
    if (!claimId) return;
    setClaim(null);
    setTab("overview");
    setOpenStage(null);
    getClaim(claimId).then((c) => {
      setClaim(c);
      const idx = c ? STAGE_CHAIN.indexOf(c.next_workflow as StageKey) : -1;
      setAccepted(new Set(idx > 0 ? STAGE_CHAIN.slice(0, idx) : []));
    });
  }, [claimId]);

  if (!claim) {
    return (
      <div className="screen">
        <DetailTopbar onBack={onBack} claimId={claimId} />
        <div className="scroll pad">
          <div className="muted" style={{ fontSize: 13, padding: "18px 0" }}>Loading claim…</div>
        </div>
      </div>
    );
  }

  const activeStage = STAGE_CHAIN.find((s) => !accepted.has(s)) ?? null;

  // Stages carrying unread new info the adjuster hasn't reviewed yet — drives
  // the per-stage flag and the Recent-activity dot. Reviewed stages drop out.
  const unreadStages = new Set(
    (claim.dossier?.new_info ?? [])
      .filter((n): n is typeof n & { stage: StageKey } => !!n.is_new && !!n.stage && !read.includes(n.stage))
      .map((n) => n.stage),
  );

  function acceptStage(stage: StageKey) {
    setAccepted((prev) => new Set(prev).add(stage)); // optimistic — UI advances now
    onMarkRead(stage); // acting on the stage clears its new-info flag
    // Commit to the backend: logs the audit row, routes to the orchestrator
    // action handler (mutates the claim + fires the Foundry bridge), advances
    // the chain. No-op offline (returns null), so fixtures still work. On
    // success, refetch so committed state (e.g. coverage posture) is reflected.
    if (claim) {
      const rec = claim.pending_recommendations.find((r) => r.workflow === stage);
      postDecision(claim.claim_id, {
        recommendation_id: rec?.recommendation_id ?? `${claim.claim_id}:${stage}`,
        workflow: stage,
        outcome: "approved",
        final_title: rec?.title ?? `Approved ${stage}`,
      })
        .then((res) => {
          if (res) getClaim(claim.claim_id).then((c) => c && setClaim(c));
        })
        .catch(() => {}); // offline / transient — optimistic UI already advanced
    }
  }

  // Recent activity → "Review {stage}": switch to Workflow and open that card.
  function routeToStage(stage: StageKey) {
    setOpenStage(stage);
    setTab("workflow");
  }

  return (
    <div className="screen">
      <DetailTopbar onBack={onBack} claimId={claim.claim_id} />
      <div className="scroll pad">
        <div className="wrap">
          <ClaimHeaderCard claim={claim} />

          <div className="tabs" role="tablist">
            <button className={`tab${tab === "overview" ? " on" : ""}`} onClick={() => setTab("overview")}>Overview</button>
            <button className={`tab${tab === "workflow" ? " on" : ""}`} onClick={() => setTab("workflow")}>Workflow</button>
            <button className={`tab${tab === "sources" ? " on" : ""}`} onClick={() => setTab("sources")}>
              Documents <span className="badge">{claim.citations.length}</span>
            </button>
          </div>

          {!claim.dossier ? (
            <div className="muted" style={{ fontSize: 13, padding: "18px 0", lineHeight: 1.6 }}>
              Workflow chain queued — Argos drafts coverage, reserve, liability,
              recovery, and closure on first open. Check back in a moment.
            </div>
          ) : tab === "overview" ? (
            <OverviewPanel
              dossier={claim.dossier}
              citations={claim.citations}
              unreadStages={unreadStages}
              onCite={setActiveCitation}
              onRoute={routeToStage}
            />
          ) : tab === "workflow" ? (
            <WorkflowPanel
              dossier={claim.dossier}
              citations={claim.citations}
              accepted={accepted}
              activeStage={activeStage}
              openStage={openStage}
              unreadStages={unreadStages}
              onAccept={acceptStage}
              onCite={setActiveCitation}
            />
          ) : (
            <SourcesPanel citations={claim.citations} onCite={setActiveCitation} />
          )}
        </div>
      </div>
      {activeCitation ? (
        <DocumentSheet citation={activeCitation} onClose={() => setActiveCitation(null)} />
      ) : null}
    </div>
  );
}

// Section heading — just the title. No inline hint/subtext on the heading line.
function Sect({ title }: { title: string }) {
  return (
    <div className="sect">
      <h3>{title}</h3>
    </div>
  );
}

// Inline [n] citation markers in prose → clickable chips that open the source.
function CiteText({
  text,
  citations,
  onCite,
  className,
}: {
  text: string;
  citations: Citation[];
  onCite: (c: Citation) => void;
  className?: string;
}) {
  const parts = text.split(/(\[\d+\])/g);
  return (
    <p className={className ?? "brief"}>
      {parts.map((part, i) => {
        const m = part.match(/^\[(\d+)\]$/);
        if (m) {
          const idx = parseInt(m[1], 10);
          const c = citations.find((x) => x.index === idx);
          if (c) {
            return (
              <button
                key={i}
                type="button"
                className="cite-link"
                onClick={(e) => {
                  e.stopPropagation();
                  onCite(c);
                }}
              >
                {String(idx).padStart(2, "0")}
              </button>
            );
          }
        }
        return <span key={i}>{part}</span>;
      })}
    </p>
  );
}

// Clickable findings — each row links to the document it rests on.
function FindingList({ items, citations, onCite }: { items: Finding[]; citations: Citation[]; onCite: (c: Citation) => void }) {
  return (
    <ul className="findings2">
      {items.map((f, i) => {
        const c = citations.find((x) => x.index === f.cite);
        return (
          <li key={i}>
            <button className="finding" type="button" onClick={() => c && onCite(c)}>
              <span className="tick">✓</span>
              <span className="ftext">{f.text}</span>
              <span className="fdoc">{f.doc} ↗</span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

function CheckList({ items }: { items: StageCheck[] }) {
  return (
    <div className="checks">
      {items.map((c, i) => (
        <div className="check" key={i}>
          <span className={`ck ${c.status}`}>{c.label}</span>
          <div className="cbody">
            <div className="ct">{c.title}</div>
            <div className="cd">{c.detail}</div>
          </div>
          {c.due ? <span className="cwhen">{c.due}</span> : null}
        </div>
      ))}
    </div>
  );
}

// ── Overview tab — the claim story + what changed since last look ──

function OverviewPanel({
  dossier,
  citations,
  unreadStages,
  onCite,
  onRoute,
}: {
  dossier: ClaimDossier;
  citations: Citation[];
  unreadStages: Set<StageKey>;
  onCite: (c: Citation) => void;
  onRoute: (stage: StageKey) => void;
}) {
  return (
    <section className="panel on">
      <Sect title="Claim summary" />
      <CiteText text={dossier.brief} citations={citations} onCite={onCite} />

      <Sect title="Recent activity" />
      <ul className="nlog">
        {dossier.new_info.map((n, i) => {
          const c = n.cite != null ? citations.find((x) => x.index === n.cite) : undefined;
          // Unread only while the stage it touches is still unreviewed.
          const unread = !!n.is_new && !!n.stage && unreadStages.has(n.stage);
          return (
            <li key={i} className={unread ? "new" : undefined}>
              <span className="udot">{unread ? <span className="d" aria-label="unread" /> : null}</span>
              <span className="when">{n.when}</span>
              <span className="what">
                {n.what}{" "}
                {c ? (
                  <button type="button" className="cite-link" onClick={() => onCite(c)}>
                    {String(c.index).padStart(2, "0")}
                  </button>
                ) : null}
                {n.note ? <span className="nnote"> — {n.note}</span> : null}
                {n.stage ? (
                  <button type="button" className="route-link" onClick={() => onRoute(n.stage!)}>
                    Review {STAGE_META[n.stage].name} →
                  </button>
                ) : null}
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

// ── Workflow tab — lifecycle accordion ──

type StageState = { state: "done" | "active" | "pending"; chip: string; chipClass: string };

function stageStatus(stage: StageKey, accepted: Set<StageKey>, activeStage: StageKey | null): StageState {
  if (accepted.has(stage)) return { state: "done", chip: "Complete", chipClass: "done" };
  if (stage === activeStage) return { state: "active", chip: "Review", chipClass: "review" };
  const ai = activeStage ? STAGE_CHAIN.indexOf(activeStage) : STAGE_CHAIN.length;
  const si = STAGE_CHAIN.indexOf(stage);
  if (si === ai + 1) return { state: "pending", chip: "Up next", chipClass: "upnext" };
  return { state: "pending", chip: "Pending", chipClass: "pending" };
}

function WorkflowPanel({
  dossier,
  citations,
  accepted,
  activeStage,
  openStage,
  unreadStages,
  onAccept,
  onCite,
}: {
  dossier: ClaimDossier;
  citations: Citation[];
  accepted: Set<StageKey>;
  activeStage: StageKey | null;
  openStage: StageKey | null;
  unreadStages: Set<StageKey>;
  onAccept: (stage: StageKey) => void;
  onCite: (c: Citation) => void;
}) {
  // A routed-to stage takes precedence over the default (the active stage).
  const opened = openStage ?? activeStage;
  return (
    <section className="panel on">
      <div className="stack">
        {STAGE_CHAIN.map((stage) => {
          const status = stageStatus(stage, accepted, activeStage);
          const meta = STAGE_META[stage];
          const hasNew = unreadStages.has(stage);
          return (
            <details key={stage} className={`scard ${status.state}${hasNew ? " has-new" : ""}`} open={stage === opened}>
              <summary>
                <span className="sc-dot" />
                <span className="sc-name">{meta.name}</span>
                {hasNew ? <span className="sc-new" aria-label="new info" /> : null}
                <span className="sc-sum">{meta.summary}</span>
                <span className={`sc-chip ${status.chipClass}`}>{status.chip}</span>
              </summary>
              <div className="sc-body">
                <StageBody stage={stage} dossier={dossier} citations={citations} onAccept={() => onAccept(stage)} onCite={onCite} />
              </div>
            </details>
          );
        })}
      </div>
    </section>
  );
}

function StageBody({
  stage,
  dossier,
  citations,
  onAccept,
  onCite,
}: {
  stage: StageKey;
  dossier: ClaimDossier;
  citations: Citation[];
  onAccept: () => void;
  onCite: (c: Citation) => void;
}) {
  switch (stage) {
    case "coverage":
      return <CoverageBody d={dossier} citations={citations} onCite={onCite} />;
    case "reserve":
      return <ReserveBody d={dossier} citations={citations} onAccept={onAccept} onCite={onCite} />;
    case "liability":
      return <LiabilityBody d={dossier} citations={citations} onAccept={onAccept} onCite={onCite} />;
    case "recovery":
      return <RecoveryBody d={dossier} onAccept={onAccept} />;
    case "closure":
      return <ClosureBody d={dossier} onAccept={onAccept} />;
  }
}

function CoverageBody({ d, citations, onCite }: { d: ClaimDossier; citations: Citation[]; onCite: (c: Citation) => void }) {
  const cov = d.coverage;
  const provCite = citations.find((x) => x.index === cov.map.cite);
  return (
    <>
      <Sect title="Why this is covered" />
      <div className="cmap">
        <div className="cmap-row">
          <div className="cmap-cell l">
            <div className="cmap-k">The accident</div>
            <div className="cmap-v">{cov.map.accident}</div>
          </div>
          <div className="cmap-arrow">→</div>
          <div className="cmap-cell">
            <div className="cmap-k">The provision that covers it</div>
            <div className="cmap-v">{cov.map.provision}</div>
            {provCite ? (
              <div className="cmap-cite">
                <button type="button" className="cite cite--btn cmap-citebtn" onClick={() => onCite(provCite)}>
                  <span className="cite-idx">[{String(provCite.index).padStart(2, "0")}]</span>
                  <div className="cite-body">
                    <div className="cite-doc">
                      {provCite.document}
                      <span className={`cite-kind cite-kind--${provCite.source_type}`}>{labelForSource(provCite.source_type)}</span>
                    </div>
                  </div>
                  <span className="cite-chev">↗</span>
                </button>
              </div>
            ) : null}
          </div>
        </div>
      </div>

      <Sect title="Coverage outcome" />
      <div className="dist">
        {cov.distribution.map((row, i) => (
          <div className="distrow" key={i}>
            <span className="dl">{row.label}</span>
            <div className="dbar">
              <div className={`dfill${i > 0 ? " dim" : ""}`} style={{ width: `${Math.round(row.p * 100)}%` }} />
            </div>
            <span className="dp">{row.p.toFixed(2)}</span>
          </div>
        ))}
      </div>
      <div className="stage-note">{cov.decided_label}</div>
    </>
  );
}

function ReserveBody({
  d,
  citations,
  onAccept,
  onCite,
}: {
  d: ClaimDossier;
  citations: Citation[];
  onAccept: () => void;
  onCite: (c: Citation) => void;
}) {
  const r = d.reserve;
  const [amount, setAmount] = useState(r.amount.toLocaleString());
  return (
    <>
      <Sect title="Recommended reserve" />
      <FindingList items={r.findings} citations={citations} onCite={onCite} />

      <Sect title="Reserve breakdown" />
      <div className="bands">
        {r.bands.map((b, i) => (
          <div className="bandrow" key={i}>
            <div className="bhead">
              <span className="bname">{b.name}</span>
              <span className="bp50">{shortAmount(b.recommend)}<small>recommended</small></span>
            </div>
            <div className="bar">
              <div className="track" />
              <div className="end" style={{ left: 0 }} />
              <div className="end" style={{ right: 0 }} />
              <div className="cur" style={{ left: `${scalePct(b.carried, b.low, b.high)}%` }} />
              <div className="p50dot" style={{ left: `${scalePct(b.recommend, b.low, b.high)}%` }} />
            </div>
            <div className="bscale"><span>{shortAmount(b.low)}</span><span>{shortAmount(b.high)}</span></div>
            <div className="curkey"><span className="sw" />Currently reserved: {shortAmount(b.carried)}</div>
          </div>
        ))}
      </div>

      <Sect title="Before this can be booked" />
      <CheckList items={r.checks} />

      <Sect title="Reserve amount" />
      <div className="amount-row">
        <span className="amount-prefix">$</span>
        <input className="inp amount-input" type="text" inputMode="numeric" value={amount} onChange={(e) => setAmount(e.target.value)} />
      </div>
      <button className="cta" onClick={onAccept}>Request sign-off</button>
    </>
  );
}

function LiabilityBody({
  d,
  citations,
  onAccept,
  onCite,
}: {
  d: ClaimDossier;
  citations: Citation[];
  onAccept: () => void;
  onCite: (c: Citation) => void;
}) {
  const l = d.liability;
  return (
    <>
      <Sect title="Fault allocation" />
      <div className="alloc">
        {l.allocation.map((a, i) => (
          <div key={i} className={`seg ${a.primary ? "tp" : "ins"}`} style={{ width: `${a.pct}%` }} />
        ))}
      </div>
      <div className="allocrows">
        {l.allocation.map((a, i) => (
          <div className="allocrow" key={i}>
            <span className="aparty">{a.party}</span>
            <span className="ap">{a.pct}%</span>
            <span className="aconf">{a.meta}</span>
          </div>
        ))}
      </div>

      <Sect title="The evidence behind it" />
      <FindingList items={l.evidence} citations={citations} onCite={onCite} />

      <button className="cta" onClick={onAccept}>Mark complete</button>
    </>
  );
}

function RecoveryBody({ d, onAccept }: { d: ClaimDossier; onAccept: () => void }) {
  const rec = d.recovery;
  return (
    <>
      <div className="statusrow">
        <span className="statuschip">{rec.status}</span>
        <span className="statusmeta">{rec.lane}</span>
      </div>

      <Sect title="Still needed" />
      <ul className="todo">
        {rec.todo.map((t, i) => (
          <li key={i}>
            <span className={`box${t.done ? " done" : ""}`} />
            <span className="tt">{t.text}<span className="sub">{t.sub}</span></span>
            {t.due ? <span className="tdue">{t.due}</span> : null}
          </li>
        ))}
      </ul>

      <Sect title="Recovery economics" />
      <div className="econ">
        <span><span className="el">Gross recoverable</span>{rec.econ.gross}</span>
        <span className="arw">→</span>
        <span><span className="el">Fee drag</span>{rec.econ.drag}</span>
        <span className="arw">→</span>
        <span className="net"><span className="el">Net to estate</span>{rec.econ.net}</span>
      </div>

      <button className="cta" onClick={onAccept}>Open subrogation</button>
    </>
  );
}

function ClosureBody({ d, onAccept }: { d: ClaimDossier; onAccept: () => void }) {
  const cl = d.closure;
  return (
    <>
      <div className="statusrow">
        <span className="statuschip">{cl.status}</span>
      </div>
      <div className="readmeter"><div className="rf" style={{ width: `${Math.round(cl.readiness * 100)}%` }} /></div>

      <Sect title="Decisions on this claim" />
      <ul className="recap">
        {cl.recap.map((r, i) => (
          <li key={i}>
            <span className="rk">{r.stage}</span>
            <span className="rv">{r.outcome}</span>
            <span className="rok">✓</span>
          </li>
        ))}
      </ul>

      <button className="cta" onClick={onAccept}>Close claim · {formatAmount(cl.amount)}</button>
    </>
  );
}

// ── Sources tab — searchable / filterable index of every document read ──

function SourcesPanel({ citations, onCite }: { citations: Citation[]; onCite: (c: Citation) => void }) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<"all" | CitationSourceType>("all");
  const filters: Array<{ key: "all" | CitationSourceType; label: string }> = [
    { key: "all", label: "All" },
    { key: "medical", label: "Medical" },
    { key: "policy", label: "Policy" },
    { key: "scene", label: "Scene" },
    { key: "liability", label: "Liability" },
    { key: "other", label: "Other" },
  ];
  const q = query.trim().toLowerCase();
  const rows = citations.filter((c) => {
    const okType = filter === "all" || c.source_type === filter;
    const okText = !q || `${c.document} ${c.excerpt}`.toLowerCase().includes(q);
    return okType && okText;
  });
  return (
    <section className="panel on">
      <Sect title="Documents" />
      <input className="search" placeholder="Search documents and excerpts…" value={query} onChange={(e) => setQuery(e.target.value)} />
      <div className="chips">
        {filters.map((f) => (
          <button key={f.key} type="button" className={`fchip${filter === f.key ? " on" : ""}`} onClick={() => setFilter(f.key)}>
            {f.label}
            {f.key === "all" ? <span style={{ opacity: 0.6 }}> {citations.length}</span> : null}
          </button>
        ))}
      </div>
      {rows.length === 0 ? (
        <div className="muted" style={{ fontSize: 13, padding: "14px 0" }}>No documents match.</div>
      ) : (
        <table className="src">
          <thead>
            <tr><th>#</th><th>Document</th><th>Type</th><th>Cited passage</th><th /></tr>
          </thead>
          <tbody>
            {rows.map((c) => (
              <tr key={c.citation_id} onClick={() => onCite(c)}>
                <td className="sidx">{String(c.index).padStart(2, "0")}</td>
                <td className="sdoc">{c.document}</td>
                <td>{labelForSource(c.source_type)}</td>
                <td className="sex">{c.excerpt}</td>
                <td className="cite-chev">↗</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

function DetailTopbar({ onBack, claimId }: { onBack: () => void; claimId: string | null }) {
  return (
    <div className="vsub">
      <button className="back" onClick={onBack}>← Home</button>
      <span className="tt">{claimId ?? "—"}</span>
    </div>
  );
}

function ClaimHeaderCard({ claim }: { claim: ClaimDetail }) {
  const facts: Array<[string, string]> = [
    ["Loss type", labelForLossType(claim.loss_type)],
    ["Date of loss", claim.date_of_loss],
    ["Severity", claim.severity],
    ["Jurisdiction", claim.jurisdiction],
    ["Policy", claim.policy_number],
    ["Status", claim.status.charAt(0).toUpperCase() + claim.status.slice(1)],
  ];
  return (
    <div className="cheader">
      <div className="cheader-top">
        <h2>{claim.insured_name}</h2>
        {labelForBand(claim.triage_band) && (
          <div className={`cband ${claim.triage_band}`}>{labelForBand(claim.triage_band)}</div>
        )}
      </div>
      <dl className="cheader-facts">
        {facts.map(([k, v]) => (
          <div key={k} className="cfact">
            <dt>{k}</dt>
            <dd>{v}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

// Split a document body into [before, match, after] around the cited passage,
// so the viewer can highlight the cited text in its real context.
function splitHighlight(body: string, excerpt: string): Array<{ text: string; mark: boolean }> {
  const idx = body.indexOf(excerpt);
  if (idx < 0) return [{ text: body, mark: false }];
  return [
    { text: body.slice(0, idx), mark: false },
    { text: excerpt, mark: true },
    { text: body.slice(idx + excerpt.length), mark: false },
  ];
}

// Document viewer — clicking a citation opens the actual uploaded document,
// rendered as a page (letterhead + meta + body) with the cited passage
// highlighted where it appears. Not a quote popup.
function DocumentSheet({ citation, onClose }: { citation: Citation; onClose: () => void }) {
  const raw = citation.body ?? citation.excerpt;
  const lines = raw.split("\n");
  const letterhead = lines[0] ?? citation.document;
  const meta = lines[1] ?? "";
  const body = lines.slice(2).join("\n").replace(/^\n+/, "");
  const parts = splitHighlight(body, citation.excerpt);
  return (
    <div className="docmodal" onClick={onClose}>
      <div className="docmodal-body" onClick={(e) => e.stopPropagation()}>
        <div className="docmodal-bar">
          <span className="doc-kicker">
            <span className={`cite-kind cite-kind--${citation.source_type}`}>{labelForSource(citation.source_type)}</span>
            {citation.document} · Cited as [{String(citation.index).padStart(2, "0")}]
          </span>
          <button className="x" onClick={onClose}>Close</button>
        </div>
        <div className="docpage">
          <div className="docpaper">
            <div className="docpage-letterhead">{letterhead}</div>
            {meta ? <div className="docpage-meta">{meta}</div> : null}
            <div className="docpage-body">
              {parts.map((p, i) =>
                p.mark ? <mark key={i} className="docmark">{p.text}</mark> : <span key={i}>{p.text}</span>,
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function labelForSource(s: CitationSourceType): string {
  return { medical: "Medical", policy: "Policy", scene: "Scene", liability: "Liability", other: "Other" }[s];
}

// Triage band → priority chip. Only the top tier (red) gets a visible chip,
// labelled "Priority"; medium/green claims show no chip — the absence is the
// signal, so the list isn't noisy with a label on every row. Returns null when
// no chip should render.
function labelForBand(band: "green" | "amber" | "red"): string | null {
  return band === "red" ? "Priority" : null;
}

function labelForLossType(loss: string): string {
  if (loss === "auto-bi") return "Auto BI";
  if (loss === "property") return "Property";
  return loss;
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

