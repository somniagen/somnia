import copy
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from somnia.engine.base import RunContext  # noqa: E402

COMFY = Path(r"D:\ComfyUI_windows_portable_nvidia_cu128\ComfyUI_windows_portable\ComfyUI\models")
FOLDERS = {
    "checkpoint": ["checkpoints", "unet", "diffusion_models"],
    "lora": ["loras"],
    "vae": ["vae"],
    "text_encoder": ["text_encoders"],
    "upscaler": ["upscale_models"],
    "detector": ["ultralytics"],
}


def resolve(mid: str) -> Path:
    try:
        from somnia import models

        return models.resolve(mid)
    except Exception:
        kind, rel = mid.split(":", 1)
        for f in FOLDERS[kind]:
            p = COMFY / f / rel
            if p.exists():
                return p
        raise FileNotFoundError(mid)


def main() -> None:
    from somnia.engine import pipeline
    from somnia.presets import illustrious_defaults

    out = ROOT / "data" / "smoke"
    out.mkdir(parents=True, exist_ok=True)
    last = {"t": 0.0}

    def progress(phase, step, total, preview):
        now = time.time()
        if now - last["t"] > 2 or step == total:
            last["t"] = now
            print(f"  {phase} {step}/{total}{' +preview' if preview else ''}", flush=True)

    ctx = RunContext(progress=progress, is_cancelled=lambda: False, resolve=resolve, preview_every=4)
    base = illustrious_defaults()
    base["model"] = "checkpoint:waiIllustriousSDXL_v170.safetensors"
    base["prompt"] = (
        "masterpiece, best quality, amazing quality, 1girl, solo, hatsune miku, (long twintails:1.1), aqua hair, "
        "smile, looking at viewer, upper body, cherry blossoms, outdoors, blue sky, detailed background"
    )
    base["seed"] = 1234

    runs = {} if "--hq-only" in sys.argv else {"base": base}
    hq = copy.deepcopy(base)
    hq["secondPass"]["enabled"] = True
    hq["detailers"][0]["enabled"] = True
    runs["hires_face"] = hq

    for name, params in runs.items():
        t = time.time()
        box: dict = {}

        def work(params=params):
            try:
                box["imgs"] = pipeline.run(params, ctx)
            except BaseException as e:
                box["err"] = e

        th = threading.Thread(target=work)
        th.start()
        th.join()
        if "err" in box:
            raise box["err"]
        imgs = box["imgs"]
        for i, im in enumerate(imgs):
            p = out / f"{name}_{i}.png"
            im.save(p)
            print(f"{name}: {im.size} seed={im.info.get('seed')} -> {p} ({time.time() - t:.1f}s)", flush=True)


if __name__ == "__main__":
    main()
