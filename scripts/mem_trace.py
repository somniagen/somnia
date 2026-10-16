import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

import torch  # noqa: E402

from mem_bench import scenarios  # noqa: E402
from somnia.config import settings  # noqa: E402
from somnia.engine.base import RunContext  # noqa: E402


def main():
    from somnia.engine import pipeline
    from somnia.models import resolve

    settings().keepModelsLoaded = True
    sc = scenarios()
    import os
    import time

    import psutil

    proc = psutil.Process(os.getpid())
    mon = {"rss": 0}

    def watch():
        while True:
            mon["rss"] = max(mon["rss"], proc.memory_info().rss)
            time.sleep(0.05)

    threading.Thread(target=watch, daemon=True).start()
    for name in sys.argv[1:]:
        last = {"k": None}

        def progress(phase, step, total, preview=None, label=None):
            k = (phase, label)
            if k != last["k"]:
                g = 2**30
                print(
                    f"  {str(last['k']):40s} peak {torch.cuda.max_memory_allocated() / g:5.2f}G res {torch.cuda.max_memory_reserved() / g:5.2f}G"
                    f" now {torch.cuda.memory_allocated() / g:5.2f}G rss {mon['rss'] / g:5.2f}G uss {proc.memory_full_info().uss / g:5.2f}G"
                    "",
                    flush=True,
                )
                mon["rss"] = 0
                torch.cuda.reset_peak_memory_stats()
                last["k"] = k

        ctx = RunContext(progress=progress, is_cancelled=lambda: False, resolve=resolve, preview_every=2)
        print(name, flush=True)
        torch.cuda.reset_peak_memory_stats()
        th = threading.Thread(target=lambda: pipeline.run(sc[name](), ctx))
        th.start()
        th.join()
        progress("end", 0, 0)


if __name__ == "__main__":
    main()
