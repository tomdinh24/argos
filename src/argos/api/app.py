"""Railway-deployed FastAPI surface.

Minimal app — only `/healthz` so Railway has a known-good baseline
deploy target. Real Argos endpoints land here when the Vercel cockpit
(SYSTEM_ARCHITECTURE.md §0.2 item 7) defines what it needs to call.
"""
from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="Argos API", version="0.0.1")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
