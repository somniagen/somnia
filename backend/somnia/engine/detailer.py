from __future__ import annotations

import math
import threading
from pathlib import Path
from typing import Callable

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

_lock = threading.Lock()
_models: dict[str, object] = {}


def load_detector(path: Path):
    key = str(path)
    with _lock:
        m = _models.get(key)
        if m is None:
            from ultralytics import YOLO

            m = YOLO(key)
            _models.clear()
            _models[key] = m
        return m


def unload() -> None:
    with _lock:
        _models.clear()
    try:
        import torch

        torch.cuda.empty_cache()
    except Exception:
        pass


def release() -> None:
    # yolo models are small and reload fast, never keep them on the gpu between phases
    unload()


def detect(img: Image.Image, path: Path, conf: float = 0.3) -> list[dict]:
    m = load_detector(path)
    img = img.convert("RGB")
    res = m.predict(img, conf=conf, verbose=False)
    out: list[dict] = []
    if not res:
        return out
    r = res[0]
    names = r.names or {}
    boxes = r.boxes
    polys = r.masks.xy if r.masks is not None else None
    for i in range(len(boxes)):
        x0, y0, x1, y1 = [float(v) for v in boxes.xyxy[i].tolist()]
        c = float(boxes.conf[i])
        label = names.get(int(boxes.cls[i]), str(int(boxes.cls[i])))
        mask = None
        if polys is not None and i < len(polys) and len(polys[i]) >= 3:
            mask = Image.new("L", img.size, 0)
            ImageDraw.Draw(mask).polygon([(float(p[0]), float(p[1])) for p in polys[i]], fill=255)
        out.append({"label": label, "confidence": c, "bbox": [x0, y0, x1, y1], "mask": mask})
    out.sort(key=lambda d: -d["confidence"])
    return out


def det_mask(size: tuple[int, int], d: dict) -> Image.Image:
    if d.get("mask") is not None:
        return d["mask"].convert("L")
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).rectangle([int(v) for v in d["bbox"]], fill=255)
    return m


def dilate(mask: Image.Image, px: int) -> Image.Image:
    if px == 0:
        return mask
    a = np.asarray(mask.convert("L"))
    k = np.ones((abs(px) * 2 + 1, abs(px) * 2 + 1), np.uint8)
    a = cv2.dilate(a, k) if px > 0 else cv2.erode(a, k)
    return Image.fromarray(a)


def masked_inpaint(
    img: Image.Image,
    mask: Image.Image,
    run: Callable[[Image.Image, Image.Image], Image.Image],
    padding: int = 32,
    blur: int = 4,
    target: int = 1024,
    base: Image.Image | None = None,
    on_box: Callable[[tuple[int, int, int, int], Image.Image], None] | None = None,
) -> Image.Image:
    img = img.convert("RGB")
    base = (base or img).convert("RGB")
    mask = mask.convert("L")
    bb = mask.point(lambda v: 255 if v > 127 else 0).getbbox()
    if bb is None:
        return img
    W, H = img.size
    x0, y0 = max(0, bb[0] - padding), max(0, bb[1] - padding)
    x1, y1 = min(W, bb[2] + padding), min(H, bb[3] + padding)
    bw, bh = x1 - x0, y1 - y0
    s = target / math.sqrt(bw * bh)
    tw = max(64, int(round(bw * s / 8)) * 8)
    th = max(64, int(round(bh * s / 8)) * 8)
    box = (x0, y0, x1, y1)
    crop = img.crop(box).resize((tw, th), Image.LANCZOS)
    cm = mask.crop(box).resize((tw, th), Image.LANCZOS)
    feather = mask.crop(box)
    if blur > 0:
        feather = feather.filter(ImageFilter.GaussianBlur(blur))
    if on_box is not None:
        on_box(box, feather)
    res = run(crop, cm).convert("RGB").resize((bw, bh), Image.LANCZOS)
    out = base.copy()
    out.paste(Image.composite(res, base.crop(box), feather), box)
    return out
