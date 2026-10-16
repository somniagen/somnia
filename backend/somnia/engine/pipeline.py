from __future__ import annotations

import random
import threading
from dataclasses import replace
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image, ImageFilter

from ..config import DATA_DIR, settings
from . import detailer, mem, optim, passes, previews
from .base import Engine, RunContext, SampleRequest

UPLOADS = DATA_DIR / "uploads"

_lock = threading.RLock()
_engines: dict[str, Engine] = {}


def get_engine(family: str) -> Engine:
    with _lock:
        for f in list(_engines):
            if f != family:
                _engines.pop(f).unload()
                previews.unload()
                mem.flush()
        e = _engines.get(family)
        if e is None:
            if family == "illustrious":
                from .illustrious import IllustriousEngine

                e = IllustriousEngine()
            elif family == "anima":
                from .anima import AnimaEngine

                e = AnimaEngine()
            else:
                raise ValueError(f"unknown family: {family}")
            _engines[family] = e
        return e


def unload_all() -> None:
    with _lock:
        for f in list(_engines):
            _engines.pop(f).unload()
        passes.unload()
        detailer.unload()
        previews.unload()
        mem.flush()


def _upload(image_id: str) -> Image.Image:
    p = UPLOADS / f"{image_id}.png"
    if not p.exists():
        p = UPLOADS / image_id
    im = Image.open(p)
    im.load()
    return im


def _resolve_upscaler(ctx: RunContext, uid: str | None) -> Path | None:
    if not uid or uid == "latent" or uid == "none":
        return None
    return ctx.resolve(uid)


def _fill(img: Image.Image, mask: Image.Image, mode: str, seed: int) -> Image.Image:
    if mode == "noise":
        rng = np.random.default_rng(seed)
        filler = Image.fromarray(rng.integers(0, 256, (img.height, img.width, 3), dtype=np.uint8))
    elif mode == "blur":
        filler = img.filter(ImageFilter.GaussianBlur(max(img.size) // 16))
    else:
        return img
    return Image.composite(filler, img, mask.point(lambda v: 255 if v > 127 else 0))


def _detail_prompt(main: str, d: dict) -> str:
    extra = (d.get("prompt") or "").strip().strip(",").strip()
    if not extra:
        return main
    if d.get("appendPrompt"):
        return f"{main.rstrip().rstrip(',')}, {extra}" if main.strip() else extra
    return extra


def _base_request(p: dict, seed: int) -> SampleRequest:
    pag = p.get("pag") or {}
    return SampleRequest(
        model=p["model"],
        prompt=p.get("prompt", ""),
        negative=p.get("negative", ""),
        width=int(p.get("width", 1024)),
        height=int(p.get("height", 1024)),
        steps=int(p.get("steps", 28)),
        cfg=float(p.get("cfg", 6.0)),
        sampler=p.get("sampler") or "euler_a",
        scheduler=p.get("scheduler") or "normal",
        seed=seed,
        batch_size=max(1, int(p.get("batchSize", 1))),
        clip_skip=int(p.get("clipSkip", 2) or 1),
        loras=[(l["id"], float(l.get("weight", 1.0))) for l in p.get("loras") or [] if l.get("id")],
        vae=p.get("vae") or None,
        text_encoder=p.get("textEncoder") or None,
        pag_scale=float(pag.get("scale", 0.0)) if pag.get("enabled") else 0.0,
        cfg_rescale=float(p.get("cfgRescale") or 0.0),
    )


def _base_sample(engine: Engine, req: SampleRequest, p: dict, ctx: RunContext) -> list[Image.Image]:
    init = p.get("init")
    if not init or not init.get("imageId"):
        return engine.sample(req, ctx)
    size = (req.width // 8 * 8, req.height // 8 * 8)
    src = _upload(init["imageId"]).convert("RGB")
    if src.size != size:
        src = src.resize(size, Image.LANCZOS)
    denoise = float(init.get("denoise", 0.75))
    mask = None
    if init.get("maskId"):
        mask = _upload(init["maskId"]).convert("L").resize(size, Image.LANCZOS)
    if mask is None:
        return engine.sample(replace(req, init_images=[src], denoise=denoise), ctx)
    blur = int(init.get("maskBlur", 4))
    outs = []
    for i in range(req.batch_size):
        seed = req.seed + i
        filled = _fill(src, mask, init.get("fill", "original"), seed)
        if init.get("onlyMasked"):

            def run(crop, cm, seed=seed):
                r = replace(req, init_images=[crop], mask=cm, denoise=denoise, batch_size=1, seed=seed, width=crop.width, height=crop.height)
                return engine.sample(r, ctx)[0]

            out = detailer.masked_inpaint(filled, mask, run, padding=int(init.get("padding", 32)), blur=blur, base=src)
        else:
            r = replace(req, init_images=[filled], mask=mask, denoise=denoise, batch_size=1, seed=seed)
            out = engine.sample(r, ctx)[0]
            feather = mask.filter(ImageFilter.GaussianBlur(blur)) if blur > 0 else mask
            out = Image.composite(out.convert("RGB").resize(size, Image.LANCZOS), src, feather)
        outs.append(out)
    return outs


def _labeled(ctx: RunContext, label: str | None) -> RunContext:
    base = ctx.progress

    def progress(phase, step, total, preview=None, label_=None):
        base(phase, step, total, preview, label_ or label)

    return replace(ctx, progress=progress)


LATENT_MODES = {"latent": "bicubic", "latent-bicubic": "bicubic", "latent-nearest": "nearest", "latent-bislerp": "bislerp"}


def _latent_mode(uid: str | None) -> str | None:
    return LATENT_MODES.get(uid or "")


def _slerp(a: torch.Tensor, b: torch.Tensor, t: torch.Tensor) -> torch.Tensor:
    an = a.norm(dim=1, keepdim=True)
    bn = b.norm(dim=1, keepdim=True)
    au, bu = a / an.clamp(min=1e-8), b / bn.clamp(min=1e-8)
    dot = (au * bu).sum(1, keepdim=True).clamp(-1 + 1e-6, 1 - 1e-6)
    om = torch.acos(dot)
    so = torch.sin(om)
    res = (torch.sin((1 - t) * om) / so) * au + (torch.sin(t * om) / so) * bu
    res = res * ((1 - t) * an + t * bn)
    lin = (1 - t) * a + t * b
    return torch.where(dot > 0.9995, lin, res)


def _bislerp_axis(x: torch.Tensor, n: int, dim: int) -> torch.Tensor:
    size = x.shape[dim]
    pos = (torch.arange(n, dtype=torch.float32) + 0.5) * size / n - 0.5
    pos = pos.clamp(0, size - 1)
    i0 = pos.floor().long()
    i1 = (i0 + 1).clamp(max=size - 1)
    t = (pos - i0.float()).to(x.device)
    a = x.index_select(dim, i0.to(x.device))
    b = x.index_select(dim, i1.to(x.device))
    shape = [1] * x.ndim
    shape[dim] = n
    return _slerp(a, b, t.view(shape))


def latent_resize(lat: torch.Tensor, h: int, w: int, mode: str = "bicubic") -> torch.Tensor:
    five = lat.ndim == 5
    x = lat[:, :, 0] if five else lat
    x = x.float()
    if x.shape[-2:] != (h, w):
        if mode == "nearest":
            x = F.interpolate(x, size=(h, w), mode="nearest-exact")
        elif mode == "bislerp":
            x = _bislerp_axis(_bislerp_axis(x, h, 2), w, 3)
        else:
            x = F.interpolate(x, size=(h, w), mode="bicubic", align_corners=False)
    return x[:, :, None] if five else x


def _second_pass(engine: Engine, req: SampleRequest, sp: dict, images: list[Image.Image], latents, seed: int, ctx: RunContext):
    uid = sp.get("upscaler")
    mode = _latent_mode(uid)
    scale = float(sp.get("scale", 1.5))
    denoise = float(sp.get("denoise", 0.35))
    out = []
    n = len(images) if latents is None else latents.shape[0]
    for i in range(n):
        ctx.check()
        tag = f" {i + 1}/{n}" if n > 1 else ""
        r = replace(
            req,
            model=sp.get("model") or req.model,
            init_images=None,
            init_latents=None,
            mask=None,
            denoise=denoise,
            steps=int(sp.get("steps", 15)),
            cfg=float(sp["cfg"]) if sp.get("cfg") is not None else req.cfg,
            sampler=sp.get("sampler") or req.sampler,
            scheduler=sp.get("scheduler") or req.scheduler,
            batch_size=1,
            seed=seed + i,
            phase="second",
        )
        if mode and latents is not None:
            m = engine.size_multiple
            ls = engine.latent_scale
            src = latents[i : i + 1]
            ph, pw = src.shape[-2] * ls, src.shape[-1] * ls
            tw = max(m, int(round(pw * scale / m)) * m)
            th = max(m, int(round(ph * scale / m)) * m)
            ctx.progress("second", 0, 1, None, "Latent upscale" + tag)
            big = latent_resize(src, th // ls, tw // ls, mode)
            r = replace(r, init_latents=big, denoise=max(denoise, 0.5), width=tw, height=th)
        else:
            up = _resolve_upscaler(ctx, None if mode else uid)
            im = images[i]
            sctx = _labeled(ctx, "Upscaling" + tag)
            sctx.progress("second", 0, 1, None)
            big = passes.upscale_to(
                im, up, scale, progress=lambda k, t: sctx.progress("second", k, t, None), check=ctx.check, multiple=engine.size_multiple
            )
            if up is not None:
                passes.release()
            r = replace(r, init_images=[big], width=big.width, height=big.height)
        out.append(engine.sample(r, _labeled(ctx, "Second pass" + tag))[0])
        mem.flush()
    return out


def run(params: dict, ctx: RunContext) -> list[Image.Image]:
    p = params
    seed = int(p.get("seed", -1))
    if seed < 0:
        seed = random.randint(0, 2**32 - 1)
        p["seed"] = seed
    family = p.get("family") or "illustrious"
    engine = get_engine(family)
    req = _base_request(p, seed)
    optim.apply()
    try:
        from .illustrious import cap_vram

        cap_vram()
    except Exception:
        pass
    try:
        sp = p.get("secondPass") or {}
        init = p.get("init") or {}
        latent_sp = (
            sp.get("enabled")
            and _latent_mode(sp.get("upscaler"))
            and engine.supports_latents
            and not init.get("maskId")
        )
        latents = None
        if latent_sp:
            images = _base_sample(engine, replace(req, keep_latents=True, decode=False), p, _labeled(ctx, None))
            latents = engine.last_latents
            engine.last_latents = None
            if latents is None:
                images = _base_sample(engine, req, p, ctx)
        else:
            images = _base_sample(engine, req, p, ctx)
        ctx.check()

        if sp.get("enabled"):
            images = _second_pass(engine, req, sp, images, latents, seed, ctx)
            latents = None

        dets = [d for d in p.get("detailers") or [] if d.get("enabled") and d.get("detector")]
        for di, d in enumerate(dets):
            dpath = ctx.resolve(d["detector"])
            kind = Path(str(d["detector"])).stem.split("_")[0] if d.get("detector") else "detail"
            out = []
            for i, im in enumerate(images):
                ctx.progress("detail", 0, 1, None, f"Detecting {kind}")
                found = detailer.detect(im, dpath, float(d.get("confidence", 0.3)))
                if di == len(dets) - 1 and i == len(images) - 1:
                    detailer.release()
                for k, det in enumerate(found):
                    ctx.check()
                    mask = detailer.dilate(detailer.det_mask(im.size, det), int(d.get("dilate", 4)))
                    label = f"Detailer {det.get('label') or kind} {k + 1}/{len(found)}"
                    dctx = _labeled(ctx, label)

                    def run_crop(crop, cm, i=i, dctx=dctx):
                        r = replace(
                            req,
                            prompt=_detail_prompt(req.prompt, d),
                            negative=d.get("negative") or req.negative,
                            init_images=[crop],
                            mask=cm,
                            denoise=float(d.get("denoise", 0.4)),
                            steps=int(d.get("steps", 20)),
                            width=crop.width,
                            height=crop.height,
                            batch_size=1,
                            seed=seed + i,
                            phase="detail",
                        )
                        return engine.sample(r, dctx)[0]

                    im = detailer.masked_inpaint(im, mask, run_crop, padding=int(d.get("padding", 32)), blur=int(d.get("blur", 4)))
                out.append(im)
            images = out
            mem.flush()

        upc = p.get("upscale") or {}
        if upc.get("enabled") and float(upc.get("scale", 1)) > 1:
            up = _resolve_upscaler(ctx, upc.get("upscaler"))
            out = []
            for i, im in enumerate(images):
                uctx = _labeled(ctx, "Upscaling" + (f" {i + 1}/{len(images)}" if len(images) > 1 else ""))
                uctx.progress("upscale", 0, 1, None)
                out.append(
                    passes.upscale_to(
                        im, up, float(upc["scale"]), progress=lambda k, t: uctx.progress("upscale", k, t, None), check=ctx.check
                    )
                )
            images = out
            passes.release()
    except torch.OutOfMemoryError as e:
        mem.flush()
        raise RuntimeError("out of VRAM (close other GPU apps, lower resolution or enable lowVram)") from e
    finally:
        if not settings().keepModelsLoaded:
            engine.unload()
            passes.unload()
            detailer.unload()
            previews.unload()
        mem.flush()

    res = []
    for i, im in enumerate(images):
        im = im.convert("RGB")
        im.info["seed"] = seed + i
        res.append(im)
    return res


def detect(image_path: str | Path, detector_id: str, conf: float = 0.3) -> list[dict]:
    from .. import models

    img = Image.open(image_path)
    img.load()
    return detailer.detect(img, models.resolve(detector_id), conf)
