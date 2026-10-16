from __future__ import annotations

import json
import re
import shutil
import struct
import threading
import time
from pathlib import Path

from .config import DATA_DIR, settings

CACHE_FILE = DATA_DIR / "models_cache.json"
TRASH_DIR = DATA_DIR / "trash"

KIND_FOLDERS: dict[str, list[str]] = {
    "checkpoint": ["checkpoints", "unet", "diffusion_models"],
    "lora": ["loras"],
    "vae": ["vae"],
    "text_encoder": ["text_encoders"],
    "upscaler": ["upscale_models"],
    "detector": ["ultralytics"],
}
EXTS = {".safetensors", ".ckpt", ".pt", ".pth", ".gguf"}
PREVIEW_EXTS = [".preview.png", ".preview.jpeg", ".preview.jpg", ".preview.webp", ".png", ".jpeg", ".jpg", ".webp"]

_lock = threading.RLock()
_models: dict[str, dict] | None = None
_paths: dict[str, Path] = {}
_cache: dict | None = None
_cache_dirty = False


def _load_cache() -> dict:
    global _cache
    if _cache is None:
        try:
            _cache = json.loads(CACHE_FILE.read_text("utf-8"))
        except Exception:
            _cache = {}
    return _cache


def _save_cache() -> None:
    global _cache_dirty
    if _cache is not None and _cache_dirty:
        try:
            CACHE_FILE.write_text(json.dumps(_cache), "utf-8")
            _cache_dirty = False
        except OSError:
            pass


def read_header(path: Path) -> dict | None:
    try:
        with open(path, "rb") as f:
            raw = f.read(8)
            if len(raw) < 8:
                return None
            n = struct.unpack("<Q", raw)[0]
            if n <= 0 or n > 200_000_000:
                return None
            return json.loads(f.read(n))
    except Exception:
        return None


_SDXL_LORA_UNET = re.compile(r"lora_unet_(input_blocks|middle_block|output_blocks)_")
_SDXL_LORA_DIFFUSERS = re.compile(r"lora_unet_(down_blocks|up_blocks|mid_block)_")
_ANIMA_KEYS = ("llm_adapter", "diffusion_model.blocks", "lora_unet_blocks_", "net.blocks.", "transformer.blocks.")


def _ctx_dim(h: dict, keys: list[str]) -> int | None:
    for k in keys:
        if "attn2_to_k.lora_down" in k or "attn2.to_k.lora_A" in k or "attn2.to_k.lora_down" in k:
            shp = h[k].get("shape") if isinstance(h[k], dict) else None
            if shp and len(shp) == 2:
                return shp[1]
    return None


def _family_from_header(h: dict, kind: str) -> str | None:
    keys = [k for k in h if k != "__metadata__"]
    if not keys:
        return None
    sample = keys[:4000]
    if any(any(a in k for a in _ANIMA_KEYS) for k in sample):
        return "anima"
    if any("llm_adapter" in k for k in keys):
        return "anima"
    if kind == "lora":
        if any(k.startswith(("lora_te1_", "lora_te2_")) or ".text_encoder_2." in k or "text_encoder_2" in k for k in keys):
            return "illustrious"
        if any(_SDXL_LORA_UNET.match(k) for k in sample):
            return "illustrious"
        if any(_SDXL_LORA_DIFFUSERS.match(k) for k in sample):
            d = _ctx_dim(h, keys)
            if d == 2048:
                return "illustrious"
            if d == 768:
                return None
            return "illustrious" if any("transformer_blocks_1_" in k for k in sample) else None
        d = _ctx_dim(h, keys)
        if d == 2048:
            return "illustrious"
        return None
    if any(k.startswith("conditioner.") or "conditioner.embedders" in k for k in sample):
        return "illustrious"
    if any("model.diffusion_model.input_blocks" in k for k in sample):
        return "illustrious" if any("label_emb" in k for k in sample) else None
    if any("down_blocks" in k and "add_embedding" in k for k in sample) or any("add_embedding" in k for k in sample):
        return "illustrious"
    return None


def _family_from_base(base: str | None) -> str | None:
    if not base:
        return None
    b = base.lower()
    if "anima" in b:
        return "anima"
    if "illustrious" in b or "noobai" in b or "pony" in b or "sdxl" in b:
        return "illustrious"
    return None


def detect_family(path: Path | str, kind: str | None = None) -> str | None:
    p = Path(path)
    if p.suffix.lower() != ".safetensors":
        return None
    if kind is None:
        kind = "lora" if "lora" in p.parts[-3:-1] or any("lora" in x.lower() for x in p.parts[-3:-1]) else "checkpoint"
    h = read_header(p)
    if h is None:
        return None
    return _family_from_header(h, kind)


def _first_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text("utf-8"))
    except Exception:
        return None


def _info_from_version(v: dict, model: dict | None) -> dict | None:
    if not isinstance(v, dict) or "id" not in v:
        return None
    m = model or v.get("model") or {}
    return {
        "modelId": int(v.get("modelId") or m.get("id") or 0),
        "versionId": int(v["id"]),
        "name": str(m.get("name") or v.get("name") or ""),
        "versionName": str(v.get("name") or ""),
        "baseModel": str(v.get("baseModel") or ""),
        "trainedWords": [str(w) for w in (v.get("trainedWords") or [])],
        "nsfw": bool(m.get("nsfw")),
    }


def read_sidecar(path: Path) -> dict | None:
    stem = path.with_suffix("")
    ours = _first_json(Path(str(stem) + ".civitai.json"))
    if ours:
        v = ours.get("version") if isinstance(ours.get("version"), dict) else ours
        m = ours.get("model") if isinstance(ours.get("model"), dict) else None
        info = _info_from_version(v, m)
        if info:
            return info
    ci = _first_json(Path(str(stem) + ".civitai.info"))
    if ci:
        info = _info_from_version(ci, ci.get("model") if isinstance(ci.get("model"), dict) else None)
        if info:
            return info
    md = _first_json(Path(str(stem) + ".metadata.json"))
    if md:
        c = md.get("civitai")
        if isinstance(c, dict) and "id" in c:
            m = dict(c.get("model") or {})
            if md.get("model_name"):
                m["name"] = md["model_name"]
            if "id" not in m and c.get("modelId"):
                m["id"] = c["modelId"]
            info = _info_from_version(c, m)
            if info:
                if not info["baseModel"] and md.get("base_model"):
                    info["baseModel"] = str(md["base_model"])
                return info
        if md.get("model_name"):
            return {
                "modelId": 0,
                "versionId": 0,
                "name": str(md["model_name"]),
                "versionName": "",
                "baseModel": str(md.get("base_model") or ""),
                "trainedWords": [],
                "nsfw": False,
            }
    return None


def _find_preview(path: Path) -> Path | None:
    stem = str(path.with_suffix(""))
    for e in PREVIEW_EXTS:
        p = Path(stem + e)
        if p.exists():
            return p
    return None


def _kind_of_ext(kind: str, path: Path, rel: str) -> str | None:
    ext = path.suffix.lower()
    if ext not in EXTS:
        return None
    if kind == "detector":
        return kind if ext == ".pt" else None
    if ext == ".gguf":
        return None
    if kind in ("upscaler",):
        return kind
    if kind in ("checkpoint", "lora", "vae", "text_encoder"):
        return kind if ext in (".safetensors", ".ckpt", ".pt", ".pth") else None
    return None


def _display_name(kind: str, rel: str) -> str:
    p = Path(rel)
    name = p.stem
    if kind == "detector":
        parts = p.parts
        sub = parts[-2] if len(parts) > 1 else ""
        if sub in ("bbox", "segm"):
            return f"{name} ({sub})"
    return name


def _scan() -> tuple[dict[str, dict], dict[str, Path]]:
    cache = _load_cache()
    global _cache_dirty
    out: dict[str, dict] = {}
    paths: dict[str, Path] = {}
    seen_cache_keys: set[str] = set()
    roots: list[str] = []
    for root in [*settings().modelRoots, settings().downloadRoot]:
        if root and root not in roots:
            roots.append(root)
    for root in roots:
        rootp = Path(root)
        if not rootp.is_dir():
            continue
        for kind, folders in KIND_FOLDERS.items():
            for folder in folders:
                base = rootp / folder
                if not base.is_dir():
                    continue
                for p in base.rglob("*"):
                    try:
                        if not p.is_file():
                            continue
                        if _kind_of_ext(kind, p, "") is None:
                            continue
                        rel = p.relative_to(base).as_posix()
                        if kind == "detector":
                            rel = p.relative_to(base).as_posix()
                        mid = f"{kind}:{rel}"
                        if mid in out:
                            continue
                        st = p.stat()
                    except OSError:
                        continue
                    key = str(p)
                    seen_cache_keys.add(key)
                    ent = cache.get(key)
                    if not ent or ent.get("mtime") != st.st_mtime or ent.get("size") != st.st_size:
                        fam = None
                        if p.suffix.lower() == ".safetensors" and kind in ("checkpoint", "lora", "vae", "text_encoder"):
                            h = read_header(p)
                            fam = _family_from_header(h, kind) if h is not None and kind in ("checkpoint", "lora") else None
                        ent = {"mtime": st.st_mtime, "size": st.st_size, "family": fam}
                        cache[key] = ent
                        _cache_dirty = True
                    civ = read_sidecar(p)
                    fam = ent.get("family")
                    if fam is None and civ and kind in ("checkpoint", "lora"):
                        fam = _family_from_base(civ.get("baseModel"))
                    prev = _find_preview(p)
                    out[mid] = {
                        "id": mid,
                        "kind": kind,
                        "family": fam,
                        "name": _display_name(kind, rel),
                        "path": str(p),
                        "size": st.st_size,
                        "mtime": st.st_mtime,
                        "previewUrl": f"/api/models/preview/{mid}" if prev else None,
                        "civitai": civ,
                    }
                    paths[mid] = p
    stale = [k for k in cache if k not in seen_cache_keys and not k.startswith("sha:")]
    if stale:
        for k in stale:
            del cache[k]
        _cache_dirty = True
    _save_cache()
    return out, paths


def rescan() -> list[dict]:
    global _models, _paths
    with _lock:
        _models, _paths = _scan()
        return list(_models.values())


def _ensure() -> dict[str, dict]:
    global _models
    with _lock:
        if _models is None:
            rescan()
        return _models or {}


def list_models(kind: str | None = None) -> list[dict]:
    ms = _ensure()
    items = [m for m in ms.values() if kind is None or m["kind"] == kind]
    items.sort(key=lambda m: (m["kind"], m["name"].lower()))
    return items


def get(model_id: str) -> dict | None:
    return _ensure().get(model_id)


def resolve(model_id: str) -> Path:
    _ensure()
    p = _paths.get(model_id)
    if p is not None and p.exists():
        return p
    if ":" in model_id:
        kind, rel = model_id.split(":", 1)
        for root in settings().modelRoots + [settings().downloadRoot]:
            for folder in KIND_FOLDERS.get(kind, []):
                c = Path(root) / folder / rel
                if c.exists():
                    return c
    raise FileNotFoundError(f"model not found: {model_id}")


def preview_path(model_id: str) -> Path | None:
    try:
        return _find_preview(resolve(model_id))
    except FileNotFoundError:
        return None


def installed_by_version() -> dict[int, str]:
    out: dict[int, str] = {}
    for m in _ensure().values():
        c = m.get("civitai")
        if c and c.get("versionId"):
            out.setdefault(int(c["versionId"]), m["id"])
    return out


def trash(model_id: str) -> None:
    p = resolve(model_id)
    TRASH_DIR.mkdir(parents=True, exist_ok=True)
    stem = str(p.with_suffix(""))
    stamp = str(int(time.time()))
    sidecars = [".civitai.json", ".civitai.info", ".metadata.json", ".sha256"] + PREVIEW_EXTS
    for f in [p] + [Path(stem + e) for e in sidecars]:
        if f.exists():
            shutil.move(str(f), str(TRASH_DIR / f"{stamp}_{f.name}"))
    rescan()
