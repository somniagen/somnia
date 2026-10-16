import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

import torch  # noqa: E402

from mem_bench import anima_base, ill_base  # noqa: E402
from somnia.config import settings  # noqa: E402
from somnia.engine.base import RunContext  # noqa: E402


def timed(params: dict) -> float:
    from somnia.engine import pipeline
    from somnia.models import resolve

    ts: list[float] = []

    def progress(phase, step, total, preview=None, label=None):
        if phase == "sample":
            ts.append(time.perf_counter())

    ctx = RunContext(progress=progress, is_cancelled=lambda: False, resolve=resolve, preview_every=0)
    box = {}
    th = threading.Thread(target=lambda: box.update(r=pipeline.run(params, ctx)))
    th.start()
    th.join()
    d = [b - a for a, b in zip(ts[2:], ts[3:])]
    return sum(d) / max(1, len(d))


def flags(tf32=False, fp16acc=False, bench=False):
    torch.backends.cuda.matmul.allow_tf32 = tf32
    torch.backends.cudnn.allow_tf32 = tf32
    torch.backends.cuda.matmul.allow_fp16_accumulation = fp16acc
    torch.backends.cudnn.benchmark = bench


def channels_last(on: bool):
    from somnia.engine import pipeline

    e = pipeline._engines.get("illustrious")
    if e and e._cur:
        fmt = torch.channels_last if on else torch.contiguous_format
        e._cur.pipe.unet.to(memory_format=fmt)
        e._cur.pipe.vae.to(memory_format=fmt)


def main():
    s = settings()
    s.keepModelsLoaded = True
    s.nvidiaOptimizations = False
    fams = [a for a in sys.argv[1:] if not a.startswith("-")] or ["illustrious", "anima"]
    configs = [
        ("baseline", dict()),
        ("tf32", dict(tf32=True)),
        ("tf32+fp16acc", dict(tf32=True, fp16acc=True)),
        ("tf32+fp16acc+cudnnbench", dict(tf32=True, fp16acc=True, bench=True)),
    ]
    for fam in fams:
        mk = (lambda: ill_base(width=1024, height=1024, steps=14)) if fam == "illustrious" else (lambda: anima_base(steps=12))
        flags()
        timed(mk())
        for name, kw in configs:
            flags(**kw)
            print(f"{fam:12s} {name:28s} {timed(mk()):.3f} s/it", flush=True)
        if fam == "illustrious":
            flags(tf32=True, fp16acc=True)
            channels_last(True)
            print(f"{fam:12s} {'tf32+fp16acc+channels_last':28s} {timed(mk()):.3f} s/it", flush=True)
            channels_last(False)


if __name__ == "__main__":
    main()
