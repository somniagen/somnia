from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
SETTINGS_FILE = DATA_DIR / "settings.json"

COMFY_MODELS = Path(r"D:\ComfyUI_windows_portable_nvidia_cu128\ComfyUI_windows_portable\ComfyUI\models")


def _default_roots() -> list[str]:
    roots = [str(ROOT / "models")]
    if COMFY_MODELS.exists():
        roots.append(str(COMFY_MODELS))
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
