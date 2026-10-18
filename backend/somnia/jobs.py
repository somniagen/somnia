from __future__ import annotations

import base64
import copy
import gc
import io
import json
import random
import threading
import time
import uuid
from pathlib import Path

from PIL import Image
from PIL.PngImagePlugin import PngInfo

from . import config, store
from .engine.base import Cancelled, RunContext
from .hub import hub

_cond = threading.Condition()
_jobs: list[dict] = []
_cancel: set[str] = set()
_worker: threading.Thread | None = None
_paused = False
# repeating jobs: job id -> params the next copy is queued from
_repeat: dict[str, dict] = {}
# called with the finished job dict (done, error or cancelled) from the worker thread
on_finish: list = []
# called with params before jobs are queued, may return replacement params (plugins)
on_submit: list = []


def queue_list() -> list[dict]:
    with _cond:
        return copy.deepcopy(_jobs)


def paused() -> bool:
    return _paused


def _broadcast_queue() -> None:
    hub.broadcast({"type": "queue", "queue": queue_list(), "paused": _paused})


def set_paused(value: bool) -> bool:
    global _paused
    with _cond:
        _paused = bool(value)
        _cond.notify_all()
    _broadcast_queue()
    return _paused


def _rand() -> int:
    return random.randint(0, 2**32 - 1)


def _seeds(params: dict, count: int) -> list[tuple[int, int | None]]:
    # with a variation the main seed stays put and the variation seed advances instead
    base = int(params.get("seed", -1))
    var = params.get("variation") or {}
    if var.get("enabled") and float(var.get("strength") or 0) > 0:
        main = _rand() if base == -1 else base
        vb = int(var.get("seed", -1))
        return [(main, _rand() if vb == -1 else vb + i) for i in range(count)]
    return [(_rand() if base == -1 else base + i, None) for i in range(count)]


def submit(params: dict, count: int = 1, meta: list[dict] | None = None, repeat: bool = False) -> list[str]:
    # meta, when given, is one dict per job merged into the job record (e.g. grid cells)
    for fn in list(on_submit):
        try:
            params = fn(params) or params
        except Exception as e:
            print(f"[somnia] submit hook failed: {e}")
    count = 1 if repeat else len(meta) if meta else max(1, int(count))
    seeds = _seeds(params, 1 if meta else count) * (count if meta else 1)
    ids = []
    with _cond:
        for i in range(count):
            p = copy.deepcopy(params)
            p["seed"], vs = seeds[i]
            if vs is not None:
                p["variation"] = dict(p["variation"], seed=vs)
            jid = uuid.uuid4().hex[:12]
            ids.append(jid)
            job = {
                "id": jid,
                "params": p,
                "status": "queued",
                "createdAt": store.now_ms(),
                "startedAt": None,
                "finishedAt": None,
                "images": [],
                "error": None,
            }
            if meta:
                extra = copy.deepcopy(meta[i])
                job["params"] = _merge(p, extra.pop("patch", {}))
                job.update(extra)
            if repeat:
                job["repeat"] = True
                _repeat[jid] = _advance(params)
            _jobs.append(job)
        _cond.notify_all()
    _broadcast_queue()
    return ids


def _advance(params: dict) -> dict:
    # locked seeds step forward for each repeat, random ones stay random
    p = copy.deepcopy(params)
    var = p.get("variation") or {}
    if var.get("enabled") and float(var.get("strength") or 0) > 0:
        if int(var.get("seed", -1)) >= 0:
            p["variation"] = dict(var, seed=int(var["seed"]) + 1)
    elif int(p.get("seed", -1)) >= 0:
        p["seed"] = int(p["seed"]) + 1
    return p


def _merge(base: dict, patch: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def cancel_where(pred) -> int:
    n = 0
    with _cond:
        for j in list(_jobs):
            if not pred(j):
                continue
            n += 1
            if j["status"] == "running":
                _cancel.add(j["id"])
            else:
                _jobs.remove(j)
                _repeat.pop(j["id"], None)
    if n:
        _broadcast_queue()
    return n


def cancel(jid: str) -> bool:
    with _cond:
        for j in _jobs:
            if j["id"] == jid:
                if j["status"] == "running":
                    _cancel.add(jid)
                else:
                    _jobs.remove(j)
                    _repeat.pop(jid, None)
                break
        else:
            return False
    _broadcast_queue()
    return True


def stop_repeat() -> None:
    # the running copy still finishes, it just stops queueing new ones
    with _cond:
        _repeat.clear()
        for j in _jobs:
            j.pop("repeat", None)
    _broadcast_queue()


def reorder(ids: list[str]) -> list[dict]:
    with _cond:
        running = [j for j in _jobs if j["status"] == "running"]
        queued = {j["id"]: j for j in _jobs if j["status"] == "queued"}
        ordered = [queued.pop(i) for i in ids if i in queued]
        ordered += list(queued.values())
        _jobs[:] = running + ordered
    _broadcast_queue()
    return queue_list()


def clear() -> None:
    with _cond:
        _jobs[:] = [j for j in _jobs if j["status"] == "running"]
        for k in [k for k in _repeat if not any(j["id"] == k for j in _jobs)]:
            del _repeat[k]
    _broadcast_queue()


def start() -> None:
    global _worker
    if _worker and _worker.is_alive():
        return
    _worker = threading.Thread(target=_loop, name="somnia-worker", daemon=True)
    _worker.start()


def _loop() -> None:
    while True:
        with _cond:
            job = None if _paused else next((j for j in _jobs if j["status"] == "queued"), None)
            while job is None:
                _cond.wait()
                job = None if _paused else next((j for j in _jobs if j["status"] == "queued"), None)
            job["status"] = "running"
            job["startedAt"] = store.now_ms()
        _broadcast_queue()
        try:
            _run_job(job)
        except Exception as e:
            _fail(job, e)
        finally:
            nxt = _repeat.pop(job["id"], None)
            if nxt is not None and job["status"] == "done":
                submit(nxt, repeat=True)
            with _cond:
                if job in _jobs:
                    _jobs.remove(job)
                _cancel.discard(job["id"])
                drained = not any(j["status"] == "queued" for j in _jobs)
            _broadcast_queue()
            for fn in list(on_finish):
                try:
                    fn(job, drained)
                except Exception as e:
                    print(f"[somnia] finish hook failed: {e}")


def _fail(job: dict, e: Exception) -> None:
    job["finishedAt"] = store.now_ms()
    if isinstance(e, Cancelled):
        job["status"] = "cancelled"
        hub.broadcast({"type": "done", "job": copy.deepcopy(job)})
        return
    msg = str(e) or type(e).__name__
    if "out of memory" in msg.lower() or type(e).__name__ == "OutOfMemoryError":
        msg = "out of memory: " + msg
        try:
            import torch

            gc.collect()
            torch.cuda.empty_cache()
        except Exception:
            pass
    job["status"] = "error"
    job["error"] = msg
    hub.broadcast({"type": "error", "jobId": job["id"], "message": msg})


def _data_url(img: Image.Image, size: int = 512) -> str:
    im = img.convert("RGB")
    im.thumbnail((size, size))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=70)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def _weights(p: dict) -> list[tuple[str, float]]:
    w: list[tuple[str, float]] = [("sample", 1.0)]
    if (p.get("secondPass") or {}).get("enabled"):
        w.append(("second", 0.5))
    n = sum(1 for d in (p.get("detailers") or []) if d.get("enabled"))
    if n:
        w.append(("detail", 0.2 * n))
    if (p.get("upscale") or {}).get("enabled"):
        w.append(("upscale", 0.2))
        if ((p.get("upscale") or {}).get("tiled") or {}).get("enabled"):
            w.append(("refine", 0.8))
    return w


def _run_job(job: dict) -> None:
    from . import models
    from .engine import pipeline

    p = job["params"]
    weights = _weights(p)
    total_w = sum(w for _, w in weights)
    t0 = time.monotonic()
    state = {"overall": 0.0}

    def overall(phase: str, step: int, total: int) -> float:
        frac = step / total if total else 0.0
        done = 0.0
        for name, w in weights:
            if name == phase:
                v = (done + w * frac) / total_w
                state["overall"] = max(state["overall"], min(v, 0.99))
                return state["overall"]
            done += w
        if phase == "save":
            state["overall"] = 0.99
        return state["overall"]

    def progress(
        phase: str, step: int, total: int, preview: Image.Image | None = None, label: str | None = None, region: dict | None = None
    ) -> None:
        o = overall(phase, step, total)
        el = time.monotonic() - t0
        eta = round(el / o * (1 - o), 1) if o > 0.03 else None
        hub.broadcast(
            {
                "type": "progress",
                "jobId": job["id"],
                "phase": phase,
                "step": step,
                "total": total,
                "overall": round(o, 4),
                "etaSec": eta,
                "preview": _data_url(preview, 1024 if region else 512) if preview is not None else None,
                "label": label,
                "region": region,
            }
        )

    ctx = RunContext(
        progress=progress,
        is_cancelled=lambda: job["id"] in _cancel,
        resolve=models.resolve,
        preview_every=config.settings().previewEvery,
    )
    images = pipeline.run(copy.deepcopy(p), ctx)
    ctx.check()
    progress("save", 1, 1, None)
    items = [_save_image(img, p, i) for i, img in enumerate(images)]
    job["images"] = items
    job["status"] = "done"
    job["finishedAt"] = store.now_ms()
    hub.broadcast({"type": "done", "job": copy.deepcopy(job)})


def a1111_text(p: dict, seed: int) -> str:
    loras = "".join(f"<lora:{l['id']}:{l['weight']}>" for l in p.get("loras") or [])
    prompt = (p.get("prompt") or "") + (" " + loras if loras else "")
    return (
        f"{prompt}\nNegative prompt: {p.get('negative', '')}\n"
        f"Steps: {p.get('steps')}, Sampler: {p.get('sampler')}, Schedule type: {p.get('scheduler')}, "
        f"CFG scale: {p.get('cfg')}, Seed: {seed}, Size: {p.get('width')}x{p.get('height')}, "
        f"Model: {p.get('model')}, Clip skip: {p.get('clipSkip')}"
    )


def _save_image(img: Image.Image, p: dict, idx: int) -> dict:
    out = Path(config.settings().outputDir)
    thumbs = out / "thumbs"
    thumbs.mkdir(parents=True, exist_ok=True)
    seed = int(p["seed"]) + idx
    saved = copy.deepcopy(p)
    saved["seed"] = seed
    stack = saved.pop("stackId", None)
    stem = time.strftime("%Y%m%d-%H%M%S") + f"-{seed}-{uuid.uuid4().hex[:4]}"
    name = stem + ".png"
    info = PngInfo()
    info.add_text("somnia", json.dumps(saved))
    info.add_text("parameters", a1111_text(saved, seed))
    img.save(out / name, "PNG", pnginfo=info)
    th = img.convert("RGB")
    th.thumbnail((384, 384))
    th.save(thumbs / (stem + ".webp"), "WEBP", quality=80)
    item = {
        "id": stem,
        "url": f"/outputs/{name}",
        "thumbUrl": f"/outputs/thumbs/{stem}.webp",
        "width": img.width,
        "height": img.height,
        "seed": seed,
        "createdAt": store.now_ms(),
        "params": saved,
        "stackId": stack,
    }
    store.add_gallery(item)
    return item
