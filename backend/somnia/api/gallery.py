from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile

from .. import gallery, store

router = APIRouter(prefix="/api")


@router.get("/gallery")
def list_items(cursor: str | None = None, limit: int = 40, q: str = "", model: str = "", sort: str = "newest") -> dict:
    limit = max(1, min(limit, 200))
    if q.strip() or model or sort != "newest":
        off = int(cursor[2:]) if cursor and cursor.startswith("o:") and cursor[2:].isdigit() else 0
        items, nxt = store.search_gallery(q, model, sort, off, limit)
    else:
        items, nxt = store.list_gallery(cursor, limit)
    return {"items": items, "nextCursor": nxt}


@router.get("/gallery/models")
def models_used() -> list[dict]:
    return store.gallery_models()


@router.get("/gallery/{gid}/stack")
def stack(gid: str) -> list[dict]:
    item = store.get_gallery(gid)
    if item is None:
        raise HTTPException(404, "not found")
    return store.list_stack(item.get("stackId") or gid)


@router.post("/gallery/{gid}/upload")
def to_upload(gid: str) -> dict:
    item = store.get_gallery(gid)
    if item is None:
        raise HTTPException(404, "not found")
    try:
        return gallery.upload_from_gallery(item)
    except OSError:
        raise HTTPException(404, "image file missing")


@router.delete("/gallery/{gid}")
def delete(gid: str) -> dict:
    item = store.get_gallery(gid)
    if item is None:
        raise HTTPException(404, "not found")
    store.delete_gallery(gid)
    gallery.delete_files(item)
    return {}


@router.post("/upload")
async def upload(file: UploadFile = File(...)) -> dict:
    data = await file.read()
    try:
        return gallery.save_upload(data)
    except Exception:
        raise HTTPException(400, "not a valid image")
