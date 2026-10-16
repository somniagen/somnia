from __future__ import annotations

import logging
import threading
import urllib.request

import torch
import torch.nn as nn
import torch.nn.functional as F
from PIL import Image

from ..config import DATA_DIR

log = logging.getLogger(__name__)

HF_CACHE = DATA_DIR / "hf"
TAEW_URL = "https://github.com/madebyollin/taehv/raw/main/safetensors/taew2_1.safetensors"
MAX_SIDE = 640
_lock = threading.Lock()
_models: dict[str, object] = {}
_failed: set[str] = set()


def _dev() -> str:
    return "cuda" if torch.cuda.is_available() else "cpu"


def taesd(repo: str = "madebyollin/taesdxl"):
    with _lock:
        if repo in _failed:
            return None
        m = _models.get(repo)
        if m is None:
            try:
                from diffusers import AutoencoderTiny

                m = AutoencoderTiny.from_pretrained(repo, torch_dtype=torch.float16, cache_dir=str(HF_CACHE))
                m.encoder = None
                m.to(_dev()).eval().requires_grad_(False)
            except Exception as e:
                log.warning("taesd unavailable (%s), using linear previews", e)
                _failed.add(repo)
                return None
            _models[repo] = m
        return m


def _conv(n_in: int, n_out: int, **kw) -> nn.Conv2d:
    return nn.Conv2d(n_in, n_out, 3, padding=1, **kw)


class _Clamp(nn.Module):
    def forward(self, x):
        return torch.tanh(x / 3) * 3


class _MemBlock(nn.Module):
    def __init__(self, n_in: int, n_out: int):
        super().__init__()
        self.conv = nn.Sequential(_conv(n_in * 2, n_out), nn.ReLU(inplace=True), _conv(n_out, n_out), nn.ReLU(inplace=True), _conv(n_out, n_out))
        self.skip = nn.Conv2d(n_in, n_out, 1, bias=False) if n_in != n_out else nn.Identity()
        self.act = nn.ReLU(inplace=True)

    def forward(self, x):
        return self.act(self.conv(torch.cat([x, torch.zeros_like(x)], 1)) + self.skip(x))


class _TGrow(nn.Module):
    def __init__(self, n_f: int):
        super().__init__()
        self.conv = nn.Conv2d(n_f, n_f, 1, bias=False)

    def forward(self, x):
        return self.conv(x)


def _taehv_decoder(latent_channels: int = 16) -> nn.Sequential:
    # single frame taehv decoder (time upscaling disabled, memory = zeros)
    n = [256, 128, 64, 64]
    return nn.Sequential(
        _Clamp(), _conv(latent_channels, n[0]), nn.ReLU(inplace=True),
        _MemBlock(n[0], n[0]), _MemBlock(n[0], n[0]), _MemBlock(n[0], n[0]), nn.Upsample(scale_factor=2), _TGrow(n[0]), _conv(n[0], n[1], bias=False),
        _MemBlock(n[1], n[1]), _MemBlock(n[1], n[1]), _MemBlock(n[1], n[1]), nn.Upsample(scale_factor=2), _TGrow(n[1]), _conv(n[1], n[2], bias=False),
        _MemBlock(n[2], n[2]), _MemBlock(n[2], n[2]), _MemBlock(n[2], n[2]), nn.Upsample(scale_factor=2), _TGrow(n[2]), _conv(n[2], n[3], bias=False),
        nn.ReLU(inplace=True), _conv(n[3], 3),
    )  # fmt: skip


def taew():
    key = "taew2_1"
    with _lock:
        if key in _failed:
            return None
        m = _models.get(key)
        if m is not None:
            return m
        try:
            from safetensors.torch import load_file

            path = HF_CACHE / "taehv" / "taew2_1.safetensors"
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                tmp = path.with_suffix(".part")
                urllib.request.urlretrieve(TAEW_URL, tmp)
                tmp.replace(path)
            sd = {k[len("decoder."):]: v for k, v in load_file(str(path)).items() if k.startswith("decoder.")}
            m = _taehv_decoder()
            own = m.state_dict()
            for k, v in own.items():
                if v.shape != sd[k].shape:
                    sd[k] = sd[k][-v.shape[0]:]
            m.load_state_dict(sd)
            m = m.to(_dev(), torch.float16).eval().requires_grad_(False)
        except Exception as e:
            log.warning("taew2.1 unavailable (%s), using linear previews", e)
            _failed.add(key)
            return None
        _models[key] = m
        return m


def to_pil(x: torch.Tensor, max_side: int = MAX_SIDE) -> Image.Image:
    h, w = x.shape[-2:]
    if max(h, w) > max_side:
        k = max_side / max(h, w)
        x = F.interpolate(x[None].float(), size=(max(1, int(h * k)), max(1, int(w * k))), mode="area")[0]
    x = x.float().clamp(0, 1).mul(255).round().byte().permute(1, 2, 0).cpu().numpy()
    img = Image.fromarray(x)
    s = max_side / max(img.size)
    if s < 1:
        img = img.resize((max(1, int(img.width * s)), max(1, int(img.height * s))), Image.BILINEAR)
    return img


def _shrink(lat: torch.Tensor, max_side: int) -> torch.Tensor:
    h, w = lat.shape[-2:]
    lim = max(8, max_side // 5)
    if max(h, w) <= lim:
        return lat
    s = lim / max(h, w)
    return F.interpolate(lat, size=(max(1, round(h * s)), max(1, round(w * s))), mode="area")


def _strips(fn, lat: torch.Tensor, max_px: int = 1_100_000, pad: int = 8) -> torch.Tensor:
    # decode in horizontal strips so big latents never spike vram; tiny vaes have a small receptive field
    h, w = lat.shape[-2:]
    rows = max(16, max_px // (w * 64))
    if rows >= h:
        return fn(lat)
    parts = []
    for y in range(0, h, rows):
        y0, y1 = max(0, y - pad), min(h, y + rows + pad)
        out = fn(lat[..., y0:y1, :])
        sc = out.shape[-2] // (y1 - y0)
        parts.append(out[..., (y - y0) * sc : (y - y0 + min(rows, h - y)) * sc, :])
    return torch.cat(parts, dim=-2)


@torch.no_grad()
def sdxl_preview(latents: torch.Tensor, max_side: int = MAX_SIDE) -> Image.Image | None:
    # latents: unet space (scaled) sdxl latents, ideally the predicted x0
    m = taesd()
    if m is None:
        return _linear(_shrink(latents[:1].float(), max_side)[0], _SDXL_RGB, None, max_side)
    lat = latents[:1].to(m.device, torch.float16)
    out = _strips(lambda z: m.decode(z).sample, lat)[0]
    return to_pil((out + 1) / 2, max_side)


@torch.no_grad()
def wan_preview(latents: torch.Tensor, max_side: int = MAX_SIDE, rgb_factors=None, rgb_bias=None) -> Image.Image | None:
    # latents: (b, 16, 1, h, w) normalized wan 2.1 latents, ideally the predicted x0
    m = taew()
    if m is None:
        if rgb_factors is None:
            return None
        lat = _shrink(latents[:1, :, 0].float(), max_side)
        return _linear(lat[0], torch.tensor(rgb_factors), torch.tensor(rgb_bias), max_side)
    lat = latents[:1, :, 0].to(next(m.parameters()).device, torch.float16)
    out = _strips(m, lat)[0]
    return to_pil(out, max_side)


_SDXL_RGB = torch.tensor(
    [[0.3651, 0.4232, 0.4341], [-0.2533, -0.0042, 0.1068], [0.1076, 0.1111, -0.0362], [-0.3165, -0.2492, -0.2188]]
)


def _linear(lat: torch.Tensor, factors: torch.Tensor, bias: torch.Tensor | None, max_side: int) -> Image.Image:
    rgb = torch.einsum("chw,cr->rhw", lat.float().cpu(), factors.float())
    if bias is not None:
        rgb = rgb + bias.float().view(3, 1, 1)
    img = to_pil((rgb + 1) / 2, 4096)
    s = max_side / max(img.size)
    return img.resize((max(1, int(img.width * s)), max(1, int(img.height * s))), Image.BILINEAR)


def unload() -> None:
    with _lock:
        _models.clear()
