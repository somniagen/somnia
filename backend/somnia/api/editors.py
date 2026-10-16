from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import FileResponse

from .. import config, editing, editors, gallery, net, store
from ..hub import hub
from .settings import masked

router = APIRouter(prefix="/api/editors", tags=["editors"])


def _local(request: Request) -> bool:
    return net.is_loopback(request.client.host if request.client else None)


def _listing(found: list[dict]) -> dict:
    cur = editors.current()
    return {
        "local": True,
        "editors": [
            {"id": e["id"], "name": e["name"], "custom": bool(e.get("custom")), "path": e["path"] if e.get("custom") else None}
            for e in found
        ],
        "current": cur["id"] if cur else None,
    }


def _guard(request: Request) -> None:
    if not _local(request):
        raise HTTPException(403, "editors can only be changed from this machine")


def _save_custom(items: list[dict], **extra) -> None:
    config.update_settings(customEditors=items, **extra)
    hub.broadcast({"type": "settings", "settings": masked()})


@router.get("")
async def list_editors(request: Request, rescan: bool = False) -> dict:
    # launching apps only makes sense on the machine somnia runs on
    if not _local(request):
        return {"local": False, "editors": [], "current": None}
    return _listing(await asyncio.to_thread(editors.detect, rescan))


@router.post("/browse")
async def browse(request: Request) -> dict:
    _guard(request)
    try:
        path = await asyncio.to_thread(editors.browse)
    except Exception as e:
        raise HTTPException(500, f"no file picker available: {e}") from e
    return {"path": path, "name": editors.product_name(path) if path else None}


@router.post("/custom")
async def add_custom(request: Request, body: dict = Body(...)) -> dict:
    _guard(request)
    path = str(body.get("path") or "").strip().strip('"')
    p = Path(path)
    if not path or not p.exists() or (p.is_dir() and p.suffix.lower() != ".app"):
        raise HTTPException(400, "that program does not exist")
    name = str(body.get("name") or "").strip() or editors.product_name(path)
    items = [c for c in config.settings().customEditors or [] if c.get("path", "").lower() != path.lower()]
    items.append({"name": name, "path": path})
    (editors.ICON_DIR / f"{editors.custom_id(path)}.png").unlink(missing_ok=True)
    # a freshly added editor is what the user wants to use
    _save_custom(items, imageEditor=editors.custom_id(path))
    return _listing(editors.detect())


@router.put("/custom/{editor_id}")
async def rename_custom(request: Request, editor_id: str, body: dict = Body(...)) -> dict:
    _guard(request)
    name = str(body.get("name") or "").strip()
    items = [dict(c, name=name) if name and editors.custom_id(c.get("path", "")) == editor_id else c for c in config.settings().customEditors or []]
    _save_custom(items)
    return _listing(editors.detect())


@router.delete("/custom/{editor_id}")
async def remove_custom(request: Request, editor_id: str) -> dict:
    _guard(request)
    items = [c for c in config.settings().customEditors or [] if editors.custom_id(c.get("path", "")) != editor_id]
    extra = {"imageEditor": ""} if config.settings().imageEditor == editor_id else {}
    _save_custom(items, **extra)
    return _listing(editors.detect())


@router.get("/{editor_id}/icon")
async def editor_icon(editor_id: str):
    p = await asyncio.to_thread(editors.icon, editor_id)
    if not p:
        raise HTTPException(404, "no icon")
    return FileResponse(p, media_type="image/png", headers={"cache-control": "max-age=86400"})


def _resolve(url: str) -> Path:
    bases = {
        "/outputs/": Path(config.settings().outputDir),
        "/files/uploads/": gallery.uploads_dir(),
    }
    for prefix, base in bases.items():
        if url.startswith(prefix):
            p = (base / url.removeprefix(prefix).split("?")[0]).resolve()
            if p.is_file() and p.is_relative_to(base.resolve()):
                return p
    raise HTTPException(404, "image not found")


@router.post("/open")
async def open_in_editor(request: Request, body: dict = Body(...)) -> dict:
    if not _local(request):
        raise HTTPException(403, "editors can only be opened from this machine")
    path = _resolve(str(body.get("url") or ""))
    want = body.get("editor")
    found = editors.detect()
    e = next((x for x in found if x["id"] == want), None) if want else editors.current()
    if not e:
        raise HTTPException(404, "no image editor found")
    gid = body.get("galleryId")
    source = store.get_gallery(gid) if isinstance(gid, str) and gid else None
    # the editor gets a private copy; saves come back as new gallery images, the copy goes when the editor closes
    try:
        sid = await asyncio.to_thread(editing.start, e, path, source)
    except OSError as err:
        raise HTTPException(500, f"could not start {e['name']}: {err}") from err
    return {"editor": e["id"], "session": sid}


def startup() -> None:
    editing.resume()
