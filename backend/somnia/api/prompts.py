from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException

from .. import store

router = APIRouter(prefix="/api")


@router.get("/prompts")
def list_prompts() -> list[dict]:
    return store.list_prompts()


@router.post("/prompts")
def create(body: dict = Body(...)) -> dict:
    return store.create_prompt(body)


@router.put("/prompts/{pid}")
def update(pid: str, body: dict = Body(...)) -> dict:
    p = store.update_prompt(pid, body)
    if p is None:
        raise HTTPException(404, "not found")
    return p


@router.delete("/prompts/{pid}")
def delete(pid: str) -> dict:
    store.delete_prompt(pid)
    return {}
