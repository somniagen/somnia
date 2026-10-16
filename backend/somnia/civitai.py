from __future__ import annotations

import re
import time
from typing import Any

import httpx

from . import models
from .config import settings

BASE = "https://civitai.com/api/v1"
TTL = 120.0

_client: httpx.AsyncClient | None = None
_cache: dict[str, tuple[float, Any]] = {}


class CivitaiError(Exception):
    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


def headers() -> dict[str, str]:
    h = {"User-Agent": "somnia/0.1"}
    tok = settings().civitaiToken
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    return h


def client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0), follow_redirects=True)
    return _client


async def _get(path: str, params: dict | None = None, ttl: float = TTL) -> Any:
    params = {k: v for k, v in (params or {}).items() if v is not None and v != ""}
    key = path + "?" + "&".join(f"{k}={params[k]}" for k in sorted(params)) + "|" + ("t" if settings().civitaiToken else "")
    now = time.time()
    hit = _cache.get(key)
    if hit and now - hit[0] < ttl:
        return hit[1]
    try:
        r = await client().get(BASE + path, params=params, headers=headers())
    except httpx.HTTPError as e:
        raise CivitaiError(f"civitai unreachable: {e}") from e
    if r.status_code == 404:
        raise CivitaiError("not found on civitai", 404)
    if r.status_code in (401, 403):
        raise CivitaiError("civitai rejected the request, set a civitai token in settings", r.status_code)
    if r.status_code >= 400:
        raise CivitaiError(f"civitai error {r.status_code}", 502)
    data = r.json()
    if len(_cache) > 200:
        for k in sorted(_cache, key=lambda k: _cache[k][0])[:100]:
            _cache.pop(k, None)
    _cache[key] = (now, data)
    return data


def image_url(url: str, width: int | None = None) -> str:
    if not width or "image.civitai.com" not in url:
        return url
    if re.search(r"/(width|original)=[^/]+/", url):
        return re.sub(r"/(width|original)=[^/]+/", f"/width={width}/", url, count=1)
    return url


def map_image(i: dict) -> dict:
    meta = i.get("meta")
    url = i.get("url") or ""
    typ = i.get("type") or ("video" if url.endswith((".mp4", ".webm")) else "image")
    nl = i.get("nsfwLevel", 0)
    if not isinstance(nl, int):
        nl = {"None": 1, "Soft": 2, "Mature": 4, "X": 8}.get(str(nl), 0)
    return {
        "id": int(i.get("id") or 0),
        "url": url,
        "thumb": image_url(url, 450) if typ == "image" else url,
        "width": int(i.get("width") or 0),
        "height": int(i.get("height") or 0),
        "nsfwLevel": nl,
        "type": "video" if typ == "video" else "image",
        "meta": meta if isinstance(meta, dict) else None,
    }


def map_file(f: dict) -> dict:
    md = f.get("metadata") or {}
    return {
        "id": int(f["id"]),
        "name": f.get("name") or "",
        "sizeKB": float(f.get("sizeKB") or 0),
        "type": f.get("type") or "",
        "primary": bool(f.get("primary")),
        "format": md.get("format"),
        "fp": md.get("fp"),
    }


def map_version(v: dict, installed: dict[int, str]) -> dict:
    return {
        "id": int(v["id"]),
        "name": v.get("name") or "",
        "baseModel": v.get("baseModel") or "",
        "createdAt": v.get("createdAt") or "",
        "trainedWords": [str(w) for w in (v.get("trainedWords") or [])],
        "files": [map_file(f) for f in (v.get("files") or []) if "id" in f],
        "images": [map_image(i) for i in (v.get("images") or [])],
        "downloadCount": int((v.get("stats") or {}).get("downloadCount") or 0),
        "description": v.get("description"),
        "installed": installed.get(int(v["id"])),
    }


def map_model(m: dict, installed: dict[int, str] | None = None) -> dict:
    installed = installed if installed is not None else models.installed_by_version()
    st = m.get("stats") or {}
    cr = m.get("creator")
    return {
        "id": int(m["id"]),
        "name": m.get("name") or "",
        "type": m.get("type") or "",
        "nsfw": bool(m.get("nsfw")),
        "creator": {"username": cr.get("username") or "", "image": cr.get("image")} if isinstance(cr, dict) else None,
        "tags": [t if isinstance(t, str) else str(t.get("name", "")) for t in (m.get("tags") or [])],
        "description": m.get("description"),
        "stats": {
            "downloadCount": int(st.get("downloadCount") or 0),
            "thumbsUpCount": int(st.get("thumbsUpCount") or st.get("rating") or 0),
            "favoriteCount": int(st.get("favoriteCount") or 0),
            "commentCount": int(st.get("commentCount") or 0),
        },
        "versions": [map_version(v, installed) for v in (m.get("modelVersions") or []) if "id" in v],
    }


def _next_cursor(meta: dict | None) -> str | None:
    meta = meta or {}
    if meta.get("nextCursor"):
        return str(meta["nextCursor"])
    np = meta.get("nextPage")
    if np:
        m = re.search(r"[?&]page=(\d+)", np)
        if m:
            return "page:" + m.group(1)
    return None


async def search(q: dict) -> dict:
    cursor = q.get("cursor")
    params: dict[str, Any] = {
        "limit": q.get("limit") or 24,
        "query": q.get("query"),
        "types": q.get("types"),
        "sort": q.get("sort") or "Most Downloaded",
        "period": q.get("period"),
        "baseModels": q.get("baseModels"),
    }
    nsfw = q.get("nsfw")
    if nsfw is not None:
        params["nsfw"] = "true" if nsfw else "false"
    if cursor:
        if cursor.startswith("page:"):
            params["page"] = cursor[5:]
        else:
            params["cursor"] = cursor
    if params["query"] and params["baseModels"]:
        pass
    data = await _get("/models", params)
    installed = models.installed_by_version()
    return {
        "items": [map_model(m, installed) for m in data.get("items", []) if m.get("modelVersions")],
        "nextCursor": _next_cursor(data.get("metadata")),
    }


async def get_model(model_id: int) -> dict:
    data = await _get(f"/models/{model_id}", ttl=60)
    return map_model(data)


async def get_images(version_id: int, cursor: str | None = None, limit: int = 24, nsfw: bool | None = None) -> dict:
    if nsfw is None:
        nsfw = settings().showNsfw
    params: dict[str, Any] = {
        "modelVersionId": version_id,
        "limit": limit,
        "sort": "Most Reactions",
        "cursor": cursor,
    }
    params["nsfw"] = "X" if nsfw else "None"
    data = await _get("/images", params)
    return {
        "items": [map_image(i) for i in data.get("items", [])],
        "nextCursor": _next_cursor(data.get("metadata")),
    }


async def by_hash(sha256: str) -> dict | None:
    try:
        return await _get(f"/model-versions/by-hash/{sha256}", ttl=3600)
    except CivitaiError as e:
        if e.status == 404:
            return None
        raise


async def get_version_raw(version_id: int) -> dict:
    return await _get(f"/model-versions/{version_id}", ttl=60)


async def get_model_raw(model_id: int) -> dict:
    return await _get(f"/models/{model_id}", ttl=60)
