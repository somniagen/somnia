import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from somnia.engine.base import RunContext  # noqa: E402


# same seed twice per sampler (with live previews on, like the app) must give identical pixels
def main() -> None:
    from somnia import models
    from somnia.engine import pipeline
    from somnia.presets import illustrious_defaults

    ctx = RunContext(progress=lambda *a, **k: None, is_cancelled=lambda: False, resolve=models.resolve, preview_every=2)
    base = illustrious_defaults()
    base.update(
        model=sys.argv[1] if len(sys.argv) > 1 else "checkpoint:waiIllustriousSDXL_v170.safetensors",
        prompt="masterpiece, best quality, 1girl, solo, hatsune miku, smile, upper body",
        width=832,
        height=1216,
        steps=12,
        seed=1234,
    )
    ok = True
    for sampler in ("euler_a", "dpmpp_2m_sde", "euler"):
        digests = []
        for _ in range(2):
            p = dict(base, sampler=sampler)
            img = pipeline.run(p, ctx)[0]
            digests.append(hashlib.sha1(img.tobytes()).hexdigest()[:12])
        same = digests[0] == digests[1]
        ok &= same
        print(f"{sampler:13s} {'same' if same else 'DIFFERENT'} {digests}", flush=True)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
