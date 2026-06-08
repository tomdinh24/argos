"""Map Argos internal types (ontology Claims, workflow result dicts) to the
cockpit's wire shape. Kept thin and deterministic — no LLM calls here.

The decision to derive triage_band from severity_tier_summary is intentional
shorthand for the demo. The real ranker (services/triage/policy_engine.py)
returns a bucket per CoverageRequest; mapping that into a per-claim band is
a separate piece of work and not required to put a real LLM workflow run on
screen.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from argos.api.schemas import (
    AllocRow,
    Citation,
    ClaimDetail,
    ClaimDossier,
    ClaimSummary,
    ClosureSection,
    CoverageMap,
    CoverageSection,
    DashboardMetrics,
    DistRow,
    Econ,
    Finding,
    LiabilitySection,
    NewInfoItem,
    PendingRecommendation,
    RecapRow,
    RecoverySection,
    ReserveBand,
    ReserveSection,
    StageCheck,
    TodoItem,
    TriageBand,
    WorkflowName,
)
from argos.ontology.types import Caseload, Claim


# Ordered workflow chain — the cockpit follows the same order. "reopen" is
# only reachable after closure, so it's not in the default chain.
WORKFLOW_CHAIN: list[WorkflowName] = ["coverage", "reserve", "liability", "recovery", "closure"]


def _num(value: object, default: float = 0.0) -> float:
    """Coerce a workflow-result scalar to float. Workflow outputs serialize
    Decimal money/percentage fields as strings ("35.00", "0.00"), so callers
    that do arithmetic must run values through this first."""
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _band_from_severity(claim: Claim) -> TriageBand:
    """Severity tier → cockpit triage band. Demo shorthand (see module doc).
    Serious/catastrophic exposures and litigation/complaint claims surface red;
    standard claims amber; minor claims green."""
    sev = (claim.severity_tier_summary or "standard").lower()
    if claim.litigation_flag or claim.complaint_flag or sev in {
        "critical", "major", "serious", "catastrophic",
    }:
        return "red"
    if claim.rep_flag or sev == "standard":
        return "amber"
    return "green"


def _loss_type_from_caseload(caseload: Caseload, claim_id: str) -> str:
    """Pull a friendly loss-type label from the claim's first CoverageRequest.
    Demo shorthand — real mapping would consult PolicyCoverage.loss_kind."""
    for req in caseload.requests:
        if req.claim_id == claim_id:
            cov = (req.coverage_id or "").upper()
            if "AUTO" in cov and "BI" in cov:
                return "auto-bi"
            if "AUTO" in cov and "PD" in cov:
                return "auto-pd"
            if "PROP" in cov:
                return "property"
            return cov.lower() or "unknown"
    return "unknown"


def _decided_stages(audit_log_root: Path, claim_id: str) -> set[str]:
    """Workflows whose recommendation has been approved or modified by a human.
    Read from the AgentAction audit log. validator_pass = approved/modified;
    validator_fail = rejected (stage stays open)."""
    decided: set[str] = set()
    p = audit_log_root / f"{claim_id}.jsonl"
    if not p.exists():
        return decided
    try:
        for line in p.read_text().splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("action_type") == "validator_pass" and row.get("success"):
                wf = row.get("workflow")
                if wf:
                    decided.add(wf)
    except (json.JSONDecodeError, OSError):
        pass
    return decided


def _next_workflow(
    results_root: Path, claim_id: str, audit_log_root: Path | None = None,
) -> WorkflowName:
    """First workflow in the chain whose decision hasn't been recorded yet.

    "Active stage" semantics: a stage stays active until a human approves or
    modifies its recommendation. So after coverage runs but before approval,
    coverage is still the active stage and its draft rec is what the cockpit
    surfaces. Once approved, reserve becomes active.

    Falls back to the no-decision-log behavior (first missing JSON) when
    audit_log_root is None — preserves the simpler path for the few callers
    that don't pass it.
    """
    if audit_log_root is not None:
        decided = _decided_stages(audit_log_root, claim_id)
        for w in WORKFLOW_CHAIN:
            if w not in decided:
                return w
        return "closure"
    claim_dir = results_root / claim_id
    for w in WORKFLOW_CHAIN:
        if not (claim_dir / f"{w}.json").exists():
            return w
    return "closure"


def _reserve_total(results_root: Path, claim_id: str) -> float | None:
    """Read the latest reserve recommendation's total from disk, if any."""
    path = results_root / claim_id / "reserve.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        total = 0.0
        for comp in data.get("per_component", []) or []:
            band = comp.get("recommended_outstanding_band", {}) or {}
            total += float(band.get("p50", 0))
        return total or None
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def _short_money(amount: float) -> str:
    """255360.0 → '$255k'; 1500000.0 → '$1.5M'; 800.0 → '$800'."""
    if amount >= 1_000_000:
        return f"${amount / 1_000_000:.1f}M".replace(".0M", "M")
    if amount >= 1_000:
        return f"${amount / 1_000:.0f}k"
    return f"${amount:,.0f}"


def _rationale_one_liner(
    results_root: Path, claim_id: str, next_wf: WorkflowName, band: TriageBand,
) -> str:
    """A single-sentence summary for the caseload row.

    Surfaces the most *salient* signal across the committed chain so the
    caseload list differentiates claims — rather than echoing the last stage,
    which is `closure: blocked_by_defects` for every fully pre-run claim and
    makes every row read identically. Priority: a live (non-abstain) recovery,
    then an escalated reserve, then a liability bar, then contested coverage;
    falling back to the most-recent-stage summary (partial chains) and finally
    the band default."""
    rec = _load_result(results_root, claim_id, "recovery")
    res = _load_result(results_root, claim_id, "reserve")
    lia = _load_result(results_root, claim_id, "liability")
    cov = _load_result(results_root, claim_id, "coverage")

    # 1. Recovery actively in play — the subrogation story (abstain is the
    #    common case and not worth surfacing over the stages below).
    if rec:
        r = (rec.get("recommendation") or "").strip()
        if r and r not in ("abstain", "uncommitted"):
            # subrogation_lane may persist as {lane_id: ...} or a bare string
            # (older results) — mirror _recovery_section's defensive handling so
            # one odd result file can't 500 the whole /api/claims list.
            lane_raw = rec.get("subrogation_lane")
            lane = lane_raw.get("lane_id") if isinstance(lane_raw, dict) else lane_raw
            lane = (lane or "").replace("_", " ").strip()
            tail = f" — {lane} lane" if lane else ""
            return f"Recovery: {r.replace('_', ' ')}{tail}."

    # 2. Reserve escalation — a real reserve that needs above-handler sign-off.
    if res:
        total = sum(
            float((c.get("recommended_outstanding_band", {}) or {}).get("p50", 0))
            for c in (res.get("per_component", []) or [])
        )
        auth = res.get("authority_required_level")
        if total and auth and auth not in ("handler", "adjuster"):
            return f"Reserve {_short_money(total)} — {auth} sign-off needed."

    # 3. Liability barred — comparative-fault threshold tripped.
    if lia:
        bar = (lia.get("applicable_regime", {}) or {}).get("bar_basis")
        if bar and bar not in ("none", ""):
            return "Liability barred — comparative-fault threshold; reserve $0."

    # 4. Contested coverage — ROR / denial leads the distribution.
    if cov:
        outcomes = (cov.get("synthesis", {}) or {}).get("outcomes", []) or []
        if outcomes:
            top = max(outcomes, key=lambda o: o.get("probability", 0))
            verdict = _verdict_label(top.get("claim_text", ""))
            prob = float(top.get("probability", 0))
            if not verdict.lower().startswith("clean") and prob >= 0.45:
                return f"Coverage: {verdict.lower()} — open coverage questions ({prob:.0%})."

    claim_dir = results_root / claim_id
    # Fallback: the most recently completed workflow whose summary we can show.
    for w in reversed(WORKFLOW_CHAIN):
        p = claim_dir / f"{w}.json"
        if p.exists():
            try:
                data = json.loads(p.read_text())
                # Each workflow result shape differs; pull a recognizable field.
                if w == "coverage":
                    syn = data.get("synthesis", {}).get("outcomes", []) or []
                    prob = syn[0].get("probability", 0) if syn else 0
                    tail = "awaiting approval" if next_wf == "coverage" else f"next: {next_wf}"
                    return f"Coverage clean prob {prob:.0%}; {tail}."
                if w == "reserve":
                    n_notice = len(data.get("notice_obligations_triggered", []) or [])
                    return f"Reserve indemnity computed; {n_notice} notice(s); next: {next_wf}."
                if w == "liability":
                    flags = len(data.get("variance_flags", []) or [])
                    return f"Liability assessed; {flags} variance flag(s); next: {next_wf}."
                if w == "recovery":
                    rec = data.get("recommendation", "")
                    return f"Recovery recommendation: {rec}; next: {next_wf}."
                if w == "closure":
                    rec = data.get("recommendation", "")
                    return f"Closure: {rec}."
            except (json.JSONDecodeError, KeyError, TypeError):
                continue
    return {
        "red": "Outside band; senior attention recommended.",
        "amber": "Within band but needs judgment.",
        "green": "Follows policy; routine handling.",
    }[band]


def to_claim_summary(
    claim: Claim, caseload: Caseload, results_root: Path,
    audit_log_root: Path | None = None,
) -> ClaimSummary:
    band = _band_from_severity(claim)
    next_wf = _next_workflow(results_root, claim.claim_id, audit_log_root)
    return ClaimSummary(
        claim_id=claim.claim_id,
        insured_name=claim.insured_name or "Unnamed insured",
        loss_type=_loss_type_from_caseload(caseload, claim.claim_id),
        reported_at=claim.opened_date.isoformat(),
        triage_band=band,
        next_workflow=next_wf,
        rationale=_rationale_one_liner(results_root, claim.claim_id, next_wf, band),
        reserve_total=_reserve_total(results_root, claim.claim_id),
        status=claim.status,
    )


def _pending_rec_from_result(
    workflow: WorkflowName, result_path: Path,
) -> PendingRecommendation | None:
    """Translate the latest workflow result on disk into a cockpit-shaped
    pending recommendation. Workflow result shapes differ per workflow — we
    pull the fields the cockpit needs and synthesize the rest."""
    if not result_path.exists():
        return None
    try:
        data = json.loads(result_path.read_text())
    except json.JSONDecodeError:
        return None
    rec_id = f"REC-{workflow.upper()}-{result_path.stat().st_mtime_ns:x}"

    if workflow == "coverage":
        outcomes = data.get("synthesis", {}).get("outcomes", []) or []
        top = max(outcomes, key=lambda o: o.get("probability", 0)) if outcomes else {}
        prob = top.get("probability", 0)
        claim_text = top.get("claim_text", "") or ""
        # claim_text shape: "<verdict> — <comma-separated findings>". Split on
        # the em-dash to surface the structured tail as bullets in the cockpit.
        verdict_label = claim_text.split("—")[0].strip() or "coverage"
        findings: list[str] = []
        if "—" in claim_text:
            tail = claim_text.split("—", 1)[1]
            findings = [
                f.strip().rstrip(".").capitalize()
                for f in tail.split(",") if f.strip()
            ]
        cite_count = sum(len(o.get("evidence_citations", []) or []) for o in outcomes)
        return PendingRecommendation(
            recommendation_id=rec_id,
            workflow="coverage",
            title=f"{verdict_label} ({prob:.0%})",
            posture=verdict_label.lower().replace(" ", "_"),
            rationale=top.get("reasoning", "") or claim_text,
            citations=cite_count or 3,
            awaiting_approval=True,
            findings=findings,
        )
    if workflow == "reserve":
        total = 0.0
        for comp in data.get("per_component", []) or []:
            band = comp.get("recommended_outstanding_band", {}) or {}
            total += float(band.get("p50", 0))
        auth = data.get("authority_required_level", "adjuster")
        return PendingRecommendation(
            recommendation_id=rec_id,
            workflow="reserve",
            title="Set reserve to",
            amount=round(total),
            posture="set",
            rationale=(
                f"Indemnity central estimate from per-component bands; authority tier {auth}."
            ),
            citations=len(data.get("notice_obligations_triggered", []) or []) + 4,
            awaiting_approval=True,
        )
    if workflow == "liability":
        apport = data.get("apportionment", {}) or {}
        insured_id = next(
            (pid for pid in apport if "insured" in pid.lower()), None,
        )
        insured_pct = _num(apport[insured_id].get("fault_pct")) if insured_id else None
        return PendingRecommendation(
            recommendation_id=rec_id,
            workflow="liability",
            title=(
                f"Allocate {100 - insured_pct:.0f}% fault to third party"
                if insured_pct is not None else "Allocate comparative fault"
            ),
            posture="allocate",
            rationale=(
                f"Regime {data.get('applicable_regime', {}).get('statute', 'unknown')}; "
                f"{len(data.get('variance_flags', []) or [])} variance flag(s)."
            ),
            citations=4,
            awaiting_approval=True,
        )
    if workflow == "recovery":
        rec = data.get("recommendation", "uncommitted")
        net = _num(data.get("net_economics", {}).get("net_total", 0))
        return PendingRecommendation(
            recommendation_id=rec_id,
            workflow="recovery",
            title=f"Recovery: {rec}",
            posture=rec,
            rationale=f"Net recovery economics ${net:,.0f}.",
            citations=5,
            awaiting_approval=True,
        )
    if workflow == "closure":
        rec = data.get("recommendation", "uncommitted")
        return PendingRecommendation(
            recommendation_id=rec_id,
            workflow="closure",
            title=f"Closure: {rec}",
            posture=rec,
            rationale=(
                f"Ready probability {data.get('ready_probability', 0):.0%}; "
                f"OIR {data.get('oir_classification', 'unknown')}."
            ),
            citations=3,
            awaiting_approval=True,
        )
    return None


# ── Dossier assembly — real per-stage content from persisted workflow results ─

def _load_result(results_root: Path, claim_id: str, workflow: str) -> dict | None:
    p = results_root / claim_id / f"{workflow}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return None


_DOC_TITLES = {
    "medical_records": "Medical record",
    "police_report": "Police report",
    "policy": "Policy",
    "correspondence": "Correspondence",
}
_SOURCE_TYPES = {
    "medical_records": "medical",
    "police_report": "scene",
    "policy": "policy",
    "correspondence": "other",
}


def _ago(when: object, as_of: object) -> str:
    from datetime import date, datetime
    if isinstance(when, datetime):
        wd = when.date()
    elif isinstance(when, date):
        wd = when
    else:
        return str(when)
    ad = as_of.date() if isinstance(as_of, datetime) else as_of
    if not isinstance(ad, date):
        return str(when)
    days = (ad - wd).days
    if days <= 0:
        return "today"
    return "1d ago" if days == 1 else f"{days}d ago"


def _friendly_party(party_id: str) -> str:
    pid = party_id.lower()
    if "insured" in pid:
        return "Insured driver"
    if "claimant" in pid or "v2" in pid or "third" in pid:
        return "Third party — claimant driver"
    return party_id.replace("_", " ").title()


class _CiteReg:
    """Builds a deduplicated, indexed Citation list from workflow EvidenceCitation
    dicts, joining document_id → the claim's Document.body_text so the cockpit
    viewer can highlight the cited passage in the real document."""

    def __init__(self, caseload: Caseload, claim_id: str) -> None:
        self._docs = {
            d.document_id: d for d in caseload.documents if d.claim_id == claim_id
        }
        self.items: list[Citation] = []
        self._key_to_index: dict[tuple, int] = {}

    def add(self, ev: dict) -> int:
        doc_id = ev.get("document_id")
        rule_id = ev.get("sourced_rule_id")
        excerpt = ev.get("text_excerpt", "") or ""
        locator = ev.get("locator", "") or ""
        key = (doc_id or rule_id or locator, excerpt)
        if key in self._key_to_index:
            return self._key_to_index[key]
        idx = len(self.items) + 1
        doc = self._docs.get(doc_id) if doc_id else None
        if doc is not None:
            dtype = doc.document_type
            label = _DOC_TITLES.get(dtype, dtype.replace("_", " ").title())
            document = f"{label} · {locator}".rstrip(" ·") if locator else label
            source_type = _SOURCE_TYPES.get(dtype, "other")
            body = doc.body_text
        elif rule_id:
            document = f"Policy rule · {locator}".rstrip(" ·") if locator else rule_id
            source_type = "policy"
            body = None
        else:
            document = locator or "Source"
            source_type = "other"
            body = None
        self.items.append(Citation(
            citation_id=str(doc_id or rule_id or f"C-{idx:02d}"),
            index=idx,
            source_type=source_type,  # type: ignore[arg-type]
            document=document,
            excerpt=excerpt,
            body=body,
        ))
        self._key_to_index[key] = idx
        return idx


def _add_from(reg: _CiteReg, evs: object) -> None:
    if isinstance(evs, list):
        for ev in evs:
            if isinstance(ev, dict):
                reg.add(ev)


def _verdict_label(claim_text: str) -> str:
    head = (claim_text or "").split("—")[0].split(":")[0].strip()
    return head or "Coverage"


_POSTURE_LABELS = {
    "accepted": "Affirmed by you",
    "ROR_issued": "Reservation of rights issued",
    "denied": "Denied",
    "under_investigation": "Pending your review",
}


def _coverage_section(reg: _CiteReg, cov: dict | None, claim: Claim) -> CoverageSection:
    outcomes = ((cov or {}).get("synthesis", {}) or {}).get("outcomes", []) or []
    top = max(outcomes, key=lambda o: o.get("probability", 0)) if outcomes else {}
    # provision: prefer a policy/endorsement citation; else the top outcome reasoning.
    endorse_idx, provision = 0, (top.get("reasoning", "") or "Coverage under policy.")[:160]
    for ev in (cov or {}).get("evidence_found", []) or []:
        loc = (ev.get("locator") or "").lower()
        if "endorse" in loc or "coverage" in loc or "policy" in loc:
            endorse_idx = reg.add(ev)
            provision = ev.get("text_excerpt", provision) or provision
            break
    accident = f"{_loss_label(claim)} loss; {(claim.severity_tier_summary or 'standard').title()} severity."
    return CoverageSection(
        map=CoverageMap(accident=accident, provision=provision, cite=endorse_idx or 1),
        distribution=[
            DistRow(label=_verdict_label(o.get("claim_text", "")), p=float(o.get("probability", 0)))
            for o in outcomes
        ],
        decided_label=_POSTURE_LABELS.get(claim.coverage_posture, "Pending your review"),
    )


def _loss_label(claim: Claim) -> str:
    return "Auto BI"  # display fallback; overridden by caller where caseload is known


def _reserve_section(reg: _CiteReg, res: dict | None, claim: Claim) -> ReserveSection:
    res = res or {}
    bands, findings, total = [], [], 0.0
    for comp in res.get("per_component", []) or []:
        b = comp.get("recommended_outstanding_band", {}) or {}
        p50 = _num(b.get("p50"))
        total += p50
        bands.append(ReserveBand(
            name=str(comp.get("component", "indemnity")).title(),
            recommend=p50, low=_num(b.get("p10")), high=_num(b.get("p90")),
            carried=_num(comp.get("current_outstanding")),
        ))
        evs = comp.get("evidence_citations", []) or []
        cite_idx = reg.add(evs[0]) if evs else 1
        rationale = comp.get("rationale") or "Component reviewed."
        findings.append(Finding(text=rationale[:200], cite=cite_idx, doc=reg.items[cite_idx - 1].document if reg.items else "Reserve schedule"))
    checks: list[StageCheck] = []
    auth = str(res.get("authority_required_level", "adjuster"))
    if auth not in {"adjuster", "handler"}:
        checks.append(StageCheck(
            label="Sign-off", status="ok" if claim.reserve_decision_committed else "need",
            title="Supervisor sign-off", detail=f"Authority tier '{auth}' required for this reserve.",
            action=None if claim.reserve_decision_committed else "Request →",
        ))
    for notice in res.get("notice_obligations_triggered", []) or []:
        checks.append(StageCheck(
            label="Notice", status="need",
            title=f"{str(notice.get('notice_type', 'carrier')).replace('_', ' ').title()} notice owed",
            detail=notice.get("reasoning", "Notice threshold crossed.")[:160],
            due=str(notice.get("required_by_date", "")) or None,
        ))
    if bands:
        checks.append(StageCheck(
            label="Done", status="ok", title="Components analyzed",
            detail=f"{len(bands)} reserve component(s) modeled from the file.",
        ))
    # Always a number (the cockpit calls amount.toLocaleString()); 0 reads as
    # "no reserve modeled yet" rather than crashing the panel.
    return ReserveSection(findings=findings, bands=bands, checks=checks, amount=float(round(total)))


def _liability_section(reg: _CiteReg, liab: dict | None) -> LiabilitySection:
    liab = liab or {}
    apport = liab.get("apportionment", {}) or {}
    rows = []
    max_pct = max((_num(v.get("fault_pct")) for v in apport.values()), default=0.0)
    for pid, v in apport.items():
        pct = _num(v.get("fault_pct"))
        lo, hi = _num(v.get("fault_pct_band_low")), _num(v.get("fault_pct_band_high"))
        conf = v.get("confidence")
        meta = f"band {lo:.0f}–{hi:.0f} · conf {conf}" if conf is not None else f"band {lo:.0f}–{hi:.0f}"
        rows.append(AllocRow(party=_friendly_party(pid), pct=pct, meta=meta, primary=pct == max_pct and pct > 0))
    evidence = []
    for be in (liab.get("diligence_ledger", {}) or {}).get("basis_evidence", []) or []:
        idx = reg.add({"document_id": be.get("source_doc_id"), "text_excerpt": be.get("quoted_span", ""), "locator": be.get("kind") or ""})
        evidence.append(Finding(text=be.get("quoted_span", "")[:200], cite=idx, doc=reg.items[idx - 1].document))
    return LiabilitySection(allocation=rows, evidence=evidence)


def _recovery_section(rec: dict | None) -> RecoverySection:
    rec = rec or {}
    lane_raw = rec.get("subrogation_lane")
    lane = (lane_raw.get("lane_id") if isinstance(lane_raw, dict) else lane_raw) or "—"
    todo: list[TodoItem] = []
    for e in (rec.get("deadline_calendar", {}) or {}).get("entries", []) or []:
        todo.append(TodoItem(
            text=str(e.get("statute_or_rule_cite", "Statute of limitations")),
            sub=f"{e.get('days_remaining', '?')} days remaining",
            due=str(e.get("deadline_date", "")) or None,
        ))
    ph = rec.get("preservation_hold", {}) or {}
    if ph:
        scope = ph.get("hold_scope")
        scope_txt = ", ".join(scope) if isinstance(scope, list) else (scope or "evidence")
        todo.append(TodoItem(
            text="Preservation hold", sub=f"scope: {scope_txt}",
            done=ph.get("acknowledgment_status") == "acknowledged",
        ))
    econ = rec.get("net_economics", {}) or {}
    return RecoverySection(
        status=str(rec.get("recommendation", "—")).replace("_", " ").title(),
        lane=f"{str(lane).replace('_', ' ')} lane",
        todo=todo,
        econ=Econ(
            gross=f"${_num(econ.get('gross_recoverable_total')):,.0f}",
            drag=f"−${_num(econ.get('fee_drag')):,.0f}",
            net=f"${_num(econ.get('net_total')):,.0f}",
        ),
    )


def _closure_section(clo: dict | None, liab: dict | None, claim: Claim) -> ClosureSection:
    clo = clo or {}
    recap = [
        RecapRow(stage="Coverage", outcome=_POSTURE_LABELS.get(claim.coverage_posture, "Pending")),
        RecapRow(stage="Reserve", outcome="Committed" if claim.reserve_decision_committed else "Pending"),
    ]
    apport = (liab or {}).get("apportionment", {}) or {}
    tp = next((_num(v.get("fault_pct")) for k, v in apport.items() if "claimant" in k.lower() or "v2" in k.lower()), None)
    recap.append(RecapRow(stage="Liability", outcome=f"{tp:.0f}% third party" if tp is not None else "Pending"))
    recap.append(RecapRow(
        stage="Recovery",
        outcome="Committed" if claim.recovery_pursuit_decision_committed else "Pending",
    ))
    return ClosureSection(
        status=str(clo.get("recommendation", "—")).replace("_", " ").title(),
        readiness=_num(clo.get("ready_probability")),
        recap=recap,
        amount=0.0,  # number, not None — the cockpit formats it on the CTA
    )


def _new_info(reg: _CiteReg, caseload: Caseload, claim_id: str) -> list[NewInfoItem]:
    items: list[NewInfoItem] = []
    docs = sorted(
        [d for d in caseload.documents if d.claim_id == claim_id],
        key=lambda d: d.received_date, reverse=True,
    )
    cited = {c.citation_id: c.index for c in reg.items}
    for d in docs[:3]:
        label = _DOC_TITLES.get(d.document_type, d.document_type.replace("_", " ").title())
        items.append(NewInfoItem(
            when=_ago(d.received_date, caseload.as_of),
            what=f"{label} received.",
            cite=cited.get(d.document_id),
            is_new=True,
        ))
    actions = sorted(
        [a for a in caseload.agent_actions if a.claim_id == claim_id],
        key=lambda a: a.timestamp, reverse=True,
    )
    for a in actions[:2]:
        items.append(NewInfoItem(when=_ago(a.timestamp, caseload.as_of), what=a.summary))
    return items


def to_dossier(
    claim: Claim, caseload: Caseload, results_root: Path,
) -> tuple[ClaimDossier, list[Citation]] | None:
    """Assemble the cockpit detail-page dossier from persisted workflow results +
    ontology objects. Returns (dossier, real_citations) — the citations carry
    document bodies for the viewer. Returns None if no coverage result exists yet
    (the page shows a drafting state). Degrades gracefully on missing stages."""
    cov = _load_result(results_root, claim.claim_id, "coverage")
    if cov is None:
        return None
    res = _load_result(results_root, claim.claim_id, "reserve")
    liab = _load_result(results_root, claim.claim_id, "liability")
    rec = _load_result(results_root, claim.claim_id, "recovery")
    clo = _load_result(results_root, claim.claim_id, "closure")

    reg = _CiteReg(caseload, claim.claim_id)
    # Seed citations in display order: coverage evidence first, then liability.
    _add_from(reg, cov.get("evidence_found"))
    for o in (cov.get("synthesis", {}) or {}).get("outcomes", []) or []:
        _add_from(reg, o.get("evidence_citations"))

    loss = _loss_type_from_caseload(caseload, claim.claim_id).replace("-", " ").upper()
    coverage = _coverage_section(reg, cov, claim)
    coverage.map.accident = f"{loss} loss; {(claim.severity_tier_summary or 'standard').title()} severity."

    # Build a short, cited brief from the strongest liability fact + coverage verdict.
    brief_bits = [f"{loss} claim — insured {claim.insured_name or 'unnamed'}."]
    liab_be = ((liab or {}).get("diligence_ledger", {}) or {}).get("basis_evidence", []) or []
    if liab_be:
        idx = reg.add({"document_id": liab_be[0].get("source_doc_id"), "text_excerpt": liab_be[0].get("quoted_span", ""), "locator": liab_be[0].get("kind") or ""})
        brief_bits.append(f"{liab_be[0].get('quoted_span', '')} [{idx}]")
    outcomes = (cov.get("synthesis", {}) or {}).get("outcomes", []) or []
    if outcomes:
        top = max(outcomes, key=lambda o: o.get("probability", 0))
        brief_bits.append(f"Coverage assessed {_verdict_label(top.get('claim_text', '')).lower()} at {float(top.get('probability', 0)):.0%}.")

    dossier = ClaimDossier(
        brief=" ".join(brief_bits),
        new_info=_new_info(reg, caseload, claim.claim_id),
        coverage=coverage,
        reserve=_reserve_section(reg, res, claim),
        liability=_liability_section(reg, liab),
        recovery=_recovery_section(rec),
        closure=_closure_section(clo, liab, claim),
    )
    return dossier, reg.items


# Demo citation set — synthesized so the cockpit can show inline citation pins
# and a detail sheet without requiring the workflow to emit a structured
# evidence chain. The function-backed AgentAction upgrade noted in
# docs/architecture/foundry-bridge-pattern.md is the path to real per-rec
# citations; until that lands, this gives the surface its shape.
_DEMO_CITATIONS = [
    Citation(citation_id="C-01", index=1, source_type="medical",
        document="ED record · facility AMC, p.4",
        excerpt="Patient presented with cervical pain; MRI ordered; admitted overnight."),
    Citation(citation_id="C-02", index=2, source_type="medical",
        document="Ortho consult · 2026-05-28",
        excerpt="Disc herniation noted; surgical consult pending."),
    Citation(citation_id="C-03", index=3, source_type="scene",
        document="Police report · line 12",
        excerpt="Vehicle 2 driver admits inattention; vehicle 1 stopped at signal."),
    Citation(citation_id="C-04", index=4, source_type="liability",
        document="Comparative fault memo",
        excerpt="100% allocation to vehicle 2; no contributory factors."),
    Citation(citation_id="C-05", index=5, source_type="policy",
        document="Endorsement 3 · policy",
        excerpt="Sublimit raised; defense within limits."),
    Citation(citation_id="C-06", index=6, source_type="policy",
        document="Reserve schedule · tier B",
        excerpt="Tier B reserve range applicable to documented surgical specials."),
    Citation(citation_id="C-07", index=7, source_type="other",
        document="Defense estimate · phase-aligned",
        excerpt="Pre-litigation phase allocation; mediation contingent."),
]


def to_claim_detail(
    claim: Claim, caseload: Caseload, results_root: Path,
    audit_log_root: Path | None = None,
) -> ClaimDetail:
    summary = to_claim_summary(claim, caseload, results_root, audit_log_root)
    next_wf = summary.next_workflow

    # Read prior workflow result for the active stage if it exists; otherwise
    # the cockpit shows "Argos is drafting..." until /run is called.
    pending: list[PendingRecommendation] = []
    rec = _pending_rec_from_result(next_wf, results_root / claim.claim_id / f"{next_wf}.json")
    if rec is not None:
        pending.append(rec)

    # Derive a description + policy_number + DOL from the first CoverageRequest
    req = next(
        (r for r in caseload.requests if r.claim_id == claim.claim_id), None,
    )
    policy_number = req.coverage_id if req else "—"
    date_of_loss = claim.opened_date.isoformat()
    severity = (claim.severity_tier_summary or "unknown").title()
    description = (
        f"{summary.loss_type.replace('-', ' ').title()} claim opened "
        f"{claim.opened_date.isoformat()}. "
        f"Status {claim.status}. Severity tier {claim.severity_tier_summary}."
    )

    # Real dossier + citations from persisted workflow results. Falls back to the
    # demo citation set only when the claim has no coverage result yet (so an
    # un-run claim still shows pins rather than an empty Documents tab).
    built = to_dossier(claim, caseload, results_root)
    if built is not None:
        dossier, citations = built
    else:
        dossier, citations = None, _DEMO_CITATIONS

    return ClaimDetail(
        **summary.model_dump(),
        policy_number=policy_number,
        date_of_loss=date_of_loss,
        jurisdiction="CA",  # demo shorthand
        severity=severity,
        description=description,
        pending_recommendations=pending,
        citations=citations,
        dossier=dossier,
    )


def to_dashboard_metrics(
    caseload: Caseload, results_root: Path, audit_log_root: Path,
) -> DashboardMetrics:
    """Roll up dashboard metrics from caseload + results dir + audit log.

    Demo shorthand: most metrics are derived counts; the ones the demo doesn't
    have a real signal for (reserve accuracy, cycle time) use plausible static
    values so the dashboard renders. Wiring these to real measurements is a
    next step once the cockpit is on real data end-to-end.
    """
    active = [c for c in caseload.claims if c.status == "open"]
    awaiting = 0
    for c in active:
        next_wf = _next_workflow(results_root, c.claim_id, audit_log_root)
        if (results_root / c.claim_id / f"{next_wf}.json").exists():
            awaiting += 1

    # Approved count + avg citations would come from the audit log /
    # decisions store; until that's wired, present the current run state.
    approved_7d, approved_cites = _approved_metrics(audit_log_root)

    return DashboardMetrics(
        adjuster_first_name="Tom",
        active_claims=len(active),
        active_delta_label="this session",
        awaiting_approval=awaiting,
        cycle_time_days=9.4,
        cycle_band_days=12.0,
        reserve_accuracy_pct=94.0,
        reserve_target_pct=90.0,
        approved_7d=approved_7d,
        approved_avg_citations=approved_cites,
    )


def _approved_metrics(audit_log_root: Path) -> tuple[int, float]:
    """Best-effort count of recent approve/modify events from the audit log."""
    if not audit_log_root.exists():
        return (0, 0.0)
    approved = 0
    cite_total = 0
    for jsonl in audit_log_root.glob("*.jsonl"):
        try:
            for line in jsonl.read_text().splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                if row.get("action_type") in {"validator_pass", "analysis_emitted"}:
                    approved += 1
                    cite_total += 5  # placeholder per-action citation count
        except (json.JSONDecodeError, OSError):
            continue
    avg = round(cite_total / approved, 1) if approved else 0.0
    return (approved, avg)


def iter_open_claims(caseload: Caseload) -> Iterable[Claim]:
    return (c for c in caseload.claims if c.status == "open")
