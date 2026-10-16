from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from .. import civitai, models
from ..downloads import _broadcast

router = APIRouter(prefix="/api/models", tags=["models"])

_identify_task: asyncio.Task | None = None
_identify_state = {"running": False, "done": 0, "total": 0}


@router.get("")
async def list_models(kind: str | None = None):
    return await asyncio.to_thread(models.list_models, kind)


@router.post("/rescan")
async def rescan():
    items = await asyncio.to_thread(models.rescan)
    _broadcast({"type": "models_changed"})
    return items


@router.get("/preview/{model_id:path}")
async def preview(model_id: str):
    p = models.preview_path(model_id)
    if p is None:
        raise HTTPException(404, "no preview")
    return FileResponse(p, headers={"Cache-Control": "public, max-age=3600"})


@router.delete("/{model_id:path}")
async def delete(model_id: str):
    try:
        await asyncio.to_thread(models.trash, model_id)
    except FileNotFoundError:
        raise HTTPException(404, "model not found")
    _broadcast({"type": "models_changed"})
    return {"ok": True}


def _sha256(path: Path) -> str:
    cache = models._load_cache()
    st = path.stat()
    key = "sha:" + str(path)
    ent = cache.get(key)
    if ent and ent.get("mtime") == st.st_mtime and ent.get("size") == st.st_size:
        return ent["sha256"]
    sidecar = Path(str(path.with_suffix("")) + ".sha256")
    h = None
    if sidecar.exists() and sidecar.stat().st_mtime >= st.st_mtime:
        txt = sidecar.read_text("utf-8").strip().split()
        if txt and len(txt[0]) == 64:
            h = txt[0].lower()
    if h is None:
        m = hashlib.sha256()
        with open(path, "rb") as f:
            while True:
                b = f.read(1 << 24)
                if not b:
                    break
                m.update(b)
        h = m.hexdigest()
    cache[key] = {"mtime": st.st_mtime, "size": st.st_size, "sha256": h}
    models._cache_dirty = True
    models._save_cache()
    return h


async def _identify() -> None:
    st = _identify_state
    todo = [m for m in models.list_models() if m["kind"] in ("checkpoint", "lora", "vae") and not (m["civitai"] and m["civitai"]["versionId"]) and m["path"].endswith(".safetensors")]
    st.update(running=True, done=0, total=len(todo))
    found = 0
    try:
        for m in todo:
            p = Path(m["path"])
            try:
                h = await asyncio.to_thread(_sha256, p)
                v = await civitai.by_hash(h)
                if v:
                    mraw = {}
                    try:
                        mraw = await civitai.get_model_raw(int(v["modelId"]))
                    except Exception:
                        pass
                    model = {k: x for k, x in mraw.items() if k != "modelVersions"} or dict(v.get("model") or {})
                    ver = {k: x for k, x in v.items() if k != "model"}
                    Path(str(p.with_suffix("")) + ".civitai.json").write_text(json.dumps({"model": model, "version": ver}, indent=1), "utf-8")
                    found += 1
            except Exception:
                pass
            st["done"] += 1
        if found:
            await asyncio.to_thread(models.rescan)
            _broadcast({"type": "models_changed"})
    finally:
        st["running"] = False


@router.post("/identify")
async def identify():
    global _identify_task
    if _identify_task is None or _identify_task.done():
        _identify_task = asyncio.create_task(_identify())
    return dict(_identify_state)


@router.get("/identify")
async def identify_status():
    return dict(_identify_state)
