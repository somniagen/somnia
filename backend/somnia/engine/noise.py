from __future__ import annotations

import torch


def slerp(a: torch.Tensor, b: torch.Tensor, t: float) -> torch.Tensor:
    # per sample spherical interpolation between two noise tensors (a1111 style variation seeds)
    if t <= 0:
        return a
    if t >= 1:
        return b
    x, y = a.flatten(1).float(), b.flatten(1).float().to(a.device)
    xn = x / x.norm(dim=1, keepdim=True).clamp(min=1e-8)
    yn = y / y.norm(dim=1, keepdim=True).clamp(min=1e-8)
    dot = (xn * yn).sum(1, keepdim=True).clamp(-1, 1)
    om = torch.acos(dot)
    so = torch.sin(om)
    res = torch.where(
        dot.abs() > 0.9995,
        (1 - t) * x + t * y,
        (torch.sin((1 - t) * om) / so.clamp(min=1e-8)) * x + (torch.sin(t * om) / so.clamp(min=1e-8)) * y,
    )
    return res.reshape(a.shape).to(a.dtype)
