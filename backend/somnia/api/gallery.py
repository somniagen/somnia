from __future__ import annotations

import threading

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from .. import gallery, store
from ..hub import hub

router = APIRouter(prefix="/api")
_bg_lock = threading.Lock()


@router.get("/gallery")
def list_items(
    cursor: str | None = None, limit: int = 40, q: str = "", model: str = "", sort: str = "newest", fav: bool = False, album: str = ""
) -> dict:
    limit = max(1, min(limit, 200))
    if q.strip() or model or sort != "newest" or fav or album:
        off = int(cursor[2:]) if cursor and cursor.startswith("o:") and cursor[2:].isdigit() else 0
        items, nxt = store.search_gallery(q, model, sort, off, limit, fav, album)
    else:
        items, nxt = store.list_gallery(cursor, limit)
    return {"items": items, "nextCursor": nxt}


@router.get("/gallery/models")
def models_used() -> list[dict]:
    return store.gallery_models()


class AlbumBody(BaseModel):
    ids: list[str]
    album: str


class NameBody(BaseModel):
    name: str


class FavoriteBody(BaseModel):
    favorite: bool


class FavoriteManyBody(BaseModel):
    ids: list[str]
    favorite: bool


@router.get("/gallery/albums")
def albums() -> list[dict]:
    return store.list_albums()


@router.post("/gallery/albums/add")
def album_add(body: AlbumBody) -> list[dict]:
    if not store.album_name(body.album):
        raise HTTPException(400, "album name required")
    return store.edit_albums(body.ids, body.album, True)


@router.post("/gallery/albums/remove")
def album_remove(body: AlbumBody) -> list[dict]:
    return store.edit_albums(body.ids, body.album, False)


@router.put("/gallery/albums/{name:path}")
def album_rename(name: str, body: NameBody) -> list[dict]:
    if not store.album_name(body.name):
        raise HTTPException(400, "album name required")
    store.rename_album(name, body.name)
    return store.list_albums()


@router.delete("/gallery/albums/{name:path}")
def album_delete(name: str) -> list[dict]:
    store.delete_album(name)
    return store.list_albums()


@router.post("/gallery/favorite")
def favorite_many(body: FavoriteManyBody) -> list[dict]:
    return store.set_favorite(body.ids, body.favorite)


@router.put("/gallery/{gid}/favorite")
def favorite(gid: str, body: FavoriteBody) -> dict:
    out = store.set_favorite([gid], body.favorite)
    if not out:
        raise HTTPException(404, "not found")
    return out[0]


@router.post("/gallery/{gid}/remove-bg")
def remove_bg(gid: str) -> dict:
    src = store.get_gallery(gid)
    if src is None:
        raise HTTPException(404, "not found")
    from PIL import Image

    from .. import bgremove

    try:
        with Image.open(gallery.file_of(src)) as im:
            im.load()
            img = im.convert("RGB")
    except OSError:
        raise HTTPException(404, "image file missing")
    from .. import config, jobs

    # stay off the gpu while a generation holds it
    busy = any(j["status"] == "running" for j in jobs.queue_list())
    with _bg_lock:
        out = bgremove.remove_background(img, cpu=busy)
        if not config.settings().keepModelsLoaded:
            bgremove.release()
    item = gallery.save_derived(out, src, "nobg")
    hub.broadcast({"type": "gallery_item", "item": item})
    return item


@router.get("/gallery/{gid}/stack")
def stack(gid: str) -> list[dict]:
    item = store.get_gallery(gid)
    if item is None:
        raise HTTPException(404, "not found")
    return store.list_stack(item.get("stackId") or gid)


class DownloadBody(BaseModel):
    ids: list[str]


@router.post("/gallery/download")
def download(body: DownloadBody) -> Response:
    items: list[dict] = []
    seen: set[str] = set()
    for gid in body.ids:
        it = store.get_gallery(gid)
        if it and it["id"] not in seen:
            seen.add(it["id"])
            items.append(it)
    if not items:
        raise HTTPException(404, "not found")
    if len(items) == 1:
        try:
            name, data = gallery.png_bytes(items[0])
        except OSError:
            raise HTTPException(404, "image file missing")
        return Response(data, media_type="image/png", headers={"content-disposition": f'attachment; filename="{name}"'})
    data = gallery.zip_items(items).getvalue()
    name = f"somnia-{len(items)}.zip"
    return Response(data, media_type="application/zip", headers={"content-disposition": f'attachment; filename="{name}"'})


@router.put("/gallery/{gid}/cover")
def cover(gid: str) -> dict:
    root = store.set_cover(gid)
    if root is None:
        raise HTTPException(404, "not found")
    return root


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
