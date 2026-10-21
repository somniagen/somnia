from __future__ import annotations

import functools
import os

import torch


@functools.lru_cache(maxsize=1)
def kind() -> str:
    # SOMNIA_DEVICE forces cuda / mps / cpu
    want = os.environ.get("SOMNIA_DEVICE", "").lower()
    if want in ("cuda", "mps", "cpu"):
        return want
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def get() -> torch.device:
    return torch.device(kind())


def is_cuda() -> bool:
    return kind() == "cuda"


def is_mps() -> bool:
    return kind() == "mps"


def gpu() -> bool:
    return kind() != "cpu"


def unified() -> bool:
    # apple silicon shares ram with the gpu, so parking weights in cpu memory only costs copies
    return is_mps()


def empty_cache() -> None:
    if is_cuda():
        torch.cuda.empty_cache()
    elif is_mps():
        torch.mps.empty_cache()


def synchronize() -> None:
    if is_cuda():
        torch.cuda.synchronize()
    elif is_mps():
        torch.mps.synchronize()


def total_memory() -> int:
    if is_cuda():
        return torch.cuda.get_device_properties(0).total_memory
    if is_mps():
        try:
            return int(torch.mps.recommended_max_memory())
        except Exception:
            return 0
    return 0


def free_memory() -> int:
    if is_cuda():
        return torch.cuda.mem_get_info()[0]
    if is_mps():
        try:
            return max(0, int(torch.mps.recommended_max_memory()) - int(torch.mps.driver_allocated_memory()))
        except Exception:
            return 0
    return 0


def half() -> torch.dtype:
    # fp16 everywhere a gpu is present, cpu matmuls in half are slow or missing
    return torch.float16 if gpu() else torch.float32


def bf16_ok() -> bool:
    if is_cuda():
        return torch.cuda.is_bf16_supported()
    if is_mps():
        # native bf16 needs macos 14, and m1/m2 still run it slower than fp16
        try:
            return torch.backends.mps.is_macos_or_newer(14, 0)
        except Exception:
            return False
    return False


def name() -> str:
    if is_cuda():
        return torch.cuda.get_device_name(0)
    if is_mps():
        return "Apple GPU (Metal)"
    return "CPU"
