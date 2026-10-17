from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from pathlib import Path

import httpx

from . import civitai, models
from .config import settings

TYPE_MAP: dict[str, tuple[str, str]] = {
    "checkpoint": ("checkpoint", "checkpoints"),
    "lora": ("lora", "loras"),
    "locon": ("lora", "loras"),
    "dora": ("lora", "loras"),
    "vae": ("vae", "vae"),
    "upscaler": ("upscaler", "upscale_models"),
    "textencoder": ("text_encoder", "text_encoders"),
    "textualinversion": ("embedding", "embeddings"),
}

MAX_CONCURRENT = 2
THROTTLE = 0.25

_downloads: dict[str, dict] = {}
_tasks: dict[str, asyncio.Task] = {}
_sem: asyncio.Semaphore | None = None


def _broadcast(msg: dict) -> None:
    try:
        from .hub import hub
    except Exception:
        return
    try:
        hub.broadcast(msg)
    except Exception:
        pass


def _emit(d: dict) -> None:
    _broadcast({"type": "download", "download": dict(d)})


def list_downloads() -> list[dict]:
    return [dict(d) for d in _downloads.values()]


def _safe_name(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|]', "_", name).strip().strip(".")
    return name or "model.safetensors"


def _semaphore() -> asyncio.Semaphore:
    global _sem
    if _sem is None:
        _sem = asyncio.Semaphore(MAX_CONCURRENT)
    return _sem


async def start(version_id: int, file_id: int | None = None) -> dict:
    v = await civitai.get_version_raw(version_id)
    mid = int(v.get("modelId") or (v.get("model") or {}).get("id") or 0)
    mtype = str((v.get("model") or {}).get("type") or "")
    if not mtype and mid:
        mtype = str((await civitai.get_model_raw(mid)).get("type") or "")
    kind_folder = TYPE_MAP.get(mtype.lower().replace(" ", ""))
    if not kind_folder:
        raise civitai.CivitaiError(f"unsupported model type: {mtype}", 400)
    files = v.get("files") or []
    f = None
    if file_id is not None:
        f = next((x for x in files if x.get("id") == file_id), None)
    if f is None:
        f = next((x for x in files if x.get("primary")), None)
    if f is None:
        f = next((x for x in files if x.get("type") == "Model"), files[0] if files else None)
    if f is None:
        raise civitai.CivitaiError("version has no files", 400)
    for d in _downloads.values():
        if d["versionId"] == version_id and d["fileId"] == f["id"] and d["status"] in ("queued", "downloading"):
            return dict(d)
    kind, folder = kind_folder
    dest_dir = Path(settings().downloadRoot) / folder
    name = _safe_name(f.get("name") or f"{version_id}.safetensors")
    dest = dest_dir / name
    if dest.exists():
        raise civitai.CivitaiError(f"{name} already exists", 409)
    did = uuid.uuid4().hex[:10]
    d = {
        "id": did,
        "name": name,
        "kind": kind,
        "modelId": mid,
        "versionId": version_id,
        "received": 0,
        "total": int(float(f.get("sizeKB") or 0) * 1024),
        "speed": 0.0,
        "status": "queued",
        "error": None,
        "fileId": f["id"],
    }
    _downloads[did] = d
    _emit(d)
    _tasks[did] = asyncio.create_task(_run(d, v, f, dest))
    return dict(d)


def cancel(did: str) -> bool:
    d = _downloads.get(did)
    if d is None:
        return False
    t = _tasks.get(did)
    if t and not t.done():
        t.cancel()
        return True
    if d["status"] in ("done", "error", "cancelled"):
        _downloads.pop(did, None)
        _emit({**d, "status": "cancelled"})
        return True
    return False


async def wait(did: str) -> None:
    t = _tasks.get(did)
    if t:
        try:
            await t
        except BaseException:
            pass


async def _run(d: dict, v: dict, f: dict, dest: Path) -> None:
    try:
        async with _semaphore():
            d["status"] = "downloading"
            _emit(d)
            await _download(d, f, dest)
            await _sidecars(d, v, dest)
        d["status"] = "done"
        d["speed"] = 0.0
        d["received"] = d["total"] = max(d["total"], d["received"])
        _emit(d)
        await asyncio.to_thread(models.rescan)
        _broadcast({"type": "models_changed"})
    except asyncio.CancelledError:
        d["status"] = "cancelled"
        d["speed"] = 0.0
        _emit(d)
    except civitai.CivitaiError as e:
        d["status"] = "error"
        d["error"] = str(e)
        d["speed"] = 0.0
        _emit(d)
    except Exception as e:
        d["status"] = "error"
        d["error"] = f"{type(e).__name__}: {e}"
        d["speed"] = 0.0
        _emit(d)


async def _download(d: dict, f: dict, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    url = f.get("downloadUrl") or f"https://civitai.com/api/download/models/{d['versionId']}"
    have = part.stat().st_size if part.exists() else 0
    hdrs = civitai.headers()
    if have:
        hdrs["Range"] = f"bytes={have}-"
    async with civitai.client().stream("GET", url, headers=hdrs, timeout=httpx.Timeout(30.0, read=60.0)) as r:
        if r.status_code in (401, 403):
            raise civitai.CivitaiError("civitai requires login for this file, set a civitai token in settings", 401)
        if r.status_code == 416:
            have = 0
            part.unlink(missing_ok=True)
            raise civitai.CivitaiError("resume failed, retry", 416)
        if r.status_code >= 400:
            raise civitai.CivitaiError(f"download failed with http {r.status_code}", 502)
        if "text/html" in r.headers.get("content-type", ""):
            raise civitai.CivitaiError("civitai requires login for this file, set a civitai token in settings", 401)
        mode = "ab"
        if r.status_code == 200 and have:
            have = 0
            mode = "wb"
        clen = int(r.headers.get("content-length") or 0)
        if clen:
            d["total"] = have + clen
        d["received"] = have
        last = time.monotonic()
        last_bytes = have
        speed = 0.0
        with open(part, mode) as out:
            async for chunk in r.aiter_bytes(1 << 20):
                out.write(chunk)
                d["received"] += len(chunk)
                now = time.monotonic()
                if now - last >= THROTTLE:
                    inst = (d["received"] - last_bytes) / (now - last)
                    speed = inst if speed == 0 else speed * 0.6 + inst * 0.4
                    d["speed"] = speed
                    last, last_bytes = now, d["received"]
                    _emit(d)
    if d["total"] and part.stat().st_size < d["total"]:
        raise civitai.CivitaiError("download incomplete, retry to resume", 502)
    part.replace(dest)


async def _sidecars(d: dict, v: dict, dest: Path) -> None:
    stem = dest.with_suffix("")
    model = dict(v.get("model") or {})
    model["id"] = d["modelId"]
    try:
        mraw = await civitai.get_model_raw(d["modelId"])
        model = {k: x for k, x in mraw.items() if k != "modelVersions"}
    except Exception:
        pass
    ver = {k: x for k, x in v.items() if k != "model"}
    Path(str(stem) + ".civitai.json").write_text(json.dumps({"model": model, "version": ver}, indent=1), "utf-8")
    for img in v.get("images") or []:
        if img.get("type", "image") != "image" or not img.get("url"):
            continue
        try:
            r = await civitai.client().get(civitai.image_url(img["url"], 512), headers={"User-Agent": "somnia/0.1"})
            if r.status_code != 200:
                continue
            ct = r.headers.get("content-type", "")
            ext = ".preview.webp" if "webp" in ct else ".preview.png" if "png" in ct else ".preview.jpeg"
            Path(str(stem) + ext).write_bytes(r.content)
            break
        except Exception:
            continue
