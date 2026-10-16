from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from PIL import Image


class Cancelled(Exception):
    pass


@dataclass
class SampleRequest:
    model: str
    prompt: str
    negative: str
    width: int
    height: int
    steps: int
    cfg: float
    sampler: str
    scheduler: str
    seed: int
    batch_size: int = 1
    clip_skip: int = 1
    loras: list[tuple[str, float]] = field(default_factory=list)
    vae: str | None = None
    text_encoder: str | None = None
    pag_scale: float = 0.0
    cfg_rescale: float = 0.0
    # img2img / inpaint: init images are already at width x height, mask is L mode (white = repaint)
    init_images: list[Image.Image] | None = None
    mask: Image.Image | None = None
    denoise: float = 1.0
    phase: str = "sample"
    # latent img2img: engine-space latents (cpu tensor, already at the target size); overrides init_images
    init_latents: Any = None
    # keep the final latents in engine.last_latents (cpu); decode=False skips vae decoding and returns []
    keep_latents: bool = False
    decode: bool = True


@dataclass
class RunContext:
    # progress(phase, step, total, preview, label=None) where preview is a PIL image or None
    progress: Callable[..., None]
    is_cancelled: Callable[[], bool]
    resolve: Callable[[str], Path]
    preview_every: int = 2

    def check(self) -> None:
        if self.is_cancelled():
            raise Cancelled()


class Engine(ABC):
    family: str
    supports_latents: bool = False
    # pixels per latent cell and the pixel multiple sizes must snap to
    latent_scale: int = 8
    size_multiple: int = 8
    last_latents: Any = None

    @abstractmethod
    def sample(self, req: SampleRequest, ctx: RunContext) -> list[Image.Image]:
        """txt2img when init_images is None, img2img when set, inpaint when mask is also set.
        must call ctx.progress per step (with a cheap preview every ctx.preview_every steps)
        and ctx.check() per step."""

    @abstractmethod
    def unload(self) -> None: ...

    def samplers(self) -> list[str]:
        return ["euler", "euler_a"]

    def schedulers(self) -> list[str]:
        return ["normal"]
