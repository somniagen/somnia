from __future__ import annotations

import torch

from ..config import settings

_state: dict = {}


def enabled() -> bool:
    return torch.cuda.is_available() and bool(getattr(settings(), "nvidiaOptimizations", True))


def apply() -> bool:
    on = enabled()
    if _state.get("on") == on:
        return on
    _state["on"] = on
    if not torch.cuda.is_available():
        return False
    torch.backends.cuda.matmul.allow_tf32 = on
    torch.backends.cudnn.allow_tf32 = on
    torch.backends.cuda.matmul.allow_fp16_reduced_precision_reduction = True
    torch.backends.cuda.matmul.allow_bf16_reduced_precision_reduction = True
    if hasattr(torch.backends.cuda.matmul, "allow_fp16_accumulation"):
        torch.backends.cuda.matmul.allow_fp16_accumulation = on
    return on
