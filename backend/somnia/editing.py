from __future__ import annotations

import copy
import json
import logging
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

from PIL import Image
from PIL.PngImagePlugin import PngInfo

from . import config, editors, store
from .hub import hub

log = logging.getLogger(__name__)

EDIT_DIR = config.DATA_DIR / "editing"
IMAGES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".psd"}
POLL = 1.0
# editors take a while to start; until then a missing process is not a close
GRACE = 25.0

_lock = threading.Lock()
_sessions: dict[str, "Session"] = {}


def _running(exe: str) -> bool:
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        psapi = ctypes.windll.psapi
        k32 = ctypes.windll.kernel32
        k32.OpenProcess.restype = wintypes.HANDLE
        k32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        k32.CloseHandle.argtypes = [wintypes.HANDLE]
        pids = (wintypes.DWORD * 8192)()
        got = wintypes.DWORD()
        if not psapi.EnumProcesses(pids, ctypes.sizeof(pids), ctypes.byref(got)):
            return True
        want = str(Path(exe)).lower()
        buf = ctypes.create_unicode_buffer(1024)
        for pid in pids[: got.value // ctypes.sizeof(wintypes.DWORD)]:
            h = k32.OpenProcess(0x1000, False, pid)
            if not h:
                continue
            try:
                n = wintypes.DWORD(len(buf))
                if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)) and buf.value.lower() == want:
                    return True
            finally:
                k32.CloseHandle(h)
        return False
    target = exe
    if exe.endswith(".app"):
        target = Path(exe).stem
    try:
        return subprocess.run(["pgrep", "-f", target], capture_output=True).returncode == 0
    except OSError:
        return True


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


class Session:
    def __init__(self, sid: str, folder: Path, meta: dict):
        self.id = sid
        self.dir = folder
        self.meta = meta
        self.seen: dict[str, tuple[float, int]] = {}
        self.pending: dict[str, tuple[float, int]] = {}
        self.started = time.monotonic()
        self.misses = 0
        if "seen" in meta:
            self.seen = {k: tuple(v) for k, v in meta["seen"].items()}
        else:
            for f in self._images():
                st = f.stat()
                self.seen[f.name] = (st.st_mtime, st.st_size)
            meta["seen"] = self.seen

    def _images(self) -> list[Path]:
        return [
            f
            for f in self.dir.iterdir()
            if f.is_file() and f.suffix.lower() in IMAGES and not f.name.startswith((".", "~"))
        ]

    def save_meta(self) -> None:
        (self.dir / "session.json").write_text(json.dumps(self.meta), "utf-8")

    # a file counts as saved once it changed and then held still for one poll
    def scan(self, final: bool = False) -> None:
        for f in self._images():
            try:
                st = f.stat()
            except OSError:
                continue
            sig = (st.st_mtime, st.st_size)
            if self.seen.get(f.name) == sig:
                continue
            if final or self.pending.get(f.name) == sig:
                self.pending.pop(f.name, None)
                if self._import(f):
                    self.seen[f.name] = sig
                    self.meta["seen"] = self.seen
                    self.save_meta()
            else:
                self.pending[f.name] = sig

    def _import(self, f: Path) -> bool:
        try:
            with Image.open(f) as im:
                im.load()
                img = im.convert("RGBA" if "A" in im.getbands() else "RGB")
        except Exception as e:
            # half written or a format pillow cannot read; a later save gets another try
            log.info("edited file not readable yet: %s (%s)", f.name, e)
            return False
        item = _save_item(img, self.meta)
        self.meta["itemId"] = item["id"]
        self.save_meta()
        hub.broadcast({"type": "gallery_item", "item": item})
        return True

    def alive(self) -> bool:
        if time.monotonic() - self.started < GRACE:
            return True
        if _running(self.meta["editor"]["path"]):
            self.misses = 0
            return True
        self.misses += 1
        return self.misses < 3

    def run(self) -> None:
        try:
            while True:
                time.sleep(POLL)
                if not self.dir.exists():
                    return
                self.scan()
                if not self.alive():
                    self.scan(final=True)
                    shutil.rmtree(self.dir, ignore_errors=True)
                    return
        except Exception:
            log.exception("editing session %s failed", self.id)
        finally:
            with _lock:
                _sessions.pop(self.id, None)


def _save_item(img: Image.Image, meta: dict) -> dict:
    out = Path(config.settings().outputDir)
    thumbs = out / "thumbs"
    thumbs.mkdir(parents=True, exist_ok=True)
    src = store.get_gallery(meta["sourceId"]) if meta.get("sourceId") else None
    existing = store.get_gallery(meta["itemId"]) if meta.get("itemId") else None
    ed = meta["editor"]
    if existing:
        stem = existing["id"]
    else:
        seed = (src or {}).get("seed", 0)
        stem = time.strftime("%Y%m%d-%H%M%S") + f"-{seed}-edit-{_slug(ed['name'])}-{uuid.uuid4().hex[:4]}"
    params = copy.deepcopy((src or {}).get("params"))
    info = PngInfo()
    if params:
        info.add_text("somnia", json.dumps(params))
    info.add_text("software", ed["name"])
    img.save(out / f"{stem}.png", "PNG", pnginfo=info)
    th = img.convert("RGB")
    th.thumbnail((384, 384))
    th.save(thumbs / f"{stem}.webp", "WEBP", quality=80)
    v = store.now_ms()
    stack = (src.get("stackId") or src["id"]) if src else None
    item = {
        "id": stem,
        "url": f"/outputs/{stem}.png?v={v}",
        "thumbUrl": f"/outputs/thumbs/{stem}.webp?v={v}",
        "width": img.width,
        "height": img.height,
        "seed": (src or {}).get("seed", 0),
        "createdAt": existing["createdAt"] if existing else v,
        "updatedAt": v,
        "params": params,
        "stackId": existing.get("stackId") if existing else stack,
        "editedWith": {"id": ed["id"], "name": ed["name"]},
        "sourceId": meta.get("sourceId"),
    }
    store.add_gallery(item)
    return item


def _spawn(s: Session) -> None:
    with _lock:
        _sessions[s.id] = s
    threading.Thread(target=s.run, name=f"edit-{s.id}", daemon=True).start()


def start(editor: dict, src: Path, source: dict | None) -> str:
    sid = uuid.uuid4().hex[:10]
    folder = EDIT_DIR / sid
    folder.mkdir(parents=True, exist_ok=True)
    stem = re.sub(r"[^\w.-]+", "-", (source or {}).get("id") or src.stem)[:80]
    work = folder / f"{stem}-edit{src.suffix.lower() or '.png'}"
    shutil.copyfile(src, work)
    meta = {
        "editor": {"id": editor["id"], "name": editor["name"], "path": editor["path"]},
        "sourceId": source["id"] if source else None,
        "itemId": None,
        "file": work.name,
        "created": store.now_ms(),
    }
    s = Session(sid, folder, meta)
    s.save_meta()
    editors.open_file(editor, work)
    _spawn(s)
    return sid


# picks up sessions whose editor may still be open after a server restart
def resume() -> None:
    if not EDIT_DIR.exists():
        return
    for folder in EDIT_DIR.iterdir():
        mf = folder / "session.json"
        if not folder.is_dir():
            continue
        if not mf.exists():
            shutil.rmtree(folder, ignore_errors=True)
            continue
        try:
            meta = json.loads(mf.read_text("utf-8"))
        except ValueError:
            shutil.rmtree(folder, ignore_errors=True)
            continue
        if folder.name in _sessions:
            continue
        # saves made while the server was down differ from the stored signatures and get imported
        s = Session(folder.name, folder, meta)
        s.started = time.monotonic() - GRACE
        _spawn(s)
