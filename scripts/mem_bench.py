import copy
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import psutil  # noqa: E402
import torch  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

from somnia.config import DATA_DIR, settings  # noqa: E402
from somnia.engine.base import RunContext  # noqa: E402

ILL = "checkpoint:waiIllustriousSDXL_v170.safetensors"
ANIMA = "checkpoint:animayume_v10BaseFinal.safetensors"
UPSCALER = "upscaler:4x-AnimeSharp.pth"
FACE = "detector:bbox/face_yolov8m.pt"
OUT = DATA_DIR / "smoke" / "bench"
PREV = DATA_DIR / "smoke" / "previews"


def smi_used() -> int:
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=5
        )
        return int(r.stdout.strip().splitlines()[0])
    except Exception:
        return -1


class Monitor:
    def __init__(self):
        self.proc = psutil.Process(os.getpid())
        self.stop = False
        self.rss = 0
        self.priv = 0
        self.smi = 0
        self.th = threading.Thread(target=self.loop, daemon=True)

    def loop(self):
        n = 0
        while not self.stop:
            mi = self.proc.memory_info()
            self.rss = max(self.rss, mi.rss)
            self.priv = max(self.priv, getattr(mi, "private", 0))
            if n % 4 == 0:
                self.smi = max(self.smi, smi_used())
            n += 1
            time.sleep(0.1)

    def __enter__(self):
        self.th.start()
        return self

    def __exit__(self, *a):
        self.stop = True
        self.th.join()


def ill_base(**kw) -> dict:
    from somnia.presets import illustrious_defaults

    p = illustrious_defaults()
    p.update(
        model=ILL,
        prompt="masterpiece, best quality, amazing quality, 1girl, solo, hatsune miku, aqua hair, twintails, smile, looking at viewer, upper body, cherry blossoms, outdoors, blue sky",
        width=1024,
        height=1536,
        steps=24,
        seed=1234,
        sampler="euler_a",
    )
    p["secondPass"]["enabled"] = False
    for d in p["detailers"]:
        d["enabled"] = False
    p.update(kw)
    return p


def anima_base(**kw) -> dict:
    from somnia.presets import anima_defaults

    p = anima_defaults()
    p.update(
        model=ANIMA,
        vae="vae:qwen_image_vae.safetensors",
        textEncoder="text_encoder:waiANIMA_v10Base10_txt.safetensors",
        prompt="masterpiece, best quality, safe, 1girl, solo, upper body, silver hair, blue eyes, school uniform, cherry blossoms, smile",
        width=896,
        height=1152,
        steps=24,
        seed=42,
    )
    p["secondPass"]["enabled"] = False
    for d in p["detailers"]:
        d["enabled"] = False
    p.update(kw)
    return p


def second(p: dict, upscaler: str | None) -> dict:
    p["secondPass"].update(enabled=True, upscaler=upscaler, scale=1.5, steps=12, denoise=0.55 if upscaler == "latent" else 0.35)
    return p


def face(p: dict) -> dict:
    p["detailers"] = [
        {"enabled": True, "detector": FACE, "confidence": 0.3, "denoise": 0.4, "steps": 16, "dilate": 4, "padding": 32, "blur": 4}
    ]
    return p


def make_upload(name: str, w: int, h: int) -> dict:
    up = DATA_DIR / "uploads"
    up.mkdir(parents=True, exist_ok=True)
    src = OUT / "ill_txt2img.png" if name == "ill" else OUT / "anima_txt2img.png"
    if src.exists():
        im = Image.open(src).convert("RGB").resize((w, h))
    else:
        im = Image.new("RGB", (w, h), (180, 200, 220))
    im.save(up / f"bench_{name}_init.png")
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).ellipse((w * 0.3, h * 0.1, w * 0.7, h * 0.45), fill=255)
    m.save(up / f"bench_{name}_mask.png")
    return {"imageId": f"bench_{name}_init", "maskId": f"bench_{name}_mask", "denoise": 0.75, "maskBlur": 4, "fill": "original"}


def scenarios() -> dict:
    return {
        "ill_txt2img": lambda: ill_base(),
        "ill_second_latent": lambda: second(ill_base(), "latent"),
        "ill_second_model": lambda: second(ill_base(), UPSCALER),
        "ill_second_face": lambda: face(second(ill_base(), UPSCALER)),
        "ill_inpaint": lambda: ill_base(prompt=ill_base()["prompt"] + ", cat ears", init=make_upload("ill", 1024, 1536)),
        "anima_txt2img": lambda: anima_base(),
        "anima_inpaint": lambda: anima_base(init=make_upload("anima", 896, 1152)),
        "switch_ill": lambda: ill_base(width=1024, height=1024, steps=12),
        "switch_anima": lambda: anima_base(steps=12),
        "switch_ill2": lambda: ill_base(width=1024, height=1024, steps=12),
    }


def run_one(name: str, params: dict, save_previews: bool) -> dict:
    from somnia.engine import pipeline
    from somnia.models import resolve

    steps: dict[str, list[float]] = {}
    last = {"t": None, "phase": None}
    nprev = {"n": 0}

    def progress(phase, step, total, preview, label=None):
        now = time.perf_counter()
        key = (phase, label)
        if last["phase"] == key and last["t"] is not None and step > 1:
            if not (label or "").startswith(("Upscaling", "Detecting", "Latent")):
                steps.setdefault(phase, []).append(now - last["t"])
        last["t"], last["phase"] = now, key
        if preview is not None and save_previews:
            PREV.mkdir(parents=True, exist_ok=True)
            preview.save(PREV / f"{name}_{phase}_{nprev['n']:03d}_{step}of{total}.jpg", quality=85)
            nprev["n"] += 1

    ctx = RunContext(progress=progress, is_cancelled=lambda: False, resolve=resolve, preview_every=2)
    torch.cuda.reset_peak_memory_stats()
    gc_rss = psutil.Process(os.getpid()).memory_info().rss
    box = {}
    t0 = time.perf_counter()
    with Monitor() as mon:

        def work():
            try:
                box["imgs"] = pipeline.run(copy.deepcopy(params), ctx)
            except BaseException as e:
                box["err"] = e

        th = threading.Thread(target=work)
        th.start()
        th.join()
    dt = time.perf_counter() - t0
    if "err" in box:
        import traceback

        traceback.print_exception(box["err"])
        return {"name": name, "error": str(box["err"])}
    OUT.mkdir(parents=True, exist_ok=True)
    box["imgs"][0].save(OUT / f"{name}.png")
    sps = {k: sum(v) / len(v) for k, v in steps.items() if k in ("sample", "second", "detail") and v}
    return {
        "name": name,
        "time": dt,
        "alloc": torch.cuda.max_memory_allocated() / 2**30,
        "reserved": torch.cuda.max_memory_reserved() / 2**30,
        "smi": mon.smi / 1024,
        "rss": mon.rss / 2**30,
        "priv": mon.priv / 2**30,
        "rss0": gc_rss / 2**30,
        "after_alloc": torch.cuda.memory_allocated() / 2**30,
        "sps": sps,
        "size": box["imgs"][0].size,
    }


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    s = settings()
    s.keepModelsLoaded = "--no-keep" not in sys.argv
    s.lowVram = "--lowvram" in sys.argv
    if "--no-opt" in sys.argv and hasattr(s, "nvidiaOptimizations"):
        s.nvidiaOptimizations = False
    sc = scenarios()
    names = args or list(sc)
    print(f"baseline nvidia-smi used: {smi_used()} MiB, keep={s.keepModelsLoaded}", flush=True)
    res = []
    for n in names:
        r = run_one(n, sc[n](), "--previews" in sys.argv)
        res.append(r)
        if "error" in r:
            print(f"{n:20s} ERROR {r['error'][:200]}", flush=True)
            continue
        sps = " ".join(f"{k}={v:.3f}s/it" for k, v in r["sps"].items())
        print(
            f"{n:20s} {r['time']:6.1f}s  alloc {r['alloc']:5.2f}G  reserved {r['reserved']:5.2f}G  smi {r['smi']:5.2f}G  "
            f"rss {r['rss']:5.2f}G priv {r['priv']:5.2f}G (start {r['rss0']:5.2f}G)  held {r['after_alloc']:5.2f}G  {sps}  {r['size']}",
            flush=True,
        )


if __name__ == "__main__":
    main()
