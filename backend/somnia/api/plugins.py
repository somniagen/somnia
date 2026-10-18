from __future__ import annotations

import asyncio

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import FileResponse

from .. import net, plugins

router = APIRouter(prefix="/api/plugins", tags=["plugins"])
MIME = {".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css", ".json": "application/json", ".svg": "image/svg+xml"}


def startup() -> None:
    plugins.start()


def _local(request: Request) -> None:
    if not net.is_loopback(request.client.host if request.client else None):
        raise HTTPException(403, "plugins can only be managed from this machine")


@router.get("")
def list_plugins():
    return plugins.list_plugins()


@router.post("/rescan")
async def rescan(request: Request):
    _local(request)
    await asyncio.to_thread(plugins.scan)
    return plugins.list_plugins()


@router.post("/{pid}/reload")
async def reload(pid: str, request: Request):
    _local(request)
    info = await asyncio.to_thread(plugins.reload, pid)
    if info is None:
        raise HTTPException(404, "plugin not found")
    return info


@router.put("/{pid}")
async def update(pid: str, request: Request, body: dict = Body(...)):
    _local(request)
    if "enabled" not in body:
        raise HTTPException(400, "nothing to change")
    info = await asyncio.to_thread(plugins.set_enabled, pid, bool(body["enabled"]))
    if info is None:
        raise HTTPException(404, "plugin not found")
    return info


@router.get("/{pid}/web/{path:path}")
def web(pid: str, path: str):
    p = plugins.get(pid)
    if p is None:
        raise HTTPException(404, "plugin not found")
    entry = p.web_entry
    if entry is None:
        raise HTTPException(404)
    # served relative to the web entry's folder so it can import its siblings
    base = entry.parent
    f = (base / path).resolve()
    if not (f.is_file() and base in f.parents):
        raise HTTPException(404)
    return FileResponse(f, media_type=MIME.get(f.suffix.lower()), headers={"Cache-Control": "no-cache"})
