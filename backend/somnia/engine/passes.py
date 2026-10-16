from __future__ import annotations

import gc
import threading
from pathlib import Path
from typing import Callable

import numpy as np
import torch
from PIL import Image

_lock = threading.Lock()
_cache: dict[str, object] = {}


def load_upscaler(path: Path):
    key = str(path)
    with _lock:
        m = _cache.get(key)
        if m is None:
            from spandrel import ModelLoader

            m = ModelLoader().load_from_file(key).eval()
            try:
                if m.supports_half:
                    m = m.half()
            except Exception:
                pass
            _cache.clear()
            _cache[key] = m
        return m


def unload() -> None:
    with _lock:
        _cache.clear()
    gc.collect()
    torch.cuda.empty_cache()


def release() -> None:
    from ..config import settings

    if not settings().keepModelsLoaded:
        unload()


@torch.no_grad()
def model_upscale(
    img: Image.Image,
    path: Path,
    tile: int = 0,
    overlap: int = 32,
    progress: Callable[[int, int], None] | None = None,
    check: Callable[[], None] | None = None,
    target: float | None = None,
) -> Image.Image:
    import torch.nn.functional as F

    m = load_upscaler(path)
    m.to("cuda")
    dtype = torch.float16 if getattr(m, "supports_half", False) else torch.float32
    s = int(m.scale)
    tile = tile or max(128, 1024 // max(1, s))
    so = min(float(s), float(target)) if target else float(s)
    x = torch.from_numpy(np.asarray(img.convert("RGB")).copy()).permute(2, 0, 1).unsqueeze(0)
    _, _, h, w = x.shape
    oh, ow = int(round(h * so)), int(round(w * so))
    out = torch.zeros((1, 3, oh, ow), dtype=torch.float32)
    wsum = torch.zeros((1, 1, oh, ow), dtype=torch.float32)
    step = tile - overlap
    ys = list(range(0, max(h - overlap, 1), step)) if h > tile else [0]
    xs = list(range(0, max(w - overlap, 1), step)) if w > tile else [0]
    total = len(ys) * len(xs)
    f = int(overlap * so // 2)
    ramp = torch.linspace(0.05, 1, f) if f > 0 else None
    k = 0
    try:
        for y in ys:
            for xx in xs:
                if check:
                    check()
                y0, x0 = min(y, max(0, h - tile)), min(xx, max(0, w - tile))
                y1, x1 = min(y0 + tile, h), min(x0 + tile, w)
                Y0, X0, Y1, X1 = int(round(y0 * so)), int(round(x0 * so)), int(round(y1 * so)), int(round(x1 * so))
                t = x[:, :, y0:y1, x0:x1].to("cuda").to(dtype).div_(255)
                r = m(t)
                del t
                if r.shape[-2:] != (Y1 - Y0, X1 - X0):
                    r = F.interpolate(r.float(), size=(Y1 - Y0, X1 - X0), mode="bicubic", antialias=True, align_corners=False)
                r = r.float().clamp_(0, 1).cpu()
                mask = torch.ones((1, 1, Y1 - Y0, X1 - X0))
                if ramp is not None:
                    if y0 > 0:
                        mask[:, :, :f, :] *= ramp.view(1, 1, -1, 1)
                    if y1 < h:
                        mask[:, :, -f:, :] *= ramp.flip(0).view(1, 1, -1, 1)
                    if x0 > 0:
                        mask[:, :, :, :f] *= ramp.view(1, 1, 1, -1)
                    if x1 < w:
                        mask[:, :, :, -f:] *= ramp.flip(0).view(1, 1, 1, -1)
                out[:, :, Y0:Y1, X0:X1] += r * mask
                wsum[:, :, Y0:Y1, X0:X1] += mask
                del r, mask
                k += 1
                if progress:
                    progress(k, total)
    finally:
        m.to("cpu")
        torch.cuda.empty_cache()
    out.div_(wsum.clamp_(min=1e-6)).clamp_(0, 1)
    del wsum
    arr = out[0].permute(1, 2, 0).mul_(255).round_().byte().numpy()
    return Image.fromarray(arr)


def upscale_to(
    img: Image.Image,
    upscaler: Path | None,
    scale: float,
    progress: Callable[[int, int], None] | None = None,
    check: Callable[[], None] | None = None,
    multiple: int = 8,
) -> Image.Image:
    tw = max(multiple, int(round(img.width * scale / multiple)) * multiple)
    th = max(multiple, int(round(img.height * scale / multiple)) * multiple)
    if upscaler is not None and scale > 1:
        img = model_upscale(img, upscaler, progress=progress, check=check, target=max(tw / img.width, th / img.height))
    elif progress:
        progress(1, 1)
    if img.size != (tw, th):
        img = img.resize((tw, th), Image.LANCZOS)
    return img
