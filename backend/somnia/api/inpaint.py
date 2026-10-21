from __future__ import annotations

import asyncio
import gc
import re
import threading
import uuid

import numpy as np
from fastapi import APIRouter, HTTPException
from PIL import Image
from pydantic import BaseModel

from .. import config, models

router = APIRouter(prefix="/api", tags=["inpaint"])

_lock = threading.Lock()
_cache: dict[str, object] = {}
_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class DetectReq(BaseModel):
    imageId: str
    detector: str
    confidence: float = 0.3


def _uploads():
    d = config.DATA_DIR / "uploads"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _yolo(path: str):
    m = _cache.get(path)
    if m is None:
        from ultralytics import YOLO

        m = YOLO(path)
        if len(_cache) >= 3:
            _cache.pop(next(iter(_cache)))
        _cache[path] = m
    return m


def _device() -> str | int:
    try:
        from ..engine import device

        if device.is_cuda() and device.free_memory() > 1.5 * 1024**3:
            return 0
        if device.is_mps():
            return "mps"
    except Exception:
        pass
    return "cpu"


def _release(m) -> None:
    try:
        from ..engine import device

        m.predictor = None
        m.to("cpu")
        gc.collect()
        device.empty_cache()
    except Exception:
        pass


def _detect(image_id: str, detector: str, conf: float) -> list[dict]:
    src = _uploads() / f"{image_id}.png"
    if not src.is_file():
        raise HTTPException(404, "image not found")
    try:
        path = models.resolve(detector)
    except Exception:
        raise HTTPException(404, "detector not found")
    img = Image.open(src)
    img.load()
    img = img.convert("RGB")
    with _lock:
        m = _yolo(str(path))
        dev = _device()
        try:
            res = m.predict(img, conf=conf, verbose=False, retina_masks=True, device=dev)
            r = res[0].cpu() if res else None
            del res
        finally:
            if dev != "cpu":
                _release(m)
    if r is None:
        return []
    names = r.names or {}
    boxes = r.boxes
    masks = r.masks.data.numpy() if r.masks is not None else None
    out: list[dict] = []
    for i in range(len(boxes)):
        x0, y0, x1, y1 = [float(v) for v in boxes.xyxy[i].tolist()]
        cls = int(boxes.cls[i])
        url = None
        if masks is not None and i < len(masks):
            a = masks[i]
            mk = Image.fromarray(((a > 0.5) * 255).astype(np.uint8), "L")
            if mk.size != img.size:
                mk = mk.resize(img.size, Image.BILINEAR)
            uid = uuid.uuid4().hex[:12]
            mk.save(_uploads() / f"{uid}.png", "PNG")
            url = f"/files/uploads/{uid}.png"
        out.append({
            "label": str(names.get(cls, cls)),
            "confidence": float(boxes.conf[i]),
            "bbox": [x0, y0, x1, y1],
            "maskUrl": url,
        })
    out.sort(key=lambda d: -d["confidence"])
    return out


@router.post("/detect")
async def detect(req: DetectReq) -> list[dict]:
    if not _ID.match(req.imageId):
        raise HTTPException(400, "bad image id")
    conf = min(max(req.confidence, 0.01), 0.99)
    return await asyncio.to_thread(_detect, req.imageId, req.detector, conf)


@router.get("/detectors")
async def detectors() -> list[dict]:
    return await asyncio.to_thread(models.list_models, "detector")
