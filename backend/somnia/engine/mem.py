from __future__ import annotations

import gc

import torch


def flush() -> None:
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        try:
            torch._C._host_emptyCache()
        except Exception:
            pass


def vram_total() -> int:
    if not torch.cuda.is_available():
        return 0
    return torch.cuda.get_device_properties(0).total_memory


def tight() -> bool:
    return vram_total() < 20 * 2**30


class Parked:
    """keeps a module's weights in (pinned) cpu memory and swaps them onto the gpu on demand.
    weights must not be modified in place while they are on the gpu."""

    def __init__(self, module: torch.nn.Module, pin: bool = True):
        self.m = module
        self.pin = pin and torch.cuda.is_available()
        self.cpu: dict[int, tuple[torch.Tensor, torch.Tensor]] = {}
        self.on_gpu = any(p.device.type == "cuda" for p in module.parameters())

    def _tensors(self):
        yield from self.m.parameters()
        yield from self.m.buffers()

    def gpu(self) -> None:
        if self.on_gpu or not torch.cuda.is_available():
            return
        for t in self._tensors():
            if t.device.type != "cuda":
                t.data = t.data.to("cuda", non_blocking=True)
        torch.cuda.current_stream().synchronize()
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
        torch.cuda.empty_cache()
