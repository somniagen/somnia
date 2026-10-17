from __future__ import annotations

import asyncio

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import FileResponse

from .. import identify as ident
from .. import model_defaults, models
from ..downloads import _broadcast

router = APIRouter(prefix="/api/models", tags=["models"])


def startup() -> None:
    ident.startup()


@router.get("")
async def list_models(kind: str | None = None):
    return ident.decorate(await asyncio.to_thread(models.list_models, kind))


@router.post("/rescan")
async def rescan():
    items = await asyncio.to_thread(models.rescan)
    _broadcast({"type": "models_changed"})
    ident.start(auto=True)
    return ident.decorate(items)


@router.get("/preview/{model_id:path}")
async def preview(model_id: str):
    p = models.preview_path(model_id)
    if p is None:
        raise HTTPException(404, "no preview")
    return FileResponse(p, headers={"Cache-Control": "public, max-age=3600"})


@router.post("/identify")
async def identify():
    return ident.start(auto=False)


@router.get("/identify")
async def identify_status():
    return dict(ident.state)


@router.post("/updates")
async def check_updates():
    return {"changed": await ident.check_updates(force=True)}


@router.get("/defaults")
async def get_defaults():
    return model_defaults.all_defaults()


def _defaults_changed() -> None:
    _broadcast({"type": "model_defaults", "defaults": model_defaults.all_defaults()})


@router.put("/defaults/{model_id:path}")
async def put_defaults(model_id: str, body: dict = Body(...)):
    ent = model_defaults.put(model_id, body)
    if ent is None:
        raise HTTPException(400, "nothing to save")
    _defaults_changed()
    return ent


@router.delete("/defaults/{model_id:path}")
async def delete_defaults(model_id: str):
    model_defaults.delete(model_id)
    _defaults_changed()
    return {"ok": True}


@router.delete("/{model_id:path}")
async def delete(model_id: str):
    try:
        await asyncio.to_thread(models.trash, model_id)
    except FileNotFoundError:
        raise HTTPException(404, "model not found")
    _broadcast({"type": "models_changed"})
    return {"ok": True}
