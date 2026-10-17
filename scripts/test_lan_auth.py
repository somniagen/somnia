# lan password, auth cookie, public pwa assets and push (mocked), in process with a fake lan client

import asyncio
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

tmp = Path(tempfile.mkdtemp(prefix="somnia-auth-test-"))
os.environ["SOMNIA_DB"] = str(tmp / "test.db")

import httpx
from PIL import Image

from somnia import config

config.DATA_DIR = tmp
config.SETTINGS_FILE = tmp / "settings.json"
config._settings = config.Settings(outputDir=str(tmp / "outputs"), lanEnabled=True)

import somnia.app as appmod
from somnia import auth, push

dist = tmp / "dist"
shutil.copytree(ROOT / "web" / "public", dist)
(dist / "index.html").write_text("<!doctype html><title>Somnia</title>", "utf-8")
(dist / "assets").mkdir()
(dist / "assets" / "app.js").write_text("export {}", "utf-8")
appmod.DIST = dist

sent: list[dict] = []


class FakeResp:
    def __init__(self, code):
        self.status_code = code


def fake_webpush(sub, data, **kw):
    if sub["endpoint"].endswith("/gone"):
        raise push.WebPushException("gone", response=FakeResp(410))
    sent.append({"endpoint": sub["endpoint"], "data": data, "kw": kw})


push.webpush = fake_webpush
app = appmod.create_app()
LAN = ("192.168.1.5", 1234)


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        sys.exit(1)


async def ws_try(cookie: str | None, client=LAN) -> list[dict]:
    headers = [(b"host", b"t")]
    if cookie:
        headers.append((b"cookie", f"{auth.COOKIE}={cookie}".encode()))
    scope = {"type": "websocket", "path": "/ws", "raw_path": b"/ws", "query_string": b"", "headers": headers,
             "client": client, "server": ("t", 80), "scheme": "ws", "root_path": "", "subprotocols": [],
             "asgi": {"version": "3.0"}}
    inbox: asyncio.Queue = asyncio.Queue()
    inbox.put_nowait({"type": "websocket.connect"})
    out: list[dict] = []
    got = asyncio.Event()

    async def receive():
        return await inbox.get()

    async def send(m):
        out.append(m)
        if m["type"] in ("websocket.send", "websocket.close"):
            got.set()

    task = asyncio.create_task(app(scope, receive, send))
    await asyncio.wait_for(got.wait(), 5)
    inbox.put_nowait({"type": "websocket.disconnect", "code": 1000})
    try:
        await asyncio.wait_for(task, 5)
    except Exception:
        task.cancel()
    return out


async def main():
    local = httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 5555)), base_url="http://t")
    lan = httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=LAN), base_url="http://t")

    r = await lan.get("/api/state")
    check(r.status_code == 200, "no password: lan client allowed")
    check((await lan.get("/api/auth")).json() == {"required": False, "ok": True}, "no password: auth not required")

    r = await local.patch("/api/settings", json={"lanPassword": "hunter2"})
    check(r.status_code == 200 and r.json()["lanPassword"] == "****", "password set, masked in response")
    stored = config.settings().lanPassword
    check(stored.startswith("scrypt$") and "hunter2" not in stored, "password stored as salted hash")
    check((await local.get("/api/settings")).json()["lanPassword"] == "****", "GET settings masks password")
    r = await local.patch("/api/settings", json={"lanPassword": "****"})
    check(config.settings().lanPassword == stored, "patching the mask keeps the password")

    for path in ("/api/state", "/api/settings", "/outputs/x.png", "/files/uploads/x.png", "/api/push/key"):
        r = await lan.get(path)
        check(r.status_code == 401, f"lan without cookie: {path} -> 401")
    out = await ws_try(None)
    check(any(m["type"] == "websocket.close" and m.get("code") == 4401 for m in out), "lan ws without cookie closes 4401")

    for path, ct in (("/", "text/html"), ("/sw.js", "javascript"), ("/manifest.webmanifest", "application/manifest+json"),
                     ("/icons/icon-512.png", "image/png"), ("/assets/app.js", "javascript"), ("/favicon.svg", "image/svg")):
        r = await lan.get(path)
        check(r.status_code == 200 and ct in r.headers["content-type"], f"public without cookie: {path} ({r.headers['content-type']})")
    r = await lan.get("/sw.js")
    check(r.headers.get("service-worker-allowed") == "/" and "no-cache" in r.headers.get("cache-control", ""), "sw.js headers")
    check((await lan.get("/#/settings")).status_code == 200 and (await lan.get("/gallery")).status_code == 200, "spa route still served")

    check((await lan.get("/api/auth")).json() == {"required": True, "ok": False}, "auth status: required, not ok")
    check((await local.get("/api/auth")).json() == {"required": False, "ok": True}, "loopback never needs a password")
    check((await local.get("/api/state")).status_code == 200, "loopback allowed without cookie")

    t0 = time.monotonic()
    r = await lan.post("/api/auth/login", json={"password": "nope"})
    check(r.status_code == 401 and time.monotonic() - t0 >= 0.9, "wrong password: 401 after a delay")
    check(auth.COOKIE not in lan.cookies, "wrong password sets no cookie")

    r = await lan.post("/api/auth/login", json={"password": "hunter2"})
    check(r.status_code == 200 and r.json()["ok"], "login ok")
    sc = r.headers.get("set-cookie", "").lower()
    check("httponly" in sc and "samesite=lax" in sc and "max-age" in sc, "cookie is httponly, lax, long lived")
    cookie = lan.cookies.get(auth.COOKIE)
    check(bool(cookie) and "hunter2" not in cookie, "cookie holds a token, not the password")
    check((await lan.get("/api/state")).status_code == 200, "cookie works for /api")
    check((await lan.get("/api/auth")).json() == {"required": True, "ok": True}, "auth status ok with cookie")
    out = await ws_try(cookie)
    check(out[0]["type"] == "websocket.accept" and any(m["type"] == "websocket.send" for m in out), "cookie works for /ws")
    check((await lan.patch("/api/settings", json={"lanPassword": ""})).status_code == 403, "lan client cannot change the password")

    other = httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=("192.168.1.6", 1)), base_url="http://t")
    other.cookies.set(auth.COOKIE, "0" * 64)
    check((await other.get("/api/state")).status_code == 401, "forged cookie rejected")

    await local.patch("/api/settings", json={"lanPassword": "correct horse"})
    check((await lan.get("/api/state")).status_code == 401, "password change invalidates old cookie")
    out = await ws_try(cookie)
    check(any(m.get("code") == 4401 for m in out), "password change invalidates old cookie on /ws")
    r = await lan.post("/api/auth/login", json={"password": "correct horse"})
    check(r.status_code == 200 and (await lan.get("/api/state")).status_code == 200, "login with new password")

    r = await lan.post("/api/auth/logout")
    check(r.status_code == 200 and (await lan.get("/api/state")).status_code == 401, "logout clears the cookie")
    await lan.post("/api/auth/login", json={"password": "correct horse"})

    # push
    r = await lan.get("/api/push/key")
    key = r.json()["key"]
    check(r.status_code == 200 and len(key) == 87 and (tmp / "vapid_private.pem").exists(), "vapid key generated and stored")
    check((await lan.get("/api/push/key")).json()["key"] == key, "vapid key is stable")
    sub = {"endpoint": "https://push.example/abc", "keys": {"p256dh": "p", "auth": "a"}}
    r = await lan.post("/api/push/subscribe", json={"subscription": sub, "label": "iPhone Safari"})
    check(r.status_code == 200 and r.json()["label"] == "iPhone Safari", "subscribe")
    r = await lan.post("/api/push/subscribe", json={"subscription": {"endpoint": "http://evil/", "keys": {}}})
    check(r.status_code == 400, "invalid subscription rejected")
    await lan.post("/api/push/subscribe", json={"subscription": {**sub, "endpoint": "https://push.example/gone"}, "label": "old"})
    check(len(push.subscriptions()) == 2, "subscriptions persisted")

    r = await lan.post("/api/push/test", json={"endpoint": sub["endpoint"]})
    check(r.json()["sent"] == 1 and '"force": true' in sent[-1]["data"], "test push sent to this device")
    check(sent[-1]["kw"]["vapid_claims"]["sub"].startswith("mailto:"), "vapid claims set")

    sent.clear()
    out_dir = Path(config.settings().outputDir) / "thumbs"
    out_dir.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8)).save(out_dir / "img1.webp", "WEBP")
    push.on_finish({"status": "done", "images": [{"id": "img0"}]}, False)
    push.on_finish({"status": "cancelled"}, False)
    push.on_finish({"status": "done", "images": [{"id": "img1"}]}, True)
    for _ in range(50):
        if sent and len(push.subscriptions()) == 1:
            break
        await asyncio.sleep(0.05)
    check(len(sent) == 1 and '"Queue finished"' in sent[0]["data"] and '"2 images"' in sent[0]["data"], "queue drain notification with count")
    check(len(push.subscriptions()) == 1, "410 subscription dropped")
    import json as _json

    img = _json.loads(sent[0]["data"])["image"]
    check((await other.get(img)).status_code == 200, "signed notification image is public")
    check((await other.get(img.split("?")[0] + "?sig=00")).status_code == 404, "bad signature 404")

    sent.clear()
    push.on_finish({"status": "error", "error": "out of memory"}, True)
    for _ in range(50):
        if sent:
            break
        await asyncio.sleep(0.05)
    check(len(sent) == 1 and "Generation failed" in sent[0]["data"], "error notification")

    r = await lan.request("DELETE", "/api/push/subscribe", json={"endpoint": sub["endpoint"]})
    check(r.json()["removed"] and push.subscriptions() == [], "unsubscribe")

    await local.patch("/api/settings", json={"lanPassword": ""})
    check(config.settings().lanPassword == "" and (await other.get("/api/state")).status_code == 200, "clearing the password opens lan again")
    print("ALL PASSED")


asyncio.run(main())
