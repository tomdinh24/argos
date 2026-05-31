"""Triage feature extraction.

Pure function: `Caseload` in → per-request normalized feature dict out. No
side effects, no LLM calls, no wall-clock reads. The ranker in `ranker.py`
consumes the normalized vectors and produces a score.

Two stages:

1. `extract_raw(caseload)` — pulls 12 raw features off each CoverageRequest
   in the caseload. Returns a dict keyed by `request_id`. Direction is
   "as the field reads" (e.g., `hours_until_sla_breach` is small when
   urgent), so raw values are *not* directly addable across features.

2. `normalize(raw)` — applies per-caseload min-max scaling, then inverts
   the inverse-direction features (`hours_until_sla_breach`,
   `days_until_statute`) so every output feature satisfies
   "higher = more urgent." Boolean flags pass through unchanged. If a
   feature has zero spread across the caseload (all values equal), it
   contributes nothing — normalized to 0.0 for all requests.

`extract_features(caseload)` chains the two for the common case.

The 12 features and their semantics are pinned by the spec at
`docs/specs/triage-ranker.md`. See "Features" and "Scoring function."
"""
from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import timedelta

from argos.ontology.types import Caseload, SeverityTier


# Higher = more urgent for these features means smaller raw value, so
# normalize then invert with `1 - norm_x`.
INVERSE_FEATURES: frozenset[str] = frozenset({
    "hours_until_sla_breach",
    "days_until_statute",
})

# Already 0/1, no min-max needed.
BOOLEAN_FEATURES: frozenset[str] = frozenset({
    "litigation_flag",
    "rep_flag",
    "complaint_flag",
})

# Sentinel values used when a field is genuinely absent (no SLA on the
# claim, no statute on the request). Chosen large so that — after min-max
# across the caseload — the absent value maps to the least-urgent end of
# the range. If *every* request has the sentinel, min == max and the
# feature contributes nothing (see `_minmax_then_maybe_invert`).
_SLA_SENTINEL_HOURS: float = 24.0 * 30  # 30 days = "no SLA firing"
_STATUTE_SENTINEL_DAYS: float = 365.0 * 5  # 5 years = "no statute approaching"

_SEVERITY_SCORE: dict[SeverityTier, float] = {
    "minor": 1.0,
    "standard": 2.0,
    "serious": 3.0,
    "catastrophic": 4.0,
}

_EPSILON: float = 1e-9


@dataclass(frozen=True)
class RawFeatures:
    """One row of raw (pre-normalization) features for a CoverageRequest."""

    hours_until_sla_breach: float
    days_until_statute: float
    hours_since_last_touch: float
    open_diary_count: float
    severity_tier_score: float
    incurred_amount: float
    reserve_adequacy_gap: float
    days_since_claimant_contact: float
    unread_document_count: float
    litigation_flag: float
    rep_flag: float
    complaint_flag: float

    def as_dict(self) -> dict[str, float]:
        return {f.name: getattr(self, f.name) for f in fields(self)}


def extract_raw(caseload: Caseload) -> dict[str, RawFeatures]:
    """Compute the raw 12-feature vector for every CoverageRequest.

    Returns a dict keyed by `request_id`. Missing fields collapse to
    deterministic sentinels or 0; this function does not raise on
    incomplete caseload state. The ranker treats missing-state requests as
    "no signal in that feature" once normalization runs.
    """
    as_of = caseload.as_of
    out: dict[str, RawFeatures] = {}

    for request in caseload.requests:
        claim = caseload.claim_for(request)
        cid = claim.claim_id
        rid = request.request_id

        # --- SLA: smallest hours-until-breach across unmet ServiceDeadlines
        # bound to this claim (or this specific request).
        sla_hours = _SLA_SENTINEL_HOURS
        for sd in caseload.service_deadlines:
            if sd.claim_id != cid:
                continue
            if sd.request_id is not None and sd.request_id != rid:
                continue
            if sd.met:
                continue
            delta_h = (sd.deadline - as_of).total_seconds() / 3600.0
            sla_hours = min(sla_hours, delta_h)

        # --- Statute: smallest days-until-deadline on this request, unexpired.
        stat_days = _STATUTE_SENTINEL_DAYS
        for ld in caseload.legal_deadlines:
            if ld.request_id != rid or ld.expired:
                continue
            delta_d = (ld.deadline_date - as_of.date()).days
            stat_days = min(stat_days, float(delta_d))

        # --- Hours since last touch: max timestamp across AgentAction +
        # WorkItem for the claim. If neither exists, fall back to
        # hours-since-claim-opened (defensive).
        touch_ts = [
            a.timestamp for a in caseload.agent_actions if a.claim_id == cid
        ] + [
            w.timestamp for w in caseload.work_items if w.claim_id == cid
        ]
        if touch_ts:
            last_touch = max(touch_ts)
            hours_since_touch = (as_of - last_touch).total_seconds() / 3600.0
        else:
            hours_since_touch = (
                as_of - _datetime_at_start_of_day(claim.opened_date, as_of)
            ).total_seconds() / 3600.0

        # --- Open diary count: ScheduledTasks not cleared whose fire_date
        # is on or before now.
        open_diary = sum(
            1 for st in caseload.scheduled_tasks
            if st.claim_id == cid and not st.cleared and st.fire_date <= as_of
        )

        # --- Severity tier score: enum → 1..4
        severity_score = _SEVERITY_SCORE[request.severity_tier]

        # --- Incurred = paid_to_date + reserve_current
        incurred = (
            caseload.paid_to_date(rid) + caseload.reserve_current(rid)
        )

        # --- Reserve adequacy gap: |current - recommended|. Recommended is
        # populated only after the Reserve specialist runs; until then the
        # gap is 0 by design (see spec "What v1 cannot see"). With every
        # request at 0.0, per-caseload min-max normalization returns 0 for
        # every request, so w_reserve has no effect on rankings until the
        # Reserve specialist work lands.
        reserve_gap = 0.0

        # --- Days since claimant contact: max timestamp across
        # Communications with party_role = claimant. Fallback to
        # days-since-claim-opened.
        contact_ts = [
            c.timestamp for c in caseload.communications
            if c.claim_id == cid and c.party_role == "claimant"
        ]
        if contact_ts:
            last_contact = max(contact_ts)
            days_since_contact = (as_of - last_contact).total_seconds() / 86400.0
        else:
            days_since_contact = (
                as_of.date() - claim.opened_date
            ).days

        # --- Unread document count: documents received after the last
        # AgentAction. If no AgentAction exists for the claim, treat all
        # documents on the claim as unread.
        agent_ts = [
            a.timestamp for a in caseload.agent_actions if a.claim_id == cid
        ]
        if agent_ts:
            last_action_date = max(agent_ts).date()
            unread = sum(
                1 for d in caseload.documents
                if d.claim_id == cid and d.received_date > last_action_date
            )
        else:
            unread = sum(1 for d in caseload.documents if d.claim_id == cid)

        out[rid] = RawFeatures(
            hours_until_sla_breach=sla_hours,
            days_until_statute=stat_days,
            hours_since_last_touch=hours_since_touch,
            open_diary_count=float(open_diary),
            severity_tier_score=severity_score,
            incurred_amount=incurred,
            reserve_adequacy_gap=reserve_gap,
            days_since_claimant_contact=days_since_contact,
            unread_document_count=float(unread),
            litigation_flag=1.0 if claim.litigation_flag else 0.0,
            rep_flag=1.0 if claim.rep_flag else 0.0,
            complaint_flag=1.0 if claim.complaint_flag else 0.0,
        )

    return out


def normalize(raw: dict[str, RawFeatures]) -> dict[str, dict[str, float]]:
    """Min-max scale each feature across the caseload; invert inverse-direction
    features so "higher = more urgent" universally. Boolean flags pass
    through. If a feature has zero spread, all requests get 0.0 for it
    (no signal — contributes nothing to the score regardless of weight).
    """
    if not raw:
        return {}

    feature_names = [f.name for f in fields(RawFeatures)]
    request_ids = list(raw.keys())

    # Pull per-feature column across all requests in a stable order.
    columns: dict[str, list[float]] = {
        name: [raw[rid].as_dict()[name] for rid in request_ids]
        for name in feature_names
    }

    normalized_columns: dict[str, list[float]] = {}
    for name, col in columns.items():
        if name in BOOLEAN_FEATURES:
            normalized_columns[name] = list(col)
        else:
            normalized_columns[name] = _minmax_then_maybe_invert(
                col, invert=(name in INVERSE_FEATURES)
            )

    return {
        rid: {name: normalized_columns[name][i] for name in feature_names}
        for i, rid in enumerate(request_ids)
    }


def extract_features(caseload: Caseload) -> dict[str, dict[str, float]]:
    """End-to-end: raw extraction + normalization. Returns urgency-direction
    normalized vectors keyed by request_id. Every feature is in [0, 1],
    higher = more urgent."""
    return normalize(extract_raw(caseload))


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _minmax_then_maybe_invert(values: list[float], *, invert: bool) -> list[float]:
    """Min-max scale to [0, 1]; if invert=True, return 1 - x so a small raw
    value (urgent) maps to a large normalized value. If all values are
    equal (spread below epsilon), returns [0.0] * len(values) — no signal,
    no inversion (1.0s would be a false signal of universal urgency)."""
    lo, hi = min(values), max(values)
    if hi - lo < _EPSILON:
        return [0.0] * len(values)
    normed = [(v - lo) / (hi - lo) for v in values]
    if invert:
        normed = [1.0 - x for x in normed]
    return normed


def _datetime_at_start_of_day(d, ref):
    """Build a datetime at 00:00 on `d`, in `ref`'s timezone. Used only when
    no touch timestamp exists and we need to compute hours-since-open."""
    from datetime import datetime as _dt
    return _dt(d.year, d.month, d.day, tzinfo=ref.tzinfo)
