from __future__ import annotations

import copy
import itertools
import json
import random
import threading
import time
import uuid
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from PIL.PngImagePlugin import PngInfo

from . import config, jobs, store
from .hub import hub

MAX_CELLS = 500
FINISHED = {"done", "error", "cancelled"}
# a queued cell whose job vanished (removed from the queue, server restart) counts as cancelled after this
MISSING_SEC = 3.0

_lock = threading.RLock()
_active: dict[str, dict] = {}
_missing: dict[str, float] = {}
_started = False


def start() -> None:
    global _started
    if _started:
        return
    _started = True
    for g in store.list_grids(200):
        if g["status"] in ("running", "composing"):
            g["status"] = "running"
            _active[g["id"]] = g
    jobs.on_finish.append(_on_finish)
    threading.Thread(target=_watch, name="somnia-grids", daemon=True).start()


def recent(n: int = 20) -> list[dict]:
    return store.list_grids(n)


def get(gid: str) -> dict | None:
    with _lock:
        g = _active.get(gid)
        return copy.deepcopy(g) if g else store.get_grid(gid)


def create(base: dict, axes: list[dict]) -> dict:
    if not isinstance(base, dict):
        raise ValueError("base params required")
    if not isinstance(axes, list) or not 1 <= len(axes) <= 3:
        raise ValueError("1 to 3 axes required")
    clean = []
    for a in axes:
        vals = [v for v in (a.get("values") or []) if isinstance(v, dict)]
        if not vals:
            raise ValueError(f"axis {a.get('label') or a.get('kind')} has no values")
        clean.append({"kind": str(a.get("kind", "")), "label": str(a.get("label", "")), "values": [
            {"label": str(v.get("label", "")), "patch": v.get("patch") or {}} for v in vals
        ]})
    sizes = [len(a["values"]) for a in clean] + [1] * (3 - len(clean))
    total = sizes[0] * sizes[1] * sizes[2]
    if total > MAX_CELLS:
        raise ValueError(f"{total} cells, the limit is {MAX_CELLS}")

    base = copy.deepcopy(base)
    base.pop("stackId", None)
    base["batchSize"] = 1
    if any("variation" in v["patch"] for a in clean for v in a["values"]):
        var = dict(base.get("variation") or {"enabled": False, "strength": 0.0})
        if int(var.get("seed", -1)) < 0:
            var["seed"] = random.randint(0, 2**32 - 1)
        base["variation"] = var

    gid = uuid.uuid4().hex[:12]
    cells, meta = [], []
    for z, y, x in itertools.product(range(sizes[2]), range(sizes[1]), range(sizes[0])):
        vals = [clean[i]["values"][(x, y, z)[i]] for i in range(len(clean))]
        cells.append({"x": x, "y": y, "z": z, "jobId": None, "status": "queued", "item": None, "error": None})
        meta.append({"grid": {"id": gid, "x": x, "y": y, "z": z}, "patch": _cell_patch(base, vals)})
    grid = {
        "id": gid,
        "createdAt": store.now_ms(),
        "finishedAt": None,
        "status": "running",
        "base": base,
        "axes": clean,
        "cells": cells,
        "images": [],
    }
    with _lock:
        _active[gid] = grid
        ids = jobs.submit(base, meta=meta)
        for c, jid in zip(cells, ids):
            c["jobId"] = jid
        _changed(grid)
        return copy.deepcopy(grid)


def delete(gid: str) -> bool:
    with _lock:
        g = _active.pop(gid, None) or store.get_grid(gid)
        if g is None:
            return False
        store.delete_grid(gid)
    jobs.cancel_where(lambda j: (j.get("grid") or {}).get("id") == gid)
    hub.broadcast({"type": "grid_removed", "id": gid})
    return True


def _cell_patch(base: dict, vals: list[dict]) -> dict:
    # "$sr": [search, replace] edits the prompts, "$lora": {id, weight} sets one lora weight
    patch: dict = {}
    srs, loras = [], []
    for v in vals:
        p = copy.deepcopy(v["patch"])
        if "$sr" in p:
            srs.append(p.pop("$sr"))
        if "$lora" in p:
            loras.append(p.pop("$lora"))
        patch = jobs._merge(patch, p)
    if srs:
        prompt = patch.get("prompt", base.get("prompt") or "")
        neg = patch.get("negative", base.get("negative") or "")
        segs = copy.deepcopy(patch.get("segments", base.get("segments")))
        for s, r in srs:
            s, r = str(s), str(r)
            if not s:
                continue
            prompt, neg = prompt.replace(s, r), neg.replace(s, r)
            for seg in (segs or {}).get("positive", []) + (segs or {}).get("negative", []):
                seg["text"] = seg.get("text", "").replace(s, r)
        patch["prompt"], patch["negative"] = prompt, neg
        if segs:
            patch["segments"] = segs
    if loras:
        ls = copy.deepcopy(patch.get("loras", base.get("loras") or []))
        for l in loras:
            hit = next((x for x in ls if x.get("id") == l.get("id")), None)
            if hit:
                hit["weight"] = l.get("weight", 1.0)
            else:
                ls.append({"id": l.get("id"), "weight": l.get("weight", 1.0)})
        patch["loras"] = ls
    return patch


def _changed(grid: dict) -> None:
    store.save_grid(grid)
    hub.broadcast({"type": "grid", "grid": copy.deepcopy(grid)})
    if grid["status"] == "running" and all(c["status"] in FINISHED for c in grid["cells"]):
        grid["status"] = "composing"
        threading.Thread(target=_finalize, args=(grid,), name=f"grid-{grid['id']}", daemon=True).start()


def _on_finish(job: dict, drained: bool) -> None:
    gid = (job.get("grid") or {}).get("id")
    if not gid:
        return
    with _lock:
        grid = _active.get(gid)
        cell = next((c for c in grid["cells"] if c["jobId"] == job["id"]), None) if grid else None
        if cell is None:
            return
        cell["status"] = job["status"]
        cell["error"] = job.get("error")
        cell["item"] = job["images"][0] if job.get("images") else None
        _missing.pop(job["id"], None)
        if grid["status"] == "running":
            _changed(grid)


def _watch() -> None:
    while True:
        time.sleep(1.0)
        try:
            with _lock:
                if not _active:
                    continue
                live = {j["id"] for j in jobs.queue_list()}
                now = time.monotonic()
                for g in list(_active.values()):
                    if g["status"] != "running":
                        continue
                    hit = False
                    for c in g["cells"]:
                        if c["status"] in FINISHED or c["jobId"] in live:
                            _missing.pop(c["jobId"], None)
                            continue
                        first = _missing.setdefault(c["jobId"], now)
                        if now - first >= MISSING_SEC:
                            c["status"] = "cancelled"
                            _missing.pop(c["jobId"], None)
                            hit = True
                    if hit:
                        _changed(g)
        except Exception as e:
            print(f"[somnia] grid watcher failed: {e}")


def _finalize(grid: dict) -> None:
    try:
        images = _compose_all(grid)
    except Exception as e:
        print(f"[somnia] grid compose failed: {e}")
        images = []
    with _lock:
        if _active.get(grid["id"]) is not grid:
            return
        grid["images"] = images
        grid["status"] = "done" if images else "failed"
        grid["finishedAt"] = store.now_ms()
        _active.pop(grid["id"], None)
        _changed(grid)
    for it in images:
        hub.broadcast({"type": "gallery_item", "item": store.get_gallery(it["id"]) or it})


def _font(size: int):
    for name in ("segoeui.ttf", "arial.ttf", "Helvetica.ttc", "DejaVuSans.ttf", "LiberationSans-Regular.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _fit_line(draw: ImageDraw.ImageDraw, text: str, font, width: int) -> str:
    if draw.textlength(text, font=font) <= width:
        return text
    while text and draw.textlength(text + "...", font=font) > width:
        text = text[:-1]
    return text + "..."


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, width: int, max_lines: int = 3) -> list[str]:
    lines: list[str] = []
    cur = ""
    for w in text.split():
        t = f"{cur} {w}".strip()
        if not cur or draw.textlength(t, font=font) <= width:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] += " ..."
    return [_fit_line(draw, l, font, width) for l in lines] or [""]


def _label(axis: dict | None, i: int) -> str:
    if not axis:
        return ""
    v = axis["values"][i]["label"]
    return f"{axis['label']}: {v}" if axis["label"] else v


def _open(item: dict) -> Image.Image | None:
    f = Path(config.settings().outputDir) / item["url"].removeprefix("/outputs/").split("?")[0]
    try:
        with Image.open(f) as im:
            return im.convert("RGB")
    except OSError:
        return None


def _compose_all(grid: dict) -> list[dict]:
    axes = grid["axes"]
    nz = len(axes[2]["values"]) if len(axes) > 2 else 1
    out = []
    for z in range(nz):
        cells = [c for c in grid["cells"] if c["z"] == z]
        done = [c for c in cells if c["item"]]
        if not done:
            continue
        img = compose(grid, z)
        item = _save(img, grid, z, done[0]["item"])
        store.stack_under(item["id"], [c["item"]["id"] for c in done])
        out.append(store.get_gallery(item["id"]) or item)
    return out


def compose(grid: dict, z: int) -> Image.Image:
    axes = grid["axes"]
    ax = axes[0]
    ay = axes[1] if len(axes) > 1 else None
    az = axes[2] if len(axes) > 2 else None
    nx, ny = len(ax["values"]), len(ay["values"]) if ay else 1
    imgs: dict[tuple[int, int], Image.Image | None] = {}
    status: dict[tuple[int, int], str] = {}
    for c in grid["cells"]:
        if c["z"] != z:
            continue
        imgs[(c["x"], c["y"])] = _open(c["item"]) if c["item"] else None
        status[(c["x"], c["y"])] = c["status"]
    got = [i for i in imgs.values() if i is not None]
    cw = max((i.width for i in got), default=int(grid["base"].get("width") or 512))
    ch = max((i.height for i in got), default=int(grid["base"].get("height") or 512))
    s = min(1.0, 12000 / (cw * nx), 12000 / (ch * ny))
    cw, ch = max(64, int(cw * s)), max(64, int(ch * s))

    fs = max(16, min(64, cw // 15))
    font = _font(fs)
    small = _font(max(12, fs * 3 // 4))
    pad = fs // 2
    lh = int(fs * 1.3)
    gap = max(2, cw // 160)
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))

    xl = [_wrap(probe, _label(ax, i), font, cw - 2 * pad) for i in range(nx)]
    head = max(len(l) for l in xl) * lh + 2 * pad
    left = 0
    yl: list[list[str]] = []
    if ay:
        left = max(fs * 8, min(cw, cw * 3 // 5))
        yl = [_wrap(probe, _label(ay, j), font, left - 2 * pad, 6) for j in range(ny)]
    title = lh + 2 * pad if az else 0

    W = left + nx * cw + (nx - 1) * gap
    H = title + head + ny * ch + (ny - 1) * gap
    bg, fg, muted, empty = (16, 16, 16), (236, 236, 236), (140, 140, 140), (34, 34, 34)
    im = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(im)
    if az:
        d.text((pad, pad), _fit_line(d, _label(az, z), font, W - 2 * pad), font=font, fill=fg)
    for i, lines in enumerate(xl):
        x0 = left + i * (cw + gap)
        y0 = title + head - pad - len(lines) * lh
        for k, line in enumerate(lines):
            d.text((x0 + cw / 2, y0 + k * lh), line, font=font, fill=fg, anchor="ma")
    for j, lines in enumerate(yl):
        y0 = title + head + j * (ch + gap) + ch / 2 - len(lines) * lh / 2
        for k, line in enumerate(lines):
            d.text((left - pad, y0 + k * lh), line, font=font, fill=fg, anchor="ra")
    for j in range(ny):
        for i in range(nx):
            x0 = left + i * (cw + gap)
            y0 = title + head + j * (ch + gap)
            cell = imgs.get((i, j))
            if cell is None:
                d.rectangle((x0, y0, x0 + cw - 1, y0 + ch - 1), fill=empty)
                d.text((x0 + cw / 2, y0 + ch / 2), status.get((i, j), "missing"), font=small, fill=muted, anchor="mm")
                continue
            cell.thumbnail((cw, ch), Image.LANCZOS)
            im.paste(cell, (x0 + (cw - cell.width) // 2, y0 + (ch - cell.height) // 2))
    return im


def _save(img: Image.Image, grid: dict, z: int, first: dict) -> dict:
    out = Path(config.settings().outputDir)
    thumbs = out / "thumbs"
    thumbs.mkdir(parents=True, exist_ok=True)
    params = copy.deepcopy(first.get("params") or grid["base"])
    stem = time.strftime("%Y%m%d-%H%M%S") + f"-grid-{grid['id'][:6]}-{z}-{uuid.uuid4().hex[:4]}"
    info = PngInfo()
    info.add_text("somnia", json.dumps(params))
    info.add_text("somnia-grid", json.dumps({"id": grid["id"], "axes": grid["axes"], "z": z}))
    img.save(out / f"{stem}.png", "PNG", pnginfo=info)
    th = img.copy()
    th.thumbnail((768, 768))
    th.save(thumbs / f"{stem}.webp", "WEBP", quality=82)
    item = {
        "id": stem,
        "url": f"/outputs/{stem}.png",
        "thumbUrl": f"/outputs/thumbs/{stem}.webp",
        "width": img.width,
        "height": img.height,
        "seed": first.get("seed", 0),
        "createdAt": store.now_ms(),
        "params": params,
        "stackId": None,
        "coverId": stem,
        "grid": {"id": grid["id"], "z": z},
    }
    store.add_gallery(item)
    return item
