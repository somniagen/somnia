from __future__ import annotations

import functools
import inspect
import math
import re
import threading
from dataclasses import dataclass, field

import torch
from PIL import Image

from ..config import settings
from ..presets import ILLUSTRIOUS_SAMPLERS as SAMPLERS
from ..presets import ILLUSTRIOUS_SCHEDULERS as SCHEDULERS
from . import mem, previews
from .base import Engine, RunContext, SampleRequest

HF_CACHE = str(previews.HF_CACHE)



def _sampler_cls(name: str):
    import diffusers as d

    table = {
        "euler": (d.EulerDiscreteScheduler, {}),
        "euler_a": (d.EulerAncestralDiscreteScheduler, {}),
        "heun": (d.HeunDiscreteScheduler, {}),
        "dpmpp_2m": (d.DPMSolverMultistepScheduler, {"algorithm_type": "dpmsolver++", "solver_order": 2}),
        "dpmpp_2m_sde": (d.DPMSolverMultistepScheduler, {"algorithm_type": "sde-dpmsolver++", "solver_order": 2}),
        "dpmpp_3m_sde": (d.DPMSolverMultistepScheduler, {"algorithm_type": "sde-dpmsolver++", "solver_order": 3}),
        "dpmpp_sde": (d.DPMSolverSDEScheduler, {}),
        "uni_pc": (d.UniPCMultistepScheduler, {}),
        "ddim": (d.DDIMScheduler, {}),
        "lcm": (d.LCMScheduler, {}),
    }
    return table.get(name, table["euler_a"])


_SCHED_KW = {
    "normal": {"timestep_spacing": "linspace"},
    "simple": {"timestep_spacing": "trailing"},
    "sgm_uniform": {"timestep_spacing": "trailing"},
    "karras": {"use_karras_sigmas": True},
    "exponential": {"use_exponential_sigmas": True},
    "beta": {"use_beta_sigmas": True},
}


def make_scheduler(base_config, sampler: str, scheduler: str):
    cls, kw = _sampler_cls(sampler)
    kw = dict(kw)
    accepted = set(inspect.signature(cls.__init__).parameters)
    extra = {k: v for k, v in _SCHED_KW.get(scheduler, {}).items() if k in accepted}
    if not extra and scheduler not in ("normal",):
        extra = {k: v for k, v in _SCHED_KW["normal"].items() if k in accepted}
    kw.update(extra)
    if "timestep_spacing" in accepted and "timestep_spacing" not in kw:
        kw["timestep_spacing"] = "linspace"
    return cls.from_config(base_config, **kw)


_re_attention = re.compile(r"\\\(|\\\)|\\\[|\\]|\\\\|\\|\(|\[|:\s*([+-]?[.\d]+)\s*\)|\)|]|[^\\()\[\]:]+|:")
_re_break = re.compile(r"\s*\bBREAK\b\s*", re.S)


def parse_attention(text: str) -> list[tuple[str, float]]:
    res: list[list] = []
    rb: list[int] = []
    sb: list[int] = []

    def mul(start: int, m: float) -> None:
        for p in range(start, len(res)):
            if res[p][1] >= 0:
                res[p][1] *= m

    for m in _re_attention.finditer(text):
        t = m.group(0)
        w = m.group(1)
        if t.startswith("\\"):
            res.append([t[1:], 1.0])
        elif t == "(":
            rb.append(len(res))
        elif t == "[":
            sb.append(len(res))
        elif w is not None and rb:
            try:
                mul(rb.pop(), float(w))
            except ValueError:
                pass
        elif t == ")" and rb:
            mul(rb.pop(), 1.1)
        elif t == "]" and sb:
            mul(sb.pop(), 1 / 1.1)
        else:
            for i, part in enumerate(_re_break.split(t)):
                if i > 0:
                    res.append(["", -1.0])
                if part:
                    res.append([part, 1.0])
    for p in rb:
        mul(p, 1.1)
    for p in sb:
        mul(p, 1 / 1.1)
    out: list[tuple[str, float]] = []
    for t, w in res:
        if out and out[-1][1] == w and w >= 0:
            out[-1] = (out[-1][0] + t, w)
        else:
            out.append((t, w))
    return out


_fix_vae = None


def _fp16_vae():
    global _fix_vae
    if _fix_vae is None:
        try:
            from diffusers import AutoencoderKL

            _fix_vae = AutoencoderKL.from_pretrained("madebyollin/sdxl-vae-fp16-fix", torch_dtype=torch.float16, cache_dir=HF_CACHE)
            _fix_vae.register_to_config(force_upcast=False)
        except Exception:
            _fix_vae = False
    return _fix_vae or None


def cap_vram(margin_mb: int = 384) -> None:
    if not torch.cuda.is_available():
        return
    free, total = torch.cuda.mem_get_info()
    frac = (free + torch.cuda.memory_reserved() - margin_mb * 2**20) / total
    torch.cuda.set_per_process_memory_fraction(min(1.0, max(0.3, frac)))


def _tile_count(vae, lat: torch.Tensor) -> int:
    if not getattr(vae, "use_tiling", False):
        return 1
    tl = vae.tile_latent_min_size
    if lat.shape[-1] <= tl and lat.shape[-2] <= tl:
        return 1
    ov = int(tl * (1 - vae.tile_overlap_factor))
    return math.ceil(lat.shape[-2] / ov) * math.ceil(lat.shape[-1] / ov)


@torch.no_grad()
def decode_latents(vae, latents: torch.Tensor, progress=None) -> list[Image.Image]:
    h, w = latents.shape[-2] * 8, latents.shape[-1] * 8
    big = w * h > 800 * 800
    out: list[Image.Image] = []
    n = latents.shape[0]
    state = {"k": 0, "total": 1}

    def hook(*_):
        state["k"] += 1
        if progress:
            progress(min(state["k"], state["total"]), state["total"])

    handle = vae.decoder.register_forward_hook(hook)
    try:
        for i in range(n):
            lat = latents[i : i + 1].to(vae.device) / vae.config.scaling_factor
            x = None
            for attempt in range(2):
                try:
                    if big or attempt:
                        vae.enable_tiling()
                    else:
                        vae.disable_tiling()
                    per = _tile_count(vae, lat)
                    state["k"], state["total"] = i * per, n * per
                    x = vae.decode(lat.to(vae.dtype)).sample
                    if vae.dtype == torch.float16 and not torch.isfinite(x).all():
                        del x
                        vae.to(torch.float32)
                        try:
                            x = vae.decode(lat.float()).sample
                        finally:
                            vae.to(torch.float16)
                    break
                except torch.OutOfMemoryError:
                    x = None
                    mem.flush()
                    if attempt:
                        raise
            x = (x[0].float() / 2 + 0.5).clamp(0, 1).mul(255).round().byte().permute(1, 2, 0).cpu().numpy()
            out.append(Image.fromarray(x))
            del x, lat
    finally:
        handle.remove()
        vae.disable_tiling()
    return out


def _x0(sched, out: torch.Tensor, t, x: torch.Tensor) -> torch.Tensor | None:
    pred = getattr(sched.config, "prediction_type", "epsilon")
    name = type(sched).__name__
    if getattr(sched, "step_index", 0) is None and hasattr(sched, "_init_step_index"):
        sched._init_step_index(t)
    if name in ("DPMSolverMultistepScheduler", "UniPCMultistepScheduler"):
        return sched.convert_model_output(out, sample=x)
    sigmas = getattr(sched, "sigmas", None)
    if sigmas is not None and getattr(sched, "step_index", None) is not None:
        sg = sigmas[min(sched.step_index, len(sigmas) - 1)].to(x.device, torch.float32)
        if pred == "v_prediction":
            return out * (-sg / (sg**2 + 1) ** 0.5) + x / (sg**2 + 1)
        return x - sg * out
    ac = getattr(sched, "alphas_cumprod", None)
    if ac is None:
        return None
    a = ac[int(t)].to(x.device, torch.float32)
    if pred == "v_prediction":
        return a.sqrt() * x - (1 - a).sqrt() * out
    return (x - (1 - a).sqrt() * out) / a.sqrt()


@dataclass
class _Loaded:
    id: str
    pipe: object
    base_vae: object
    vae_id: str | None = None
    loras: dict[str, str] = field(default_factory=dict)
    offload: bool = False
    te: list = field(default_factory=list)


class IllustriousEngine(Engine):
    family = "illustrious"
    supports_latents = True
    latent_scale = 8

    def __init__(self) -> None:
        self._cur: _Loaded | None = None
        self._vaes: dict[str, object] = {}
        self._cond: dict[tuple, tuple] = {}
        self._lock = threading.RLock()
        self.last_latents: torch.Tensor | None = None

    def samplers(self) -> list[str]:
        return list(SAMPLERS)

    def schedulers(self) -> list[str]:
        return list(SCHEDULERS)

    def loaded_model(self) -> str | None:
        return self._cur.id if self._cur else None

    def _free(self, ld: _Loaded | None) -> None:
        if ld is None:
            return
        try:
            if ld.offload:
                ld.pipe.remove_all_hooks()
        except Exception:
            pass
        ld.te.clear()
        ld.pipe = ld.base_vae = None
        mem.flush()

    def unload(self) -> None:
        with self._lock:
            self._free(self._cur)
            self._cur = None
            self._cond.clear()
            self._vaes.clear()
            self.last_latents = None
            if _fix_vae:
                _fix_vae.to("cpu")
            previews.unload()
            mem.flush()

    def _load(self, model_id: str, ctx: RunContext) -> _Loaded:
        from diffusers import StableDiffusionXLPipeline

        s = settings()
        cur = self._cur
        if cur and cur.id == model_id and cur.offload == bool(s.lowVram):
            return cur
        ctx.progress("load", 0, 1, None)
        self._free(cur)
        self._cur = None
        self._cond.clear()
        mem.flush()
        path = ctx.resolve(model_id)
        pipe = StableDiffusionXLPipeline.from_single_file(
            str(path), torch_dtype=torch.float16, cache_dir=HF_CACHE, use_safetensors=str(path).endswith(".safetensors")
        )
        pipe.set_progress_bar_config(disable=True)
        fix = _fp16_vae()
        if fix is not None:
            pipe.vae = fix
        ld = _Loaded(id=model_id, pipe=pipe, base_vae=pipe.vae)
        if s.lowVram:
            pipe.enable_model_cpu_offload()
            ld.offload = True
        else:
            pipe.unet.to("cuda")
            pipe.vae.to("cuda")
            ld.te = [mem.Parked(pipe.text_encoder), mem.Parked(pipe.text_encoder_2)]
            if not mem.tight():
                pipe.text_encoder.to("cuda")
                pipe.text_encoder_2.to("cuda")
                ld.te = []
        mem.flush()
        self._cur = ld
        ctx.progress("load", 1, 1, None)
        return ld

    def _set_vae(self, ld: _Loaded, vae_id: str | None, ctx: RunContext) -> None:
        if vae_id == ld.vae_id:
            return
        pipe = ld.pipe
        if not vae_id:
            pipe.vae = ld.base_vae
            self._vaes.clear()
        else:
            from diffusers import AutoencoderKL

            v = self._vaes.get(vae_id)
            if v is None:
                self._vaes.clear()
                mem.flush()
                v = AutoencoderKL.from_single_file(str(ctx.resolve(vae_id)), torch_dtype=torch.float16, cache_dir=HF_CACHE)
                self._vaes = {vae_id: v}
            pipe.vae = v
        dev = "cpu" if ld.offload else "cuda"
        pipe.vae.to(dev)
        if vae_id and ld.base_vae is not pipe.vae:
            ld.base_vae.to("cpu")
        ld.vae_id = vae_id
        mem.flush()

    def _set_loras(self, ld: _Loaded, loras: list[tuple[str, float]], ctx: RunContext) -> None:
        pipe = ld.pipe
        want: dict[str, float] = {}
        for lid, w in loras:
            if lid and w != 0:
                want[lid] = want.get(lid, 0.0) + float(w)
        if not want:
            if ld.loras:
                pipe.unload_lora_weights()
                ld.loras.clear()
                mem.flush()
            return
        drop = [lid for lid in ld.loras if lid not in want]
        if drop:
            pipe.delete_adapters([ld.loras.pop(lid) for lid in drop])
        for lid in want:
            if lid not in ld.loras:
                name = "l" + re.sub(r"[^a-zA-Z0-9_]", "_", lid)[-48:] + str(abs(hash(lid)) % 10000)
                pipe.load_lora_weights(str(ctx.resolve(lid)), adapter_name=name)
                ld.loras[lid] = name
        pipe.set_adapters([ld.loras[l] for l in want], adapter_weights=[want[l] for l in want])
        if drop:
            mem.flush()

    def _chunks(self, tok, text: str) -> list[tuple[list[int], list[float]]]:
        comma = tok.convert_tokens_to_ids(",</w>")
        chunks: list[tuple[list[int], list[float]]] = []
        ct: list[int] = []
        cw: list[float] = []
        last_comma = -1
        for frag, w in parse_attention(text):
            if w < 0:
                chunks.append((ct, cw))
                ct, cw, last_comma = [], [], -1
                continue
            ids = tok(frag, add_special_tokens=False, truncation=False).input_ids
            for t in ids:
                if len(ct) == 75:
                    if last_comma >= 0 and 75 - last_comma <= 20:
                        cut = last_comma + 1
                        chunks.append((ct[:cut], cw[:cut]))
                        ct, cw = ct[cut:], cw[cut:]
                    else:
                        chunks.append((ct, cw))
                        ct, cw = [], []
                    last_comma = -1
                ct.append(t)
                cw.append(w)
                if t == comma:
                    last_comma = len(ct) - 1
        if ct or not chunks:
            chunks.append((ct, cw))
        return chunks

    @torch.no_grad()
    def _encode_chunks(self, pipe, chunks, layer: int):
        tok = pipe.tokenizer
        dev = torch.device("cuda")
        embs = []
        pooled = None
        for ci, (t, w) in enumerate(chunks):
            pad_n = 75 - len(t)
            weights = torch.tensor([1.0] + w + [1.0] * (pad_n + 1), device=dev)
            hs = []
            for enc, tk in ((pipe.text_encoder, pipe.tokenizer), (pipe.text_encoder_2, pipe.tokenizer_2)):
                pad = tk.pad_token_id if tk.pad_token_id is not None else tk.eos_token_id
                ids = [tok.bos_token_id] + t + [tok.eos_token_id] + [pad] * pad_n
                out = enc(torch.tensor([ids], device=dev), output_hidden_states=True)
                hs.append(out.hidden_states[-layer])
                if enc is pipe.text_encoder_2 and ci == 0:
                    pooled = out[0]
                del out
            z = torch.cat(hs, dim=-1)
            if not torch.all(weights == 1):
                orig = z.float().mean()
                z = z * weights.reshape(1, -1, 1).to(z.dtype)
                z = z * (orig / z.float().mean()).to(z.dtype)
            embs.append(z)
        return embs, pooled

    def encode(self, ld: _Loaded, prompt: str, negative: str, clip_skip: int):
        layer = max(2, int(clip_skip or 2))
        key = (prompt, negative, layer, tuple(sorted(ld.loras.items())))
        hit = self._cond.get(key)
        if hit is not None:
            return hit
        pipe = ld.pipe
        for p in ld.te:
            p.gpu()
        try:
            pc = self._chunks(pipe.tokenizer, prompt)
            nc = self._chunks(pipe.tokenizer, negative)
            n = max(len(pc), len(nc))
            pc += [([], [])] * (n - len(pc))
            nc += [([], [])] * (n - len(nc))
            pe, pp = self._encode_chunks(pipe, pc, layer)
            ne, npool = self._encode_chunks(pipe, nc, layer)
        finally:
            for p in ld.te:
                p.park()
        res = (torch.cat(pe, dim=1), pp, torch.cat(ne, dim=1), npool)
        if len(self._cond) >= 8:
            self._cond.pop(next(iter(self._cond)))
        self._cond[key] = res
        return res

    def _pipe_for(self, base, kind: str, pag: bool):
        import diffusers as d

        cls = {
            ("txt", False): d.StableDiffusionXLPipeline,
            ("img", False): d.StableDiffusionXLImg2ImgPipeline,
            ("inp", False): d.StableDiffusionXLInpaintPipeline,
            ("txt", True): d.StableDiffusionXLPAGPipeline,
            ("img", True): d.StableDiffusionXLPAGImg2ImgPipeline,
            ("inp", True): d.StableDiffusionXLPAGInpaintPipeline,
        }[(kind, pag)]
        if cls is type(base):
            return base
        kw = {"pag_applied_layers": ["mid"]} if pag else {}
        p = cls.from_pipe(base, torch_dtype=torch.float16, **kw)
        p.set_progress_bar_config(disable=True)
        return p

    def sample(self, req: SampleRequest, ctx: RunContext) -> list[Image.Image]:
        with self._lock:
            return self._sample(req, ctx)

    def _sample(self, req: SampleRequest, ctx: RunContext) -> list[Image.Image]:
        ld = self._load(req.model, ctx)
        self._set_vae(ld, req.vae, ctx)
        self._set_loras(ld, req.loras, ctx)
        base = ld.pipe
        ctx.check()
        ctx.progress("encode", 0, 1, None)
        pe, pp, ne, npool = self.encode(ld, req.prompt, req.negative, req.clip_skip)
        self.last_latents = None

        init = req.init_images
        lat_in = req.init_latents
        if lat_in is not None:
            n = lat_in.shape[0]
            kind = "img"
            h, w = lat_in.shape[-2] * 8, lat_in.shape[-1] * 8
        else:
            n = len(init) if init and len(init) > 1 else max(1, req.batch_size)
            if init and len(init) == 1 and n > 1:
                init = init * n
            kind = "txt" if not init else ("inp" if req.mask is not None else "img")
            w = init[0].width if init else req.width
            h = init[0].height if init else req.height
            w, h = w // 8 * 8, h // 8 * 8
        pag = req.pag_scale > 0
        pipe = self._pipe_for(base, kind, pag)
        sched = make_scheduler(base.scheduler.config, req.sampler, req.scheduler)
        if hasattr(sched, "noise_sampler_seed"):
            # dpmpp_sde draws its brownian noise from this, not from the generators
            sched.noise_sampler_seed = int(req.seed)
        pipe.scheduler = sched

        if init and lat_in is None:
            init = [im.convert("RGB").resize((w, h), Image.LANCZOS) if im.size != (w, h) else im.convert("RGB") for im in init]
        if w * h > 1100 * 1100:
            base.vae.enable_tiling()
        else:
            base.vae.disable_tiling()

        gens = [torch.Generator("cpu").manual_seed(int(req.seed) + i) for i in range(n)]
        denoise = min(1.0, max(0.01, float(req.denoise)))
        steps = int(req.steps)
        if kind != "txt" and denoise < 1.0:
            steps = max(1, math.ceil(steps / denoise))
        every = max(1, int(ctx.preview_every or 1)) if ctx.preview_every else 0
        phase = req.phase
        held: dict = {"x0": None}
        if every:
            orig_step = sched.step

            # wraps keeps step's signature visible: diffusers only passes the seeded generator
            # to schedulers whose step() declares it, so a bare wrapper made ancestral and sde samplers random
            @functools.wraps(orig_step)
            def step(model_output, timestep, sample, *a, **k):
                try:
                    held["x0"] = _x0(sched, model_output, timestep, sample)
                except Exception:
                    held["x0"] = None
                return orig_step(model_output, timestep, sample, *a, **k)

            sched.step = step

        def cb(p, i, t, kw):
            ctx.check()
            total = getattr(p, "_num_timesteps", None) or req.steps
            prev = None
            if every and (i + 1) % every == 0 and i + 1 < total:
                try:
                    x0 = held["x0"]
                    prev = previews.sdxl_preview(x0 if x0 is not None else kw["latents"])
                except Exception:
                    prev = None
            held["x0"] = None
            ctx.progress(phase, i + 1, total, prev)
            return {}

        kw = dict(
            prompt_embeds=pe.repeat(n, 1, 1),
            negative_prompt_embeds=ne.repeat(n, 1, 1),
            pooled_prompt_embeds=pp.repeat(n, 1),
            negative_pooled_prompt_embeds=npool.repeat(n, 1),
            num_inference_steps=steps,
            guidance_scale=float(req.cfg),
            guidance_rescale=float(req.cfg_rescale or 0.0),
            generator=gens,
            num_images_per_prompt=1,
            callback_on_step_end=cb,
            callback_on_step_end_tensor_inputs=["latents"],
            output_type="latent",
        )
        if pag:
            kw["pag_scale"] = float(req.pag_scale)
        if kind == "txt":
            kw.update(width=w, height=h)
        elif kind == "img":
            img = lat_in.to("cuda", torch.float16) if lat_in is not None else init
            kw.update(image=img, strength=denoise)
        else:
            mask = req.mask.convert("L").resize((w, h), Image.LANCZOS)
            kw.update(image=init, mask_image=mask, strength=denoise, width=w, height=h)

        saved = base.unet.attn_processors if pag else None
        try:
            lat = pipe(**kw).images
        finally:
            if saved is not None:
                base.unet.set_attn_processor(saved)
            del kw, pipe
            held.clear()
            sched.__dict__.pop("step", None)
        ctx.check()
        if req.keep_latents:
            self.last_latents = lat.to("cpu", torch.float16)
        if not req.decode:
            del lat
            return []
        mem.flush()
        ctx.progress("decode", 0, 1, None)
        out = decode_latents(base.vae, lat, progress=lambda k, t: ctx.progress("decode", k, t, None))
        del lat
        mem.flush()
        for i, im in enumerate(out):
            im.info["seed"] = int(req.seed) + i
        return out
