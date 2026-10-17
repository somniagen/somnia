from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException

from .. import grids

router = APIRouter(prefix="/api")


def startup() -> None:
    grids.start()


@router.post("/grids")
def create(body: dict = Body(...)) -> dict:
    try:
        return grids.create(body.get("base"), body.get("axes"))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/grids")
def recent(limit: int = 20) -> list[dict]:
    return grids.recent(max(1, min(limit, 100)))


@router.get("/grids/{gid}")
def one(gid: str) -> dict:
    g = grids.get(gid)
    if g is None:
        raise HTTPException(404, "no such grid")
    return g


@router.delete("/grids/{gid}")
def delete(gid: str) -> dict:
    if not grids.delete(gid):
        raise HTTPException(404, "no such grid")
    return {}
