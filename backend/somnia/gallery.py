from __future__ import annotations

import io
import json
import re
import shutil
import uuid
from pathlib import Path

from PIL import Image

from . import config


def uploads_dir() -> Path:
    d = config.DATA_DIR / "uploads"
    d.mkdir(parents=True, exist_ok=True)
    return d


def delete_files(item: dict) -> None:
    out = Path(config.settings().outputDir)
    for rel in (item["url"], item["thumbUrl"]):
        f = out / rel.removeprefix("/outputs/").split("?")[0]
        try:
            f.unlink(missing_ok=True)
        except OSError:
            pass


def _base_defaults(family: str) -> dict:
    try:
        from . import presets

        return dict(presets.presets()["families"][family]["defaults"])
    except Exception:
        return {
            "family": family,
            "model": "",
            "vae": None,
            "textEncoder": None,
            "prompt": "",
            "negative": "",
            "width": 1024,
            "height": 1024,
            "steps": 28,
            "cfg": 5.0,
            "sampler": "euler_a",
            "scheduler": "normal",
            "seed": -1,
            "clipSkip": 1,
            "batchSize": 1,
            "loras": [],
            "pag": {"enabled": False, "scale": 3.0},
            "cfgRescale": 0.0,
            "secondPass": {"enabled": False, "upscaler": "", "scale": 1.5, "steps": 20, "denoise": 0.5,
                           "cfg": None, "sampler": None, "scheduler": None, "model": None},
            "detailers": [],
            "upscale": {"enabled": False, "upscaler": "", "scale": 2.0},
            "init": None,
        }


def parse_a1111(text: str) -> dict | None:
    lines = text.strip().split("\n")
    idx = next((i for i, l in enumerate(lines) if l.startswith("Steps:")), None)
    if idx is None:
        return None
    neg_i = next((i for i, l in enumerate(lines) if l.startswith("Negative prompt:")), None)
    if neg_i is not None:
        prompt = "\n".join(lines[:neg_i]).strip()
        negative = "\n".join([lines[neg_i][len("Negative prompt:"):]] + lines[neg_i + 1:idx]).strip()
    else:
        prompt = "\n".join(lines[:idx]).strip()
        negative = ""
    kv = dict(re.findall(r"([A-Za-z ]+): ([^,]+)", lines[idx]))
    p = _base_defaults("illustrious")
    p["prompt"] = prompt
    p["negative"] = negative
    try:
        if "Steps" in kv:
            p["steps"] = int(kv["Steps"])
        if "CFG scale" in kv:
            p["cfg"] = float(kv["CFG scale"])
        if "Seed" in kv:
            p["seed"] = int(kv["Seed"])
        if "Size" in kv:
            w, h = kv["Size"].split("x")
            p["width"], p["height"] = int(w), int(h)
        if "Clip skip" in kv:
            p["clipSkip"] = int(kv["Clip skip"])
    except ValueError:
        pass
    if "Sampler" in kv:
        p["sampler"] = kv["Sampler"].strip()
    return p


def read_params(img: Image.Image) -> dict | None:
    info = img.info or {}
    if "somnia" in info:
        try:
            return json.loads(info["somnia"])
        except ValueError:
            pass
    if "parameters" in info:
        return parse_a1111(info["parameters"])
    return None


def upload_from_gallery(item: dict) -> dict:
    # copies a gallery image into uploads server side so clients need not round-trip the png
    url = item["url"].split("?")[0]
    if url.startswith("/outputs/"):
        src = Path(config.settings().outputDir) / url.removeprefix("/outputs/")
    else:
        src = uploads_dir() / url.removeprefix("/files/uploads/")
    if src.suffix.lower() != ".png":
        return save_upload(src.read_bytes())
    uid = uuid.uuid4().hex[:12]
    shutil.copyfile(src, uploads_dir() / f"{uid}.png")
    return {"id": uid, "url": f"/files/uploads/{uid}.png", "width": item["width"], "height": item["height"], "params": item.get("params")}


def save_upload(data: bytes) -> dict:
    img = Image.open(io.BytesIO(data))
    img.load()
    params = read_params(img)
    uid = uuid.uuid4().hex[:12]
    mode = "L" if img.mode in ("L", "1") else ("RGBA" if img.mode in ("RGBA", "LA", "P") else "RGB")
    img.convert(mode).save(uploads_dir() / f"{uid}.png", "PNG")
    return {"id": uid, "url": f"/files/uploads/{uid}.png", "width": img.width, "height": img.height, "params": params}
