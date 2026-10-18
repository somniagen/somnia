from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlparse

import httpx

from .config import settings

BASE = "https://huggingface.co"
TTL = 120.0
PAGE = 50
MAX_PAGES = 4

# category -> (kind, detector sub folder)
CATEGORIES: dict[str, tuple[str, str | None]] = {
    "checkpoint": ("checkpoint", None),
    "lora": ("lora", None),
    "vae": ("vae", None),
    "text_encoder": ("text_encoder", None),
    "upscaler": ("upscaler", None),
    "bbox": ("detector", "bbox"),
    "segm": ("detector", "segm"),
    "embedding": ("embedding", None),
}
# what an empty search shows per category, hf search is a substring match on the repo id
SEEDS: dict[str, tuple[str | None, str | None]] = {
    "": ("illustrious", None),
    "checkpoint": ("illustrious", None),
    "lora": ("illustrious", "lora"),
    "vae": ("vae", None),
    "text_encoder": ("repackaged", None),
    "upscaler": ("upscale", None),
    "bbox": (None, "ultralytics"),
    "segm": (None, "ultralytics"),
    "embedding": (None, "textual-inversion"),
}
SORTS = {"downloads", "likes", "trendingScore", "lastModified"}
FOLDERS = {
    "checkpoints": "checkpoint",
    "unet": "checkpoint",
    "diffusion_models": "checkpoint",
    "loras": "lora",
    "lora": "lora",
    "vae": "vae",
    "text_encoders": "text_encoder",
    "text_encoder": "text_encoder",
    "clip": "text_encoder",
    "upscale_models": "upscaler",
    "upscalers": "upscaler",
    "esrgan": "upscaler",
    "ultralytics": "detector",
    "bbox": "detector",
    "segm": "detector",
    "embeddings": "embedding",
    "embedding": "embedding",
}
GENERIC = {"model", "pytorch_model", "diffusion_pytorch_model", "adapter_model", "flax_model", "tf_model"}
_UPSCALE = re.compile(
    r"(?:^|[^a-z0-9])(?:[1-8]x|x[1-8])(?:[^a-z0-9]|$)|esrgan|upscal|swinir|ultrasharp|animesharp|nmkd|realesr|omnisr|scunet|"
    r"nomos|(?:^|[^a-z])(?:dat2?|hat|span|compact|plksr|rgt)(?:[^a-z]|$)"
)
_TE = re.compile(r"clip_[lg]|t5xxl|umt5|text_?encoder|(?:^|[^a-z])(?:qwen|gemma|llama)[^/]*\d+(?:\.\d+)?b")
_SHARD = re.compile(r"-\d{5}-of-\d{5}")

_client: httpx.AsyncClient | None = None
_cache: dict[str, tuple[float, Any]] = {}


class HfError(Exception):
    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


def headers() -> dict[str, str]:
    h = {"User-Agent": "somnia/0.1"}
    tok = settings().hfToken
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    return h


def client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0), follow_redirects=True)
    return _client


async def _get(url: str, params: list[tuple[str, str]] | None = None) -> tuple[Any, httpx.Headers]:
    key = url + "?" + "&".join(f"{k}={v}" for k, v in (params or [])) + "|" + ("t" if settings().hfToken else "")
    now = time.time()
    hit = _cache.get(key)
    if hit and now - hit[0] < TTL:
        return hit[1]
    try:
        r = await client().get(url, params=params, headers=headers())
    except httpx.HTTPError as e:
        raise HfError(f"hugging face unreachable: {e}") from e
    if r.status_code in (401, 403):
        raise HfError("hugging face rejected the request, the repo may be gated or need a token", r.status_code)
    if r.status_code == 404:
        raise HfError("not found on hugging face", 404)
    if r.status_code >= 400:
        raise HfError(f"hugging face error {r.status_code}", 502)
    out = (r.json(), r.headers)
    if len(_cache) > 200:
        for k in sorted(_cache, key=lambda k: _cache[k][0])[:100]:
            _cache.pop(k, None)
    _cache[key] = (now, out)
    return out


def classify(path: str, tags: list[str], library: str | None = None, size: int | None = None, diffusers: bool = False) -> tuple[str, str | None] | None:
    p = path.lower()
    parts = p.split("/")
    name = parts[-1]
    stem, _, ext = name.rpartition(".")
    if not stem or ext not in ("safetensors", "ckpt", "pt", "pth"):
        return None
    if _SHARD.search(stem) or "diffusion_pytorch_model" in stem:
        return None
    if diffusers and len(parts) > 1:
        return None
    tagset = {t.lower() for t in tags}
    yolo = library == "ultralytics" or "ultralytics" in tagset or "yolo" in p
    if ext == "pt" and yolo:
        return "detector", "segm" if "seg" in stem else "bbox"
    for seg in parts[:-1]:
        kind = FOLDERS.get(seg)
        if kind == "detector":
            return (kind, "segm" if seg == "segm" or "seg" in stem else "bbox") if ext == "pt" else None
        if kind:
            return kind, None
    if stem in GENERIC:
        return None
    lora = bool(re.search(r"lora|lycoris|locon|loha|lokr", p)) or "lora" in tagset or stem == "pytorch_lora_weights"
    upscale = bool(_UPSCALE.search(stem)) and not lora and "latent" not in p and "-ema" not in stem and (size is None or size < 400 << 20)
    if ext in ("pt", "pth"):
        if upscale:
            return "upscaler", None
        if "textual-inversion" in tagset or "textual_inversion" in tagset or "embedding" in p:
            return "embedding", None
        return None
    if "textual-inversion" in tagset or "textual_inversion" in tagset or "embedding" in p:
        if size is None or size < 4 << 20:
            return "embedding", None
    if re.search(r"(?:^|[^a-z])vae(?:[^a-z]|$)", stem) and "lora" not in stem and (size is None or size < 1 << 30):
        return "vae", None
    if _TE.search(stem):
        return "text_encoder", None
    if upscale:
        return "upscaler", None
    if lora:
        if size is None or size < 3 << 30:
            return "lora", None
    if size is not None and size < 1 << 30:
        return None
    return "checkpoint", None


def _is_diffusers(files: list[str]) -> bool:
    return "model_index.json" in files


def _label(kind: str, sub: str | None) -> str:
    return sub if kind == "detector" and sub else kind


def _repo(m: dict, category: str) -> dict | None:
    files = [s.get("rfilename", "") for s in m.get("siblings") or []]
    diff = _is_diffusers(files)
    tags = m.get("tags") or []
    want = CATEGORIES.get(category)
    kinds: set[str] = set()
    count = 0
    for f in files:
        c = classify(f, tags, m.get("library_name"), diffusers=diff)
        if c is None:
            continue
        kinds.add(_label(*c))
        if want is None or c == want:
            count += 1
    if not count:
        return None
    rid = m.get("id") or m.get("modelId") or ""
    return {
        "id": rid,
        "author": m.get("author") or rid.split("/")[0],
        "downloads": int(m.get("downloads") or 0),
        "likes": int(m.get("likes") or 0),
        "lastModified": m.get("lastModified"),
        "gated": bool(m.get("gated")),
        "tags": [t for t in tags if ":" not in t][:12],
        "kinds": sorted(kinds),
        "files": count,
    }


def _next_cursor(h: httpx.Headers) -> str | None:
    link = h.get("link") or ""
    m = re.search(r'<([^>]+)>;\s*rel="next"', link)
    if not m:
        return None
    return (parse_qs(urlparse(m.group(1)).query).get("cursor") or [None])[0]


async def _search(q: str, filt: str | None, category: str, sort: str, cursor: str | None, limit: int) -> tuple[list[dict], str | None]:
    params: list[tuple[str, str]] = [("sort", sort if sort in SORTS else "downloads"), ("direction", "-1"), ("limit", str(PAGE))]
    if q:
        params.append(("search", q))
    if filt:
        params.append(("filter", filt))
    for e in ("siblings", "downloads", "likes", "tags", "lastModified", "gated", "library_name", "author"):
        params.append(("expand[]", e))
    items: list[dict] = []
    for _ in range(MAX_PAGES):
        page = params + ([("cursor", cursor)] if cursor else [])
        data, h = await _get(f"{BASE}/api/models", page)
        for m in data:
            r = _repo(m, category)
            if r:
                items.append(r)
        cursor = _next_cursor(h)
        if not cursor or len(items) >= limit:
            break
    return items, cursor


async def search(query: str | None, category: str = "", sort: str = "downloads", cursor: str | None = None, limit: int = 24) -> dict:
    category = category if category in CATEGORIES else ""
    typed = (query or "").strip()
    seed, filt = SEEDS[category]
    if not typed:
        items, nxt = await _search(seed or "", filt, category, sort, cursor, limit)
        return {"items": items, "nextCursor": nxt}
    filt = filt if category in ("bbox", "segm") else None
    # "s:" cursors continue the fallback search that adds the category word to the query
    combined = f"{typed} {seed}" if category in ("upscaler", "vae") and seed and seed not in typed.lower() else None
    if cursor and cursor.startswith("s:") and combined:
        items, nxt = await _search(combined, filt, category, sort, cursor[2:], limit)
        return {"items": items, "nextCursor": "s:" + nxt if nxt else None}
    items, nxt = await _search(typed, filt, category, sort, cursor, limit)
    if not items and not cursor and combined:
        items, nxt = await _search(combined, filt, category, sort, None, limit)
        return {"items": items, "nextCursor": "s:" + nxt if nxt else None}
    return {"items": items, "nextCursor": nxt}


def _readme(text: str) -> str:
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end > 0:
            text = text[end + 4 :]
    return text.strip()[:6000]


async def repo(repo_id: str, category: str = "") -> dict:
    info, _ = await _get(f"{BASE}/api/models/{repo_id}")
    tree, _ = await _get(f"{BASE}/api/models/{repo_id}/tree/main", [("recursive", "true")])
    names = [t.get("path", "") for t in tree if t.get("type") == "file"]
    diff = _is_diffusers(names)
    tags = info.get("tags") or []
    lib = info.get("library_name")
    from . import downloads

    files = []
    for t in tree:
        if t.get("type") != "file":
            continue
        path = t.get("path", "")
        size = int((t.get("lfs") or {}).get("size") or t.get("size") or 0)
        c = classify(path, tags, lib, size or None, diff)
        ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
        if c is None and ext not in ("safetensors", "ckpt", "pt", "pth"):
            continue
        kind, sub = c if c else (None, None)
        files.append({
            "path": path,
            "size": size,
            "kind": kind,
            "sub": sub,
            "installed": downloads.hf_installed(repo_id, path, kind, sub) if kind else None,
        })
    want = CATEGORIES.get(category)
    files.sort(key=lambda f: (want is not None and (f["kind"], f["sub"]) != want, f["kind"] is None, f["path"].lower()))
    readme = ""
    if "README.md" in names:
        try:
            r = await client().get(f"{BASE}/{repo_id}/raw/main/README.md", headers=headers())
            if r.status_code == 200:
                readme = _readme(r.text)
        except httpx.HTTPError:
            pass
    return {
        "id": info.get("id") or repo_id,
        "author": info.get("author") or repo_id.split("/")[0],
        "downloads": int(info.get("downloads") or 0),
        "likes": int(info.get("likes") or 0),
        "lastModified": info.get("lastModified"),
        "gated": bool(info.get("gated")),
        "tags": [t for t in tags if ":" not in t][:20],
        "sha": info.get("sha"),
        "readme": readme,
        "files": files,
    }


def file_url(repo_id: str, path: str, revision: str = "main") -> str:
    return f"{BASE}/{repo_id}/resolve/{quote(revision, safe='')}/{quote(path)}"


def dest_name(repo_id: str, path: str) -> str:
    name = Path(path).name
    stem, ext = Path(name).stem, Path(name).suffix
    if stem.lower() in GENERIC or stem.lower() in ("pytorch_lora_weights",):
        return repo_id.split("/")[-1] + ext
    return name
