import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from somnia.config import COMFY_MODELS  # noqa: E402
from somnia.engine.base import RunContext, SampleRequest  # noqa: E402
from somnia.engine.anima import AnimaEngine  # noqa: E402

KIND_DIRS = {"checkpoint": ["unet", "checkpoints", "diffusion_models"], "text_encoder": ["text_encoders"], "vae": ["vae"], "lora": ["loras"]}


def resolve(mid: str) -> Path:
    kind, rel = mid.split(":", 1)
    for d in KIND_DIRS[kind]:
        p = COMFY_MODELS / d / rel
        if p.exists():
            return p
    raise FileNotFoundError(mid)


def main():
    args = dict(a.split("=", 1) for a in sys.argv[1:] if "=" in a)
    out = ROOT / "data" / "smoke"
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    def progress(phase, step, total, preview):
        if preview is not None and step <= total // 2:
            preview.save(out / "anima_preview.png")
        print(f"\r{phase} {step}/{total} {time.time() - t0:.1f}s", end="", flush=True)

    ctx = RunContext(progress=progress, is_cancelled=lambda: False, resolve=resolve, preview_every=2)
    eng = AnimaEngine()
    loras = [(args["lora"], float(args.get("lora_w", 1.0)))] if "lora" in args else []
    req = SampleRequest(
        model=args.get("model", "checkpoint:animayume_v10BaseFinal.safetensors"),
        prompt=args.get("prompt", "masterpiece, best quality, safe, 1girl, solo, full body, standing, silver hair, blue eyes, school uniform, cherry blossoms, smile"),
        negative=args.get("neg", "nsfw, worst quality, low quality, blurry, jpeg artifacts, bad anatomy, bad hands, watermark, text"),
        width=int(args.get("w", 1024)),
        height=int(args.get("h", 1024)),
        steps=int(args.get("steps", 30)),
        cfg=float(args.get("cfg", 4.5)),
        sampler=args.get("sampler", "er_sde"),
        scheduler=args.get("scheduler", "simple"),
        seed=int(args.get("seed", 42)),
        loras=loras,
        text_encoder=args.get("te", "text_encoder:waiANIMA_v10Base10_txt.safetensors"),
        vae=args.get("vae", "vae:qwen_image_vae.safetensors"),
    )
    imgs = eng.sample(req, ctx)
    name = args.get("name", "anima")
    imgs[0].save(out / f"{name}.png")
    print(f"\nsaved {out / (name + '.png')} in {time.time() - t0:.1f}s")
    if "i2i" in args:
        req.init_images = [imgs[0]]
        req.denoise = 0.5
        req.prompt = req.prompt.replace("silver hair", "red hair")
        req.seed += 1
        im2 = eng.sample(req, ctx)[0]
        im2.save(out / f"{name}_i2i.png")
        from PIL import Image, ImageDraw

        m = Image.new("L", imgs[0].size, 0)
        ImageDraw.Draw(m).ellipse((300, 100, 724, 600), fill=255)
        req.mask = m
        req.denoise = 1.0
        req.prompt = req.prompt.replace("red hair", "cat ears, green hair")
        im3 = eng.sample(req, ctx)[0]
        im3.save(out / f"{name}_inpaint.png")
        print("\nsaved i2i + inpaint")
    eng.unload()
    import torch

    print(f"\nafter unload: {torch.cuda.memory_allocated() / 2**20:.0f} MiB allocated")


if __name__ == "__main__":
    import threading

    th = threading.Thread(target=main)
    th.start()
    th.join()
