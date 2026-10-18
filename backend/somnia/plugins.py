from __future__ import annotations

import importlib.util
import json
import re
import sys
import threading
import time
import traceback
import types
from pathlib import Path
from typing import Any, Callable

from fastapi import APIRouter, FastAPI

from . import config, jobs

PLUGINS_DIR = config.ROOT / "plugins"
STATE_FILE = config.DATA_DIR / "plugins.json"
PKG = "somnia_plugins"
POLL = 1.0
_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")

_lock = threading.RLock()
_plugins: dict[str, "Plugin"] = {}
_watcher: threading.Thread | None = None


def _broadcast(msg: dict) -> None:
    from .hub import hub

    hub.broadcast(msg)


# what a plugin's setup(ctx) gets; everything registered here is undone on unload
class Context:
    def __init__(self, plugin: "Plugin"):
        self.id = plugin.id
        self.dir = plugin.dir
        self.data_dir = config.DATA_DIR / "plugins" / plugin.id
        self.router = APIRouter()
        self.manifest = dict(plugin.manifest)
        self._cleanups: list[Callable[[], Any]] = []

    def log(self, *args: Any) -> None:
        print(f"[plugin {self.id}]", *args, flush=True)

    def broadcast(self, event: str, data: Any = None) -> None:
        _broadcast({"type": "plugin", "plugin": self.id, "event": event, "data": data})

    def on_cleanup(self, fn: Callable[[], Any]) -> None:
        self._cleanups.append(fn)

    def _hook(self, lst: list, fn: Callable) -> Callable:
        lst.append(fn)
        self.on_cleanup(lambda: fn in lst and lst.remove(fn))
        return fn

    def on_job_finish(self, fn: Callable[[dict, bool], Any]) -> Callable:
        # fn(job, drained) on the worker thread after every job (done, error or cancelled)
        return self._hook(jobs.on_finish, fn)

    def on_submit(self, fn: Callable[[dict], dict | None]) -> Callable:
        # fn(params) before jobs are queued; return a new params dict or mutate in place
        return self._hook(jobs.on_submit, fn)

    def thread(self, fn: Callable[[threading.Event], Any], name: str = "worker") -> threading.Event:
        # background loop; fn gets a stop event that is set on unload
        stop = threading.Event()
        threading.Thread(target=fn, args=(stop,), name=f"plugin-{self.id}-{name}", daemon=True).start()
        self.on_cleanup(stop.set)
        return stop

    def settings(self) -> dict:
        try:
            return json.loads((self.data_dir / "settings.json").read_text("utf-8"))
        except Exception:
            return {}

    def save_settings(self, data: dict) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "settings.json").write_text(json.dumps(data, indent=1), "utf-8")


class Plugin:
    def __init__(self, pid: str, d: Path):
        self.id = pid
        self.dir = d
        self.manifest: dict = {}
        self.module: types.ModuleType | None = None
        self.ctx: Context | None = None
        self.app: FastAPI | None = None
        self.error: str | None = None
        self.sig = ""
        self.loaded_at = 0

    @property
    def web_entry(self) -> Path | None:
        name = self.manifest.get("web") or "web/index.js"
        p = (self.dir / name).resolve()
        return p if p.is_file() and self.dir.resolve() in p.parents else None

    def info(self) -> dict:
        m = self.manifest
        web = self.web_entry
        return {
            "id": self.id,
            "name": str(m.get("name") or self.id),
            "version": str(m.get("version") or ""),
            "description": str(m.get("description") or ""),
            "enabled": _enabled(self.id),
            "loaded": self.loaded_at > 0,
            "error": self.error,
            "backend": (self.dir / "plugin.py").is_file(),
            "web": web.name if web else None,
            "rev": self.sig,
        }


def _state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text("utf-8"))
    except Exception:
        return {}


def _enabled(pid: str) -> bool:
    return bool(_state().get(pid, {}).get("enabled", True))


def set_enabled(pid: str, enabled: bool) -> dict | None:
    with _lock:
        s = _state()
        s.setdefault(pid, {})["enabled"] = bool(enabled)
        STATE_FILE.write_text(json.dumps(s, indent=1), "utf-8")
        p = _plugins.get(pid)
        if p is None:
            return None
        _unload(p)
        if enabled:
            _load(p)
    _changed()
    return p.info()


def _signature(d: Path) -> str:
    n, newest = 0, 0.0
    for f in d.rglob("*"):
        if "__pycache__" in f.parts or "node_modules" in f.parts:
            continue
        try:
            if f.is_file():
                n += 1
                newest = max(newest, f.stat().st_mtime)
        except OSError:
            continue
    return f"{n}-{int(newest * 1000)}"


def _manifest(d: Path) -> dict:
    try:
        m = json.loads((d / "plugin.json").read_text("utf-8"))
        return m if isinstance(m, dict) else {}
    except Exception:
        return {}


def _purge_modules(pid: str) -> None:
    name = f"{PKG}.{pid}"
    for k in [k for k in sys.modules if k == name or k.startswith(name + ".")]:
        del sys.modules[k]


def _unload(p: Plugin) -> None:
    if p.ctx is not None:
        fn = getattr(p.module, "teardown", None) if p.module else None
        if fn:
            try:
                fn(p.ctx)
            except Exception:
                p.ctx.log("teardown failed\n" + traceback.format_exc())
        for c in reversed(p.ctx._cleanups):
            try:
                c()
            except Exception:
                pass
    p.module = p.ctx = p.app = None
    p.loaded_at = 0
    _purge_modules(p.id)


def _load(p: Plugin) -> None:
    p.error = None
    p.manifest = _manifest(p.dir)
    entry = p.dir / "plugin.py"
    if not entry.is_file():
        p.loaded_at = time.time()
        return
    if PKG not in sys.modules:
        pkg = types.ModuleType(PKG)
        pkg.__path__ = []
        sys.modules[PKG] = pkg
    name = f"{PKG}.{p.id}"
    ctx = p.ctx = Context(p)
    try:
        spec = importlib.util.spec_from_file_location(name, entry, submodule_search_locations=[str(p.dir)])
        assert spec and spec.loader
        mod = p.module = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
        fn = getattr(mod, "setup", None)
        if fn:
            fn(ctx)
        app = FastAPI(title=f"plugin {p.id}", docs_url=None, redoc_url=None, openapi_url=None)
        app.include_router(ctx.router)
        r = getattr(mod, "router", None)
        if isinstance(r, APIRouter) and r is not ctx.router:
            app.include_router(r)
        p.app = app
        p.loaded_at = time.time()
        ctx.log("loaded")
    except Exception as e:
        tb = traceback.format_exc()
        print(f"[plugin {p.id}] failed to load\n{tb}", file=sys.stderr, flush=True)
        _unload(p)
        p.error = f"{type(e).__name__}: {e}"


def _discover() -> dict[str, Path]:
    out: dict[str, Path] = {}
    if not PLUGINS_DIR.is_dir():
        return out
    for d in sorted(PLUGINS_DIR.iterdir()):
        if d.is_dir() and (d / "plugin.json").is_file() and _ID.match(d.name):
            out[d.name] = d
    return out


def _changed() -> None:
    _broadcast({"type": "plugins", "plugins": list_plugins()})


def scan() -> bool:
    # loads new plugins, reloads changed ones, unloads removed ones; True when anything changed
    changed = False
    with _lock:
        found = _discover()
        for pid in [k for k in _plugins if k not in found]:
            _unload(_plugins.pop(pid))
            changed = True
        for pid, d in found.items():
            sig = _signature(d)
            p = _plugins.get(pid)
            if p is not None and p.sig == sig:
                continue
            if p is None:
                p = _plugins[pid] = Plugin(pid, d)
            else:
                _unload(p)
            p.sig = sig
            p.manifest = _manifest(d)
            if _enabled(pid):
                _load(p)
            changed = True
    if changed:
        _changed()
    return changed


def reload(pid: str) -> dict | None:
    with _lock:
        p = _plugins.get(pid)
        if p is None:
            return None
        _unload(p)
        p.sig = _signature(p.dir)
        if _enabled(pid):
            _load(p)
    _changed()
    return p.info()


def list_plugins() -> list[dict]:
    with _lock:
        return [p.info() for p in _plugins.values()]


def get(pid: str) -> Plugin | None:
    return _plugins.get(pid)


def _watch() -> None:
    while True:
        time.sleep(POLL)
        try:
            scan()
        except Exception:
            traceback.print_exc()


def start() -> None:
    global _watcher
    PLUGINS_DIR.mkdir(exist_ok=True)
    scan()
    if _watcher is None:
        _watcher = threading.Thread(target=_watch, name="plugin-watch", daemon=True)
        _watcher.start()


# asgi app mounted at /api/ext, forwards /api/ext/{id}/... to that plugin's routes
class Dispatch:
    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            return
        path = scope.get("path", "")
        root = scope.get("root_path", "")
        rest = path[len(root):] if root and path.startswith(root) else path
        pid, _, sub = rest.lstrip("/").partition("/")
        p = _plugins.get(pid)
        app = p.app if p else None
        if app is None:
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 4404})
                return
            body = b'{"detail":"plugin not loaded"}'
            await send({"type": "http.response.start", "status": 404,
                        "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
            await send({"type": "http.response.body", "body": body})
            return
        child = dict(scope)
        child["root_path"] = f"{root}/{pid}"
        child["path"] = f"{root}/{pid}/{sub}"
        await app(child, receive, send)
