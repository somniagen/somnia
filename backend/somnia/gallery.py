from __future__ import annotations

import copy
import io
import json
import re
import shutil
import time
import uuid
import zipfile
from pathlib import Path

from PIL import Image
from PIL.PngImagePlugin import PngInfo

from . import config, store


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


_SAMPLERS = {
    "euler_a", "euler", "dpmpp_2m", "dpmpp_2m_sde", "dpmpp_3m_sde", "dpmpp_sde", "uni_pc", "heun", "ddim", "lcm", "er_sde", "res_multistep",
}
_SAMPLER_ALIASES = {"euler_ancestral": "euler_a", "unipc": "uni_pc", "dpmpp_2m_sde_gpu": "dpmpp_2m_sde", "dpmpp_3m_sde_gpu": "dpmpp_3m_sde"}
_SCHEDULERS = {"normal", "karras", "exponential", "sgm_uniform", "simple", "beta", "beta57", "linear_quadratic"}


def _sampler(name: str) -> tuple[str | None, str | None]:
    # a1111 ("DPM++ 2M Karras", "Euler a") and comfy ("euler_ancestral") names to ours, plus a folded scheduler
    s = name.strip().lower().replace("++", "pp").replace("+", "p")
    sched = None
    for k in ("karras", "exponential"):
        if s.endswith(" " + k):
            s, sched = s[: -len(k) - 1], k
    s = re.sub(r"[\s-]+", "_", s)
    s = _SAMPLER_ALIASES.get(s, s)
    return (s if s in _SAMPLERS else None), sched


def _scheduler(name: str) -> str | None:
    s = re.sub(r"[\s-]+", "_", name.strip().lower())
    return s if s in _SCHEDULERS else None


def _stem(name: str) -> str:
    return re.sub(r"\.(safetensors|ckpt|pt|pth|gguf|bin)$", "", re.split(r"[\\/]", name.strip())[-1], flags=re.I).lower()


def _local_model(name: str, kind: str) -> dict | None:
    # matches a file name from another ui against local models of a kind
    want = _stem(name)
    if not want:
        return None
    try:
        from . import models

        items = models.list_models(kind)
    except Exception:
        return None
    for m in items:
        if _stem(m["id"].split(":", 1)[-1]) == want:
            return m
    for m in items:
        if _stem(m.get("name") or "") == want:
            return m
    return None


def _apply_model(p: dict, name: str | None, unet: bool = False) -> dict:
    # rebases on the matched model's family defaults, keeping the prompts parsed so far
    m = _local_model(name, "checkpoint") if name else None
    fam = (m or {}).get("family") or ("anima" if unet and name and "anima" in name.lower() else p["family"])
    if fam != p["family"]:
        keep = {k: p[k] for k in ("prompt", "negative", "loras") if k in p}
        p = {**_base_defaults(fam), **keep, "family": fam}
    if m:
        p["model"] = m["id"]
    return p


def _lora(name: str, weight: float) -> dict | None:
    m = _local_model(name, "lora")
    return {"id": m["id"], "weight": round(float(weight), 3)} if m else None


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
    kv = {k.strip(): v.strip() for k, v in re.findall(r"\s*([A-Za-z][A-Za-z0-9 ]*): (\"(?:[^\"\\]|\\.)*\"|[^,]+)", lines[idx])}
    p = _base_defaults("illustrious")
    loras: list[dict] = []

    # local loras move from <lora:name:w> tags into the stack, unknown ones stay in the text
    def take(m: re.Match) -> str:
        try:
            lo = _lora(m.group(1), float(m.group(2) or 1))
        except ValueError:
            lo = None
        if lo is None:
            return m.group(0)
        loras.append(lo)
        return ""

    prompt = re.sub(r"<lora:([^:>]+)(?::([-\d.]+))?[^>]*>", take, prompt)
    p["prompt"] = re.sub(r"[ \t]{2,}", " ", prompt).strip().rstrip(",").strip()
    p["negative"] = negative
    if "Model" in kv:
        p = _apply_model(p, kv["Model"])
    if loras:
        p["loras"] = loras
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
        if "Hires upscale" in kv and isinstance(p.get("secondPass"), dict):
            sp = dict(p["secondPass"], enabled=True, scale=float(kv["Hires upscale"]))
            if "Denoising strength" in kv:
                sp["denoise"] = float(kv["Denoising strength"])
            if kv.get("Hires steps", "0") != "0":
                sp["steps"] = int(kv["Hires steps"])
            p["secondPass"] = sp
    except ValueError:
        pass
    if "Sampler" in kv:
        s, sched = _sampler(kv["Sampler"])
        if s:
            p["sampler"] = s
        if sched:
            p["scheduler"] = sched
    if "Schedule type" in kv and _scheduler(kv["Schedule type"]):
        p["scheduler"] = _scheduler(kv["Schedule type"])
    return p


# widget order of the ui workflow format for the node types read below
_WIDGETS = {
    "KSampler": ["seed", None, "steps", "cfg", "sampler_name", "scheduler", "denoise"],
    "KSamplerAdvanced": ["add_noise", "noise_seed", None, "steps", "cfg", "sampler_name", "scheduler", "start_at_step", "end_at_step", "return_with_leftover_noise"],
    "CLIPTextEncode": ["text"],
    "CheckpointLoaderSimple": ["ckpt_name"],
    "UNETLoader": ["unet_name", "weight_dtype"],
    "EmptyLatentImage": ["width", "height", "batch_size"],
    "LoraLoader": ["lora_name", "strength_model", "strength_clip"],
    "LoraLoaderModelOnly": ["lora_name", "strength_model"],
    "CLIPSetLastLayer": ["stop_at_clip_layer"],
    "LatentUpscaleBy": ["upscale_method", "scale_by"],
    "PrimitiveNode": ["value"],
}
_SAMPLER_NODES = ("KSampler", "KSamplerAdvanced")
_LATENT_IN = ("samples", "latent_image", "latent")


def _workflow_to_prompt(wf: dict) -> dict:
    links = {l[0]: l for l in wf.get("links") or [] if isinstance(l, list) and len(l) >= 3}
    out: dict = {}
    for n in wf.get("nodes") or []:
        vals = n.get("widgets_values") if isinstance(n.get("widgets_values"), list) else []
        ins = {k: v for k, v in zip(_WIDGETS.get(n.get("type"), []), vals) if k}
        for i in n.get("inputs") or []:
            l = links.get(i.get("link"))
            if l:
                ins[i["name"]] = [str(l[1]), l[2]]
        out[str(n.get("id"))] = {"class_type": n.get("type"), "inputs": ins}
    return out


def parse_comfy(graph: dict) -> dict | None:
    nodes = {str(k): v for k, v in graph.items() if isinstance(v, dict) and "class_type" in v}

    def node(ref):
        return nodes.get(str(ref[0])) if isinstance(ref, list) and ref else None

    def value(v, depth=0):
        # a literal input or a link to a primitive / string node
        n = node(v)
        if n is None:
            return v
        if depth > 8:
            return None
        ins = n.get("inputs", {})
        for k in ("value", "text", "string", "seed", "noise_seed", "int", "float", "Text"):
            if k in ins:
                return value(ins[k], depth + 1)
        return None

    def upstream(ref, keys):
        for _ in range(32):
            n = node(ref)
            if n is None:
                return
            yield n
            ins = n.get("inputs", {})
            ref = next((ins[k] for k in keys if isinstance(ins.get(k), list)), None)

    def text(ref, depth=0) -> str:
        n = node(ref)
        if n is None or depth > 16:
            return ""
        ins = n.get("inputs", {})
        if "text" in ins or "text_g" in ins:
            t = value(ins.get("text", ins.get("text_g")))
            return t if isinstance(t, str) else ""
        keys = ("conditioning", "conditioning_1", "conditioning_2", "conditioning_to", "conditioning_from", "positive", "negative")
        parts = [text(ins[k], depth + 1) for k in keys if isinstance(ins.get(k), list)]
        return ", ".join(t for t in parts if t)

    samplers = {k: n for k, n in nodes.items() if n.get("class_type") in _SAMPLER_NODES}
    if not samplers:
        return None

    def fed_by(n: dict) -> str | None:
        for u in upstream(n.get("inputs", {}).get("latent_image"), (*_LATENT_IN, "pixels", "image")):
            for k, s in samplers.items():
                if s is u:
                    return k
        return None

    first = next((k for k, n in samplers.items() if fed_by(n) is None), next(iter(samplers)))
    ins = samplers[first]["inputs"]
    model_name, unet, loras = None, False, []
    for n in upstream(ins.get("model"), ("model", "unet")):
        ni = n.get("inputs", {})
        if "lora_name" in ni:
            try:
                lo = _lora(str(value(ni["lora_name"])), float(value(ni.get("strength_model", 1))))
            except (TypeError, ValueError):
                lo = None
            if lo:
                loras.append(lo)
        if "ckpt_name" in ni or "unet_name" in ni:
            unet = "unet_name" in ni
            model_name = str(value(ni.get("ckpt_name", ni.get("unet_name"))))
            break
    p = _apply_model(_base_defaults("illustrious"), model_name, unet)
    p["prompt"] = text(ins.get("positive")).strip()
    p["negative"] = text(ins.get("negative")).strip()
    if loras:
        p["loras"] = loras[::-1]
    try:
        seed = value(ins.get("seed", ins.get("noise_seed")))
        if seed is not None:
            p["seed"] = int(seed)
        if ins.get("steps") is not None:
            p["steps"] = int(value(ins["steps"]))
        if ins.get("cfg") is not None:
            p["cfg"] = float(value(ins["cfg"]))
    except (TypeError, ValueError):
        pass
    s, _ = _sampler(str(value(ins.get("sampler_name")) or ""))
    if s:
        p["sampler"] = s
    sch = _scheduler(str(value(ins.get("scheduler")) or ""))
    if sch:
        p["scheduler"] = sch
    for n in upstream(ins.get("latent_image"), _LATENT_IN):
        ni = n.get("inputs", {})
        w, h = value(ni.get("width")), value(ni.get("height"))
        if isinstance(w, int) and isinstance(h, int):
            p["width"], p["height"] = w, h
            break
    for n in nodes.values():
        if n.get("class_type") == "CLIPSetLastLayer":
            try:
                p["clipSkip"] = max(1, -int(value(n["inputs"].get("stop_at_clip_layer", -1))))
            except (TypeError, ValueError):
                pass
    # a sampler fed by the first one (usually through an upscale) is a second pass
    for k, n in samplers.items():
        if k == first or fed_by(n) != first or not isinstance(p.get("secondPass"), dict):
            continue
        ni = n["inputs"]
        sp = dict(p["secondPass"], enabled=True)
        try:
            sp["steps"] = int(value(ni.get("steps", sp["steps"])))
            sp["denoise"] = float(value(ni.get("denoise", sp["denoise"])))
            for u in upstream(ni.get("latent_image"), _LATENT_IN):
                if "scale_by" in u.get("inputs", {}):
                    sp["scale"] = float(value(u["inputs"]["scale_by"]))
                    break
        except (TypeError, ValueError):
            pass
        p["secondPass"] = sp
        break
    return p


def read_params(img: Image.Image) -> dict | None:
    info = img.info or {}
    if "somnia" in info:
        try:
            return json.loads(info["somnia"])
        except ValueError:
            pass
    if "parameters" in info:
        p = parse_a1111(info["parameters"])
        if p:
            return p
    for key in ("prompt", "workflow"):
        if key not in info:
            continue
        try:
            g = json.loads(info[key])
            p = parse_comfy(_workflow_to_prompt(g) if key == "workflow" else g) if isinstance(g, dict) else None
        except (ValueError, TypeError, KeyError, AttributeError):
            p = None
        if p:
            return p
    return None


def file_of(item: dict) -> Path:
    url = item["url"].split("?")[0]
    if url.startswith("/outputs/"):
        return Path(config.settings().outputDir) / url.removeprefix("/outputs/")
    return uploads_dir() / url.removeprefix("/files/uploads/")


def png_bytes(item: dict) -> tuple[str, bytes]:
    src = file_of(item)
    if src.suffix.lower() == ".png":
        return src.name, src.read_bytes()
    img = Image.open(src)
    buf = io.BytesIO()
    img.convert("RGBA" if "A" in img.getbands() else "RGB").save(buf, "PNG")
    return src.stem + ".png", buf.getvalue()


def zip_items(items: list[dict]) -> io.BytesIO:
    # pngs are already compressed, so stored entries keep this fast
    buf = io.BytesIO()
    seen: set[str] = set()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
        for it in items:
            try:
                name, data = png_bytes(it)
            except OSError:
                continue
            base, n = name[:-4], 1
            while name in seen:
                n += 1
                name = f"{base}-{n}.png"
            seen.add(name)
            z.writestr(name, data)
    buf.seek(0)
    return buf


def save_derived(img: Image.Image, src: dict, tag: str, **extra) -> dict:
    # writes an image made from a gallery item as a new item stacked under the source's root
    out = Path(config.settings().outputDir)
    thumbs = out / "thumbs"
    thumbs.mkdir(parents=True, exist_ok=True)
    seed = src.get("seed", 0)
    stem = time.strftime("%Y%m%d-%H%M%S") + f"-{seed}-{tag}-{uuid.uuid4().hex[:4]}"
    params = copy.deepcopy(src.get("params"))
    info = PngInfo()
    if params:
        info.add_text("somnia", json.dumps(params))
    img.save(out / f"{stem}.png", "PNG", pnginfo=info)
    alpha = "A" in img.getbands()
    th = img.convert("RGBA" if alpha else "RGB")
    th.thumbnail((384, 384))
    th.save(thumbs / f"{stem}.webp", "WEBP", quality=80)
    item = {
        "id": stem,
        "url": f"/outputs/{stem}.png",
        "thumbUrl": f"/outputs/thumbs/{stem}.webp",
        "width": img.width,
        "height": img.height,
        "seed": seed,
        "createdAt": store.now_ms(),
        "params": params,
        "stackId": src.get("stackId") or src["id"],
        "sourceId": src["id"],
        **extra,
    }
    if alpha:
        item["alpha"] = True
    store.add_gallery(item)
    return item


def upload_from_gallery(item: dict) -> dict:
    # copies a gallery image into uploads server side so clients need not round-trip the png
    src = file_of(item)
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
