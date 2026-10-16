from __future__ import annotations

import glob
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from . import config

ICON_DIR = config.DATA_DIR / "editors"

_lock = threading.Lock()
_cache: tuple[float, list[dict]] | None = None


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _add(out: list[dict], name: str, path: str | Path | None) -> None:
    if not path:
        return
    p = Path(path)
    if not p.exists() or any(e["path"] == str(p) for e in out):
        return
    out.append({"id": _slug(name), "name": name, "path": str(p)})


def _windows() -> list[dict]:
    import winreg

    uninstall: list[tuple[str, str]] = []
    keys = (
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    )
    for root, path in keys:
        try:
            k = winreg.OpenKey(root, path)
        except OSError:
            continue
        for i in range(winreg.QueryInfoKey(k)[0]):
            try:
                sk = winreg.OpenKey(k, winreg.EnumKey(k, i))
                name = winreg.QueryValueEx(sk, "DisplayName")[0]
            except OSError:
                continue
            try:
                loc = winreg.QueryValueEx(sk, "InstallLocation")[0] or ""
            except OSError:
                loc = ""
            uninstall.append((str(name), str(loc)))

    def app_path(exe: str) -> str | None:
        for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                return winreg.QueryValue(winreg.OpenKey(root, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe}"), None)
            except OSError:
                pass
        return None

    pf = [os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")]
    out: list[dict] = []

    # photoshop: every installed version, newest first, shown without the "Adobe" prefix
    ps: dict[str, str] = {}
    for name, loc in uninstall:
        if name.startswith("Adobe Photoshop") and loc:
            ps[name] = os.path.join(loc, "Photoshop.exe")
    for base in pf:
        for d in glob.glob(os.path.join(base, "Adobe", "Adobe Photoshop*")):
            ps.setdefault(os.path.basename(d), os.path.join(d, "Photoshop.exe"))
    for name in sorted(ps, key=lambda n: [int(x) for x in re.findall(r"\d+", n)] or [0], reverse=True):
        _add(out, name.removeprefix("Adobe ").strip(), ps[name])

    krita = [os.path.join(loc, "bin", "krita.exe") for name, loc in uninstall if name.startswith("Krita") and loc]
    krita += [app_path("krita.exe") or ""] + [os.path.join(b, "Krita (x64)", "bin", "krita.exe") for b in pf]
    for k in krita:
        if k and Path(k).exists():
            _add(out, "Krita", k)
            break

    pdn = [app_path("paintdotnet.exe") or ""] + [os.path.join(b, "paint.net", "paintdotnet.exe") for b in pf]
    for p in pdn:
        if p and Path(p).exists():
            _add(out, "Paint.NET", p)
            break
    return out


def _mac() -> list[dict]:
    out: list[dict] = []
    apps = sorted(glob.glob("/Applications/Adobe Photoshop*/Adobe Photoshop*.app"), reverse=True)
    for a in apps:
        _add(out, Path(a).stem.removeprefix("Adobe ").strip(), a)
    _add(out, "Krita", "/Applications/krita.app")
    return out


def _linux() -> list[dict]:
    out: list[dict] = []
    _add(out, "Krita", shutil.which("krita"))
    return out


def _auto(force: bool) -> list[dict]:
    global _cache
    with _lock:
        if _cache and not force and time.monotonic() - _cache[0] < 300:
            return _cache[1]
        try:
            found = _windows() if sys.platform == "win32" else _mac() if sys.platform == "darwin" else _linux()
        except Exception:
            found = []
        _cache = (time.monotonic(), found)
        return found


def custom_id(path: str) -> str:
    return "custom-" + _slug(Path(path).stem)[:40]


def _custom() -> list[dict]:
    out = []
    for c in config.settings().customEditors or []:
        p = c.get("path") or ""
        if p and Path(p).exists():
            out.append({"id": custom_id(p), "name": c.get("name") or Path(p).stem, "path": p, "custom": True})
    return out


def detect(force: bool = False) -> list[dict]:
    auto = _auto(force)
    custom = [c for c in _custom() if all(a["path"].lower() != c["path"].lower() for a in auto)]
    return custom + auto


def product_name(path: str) -> str:
    # windows version info ProductName (e.g. "GIMP", "CLIP STUDIO PAINT"), else the file name
    p = Path(path)
    if sys.platform == "win32" and p.suffix.lower() == ".exe":
        try:
            import ctypes
            from ctypes import wintypes

            ver = ctypes.windll.version
            size = ver.GetFileVersionInfoSizeW(str(p), None)
            if size:
                buf = ctypes.create_string_buffer(size)
                if ver.GetFileVersionInfoW(str(p), 0, size, buf):
                    ptr = ctypes.c_void_p()
                    n = wintypes.UINT()
                    if ver.VerQueryValueW(buf, "\\VarFileInfo\\Translation", ctypes.byref(ptr), ctypes.byref(n)) and n.value >= 4:
                        lang, cp = ctypes.cast(ptr, ctypes.POINTER(ctypes.c_ushort * 2)).contents
                        names = []
                        for key in ("FileDescription", "ProductName"):
                            q = f"\\StringFileInfo\\{lang:04x}{cp:04x}\\{key}"
                            if ver.VerQueryValueW(buf, q, ctypes.byref(ptr), ctypes.byref(n)) and n.value > 1:
                                name = ctypes.wstring_at(ptr, n.value - 1).strip().removeprefix("Adobe ").strip()
                                if name and "operating system" not in name.lower():
                                    names.append(name)
                        if names:
                            return min(names, key=len)
        except Exception:
            pass
    return p.stem


def browse() -> str | None:
    # native open dialog on the machine somnia runs on
    import tkinter
    from tkinter import filedialog

    root = tkinter.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        types = [("Programs", "*.exe"), ("All files", "*.*")] if sys.platform == "win32" else [("All files", "*")]
        path = filedialog.askopenfilename(parent=root, title="Choose an image editor", filetypes=types)
    finally:
        root.destroy()
    return path or None


def current() -> dict | None:
    pick = config.settings().imageEditor
    found = detect()
    if pick == "none":
        return None
    auto = [e for e in found if not e.get("custom")] or found
    return next((e for e in found if e["id"] == pick), None) or (auto[0] if auto else None)


def _exe_icon(path: str, size: int = 128):
    # largest app icon from the executable via win32 (no subprocess), as an rgba pil image
    import ctypes
    from ctypes import wintypes

    from PIL import Image

    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    user32.GetDC.restype = wintypes.HDC
    user32.GetDC.argtypes = [wintypes.HWND]
    user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    user32.GetIconInfo.argtypes = [wintypes.HICON, ctypes.c_void_p]
    user32.DestroyIcon.argtypes = [wintypes.HICON]
    gdi32.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT, ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT]
    gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    hicon = wintypes.HICON()
    got = user32.PrivateExtractIconsW(path, 0, size, size, ctypes.byref(hicon), None, 1, 0)
    if got != 1 or not hicon:
        return None

    class ICONINFO(ctypes.Structure):
        _fields_ = [("fIcon", wintypes.BOOL), ("xHotspot", wintypes.DWORD), ("yHotspot", wintypes.DWORD),
                    ("hbmMask", wintypes.HBITMAP), ("hbmColor", wintypes.HBITMAP)]

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                    ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                    ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]

    info = ICONINFO()
    try:
        if not user32.GetIconInfo(hicon, ctypes.byref(info)) or not info.hbmColor:
            return None
        bih = BITMAPINFOHEADER(biSize=ctypes.sizeof(BITMAPINFOHEADER), biWidth=size, biHeight=-size, biPlanes=1, biBitCount=32)
        buf = ctypes.create_string_buffer(size * size * 4)
        dc = user32.GetDC(None)
        try:
            rows = gdi32.GetDIBits(dc, info.hbmColor, 0, size, buf, ctypes.byref(bih), 0)
        finally:
            user32.ReleaseDC(None, dc)
        if rows != size:
            return None
        im = Image.frombuffer("RGBA", (size, size), buf.raw, "raw", "BGRA", 0, 1)
        if im.getchannel("A").getextrema()[1] == 0:
            im.putalpha(255)
        return im.copy()
    finally:
        if info.hbmColor:
            gdi32.DeleteObject(info.hbmColor)
        if info.hbmMask:
            gdi32.DeleteObject(info.hbmMask)
        user32.DestroyIcon(hicon)


def icon(editor_id: str) -> Path | None:
    # app icon pulled from the executable once and cached as png (windows only)
    e = next((e for e in detect() if e["id"] == editor_id), None)
    if not e or sys.platform != "win32":
        return None
    ICON_DIR.mkdir(parents=True, exist_ok=True)
    out = ICON_DIR / f"{editor_id}.png"
    if out.exists():
        return out
    try:
        im = _exe_icon(e["path"])
    except Exception:
        im = None
    if im is None:
        return None
    bb = im.getchannel("A").getbbox()
    if bb:
        im = im.crop(bb)
    im.save(out, "PNG")
    return out


def open_file(editor: dict, path: Path) -> None:
    if sys.platform == "darwin":
        subprocess.Popen(["open", "-a", editor["path"], str(path)])
        return
    flags = 0
    if sys.platform == "win32":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen([editor["path"], str(path)], creationflags=flags, close_fds=True)
