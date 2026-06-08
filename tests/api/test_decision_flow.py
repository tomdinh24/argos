"""Default-suite guardrail for the cockpit decision seam.

This is the test that would have caught the API → orchestrator wiring being
absent: for a long time `POST /api/claims/{id}/decisions` logged an audit row
and advanced the chain but never called `apply_*_decision`, so no Foundry bridge
could ever fire. Unit tests on each layer all passed; nothing asserted the layers
were *connected*. These tests assert the connection — and run in the DEFAULT
suite (no `foundry_integration` marker, no live tenant), so a regression fails CI.

The Foundry OSDK round-trip itself stays behind `-m foundry_integration` (it
mutates the live tenant); here we mock at the orchestrator boundary.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

import argos.api.app as appmod
from argos.api.app import app

client = TestClient(app)


def _first_claim_id() -> str:
    claims = client.get("/api/claims").json()
    assert claims, "caseload is empty — the cockpit would render nothing"
    return claims[0]["claim_id"]


def test_healthz() -> None:
    assert client.get("/healthz").json()["status"] == "ok"


def test_claims_and_detail_shape() -> None:
    cid = _first_claim_id()
    detail = client.get(f"/api/claims/{cid}").json()
    # The detail contract the cockpit depends on.
    for field in ("claim_id", "insured_name", "citations", "pending_recommendations"):
        assert field in detail, f"detail missing {field}"


def test_approved_decision_routes_to_orchestrator(monkeypatch) -> None:
    """An approved reserve decision must (a) write an audit row and (b) invoke
    the orchestrator handler. If the endpoint ever stops calling the handler, the
    Foundry bridge can never fire — this test fails before that ships."""
    cid = _first_claim_id()
    calls: dict[str, object] = {}

    def spy_apply_reserve(caseload, claim_id, *, accept, **kwargs):
        calls["handler"] = (claim_id, accept)
        return caseload  # unchanged; we only assert it was invoked

    audited: list[object] = []
    monkeypatch.setattr(appmod, "apply_reserve_decision", spy_apply_reserve)
    monkeypatch.setattr(appmod, "append_agent_action", lambda action, **kw: audited.append(action))

    resp = client.post(
        f"/api/claims/{cid}/decisions",
        json={
            "recommendation_id": "REC-TEST",
            "workflow": "reserve",
            "outcome": "approved",
            "final_title": "Set reserve (guardrail test)",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["next_workflow"] == "liability"  # chain advanced
    assert calls.get("handler") == (cid, True), "endpoint did not route to apply_reserve_decision"
    assert audited, "no audit row written for the human decision"


def test_rejected_decision_does_not_commit(monkeypatch) -> None:
    """Rejection holds the stage open: it logs the decision but must NOT call a
    commit handler or advance the chain."""
    cid = _first_claim_id()
    committed: list[object] = []
    monkeypatch.setattr(
        appmod, "apply_reserve_decision",
        lambda *a, **k: committed.append(True) or a[0],
    )
    monkeypatch.setattr(appmod, "append_agent_action", lambda action, **kw: None)

    resp = client.post(
        f"/api/claims/{cid}/decisions",
        json={
            "recommendation_id": "REC-TEST",
            "workflow": "reserve",
            "outcome": "rejected",
            "final_title": "Defer reserve",
            "reason": "needs more documentation",
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["next_workflow"] is None
    assert not committed, "rejection must not invoke a commit handler"
