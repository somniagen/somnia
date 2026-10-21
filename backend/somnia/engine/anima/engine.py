from __future__ import annotations

import gc
import logging
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image
from safetensors import safe_open

from .. import device as devices
from .. import mem, optim, previews
from ..base import Engine, RunContext, SampleRequest
from ..noise import slerp
from ..stepcache import StepCache
from . import lora as lora_mod
from .dit import AnimaDiT
from .sampling import SAMPLERS, SCHEDULERS, FlowSchedule, sample, sigmas_for
from .text import AnimaTokenizer, build_qwen3, encode_qwen

log = logging.getLogger(__name__)

DEFAULT_SHIFT = 3.0
LATENT_MEAN = [-0.7571, -0.7089, -0.9113, 0.1075, -0.1745, 0.9653, -0.1517, 1.5508, 0.4134, -0.0715, 0.5517, -0.3632, -0.1922, -0.9497, 0.2503, -0.2921]
LATENT_STD = [2.8184, 1.4541, 2.3275, 2.6558, 1.2196, 1.7708, 2.6052, 2.0743, 3.2687, 2.1526, 2.8652, 1.5579, 1.6382, 1.1253, 2.8251, 1.9160]
RGB_FACTORS = [
    [-0.1299, -0.1692, 0.2932], [0.0671, 0.0406, 0.0442], [0.3568, 0.2548, 0.1747], [0.0372, 0.2344, 0.1420],
    [0.0313, 0.0189, -0.0328], [0.0296, -0.0956, -0.0665], [-0.3477, -0.4059, -0.2925], [0.0166, 0.1902, 0.1975],
    [-0.0412, 0.0267, -0.1364], [-0.1293, 0.0740, 0.1636], [0.0680, 0.3019, 0.1128], [0.0032, 0.0581, 0.0639],
    [-0.1251, 0.0927, 0.1699], [0.0060, -0.0633, 0.0005], [0.3477, 0.2275, 0.2950], [0.1984, 0.0913, 0.1861],
]
RGB_BIAS = [-0.1835, -0.0868, -0.3360]

DIT_PREFIXES = ["model.diffusion_model.", "net.", "diffusion_model.", ""]
TE_PREFIXES = ["text_encoders.qwen3_06b.transformer.", "qwen3_06b.transformer.", "text_encoder.", ""]


def _keys(path: Path) -> list[str]:
    with safe_open(str(path), framework="pt", device="cpu") as f:
        return list(f.keys())


def _dit_prefix(keys) -> str | None:
    for p in DIT_PREFIXES:
        if f"{p}blocks.0.mlp.layer1.weight" in keys and f"{p}llm_adapter.embed.weight" in keys:
            return p
    return None


def _dit_config(sd: dict[str, torch.Tensor]) -> dict:
    # bigger variants (e.g. 2.9b) only add blocks, but read every size from the weights anyway
    blocks = 1 + max(int(k.split(".")[1]) for k in sd if k.startswith("blocks."))
    ch = sd["blocks.0.self_attn.q_proj.weight"].shape[0]
    return {
        "model_channels": ch,
        "num_blocks": blocks,
        "num_heads": ch // sd["blocks.0.self_attn.q_norm.weight"].shape[0],
        "context_dim": sd["blocks.0.cross_attn.k_proj.weight"].shape[1],
    }


def _te_prefix(keys) -> str | None:
    for p in TE_PREFIXES:
        if f"{p}model.layers.0.self_attn.q_norm.weight" in keys:
            return p
    return None


def _vae_prefix(keys) -> str | None:
    for p in ["vae.", "first_stage_model.", ""]:
        if f"{p}decoder.head.2.weight" in keys and f"{p}conv2.weight" in keys:
            return p
    return None


def _load(path: Path, prefix: str, device="cpu", skip=(), dtype=None, exclude=()) -> dict[str, torch.Tensor]:
    out = {}
    dev = torch.device(device)
    # safetensors can't read straight into mps, move tensor by tensor so unified memory never holds two copies
    src = "cpu" if dev.type == "mps" else str(dev)
    with safe_open(str(path), framework="pt", device=src) as f:
        for k in f.keys():
            if k.startswith(prefix) and not any(s in k for s in skip):
                n = k[len(prefix):]
                if exclude and n.startswith(exclude):
                    continue
                t = f.get_tensor(k)
                if dtype is not None and t.is_floating_point() and t.dtype != dtype:
                    t = t.to(dtype)
                out[n] = t.to(dev) if t.device != dev else t
    return out


def _find_sibling(model_path: Path, folder: str, prefer: list[str], check) -> Path | None:
    cands = []
    for root in {model_path.parent.parent, model_path.parent}:
        d = root / folder
        if d.is_dir():
            cands += sorted(d.rglob("*.safetensors"))
    cands.sort(key=lambda p: min([i for i, s in enumerate(prefer) if s in p.name.lower()] or [99]))
    for c in cands:
        try:
            if check(_keys(c)) is not None:
                return c
        except Exception:
            continue
    return None


class AnimaEngine(Engine):
    family = "anima"
    supports_latents = True
    latent_scale = 8
    size_multiple = 16

    def __init__(self, device: str | None = None):
        self.device = torch.device(device) if device else devices.get()
        if self.device.type != "cpu" and devices.bf16_ok():
            self.dtype = torch.bfloat16
        elif self.device.type == "cuda":
            self.dtype = torch.float16
        else:
            # the wan vae overflows in fp16, keep te/vae in fp32 when bf16 is missing
            self.dtype = torch.float32
        self.tok: AnimaTokenizer | None = None
        self.dit: AnimaDiT | None = None
        self.dit_src: tuple[Path, str] | None = None
        self.te = None
        self.te_src: tuple[Path, str] | None = None
        self.vae = None
        self.vae_src: tuple[Path, str] | None = None
        self.applied: list[tuple[str, float]] = []
        self.touched_dit: set[str] = set()
        self.touched_te: set[str] = set()
        self.te_park: mem.Parked | None = None
        self.vae_park: mem.Parked | None = None
        self._cond: dict[tuple, torch.Tensor] = {}
        self.last_latents: torch.Tensor | None = None
        self.fp16_ok = True

    def _dit_dtype(self) -> torch.dtype:
        # fp16 with fp16 accumulation is ~20% faster than bf16 on ampere consumer cards,
        # apple gpus have no fast bf16 path at all. the residual stream stays fp32 either way
        if self.fp16_ok and ((self.device.type == "cuda" and optim.enabled()) or self.device.type == "mps"):
            return torch.float16
        return self.dtype

    def samplers(self) -> list[str]:
        return list(SAMPLERS)

    def schedulers(self) -> list[str]:
        return list(SCHEDULERS)

    def unload(self) -> None:
        self.dit = self.te = self.vae = None
        self.te_park = self.vae_park = None
        self._cond.clear()
        self.last_latents = None
        previews.unload()
        self.dit_src = self.te_src = self.vae_src = None
        self.applied = []
        self.touched_dit.clear()
        self.touched_te.clear()
        gc.collect()
        devices.empty_cache()

    def _ensure_models(self, req: SampleRequest, ctx: RunContext) -> None:
        mpath = Path(ctx.resolve(req.model))
        mkeys = _keys(mpath)
        dp = _dit_prefix(mkeys)
        if dp is None:
            raise ValueError(f"{mpath.name} is not an anima model")
        if self.dit_src != (mpath, dp):
            self.dit = None
            self.touched_dit.clear()
            self._cond.clear()
            mem.flush()
            ctx.progress("load", 0, 1, None)
            ex = ("text_encoders.", "vae.", "first_stage_model.") if dp == "" else ()
            sd = _load(mpath, dp, device=self.device, skip=("pos_embedder.",), dtype=self._dit_dtype(), exclude=ex)
            with torch.device("meta"):
                m = AnimaDiT(**_dit_config(sd))
            m.load_state_dict(sd, strict=True, assign=True)
            del sd
            self.dit = m.to(self.device).eval().requires_grad_(False)
            self.dit_src = (mpath, dp)
            self._restore_all()
            mem.flush()

        tpath, tp, bad = None, None, None
        if req.text_encoder:
            tpath = Path(ctx.resolve(req.text_encoder))
            tp = _te_prefix(_keys(tpath))
            if tp is None:
                bad = tpath.name
        if tp is None and _te_prefix(mkeys) is not None:
            tpath, tp = mpath, _te_prefix(mkeys)
        if tp is None:
            tpath = _find_sibling(mpath, "text_encoders", ["qwen_3_06b", "qwen3", "anima"], _te_prefix)
            tp = _te_prefix(_keys(tpath)) if tpath else None
        if tp is None:
            if bad:
                raise ValueError(f"{bad} is not the qwen3 0.6b text encoder anima needs")
            raise ValueError("anima needs a qwen3 0.6b text encoder")
        if self.te_src != (tpath, tp):
            self.te = self.te_park = None
            self.touched_te.clear()
            self._cond.clear()
            mem.flush()
            self.te = build_qwen3(_load(tpath, tp, dtype=self.dtype), self.dtype)
            if self.device.type == "cuda":
                self.te_park = mem.Parked(self.te)
                self.te_park.on_gpu = True
                self.te_park.park()
            else:
                self.te.to(self.device)
            self.te_src = (tpath, tp)
            self._restore_all()

        if req.vae:
            vpath = Path(ctx.resolve(req.vae))
            vp = _vae_prefix(_keys(vpath))
        elif _vae_prefix(mkeys) is not None and dp != "":
            vpath, vp = mpath, _vae_prefix(mkeys)
        else:
            vpath = _find_sibling(mpath, "vae", ["qwen_image", "wan_2.1", "wan2.1", "wan"], _vae_prefix)
            if vpath is None:
                raise ValueError("anima needs the qwen image / wan 2.1 vae")
            vp = _vae_prefix(_keys(vpath))
        if vp is None:
            raise ValueError(f"{vpath.name} is not a wan/qwen-image vae")
        if self.vae_src != (vpath, vp):
            from diffusers import AutoencoderKLWan
            from diffusers.loaders.single_file_utils import convert_wan_vae_to_diffusers

            self.vae = self.vae_park = None
            sd = convert_wan_vae_to_diffusers(_load(vpath, vp, dtype=self.dtype))
            with torch.device("meta"):
                v = AutoencoderKLWan()
            v.load_state_dict(sd, strict=True, assign=True)
            del sd
            self.vae = v.eval().requires_grad_(False)
            if self.device.type == "cuda":
                self.vae_park = mem.Parked(self.vae)
                self.vae_park.on_gpu = True
                self.vae_park.park()
            else:
                self.vae.to(self.device)
            self.vae_src = (vpath, vp)

        if self.tok is None:
            self.tok = AnimaTokenizer()

    def _restore_all(self) -> None:
        if self.touched_dit and self.dit is not None:
            path, p = self.dit_src
            params = dict(self.dit.named_parameters())
            with safe_open(str(path), framework="pt", device="cpu") as f:
                for n in self.touched_dit:
                    params[n].data.copy_(f.get_tensor(p + n).to(params[n].dtype))
        if self.touched_te and self.te is not None:
            path, p = self.te_src
            params = dict(self.te.named_parameters())
            with safe_open(str(path), framework="pt", device="cpu") as f:
                for n in self.touched_te:
                    params[n].data.copy_(f.get_tensor(p + "model." + n).to(params[n].dtype))
        self.touched_dit.clear()
        self.touched_te.clear()
        self.applied = []

    def _apply_loras(self, loras: list[tuple[str, float]], ctx: RunContext) -> None:
        want = [(i, float(s)) for i, s in loras if s != 0]
        if want == self.applied:
            return
        self._cond.clear()
        self._restore_all()
        if not want:
            return
        dparams = {n: p for n, p in self.dit.named_parameters() if n.endswith(".weight") and p.ndim == 2}
        tparams = {n: p for n, p in self.te.named_parameters() if n.endswith(".weight") and p.ndim == 2}
        dt = {n: lora_mod.dit_aliases(n) for n in dparams}
        tt = {n: lora_mod.te_aliases(n) for n in tparams}
        for lid, strength in want:
            sd = lora_mod.read_lora(Path(ctx.resolve(lid)))
            hits_d, _ = lora_mod.lora_deltas(sd, dt)
            hits_t, _ = lora_mod.lora_deltas(sd, tt)
            if not hits_d and not hits_t:
                log.warning("lora %s: no matching keys for anima", lid)
            for n, h in hits_d.items():
                lora_mod.apply_delta(dparams[n], h, strength)
                self.touched_dit.add(n)
            for n, h in hits_t.items():
                lora_mod.apply_delta(tparams[n], h, strength)
                self.touched_te.add(n)
            log.info("lora %s: %d dit + %d te layers", lid, len(hits_d), len(hits_t))
        self.applied = want

    @torch.no_grad()
    def _encode_prompts(self, prompts: list[str]) -> list[torch.Tensor]:
        sig = tuple(self.applied)
        todo = [p for p in dict.fromkeys(prompts) if (p, sig) not in self._cond]
        if todo:
            gpu = self.te_park is not None and self.device.type == "cuda"
            if gpu:
                self.te_park.gpu()
            try:
                raw = []
                for p in todo:
                    q, t, w = self.tok(p)
                    raw.append((p, encode_qwen(self.te, q, self.device), t, w))
            finally:
                if gpu:
                    self.te_park.park()
            for p, h, t, w in raw:
                ids = torch.tensor([t], device=self.device)
                ddt = next(self.dit.parameters()).dtype
                wt = torch.tensor([w], device=self.device, dtype=ddt)
                if len(self._cond) >= 8:
                    self._cond.pop(next(iter(self._cond)))
                self._cond[(p, sig)] = self.dit.encode_text(h.to(ddt), ids, wt if any(x != 1.0 for x in w) else None)
        return [self._cond[(p, sig)] for p in prompts]

    def _vae_on(self) -> None:
        if self.vae_park is not None and self.device.type == "cuda":
            self.vae_park.gpu()

    def _vae_off(self) -> None:
        if self.vae_park is not None and self.device.type == "cuda":
            self.vae_park.park()

    def _norm(self, z):
        m = torch.tensor(LATENT_MEAN, device=z.device).view(1, 16, 1, 1, 1)
        s = torch.tensor(LATENT_STD, device=z.device).view(1, 16, 1, 1, 1)
        return (z - m) / s

    def _denorm(self, z):
        m = torch.tensor(LATENT_MEAN, device=z.device).view(1, 16, 1, 1, 1)
        s = torch.tensor(LATENT_STD, device=z.device).view(1, 16, 1, 1, 1)
        return z * s + m

    @torch.no_grad()
    def _vae_encode(self, imgs: list[Image.Image], w: int, h: int) -> torch.Tensor:
        arr = []
        for im in imgs:
            im = im.convert("RGB")
            if im.size != (w, h):
                im = im.resize((w, h), Image.LANCZOS)
            arr.append(torch.from_numpy(np.asarray(im).copy()).permute(2, 0, 1).float() / 127.5 - 1)
        x = torch.stack(arr)[:, :, None].to(self.device, self.dtype)
        del arr
        self._vae_on()
        try:
            self._tiling(w, h)
            z = self.vae.encode(x).latent_dist.mode()
        finally:
            del x
            self._vae_off()
        return self._norm(z.float())

    def _tiling(self, w: int, h: int) -> None:
        if w * h > 640 * 640:
            self.vae.enable_tiling(512, 512, 448, 448)
        else:
            self.vae.disable_tiling()

    @torch.no_grad()
    def _vae_decode(self, z: torch.Tensor, w: int, h: int, ctx: RunContext | None = None) -> list[Image.Image]:
        mem.flush()
        self._vae_on()
        out = []
        try:
            self._tiling(w, h)
            n = z.shape[0]
            for i in range(n):
                if ctx:
                    ctx.progress("decode", i, n, None)
                x = self.vae.decode(self._denorm(z[i : i + 1].to(self.device)).to(self.dtype)).sample
                x = ((x[0, :, 0].float().clamp(-1, 1) + 1) * 127.5).round().byte().permute(1, 2, 0).cpu().numpy()
                out.append(Image.fromarray(x))
            if ctx:
                ctx.progress("decode", n, n, None)
        finally:
            self._vae_off()
            mem.flush()
        return out

    def _preview(self, x0: torch.Tensor) -> Image.Image | None:
        return previews.wan_preview(x0, rgb_factors=RGB_FACTORS, rgb_bias=RGB_BIAS)

    @torch.no_grad()
    def sample(self, req: SampleRequest, ctx: RunContext) -> list[Image.Image]:
        ctx.check()
        self._ensure_models(req, ctx)
        self._apply_loras(req.loras, ctx)
        want = self._dit_dtype()
        if next(self.dit.parameters()).dtype != want:
            self.dit.to(want)
            self._cond.clear()
        ctx.check()

        self.last_latents = None
        lat_in = req.init_latents
        if lat_in is not None:
            lat_in = lat_in if lat_in.ndim == 5 else lat_in[:, :, None]
            lh, lw = lat_in.shape[-2:]
            w, h = lw * 8, lh * 8
            bs = lat_in.shape[0]
        else:
            w, h = req.width // 16 * 16, req.height // 16 * 16
            lw, lh = w // 8, h // 8
            bs = max(1, req.batch_size)
        cfg = float(req.cfg)
        use_cfg = abs(cfg - 1.0) > 1e-4
        conds = self._encode_prompts([req.prompt, req.negative or ""] if use_cfg else [req.prompt])
        L = max(c.shape[1] for c in conds)
        conds = [F.pad(c, (0, 0, 0, L - c.shape[1])) for c in conds]
        context = torch.cat([c.expand(bs, -1, -1) for c in conds], 0)

        sched = FlowSchedule(float(getattr(req, "shift", None) or DEFAULT_SHIFT))
        seed = int(req.seed) & 0xFFFFFFFFFFFFFFFF
        gen = torch.Generator().manual_seed(seed)
        noise = torch.randn((bs, 16, 1, lh, lw), generator=gen, dtype=torch.float32)
        if req.variation_seed is not None and req.phase == "sample":
            vg = torch.Generator().manual_seed(int(req.variation_seed) & 0xFFFFFFFFFFFFFFFF)
            noise = slerp(noise, torch.randn(noise.shape, generator=vg, dtype=torch.float32), float(req.variation_strength))
        noise = noise.to(self.device)

        orig = None
        mask = None
        denoise = 1.0
        if lat_in is not None:
            orig = lat_in.to(self.device, torch.float32)
            denoise = float(req.denoise)
        elif req.init_images:
            imgs = list(req.init_images)
            while len(imgs) < bs:
                imgs.append(imgs[-1])
            orig = self._vae_encode(imgs[:bs], w, h)
            denoise = float(req.denoise)
            if req.mask is not None:
                m = torch.from_numpy(np.asarray(req.mask.convert("L").resize((w, h), Image.BILINEAR)).copy()).float() / 255.0
                mask = F.interpolate(m[None, None], size=(lh, lw), mode="bilinear")[:, :, None].to(self.device)
        sigmas = sigmas_for(sched, req.scheduler, req.steps, denoise)
        if len(sigmas) < 2:
            return self._vae_decode(orig, w, h, ctx) if orig is not None and req.decode else []
        total = len(sigmas) - 1
        if orig is not None:
            x = sigmas[0].item() * noise + (1 - sigmas[0].item()) * orig
        else:
            x = noise * sigmas[0].item()
            orig = torch.zeros_like(noise) if mask is not None else None

        dit = self.dit
        ddt = [next(dit.parameters()).dtype]
        every = max(1, int(ctx.preview_every or 0)) if ctx.preview_every else 0
        rescale = float(req.cfg_rescale or 0.0)
        progress_phase = req.phase

        def model(xc: torch.Tensor, sigma: float, i: int) -> torch.Tensor:
            ctx.check()
            if dit.cache is not None:
                dit.cache.window(i, total)
            if mask is not None:
                xc = xc * mask + (sigma * noise + (1 - sigma) * orig) * (1 - mask)
            xin = torch.cat([xc, xc], 0) if use_cfg else xc
            t = torch.full((xin.shape[0],), sigma, device=self.device, dtype=torch.float32)
            v = dit(xin.to(ddt[0]), t, context.to(ddt[0])).float()
            if ddt[0] == torch.float16 and not torch.isfinite(v).all():
                log.warning("anima fp16 overflow, falling back to %s", self.dtype)
                self.fp16_ok = False
                dit.to(self.dtype)
                ddt[0] = self.dtype
                v = dit(xin.to(ddt[0]), t, context.to(ddt[0])).float()
            if use_cfg:
                vc, vu = v.chunk(2)
                v = vu + (vc - vu) * cfg
                if rescale > 0:
                    sc = vc.std(dim=(1, 2, 3, 4), keepdim=True)
                    sv = v.std(dim=(1, 2, 3, 4), keepdim=True)
                    v = rescale * (v * (sc / sv)) + (1 - rescale) * v
            d = xc - v * sigma
            if mask is not None:
                d = d * mask + orig * (1 - mask)
            prev = None
            if every and (i + 1) % every == 0 and i + 1 < total:
                try:
                    prev = self._preview(d)
                except Exception:
                    prev = None
            ctx.progress(progress_phase, i + 1, total, prev)
            return d

        # step_cache 1 light, 2 fast: relative change of block 0's residual still treated as unchanged
        level = int(req.step_cache)
        dit.cache = StepCache({1: 0.08, 2: 0.15}[min(level, 2)]) if level >= 1 else None
        try:
            x = sample(req.sampler, model, x, sigmas.to(torch.float32), sched, seed)
        finally:
            if dit.cache is not None:
                log.info("step cache reused %d of %d steps", dit.cache.hits, total)
            dit.cache = dit.cache_rest = None
        if mask is not None:
            x = x * mask + orig * (1 - mask)
        ctx.check()
        if req.keep_latents:
            self.last_latents = x.to("cpu", torch.float32)
        if not req.decode:
            return []
        return self._vae_decode(x, w, h, ctx)
