from __future__ import annotations

import logging
from pathlib import Path

import torch
from safetensors import safe_open

log = logging.getLogger(__name__)

PAIRS = [
    (".lora_up.weight", ".lora_down.weight"),
    (".lora_B.weight", ".lora_A.weight"),
    (".lora.up.weight", ".lora.down.weight"),
    (".lora_linear_layer.up.weight", ".lora_linear_layer.down.weight"),
]


def dit_aliases(name: str) -> list[str]:
    b = name[: -len(".weight")]
    return [
        f"diffusion_model.{b}",
        f"lora_unet_{b.replace('.', '_')}",
        f"transformer.{b}",
        f"net.{b}",
        f"model.diffusion_model.{b}",
        f"lycoris_{b.replace('.', '_')}",
        b,
    ]


def te_aliases(name: str) -> list[str]:
    b = "model." + name[: -len(".weight")]
    u = b.replace(".", "_")
    return [
        f"lora_te_{u}",
        f"lora_te1_{u}",
        f"lora_te_{u[6:]}",
        f"text_encoder.{b}",
        f"text_encoders.qwen3_06b.transformer.{b}",
        f"qwen3_06b.transformer.{b}",
    ]


def read_lora(path: Path) -> dict[str, torch.Tensor]:
    out = {}
    with safe_open(str(path), framework="pt", device="cpu") as f:
        for k in f.keys():
            out[k] = f.get_tensor(k)
    return out


def lora_deltas(sd: dict[str, torch.Tensor], targets: dict[str, list[str]]) -> tuple[dict[str, tuple], int]:
    found: dict[str, tuple] = {}
    used = set()
    for name, aliases in targets.items():
        for a in aliases:
            hit = None
            for up_s, down_s in PAIRS:
                if a + up_s in sd and a + down_s in sd:
                    hit = (sd[a + up_s], sd[a + down_s], sd.get(a + ".alpha"))
                    used.update({a + up_s, a + down_s, a + ".alpha"})
                    break
            if hit is None and a + ".diff" in sd:
                hit = ("diff", sd[a + ".diff"])
                used.add(a + ".diff")
            if hit is not None:
                found[name] = hit
                break
    unused = [k for k in sd if k not in used and not k.endswith(".alpha") and "dora_scale" not in k]
    return found, len(unused)


@torch.no_grad()
def apply_delta(param: torch.Tensor, hit: tuple, strength: float) -> None:
    dev = param.device
    if isinstance(hit[0], str):
        param.add_((hit[1].to(dev, torch.float32) * strength).to(param.dtype))
        return
    up, down, alpha = hit
    up = up.to(dev, torch.float32)
    down = down.to(dev, torch.float32)
    rank = down.shape[0]
    scale = (float(alpha) / rank) if alpha is not None else 1.0
    w = torch.mm(up.flatten(1), down.flatten(1)).reshape(param.shape)
    param.add_((w * (scale * strength)).to(param.dtype))
