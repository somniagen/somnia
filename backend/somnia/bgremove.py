from __future__ import annotations

import logging
import threading

import cv2
import numpy as np
from PIL import Image

log = logging.getLogger(__name__)

# toonout: birefnet fine-tuned on anime (onnx export of joelseytre/toonout), isnet: skytnt anime-seg, smaller and faster
MODELS = {
    "toonout": {"repo": "sprited/birefnet-toonout-onnx", "file": "birefnet-toonout-fp16.onnx", "letterbox": False, "norm": True},
    "isnet": {"repo": "skytnt/anime-seg", "file": "isnetis.onnx", "letterbox": True, "norm": False},
}
DEFAULT = "toonout"
SIZE = 1024
MEAN = np.array([0.485, 0.456, 0.406], np.float32)
STD = np.array([0.229, 0.224, 0.225], np.float32)

_lock = threading.Lock()
_sessions: dict[tuple[str, bool], object] = {}


def model_name() -> str:
    from .config import settings

    name = settings().bgModel
    return name if name in MODELS else DEFAULT


def _model_path(name: str) -> str:
    from huggingface_hub import hf_hub_download

    from .engine.previews import HF_CACHE

    m = MODELS[name]
    try:
        return hf_hub_download(m["repo"], m["file"], cache_dir=str(HF_CACHE), local_files_only=True)
    except Exception:
        log.info("downloading background removal model %s", name)
        return hf_hub_download(m["repo"], m["file"], cache_dir=str(HF_CACHE))


def _session(name: str, cpu: bool = False):
    with _lock:
        s = _sessions.get((name, cpu))
        if s is not None:
            return s
        # one model resident at a time
        _sessions.clear()
        # torch ships the cuda/cudnn dlls onnxruntime needs, so load it first
        import torch  # noqa: F401
        import onnxruntime as ort

        providers = ["CPUExecutionProvider"]
        if not cpu and "CUDAExecutionProvider" in ort.get_available_providers():
            if hasattr(ort, "preload_dlls"):
                try:
                    ort.preload_dlls()
                except Exception:
                    pass
            providers.insert(0, ("CUDAExecutionProvider", {"arena_extend_strategy": "kSameAsRequested"}))
        opts = ort.SessionOptions()
        opts.log_severity_level = 3
        path = _model_path(name)
        try:
            s = ort.InferenceSession(path, opts, providers=providers)
        except Exception as e:
            if cpu:
                raise
            log.warning("cuda session failed (%s), using cpu", e)
            s = ort.InferenceSession(path, opts, providers=["CPUExecutionProvider"])
        _sessions[(name, cpu)] = s
        return s


def _predict(rgb: np.ndarray, cpu: bool, name: str) -> np.ndarray:
    m = MODELS[name]
    if m["letterbox"]:
        return _predict_letterbox(rgb, cpu, name)
    # plain resize with imagenet normalization like birefnet, returns a float mask at the input size
    h0, w0 = rgb.shape[:2]
    x = cv2.resize(rgb, (SIZE, SIZE), interpolation=cv2.INTER_AREA)
    if m["norm"]:
        x = (x - MEAN) / STD
    s = _session(name, cpu)
    out = s.run(None, {s.get_inputs()[0].name: x.transpose(2, 0, 1)[None].astype(np.float32)})[0][0, 0]
    return np.clip(cv2.resize(out.astype(np.float32), (w0, h0), interpolation=cv2.INTER_CUBIC), 0, 1)


def _predict_letterbox(rgb: np.ndarray, cpu: bool, name: str) -> np.ndarray:
    # letterboxes to SIZE x SIZE like anime-seg, returns a float mask at the input size
    h0, w0 = rgb.shape[:2]
    h, w = (SIZE, max(1, round(SIZE * w0 / h0))) if h0 > w0 else (max(1, round(SIZE * h0 / w0)), SIZE)
    ph, pw = SIZE - h, SIZE - w
    x = np.zeros((SIZE, SIZE, 3), np.float32)
    x[ph // 2 : ph // 2 + h, pw // 2 : pw // 2 + w] = cv2.resize(rgb, (w, h), interpolation=cv2.INTER_AREA)
    s = _session(name, cpu)
    out = s.run(None, {s.get_inputs()[0].name: x.transpose(2, 0, 1)[None]})[0][0, 0]
    out = out[ph // 2 : ph // 2 + h, pw // 2 : pw // 2 + w]
    return np.clip(cv2.resize(out, (w0, h0), interpolation=cv2.INTER_CUBIC), 0, 1)


def _guided(guide: np.ndarray, src: np.ndarray, r: int, eps: float) -> np.ndarray:
    # color guided filter (he et al.) so the upsampled mask snaps to full res edges
    k = (2 * r + 1, 2 * r + 1)
    def box(a):
        return cv2.boxFilter(a, -1, k, borderType=cv2.BORDER_REFLECT)

    mi = box(guide)
    mp = box(src)
    cov = box(guide * src[..., None]) - mi * mp[..., None]
    var = np.empty(guide.shape[:2] + (3, 3), np.float32)
    for a in range(3):
        for b in range(a, 3):
            v = box(guide[..., a] * guide[..., b]) - mi[..., a] * mi[..., b]
            var[..., a, b] = var[..., b, a] = v
    var += np.eye(3, dtype=np.float32) * eps
    coef = np.linalg.solve(var, cov[..., None])[..., 0]
    off = mp - (coef * mi).sum(-1)
    return (box(coef) * guide).sum(-1) + box(off)


def _foreground(img: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    # blur fusion foreground estimation strips background color from soft edges
    f, b = img, img
    a = alpha[..., None]
    for r in (90, 6):
        ba = cv2.blur(alpha, (r, r))[..., None]
        bf = cv2.blur(f * a, (r, r)) / (ba + 1e-5)
        bb = cv2.blur(b * (1 - a), (r, r)) / ((1 - ba) + 1e-5)
        f = np.clip(bf + a * (img - a * bf - (1 - a) * bb), 0, 1)
        b = bb
    return f


def remove_background(img: Image.Image, cpu: bool = False, model: str | None = None) -> Image.Image:
    name = model if model in MODELS else model_name()
    rgb = np.asarray(img.convert("RGB"), np.float32) / 255
    mask = _predict(rgb, cpu, name)
    # refine on a capped working size to keep the 3x3 solve cheap on big upscales
    h, w = mask.shape
    k = min(1.0, 2048 / max(h, w))
    small = (max(1, round(w * k)), max(1, round(h * k)))
    g = cv2.resize(rgb, small, interpolation=cv2.INTER_AREA) if k < 1 else rgb
    m = cv2.resize(mask, small, interpolation=cv2.INTER_AREA) if k < 1 else mask
    r = max(2, round(max(small) / 512))
    ref = np.clip(_guided(g, m, r, 1e-4), 0, 1)
    # keep the model's confident interior and exterior, let the filter decide only near edges
    edge = ((m > 0.02) & (m < 0.98)).astype(np.uint8)
    edge = cv2.dilate(edge, np.ones((2 * r + 1, 2 * r + 1), np.uint8)).astype(bool)
    m = np.where(edge, ref, m)
    if k < 1:
        m = cv2.resize(m, (w, h), interpolation=cv2.INTER_CUBIC)
    # crush the faint haze and near-solid speckle the network leaves
    m = np.clip((m - 0.04) / 0.92, 0, 1)
    fg = _foreground(rgb, m.astype(np.float32))
    out = np.dstack([fg, m]) * 255
    return Image.fromarray(np.round(out).astype(np.uint8), "RGBA")


def release() -> None:
    with _lock:
        _sessions.clear()
