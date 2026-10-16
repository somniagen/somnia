from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException

from .. import jobs
from ..hub import hub

router = APIRouter(prefix="/api")


@router.get("/state")
def state() -> dict:
    s = hub.snapshot()
    s.pop("type", None)
    return s


@router.post("/jobs")
def create(body: dict = Body(...)) -> dict:
    if not isinstance(body.get("params"), dict):
        raise HTTPException(400, "params required")
    return {"ids": jobs.submit(body["params"], body.get("count", 1))}


@router.post("/jobs/reorder")
def reorder(body: dict = Body(...)) -> list[dict]:
    return jobs.reorder(body.get("ids", []))


@router.post("/jobs/clear")
def clear() -> dict:
    jobs.clear()
    return {}


@router.delete("/jobs/{jid}")
def cancel(jid: str) -> dict:
    if not jobs.cancel(jid):
        raise HTTPException(404, "no such job")
    return {}


@router.get("/presets")
def presets() -> dict:
    from .. import presets as p

    return p.presets()
