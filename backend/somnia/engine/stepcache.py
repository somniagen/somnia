from __future__ import annotations

import torch


class StepCache:
    """step cache. each step runs the model's cheap outer part, compares a probe tensor to the one from the last full
    step and when the relative l1 change stays under threshold the expensive inner part is reused. without a
    threshold it reuses on a fixed rhythm, max_skip steps after every full one"""

    def __init__(self, threshold: float | None, max_skip: int = 3):
        self.threshold = threshold
        self.max_skip = max_skip
        self.ref: torch.Tensor | None = None
        self.skipped = 0
        self.hits = 0
        # the sampler turns this off for steps that must run in full (composition forming, the last step)
        self.allow = False

    def window(self, i: int, total: int) -> None:
        self.allow = total * 0.2 <= i < total - 1

    def check(self, probe: torch.Tensor) -> bool:
        r = self.ref
        hit = (
            self.allow
            and r is not None
            and r.shape == probe.shape
            and self.skipped < self.max_skip
            and (self.threshold is None or ((probe - r).abs().mean() / r.abs().mean().clamp_min(1e-8)).item() < self.threshold)
        )
        if hit:
            self.skipped += 1
            self.hits += 1
        else:
            self.ref = probe
            self.skipped = 0
        return hit


def attach_unet(unet, cache: StepCache):
    """deepcache style for sdxl: the first down block is the probe, on a hit every deeper block returns what it gave on
    the last full step and only the last up block runs, on fresh skip connections. returns a detach function"""
    down0 = unet.down_blocks[0]
    deep = [*unet.down_blocks[1:], unet.mid_block, *unet.up_blocks[:-1]]
    state = {"hit": False}
    saved: dict[int, object] = {}
    orig = {}

    def probe_fwd(*a, **k):
        out = orig[id(down0)](*a, **k)
        state["hit"] = cache.check(out[0])
        return out

    def wrap(m):
        f = orig[id(m)]

        def fwd(*a, **k):
            if state["hit"] and id(m) in saved:
                return saved[id(m)]
            out = f(*a, **k)
            saved[id(m)] = out
            return out

        return fwd

    for m in [down0, *deep]:
        orig[id(m)] = m.forward
    down0.forward = probe_fwd
    for m in deep:
        m.forward = wrap(m)

    def detach():
        for m in [down0, *deep]:
            m.__dict__.pop("forward", None)
        saved.clear()

    return detach
