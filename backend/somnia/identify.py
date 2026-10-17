from __future__ import annotations

import asyncio
import hashlib
import json
import threading
import time
from pathlib import Path

from . import civitai, config, models
from .downloads import _broadcast

MISS_RETRY = 7 * 86400
UPDATE_EVERY = 86400

state = {"running": False, "done": 0, "total": 0}
_task: asyncio.Task | None = None
_again = False
_updates: dict | None = None
_updates_lock = threading.Lock()
_check_lock: asyncio.Lock | None = None


def _emit() -> None:
    _broadcast({"type": "identify", **state})


def _hash_key(path: Path | str) -> str:
    return "sha:" + str(path)


def sha256(path: Path) -> str:
    cache = models._load_cache()
    st = path.stat()
    key = _hash_key(path)
    ent = cache.get(key)
    if ent and ent.get("mtime") == st.st_mtime and ent.get("size") == st.st_size and ent.get("sha256"):
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


def _mark_miss(path: Path) -> None:
    ent = models._load_cache().get(_hash_key(path))
    if ent is not None:
        ent["miss"] = time.time()
        models._cache_dirty = True
        models._save_cache()


def candidates(auto: bool) -> list[dict]:
    cache = models._load_cache()
    now = time.time()
    out = []
    for m in models.list_models():
        c = m.get("civitai")
        if (c and c.get("versionId")) or m["path"].lower().endswith(".gguf"):
            continue
        if auto:
            ent = cache.get(_hash_key(m["path"]))
            if ent and ent.get("mtime") == m["mtime"] and ent.get("size") == m["size"] and now - ent.get("miss", 0) < MISS_RETRY:
                continue
        out.append(m)
    return out


def _write_sidecar(path: Path, model: dict, version: dict) -> None:
    Path(str(path.with_suffix("")) + ".civitai.json").write_text(json.dumps({"model": model, "version": version}, indent=1), "utf-8")


async def _run(auto: bool) -> None:
    todo = await asyncio.to_thread(candidates, auto)
    if not todo and auto:
        return
    state.update(running=True, done=0, total=len(todo))
    _emit()
    found = 0
    try:
        for m in todo:
            p = Path(m["path"])
            try:
                h = await asyncio.to_thread(sha256, p)
                v = await civitai.by_hash(h)
                if v:
                    mraw = {}
                    try:
                        mraw = await civitai.get_model_raw(int(v["modelId"]))
                    except Exception:
                        pass
                    model = {k: x for k, x in mraw.items() if k != "modelVersions"} or dict(v.get("model") or {})
                    ver = {k: x for k, x in v.items() if k != "model"}
                    await asyncio.to_thread(_write_sidecar, p, model, ver)
                    found += 1
                else:
                    await asyncio.to_thread(_mark_miss, p)
            except civitai.CivitaiError:
                # civitai unreachable or rejecting, try again on the next run
                break
            except Exception:
                pass
            state["done"] += 1
            _emit()
        if found:
            await asyncio.to_thread(models.rescan)
            _broadcast({"type": "models_changed"})
    finally:
        state["running"] = False
        _emit()
    if found:
        await check_updates()


async def _loop(auto: bool) -> None:
    global _again
    while True:
        await _run(auto)
        if not _again:
            return
        _again = False
        auto = True


def start(auto: bool = False) -> dict:
    global _task, _again
    if auto and not config.settings().autoIdentify:
        return dict(state)
    if _task is not None and not _task.done():
        _again = True
        return dict(state)
    _again = False
    _task = asyncio.create_task(_loop(auto))
    return dict(state)


def _updates_file() -> Path:
    return config.DATA_DIR / "civitai_updates.json"


def _load_updates() -> dict:
    global _updates
    with _updates_lock:
        if _updates is None:
            try:
                _updates = json.loads(_updates_file().read_text("utf-8"))
            except Exception:
                _updates = {}
        return _updates


def _save_updates() -> None:
    with _updates_lock:
        try:
            _updates_file().write_text(json.dumps(_updates or {}), "utf-8")
        except OSError:
            pass


def _version_row(v: dict) -> dict:
    return {"id": int(v["id"]), "name": str(v.get("name") or ""), "baseModel": str(v.get("baseModel") or "")}


async def check_updates(force: bool = False) -> bool:
    global _check_lock
    if _check_lock is None:
        _check_lock = asyncio.Lock()
    async with _check_lock:
        ups = _load_updates()
        now = time.time()
        ids = sorted({int(c["modelId"]) for m in await asyncio.to_thread(models.list_models) if (c := m.get("civitai")) and c.get("modelId") and c.get("versionId")})
        dirty = changed = False
        for mid in ids:
            ent = ups.get(str(mid))
            if ent and not force and now - ent.get("checked", 0) < UPDATE_EVERY:
                continue
            try:
                raw = await civitai.get_model_raw(mid)
            except civitai.CivitaiError as e:
                if e.status != 404:
                    break
                raw = {}
            vs = [_version_row(v) for v in raw.get("modelVersions") or [] if isinstance(v, dict) and "id" in v]
            changed = changed or not ent or ent.get("versions") != vs
            ups[str(mid)] = {"checked": now, "versions": vs}
            dirty = True
            await asyncio.sleep(0.3)
        if dirty:
            await asyncio.to_thread(_save_updates)
        if changed:
            _broadcast({"type": "models_changed"})
        return changed


def update_for(c: dict, installed: dict[int, str]) -> dict | None:
    ent = _load_updates().get(str(c.get("modelId")))
    if not ent:
        return None
    vs = ent.get("versions") or []
    cur = int(c.get("versionId") or 0)
    idx = next((i for i, v in enumerate(vs) if v["id"] == cur), None)
    # civitai lists versions newest first
    newer = vs[:idx] if idx is not None else [v for v in vs if v["id"] > cur]
    base = c.get("baseModel") or ""
    for v in newer:
        if v["id"] in installed:
            return None
        if not base or not v["baseModel"] or v["baseModel"] == base:
            return v
    return None


def decorate(items: list[dict]) -> list[dict]:
    installed = models.installed_by_version()
    out = []
    for m in items:
        c = m.get("civitai")
        if c and c.get("versionId") and c.get("modelId"):
            u = update_for(c, installed)
            m = {**m, "civitai": {**c, "updateVersionId": u["id"] if u else None, "updateVersionName": u["name"] if u else None}}
        out.append(m)
    return out


async def _updates_loop() -> None:
    while True:
        try:
            if config.settings().autoIdentify:
                await check_updates()
        except Exception:
            pass
        await asyncio.sleep(3600)


_bg: list[asyncio.Task] = []


async def _startup() -> None:
    await asyncio.to_thread(models.list_models)
    start(auto=True)
    _bg.append(asyncio.create_task(_updates_loop()))


def startup() -> None:
    _bg.append(asyncio.create_task(_startup()))
