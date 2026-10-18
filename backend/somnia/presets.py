from __future__ import annotations

import re

SDXL_BUCKETS: list[tuple[int, int]] = [
    (1024, 1024),
    (1024, 1536),
    (896, 1152),
    (832, 1216),
    (768, 1344),
    (640, 1536),
    (1152, 896),
    (1216, 832),
    (1344, 768),
    (1536, 640),
]

ILLUSTRIOUS_SAMPLERS = ["euler_a", "euler", "dpmpp_2m", "dpmpp_2m_sde", "dpmpp_3m_sde", "dpmpp_sde", "uni_pc", "heun", "ddim", "lcm"]
ILLUSTRIOUS_SCHEDULERS = ["normal", "karras", "exponential", "sgm_uniform", "simple", "beta"]
ANIMA_SAMPLERS = ["er_sde", "euler_a", "euler", "dpmpp_2m"]
ANIMA_SCHEDULERS = ["simple", "normal", "karras", "beta"]


def _models(kind: str) -> list[dict]:
    try:
        from . import models

        return models.list_models(kind)
    except Exception:
        return []


def _vkey(name: str):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", name.lower())]


def _pick(kind: str, needles: list[str], family: str | None = None, exclude: list[str] | None = None) -> str:
    items = _models(kind)
    for n in needles:
        hits = [
            m
            for m in items
            if n in m["name"].lower()
            and (family is None or m.get("family") in (None, family))
            and not any(x in m["name"].lower() for x in exclude or [])
        ]
        if hits:
            hits.sort(key=lambda m: _vkey(m["name"]))
            return hits[-1]["id"]
    return ""


def _pick_family(kind: str, family: str) -> str:
    items = [m for m in _models(kind) if m.get("family") == family]
    return items[0]["id"] if items else ""


def _upscaler(prefer: list[str]) -> str:
    return _pick("upscaler", prefer) or "latent"


def _face_detector() -> str:
    return _pick("detector", ["face_yolov8m", "face_yolov8", "face"]) or "detector:bbox/face_yolov8m.pt"


def _detailer(prompt: str = "") -> dict:
    return {
        "enabled": False,
        "detector": _face_detector(),
        "prompt": prompt,
        "negative": "",
        "confidence": 0.3,
        "dilate": 4,
        "blur": 6,
        "denoise": 0.4,
        "steps": 20,
        "padding": 48,
        "appendPrompt": False,
    }


def illustrious_defaults() -> dict:
    model = _pick("checkpoint", ["waiillustrious", "wai-illustrious", "wai_illustrious"], "illustrious") or _pick_family(
        "checkpoint", "illustrious"
    )
    hires = _upscaler(["x4plusanime", "animesharp", "anime6b", "ultrasharp"])
    return {
        "family": "illustrious",
        "model": model,
        "vae": None,
        "textEncoder": None,
        "prompt": "masterpiece, best quality, amazing quality, ",
        "negative": "bad quality, worst quality, worst detail, sketch, censor, ",
        "width": 1024,
        "height": 1536,
        "steps": 28,
        "cfg": 6.0,
        "sampler": "euler_a",
        "scheduler": "normal",
        "seed": -1,
        "clipSkip": 2,
        "batchSize": 1,
        "loras": [],
        "pag": {"enabled": False, "scale": 3.0},
        "cfgRescale": 0.0,
        "secondPass": {
            "enabled": False,
            "upscaler": hires,
            "scale": 1.5,
            "steps": 15,
            "denoise": 0.35,
            "cfg": None,
            "sampler": None,
            "scheduler": None,
            "model": None,
        },
        "detailers": [_detailer()],
        "upscale": {
            "enabled": False,
            "upscaler": _upscaler(["animesharp", "ultrasharp", "anime6b"]),
            "scale": 2.0,
            "tiled": {"enabled": False, "denoise": 0.3, "steps": 20, "tileSize": 1024, "padding": 64},
        },
        "variation": {"enabled": False, "seed": -1, "strength": 0.1},
        "init": None,
    }


def anima_defaults() -> dict:
    model = _pick("checkpoint", ["animayume"], "anima") or _pick_family("checkpoint", "anima")
    te = _pick_family("text_encoder", "anima")
    vae = _pick("vae", ["qwen_image_vae", "qwen-image-vae", "qwen_image", "wan_2.1_vae", "wan2.1"])
    d = illustrious_defaults()
    d.update(
        {
            "family": "anima",
            "model": model,
            "vae": vae or None,
            "textEncoder": te or None,
            "prompt": "masterpiece, best quality, ",
            "negative": "worst quality, low quality, blurry, jpeg artifacts, bad anatomy, bad hands, watermark, text",
            "width": 896,
            "height": 1152,
            "steps": 30,
            "cfg": 4.5,
            "sampler": "er_sde",
            "scheduler": "simple",
            "clipSkip": 1,
            "pag": {"enabled": False, "scale": 2.0},
        }
    )
    d["secondPass"] = dict(d["secondPass"], steps=15, denoise=0.35)
    return d


def _anima_lists() -> tuple[list[str], list[str]]:
    try:
        from .engine.anima import AnimaEngine

        e = AnimaEngine()
        return e.samplers(), e.schedulers()
    except Exception:
        return ANIMA_SAMPLERS, ANIMA_SCHEDULERS


def presets() -> dict:
    a_s, a_sch = _anima_lists()
    res = [list(r) for r in SDXL_BUCKETS]
    return {
        "families": {
            "illustrious": {
                "family": "illustrious",
                "defaults": illustrious_defaults(),
                "samplers": ILLUSTRIOUS_SAMPLERS,
                "schedulers": ILLUSTRIOUS_SCHEDULERS,
                "resolutions": res,
            },
            "anima": {
                "family": "anima",
                "defaults": anima_defaults(),
                "samplers": a_s,
                "schedulers": a_sch,
                "resolutions": res,
            },
        }
    }
