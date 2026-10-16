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


def queue_list() -> list[dict]:
    with _cond:
        return copy.deepcopy(_jobs)


def _broadcast_queue() -> None:
    hub.broadcast({"type": "queue", "queue": queue_list()})


def submit(params: dict, count: int = 1) -> list[str]:
    count = max(1, int(count))
    base = int(params.get("seed", -1))
    ids = []
    with _cond:
        for i in range(count):
            p = copy.deepcopy(params)
            p["seed"] = random.randint(0, 2**32 - 1) if base == -1 else base + i
            jid = uuid.uuid4().hex[:12]
            ids.append(jid)
            _jobs.append(
                {
                    "id": jid,
                    "params": p,
                    "status": "queued",
                    "createdAt": store.now_ms(),
                    "startedAt": None,
                    "finishedAt": None,
                    "images": [],
                    "error": None,
                }
            )
        _cond.notify_all()
    _broadcast_queue()
    return ids


def cancel(jid: str) -> bool:
    with _cond:
        for j in _jobs:
            if j["id"] == jid:
                if j["status"] == "running":
                    _cancel.add(jid)
                else:
                    _jobs.remove(j)
                break
        else:
            return False
    _broadcast_queue()
    return True


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
            job = next((j for j in _jobs if j["status"] == "queued"), None)
            while job is None:
                _cond.wait()
                job = next((j for j in _jobs if j["status"] == "queued"), None)
            job["status"] = "running"
            job["startedAt"] = store.now_ms()
        _broadcast_queue()
        try:
            _run_job(job)
        except Exception as e:
            _fail(job, e)
        finally:
            with _cond:
                if job in _jobs:
                    _jobs.remove(job)
                _cancel.discard(job["id"])
            _broadcast_queue()


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


def _data_url(img: Image.Image) -> str:
    im = img.convert("RGB")
    im.thumbnail((512, 512))
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

    def progress(phase: str, step: int, total: int, preview: Image.Image | None = None, label: str | None = None) -> None:
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
                "preview": _data_url(preview) if preview is not None else None,
                "label": label,
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
