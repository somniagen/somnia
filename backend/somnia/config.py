from __future__ import annotations

import functools
import json
import os
import sys
import threading
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
SETTINGS_FILE = DATA_DIR / "settings.json"

# where a comfyui install keeps its models, relative to a folder it may sit in (portable builds nest it)
_COMFY_GLOBS = ["ComfyUI*/models", "ComfyUI*/ComfyUI/models", "ComfyUI*/ComfyUI*/ComfyUI/models"]


def _fixed_drives() -> list[Path]:
    if sys.platform != "win32":
        return []
    import ctypes

    k = ctypes.windll.kernel32
    mask = k.GetLogicalDrives()
    # 3 = fixed disk, skips network and removable drives that can hang
    return [Path(f"{c}:\\") for i, c in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ") if mask >> i & 1 and k.GetDriveTypeW(f"{c}:\\") == 3]


@functools.lru_cache(maxsize=1)
def comfy_models() -> Path | None:
    # COMFYUI_MODELS or COMFYUI_PATH win, else the first comfyui install found next to somnia, in home or at a drive root
    for var, sub in (("COMFYUI_MODELS", ""), ("COMFYUI_PATH", "models")):
        v = os.environ.get(var)
        if v and (Path(v) / sub / "checkpoints").is_dir():
            return Path(v) / sub
    home = Path.home()
    for base in [ROOT.parent, home, home / "Documents", home / "Desktop", *_fixed_drives()]:
        for g in _COMFY_GLOBS:
            try:
                for m in sorted(base.glob(g)):
                    if (m / "checkpoints").is_dir():
                        return m
            except OSError:
                continue
    return None


def _default_roots() -> list[str]:
    roots = [str(ROOT / "models")]
    comfy = comfy_models()
    if comfy:
        roots.append(str(comfy))
    return roots


@dataclass
class Settings:
    lanEnabled: bool = False
    # salted scrypt hash, see auth.py; never sent to clients
    lanPassword: str = ""
    # tls cert and key paths (tailscale cert, mkcert); https is used when both exist
    httpsCert: str = ""
    httpsKey: str = ""
    port: int = 7865
    modelRoots: list[str] = field(default_factory=_default_roots)
    downloadRoot: str = str(ROOT / "models")
    outputDir: str = str(ROOT / "outputs")
    civitaiToken: str = ""
    # hugging face access token, needed for gated repos
    hfToken: str = ""
    showNsfw: bool = False
    # hash new local models in the background and look them up on civitai
    autoIdentify: bool = True
    previewEvery: int = 2
    keepModelsLoaded: bool = True
    lowVram: bool = False
    nvidiaOptimizations: bool = True
    # background removal model, see bgremove.MODELS
    bgModel: str = "toonout"
    # external image editor id from /api/editors, "" picks the first detected, "none" hides the button
    imageEditor: str = ""
    # manually added editors: [{"name": str, "path": str}]
    customEditors: list[dict] = field(default_factory=list)


_lock = threading.Lock()
_settings: Settings | None = None


def settings() -> Settings:
    global _settings
    with _lock:
        if _settings is None:
            s = Settings()
            if SETTINGS_FILE.exists():
                data = json.loads(SETTINGS_FILE.read_text("utf-8"))
                known = {f.name for f in fields(Settings)}
                for k, v in data.items():
                    if k in known:
                        setattr(s, k, v)
            _settings = s
        return _settings


def update_settings(**kw) -> Settings:
    s = settings()
    with _lock:
        known = {f.name for f in fields(Settings)}
        for k, v in kw.items():
            if k in known:
                setattr(s, k, v)
        SETTINGS_FILE.write_text(json.dumps(asdict(s), indent=2), "utf-8")
    return s
