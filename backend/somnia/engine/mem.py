from __future__ import annotations

import gc

import torch

from . import device


def flush() -> None:
    gc.collect()
    device.empty_cache()
    if device.is_cuda():
        try:
            torch._C._host_emptyCache()
        except Exception:
            pass


def vram_total() -> int:
    return device.total_memory()


def tight() -> bool:
    if device.unified():
        return False
    return vram_total() < 20 * 2**30


class Parked:
    """keeps a module's weights in (pinned) cpu memory and swaps them onto the gpu on demand.
    weights must not be modified in place while they are on the gpu."""

    def __init__(self, module: torch.nn.Module, pin: bool = True):
        self.m = module
        self.dev = device.get()
        self.pin = pin and device.is_cuda()
        self.cpu: dict[int, tuple[torch.Tensor, torch.Tensor]] = {}
        self.on_gpu = any(p.device.type == self.dev.type for p in module.parameters())

    def _tensors(self):
        yield from self.m.parameters()
        yield from self.m.buffers()

    def gpu(self) -> None:
        if self.on_gpu or not device.gpu():
            return
        for t in self._tensors():
            if t.device.type != self.dev.type:
                t.data = t.data.to(self.dev, non_blocking=self.pin)
        device.synchronize()
        self.on_gpu = True

    def park(self) -> None:
        keep: dict[int, tuple[torch.Tensor, torch.Tensor]] = {}
        for t in self._tensors():
            hit = self.cpu.get(id(t))
            if hit is not None and hit[1].shape == t.shape and hit[1].dtype == t.dtype:
                c = hit[1]
            elif t.device.type == "cpu" and (not self.pin or t.data.is_pinned()):
                c = t.data
            else:
                c = t.data.to("cpu")
                if self.pin:
                    try:
                        c = c.pin_memory()
                    except Exception:
                        self.pin = False
            keep[id(t)] = (t, c)
            t.data = c
        self.cpu = keep
        self.on_gpu = False
        device.empty_cache()
