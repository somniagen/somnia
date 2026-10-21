from __future__ import annotations

import torch

from ..config import settings
from . import device

_state: dict = {}

# torch._C._SDPBackend values
_MATH, _FLASH, _EFFICIENT, _CUDNN, _OVERRIDE = 0, 1, 2, 3, 4


def enabled() -> bool:
    return device.is_cuda() and bool(getattr(settings(), "nvidiaOptimizations", True))


def _sdpa_order(order: list[int]) -> None:
    try:
        torch._C._set_sdp_priority_order(order)
    except Exception:
        pass


def apply() -> bool:
    on = enabled()
    if _state.get("on") == on:
        return on
    _state["on"] = on
    if not device.is_cuda():
        return False
    torch.backends.cuda.matmul.allow_tf32 = on
    torch.backends.cudnn.allow_tf32 = on
    torch.backends.cuda.matmul.allow_fp16_reduced_precision_reduction = True
    torch.backends.cuda.matmul.allow_bf16_reduced_precision_reduction = True
    if hasattr(torch.backends.cuda.matmul, "allow_fp16_accumulation"):
        torch.backends.cuda.matmul.allow_fp16_accumulation = on
    # windows wheels ship without flash attention and cudnn attention is ~1.6x faster than mem efficient on ampere+,
    # unsupported shapes and older cards fall through to the next backend
    _sdpa_order([_FLASH, _CUDNN, _EFFICIENT, _MATH, _OVERRIDE] if on else [_FLASH, _EFFICIENT, _MATH, _CUDNN, _OVERRIDE])
    return on
