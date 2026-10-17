from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from . import config

_NUM = (int, float)
PARAM_TYPES: dict[str, tuple] = {
    "steps": (int,),
    "cfg": _NUM,
    "sampler": (str,),
    "scheduler": (str,),
    "clipSkip": (int,),
    "cfgRescale": _NUM,
    "pag": (dict,),
    "vae": (str, type(None)),
    "width": (int,),
    "height": (int,),
}

_lock = threading.Lock()
_data: dict[str, dict] | None = None


def _file() -> Path:
    return config.DATA_DIR / "model_defaults.json"


def _load() -> dict[str, dict]:
    global _data
    if _data is None:
        try:
            _data = json.loads(_file().read_text("utf-8"))
        except Exception:
            _data = {}
    return _data


def _save() -> None:
    _file().write_text(json.dumps(_data or {}, indent=1), "utf-8")


def all_defaults() -> dict[str, dict]:
    with _lock:
        return json.loads(json.dumps(_load()))


def clean(body: dict) -> dict:
    out: dict = {}
    params = body.get("params")
    if isinstance(params, dict):
        p = {}
        for k, v in params.items():
            t = PARAM_TYPES.get(k)
            if t is None or isinstance(v, bool) and bool not in t or not isinstance(v, t):
                continue
            if k == "pag":
                if not isinstance(v.get("enabled"), bool) or not isinstance(v.get("scale"), _NUM):
                    continue
                v = {"enabled": v["enabled"], "scale": float(v["scale"])}
            p[k] = v
        if p:
            out["params"] = p
    w = body.get("weight")
    if isinstance(w, _NUM) and not isinstance(w, bool):
        out["weight"] = float(w)
    return out


def put(model_id: str, body: dict) -> dict | None:
    ent = clean(body)
    if not ent:
        return None
    ent["updatedAt"] = int(time.time() * 1000)
    with _lock:
        _load()[model_id] = ent
        _save()
    return ent


def delete(model_id: str) -> bool:
    with _lock:
        d = _load()
        if model_id not in d:
            return False
        del d[model_id]
        _save()
    return True
