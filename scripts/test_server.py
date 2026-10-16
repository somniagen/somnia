import asyncio
import json
import os
import socket
import sys
import tempfile
import threading
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

tmp = Path(tempfile.mkdtemp(prefix="somnia-test-"))
os.environ["SOMNIA_DB"] = str(tmp / "test.db")

import httpx
import uvicorn
import websockets
from PIL import Image

from somnia import config

config.DATA_DIR = tmp
config.SETTINGS_FILE = tmp / "settings.json"
config._settings = config.Settings(outputDir=str(tmp / "outputs"))



def fake_run(params, ctx):
    for step in range(1, 11):
        ctx.check()
        time.sleep(0.15)
        prev = Image.new("RGB", (64, 64), (step * 20, 80, 160)) if step % 2 == 0 else None
        ctx.progress("sample", step, 10, prev)
    return [Image.new("RGB", (128, 96), (200, 50, 50))]


fake = types.ModuleType("somnia.engine.pipeline")
fake.run = fake_run
sys.modules["somnia.engine.pipeline"] = fake
import somnia.engine as eng

eng.pipeline = fake

from somnia.app import create_app

PARAMS = {"family": "illustrious", "model": "x", "prompt": "1girl", "negative": "bad", "width": 128,
          "height": 96, "steps": 10, "cfg": 5, "sampler": "euler", "scheduler": "normal", "seed": -1,
          "clipSkip": 1, "batchSize": 1, "loras": []}


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        sys.exit(1)


async def recv_until(ws, pred, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        m = json.loads(await asyncio.wait_for(ws.recv(), timeout))
        if pred(m):
            return m
    raise TimeoutError


async def main():
    app = create_app()
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    base_url = f"http://127.0.0.1:{port}"
    async with httpx.AsyncClient(base_url=base_url) as http:
        for _ in range(50):
            try:
                await http.get("/api/state")
                break
            except httpx.HTTPError:
                await asyncio.sleep(0.1)

        async with websockets.connect(f"ws://127.0.0.1:{port}/ws") as ws1:
            snap = json.loads(await ws1.recv())
            check(snap["type"] == "snapshot" and snap["queue"] == [] and snap["current"] is None, "snapshot on connect")

            r = await http.post("/api/jobs", json={"params": PARAMS, "count": 2})
            ids = r.json()["ids"]
            check(len(ids) == 2, "2 jobs queued")
            q = await recv_until(ws1, lambda m: m["type"] == "queue")
            check(all(j["params"]["seed"] >= 0 for j in q["queue"]), "random seed made concrete")

            await recv_until(ws1, lambda m: m["type"] == "progress" and m["step"] >= 3)
            async with websockets.connect(f"ws://127.0.0.1:{port}/ws") as ws2:
                snap2 = json.loads(await ws2.recv())
                cur = snap2["current"]
                check(cur is not None and cur["jobId"] == ids[0] and len(snap2["queue"]) == 2, "late client gets current progress")
                check(cur["preview"] is not None, "late client gets last preview")

            done = await recv_until(ws1, lambda m: m["type"] == "done", 15)
            check(done["job"]["status"] == "done" and len(done["job"]["images"]) == 1, "job 1 done with image")
            item = done["job"]["images"][0]
            img = await http.get(item["url"])
            th = await http.get(item["thumbUrl"])
            check(img.status_code == 200 and th.status_code == 200, "image and thumb served")
            gal = (await http.get("/api/gallery")).json()
            check(len(gal["items"]) == 1 and gal["items"][0]["id"] == item["id"], "gallery entry created")

            await recv_until(ws1, lambda m: m["type"] == "progress" and m["jobId"] == ids[1] and m["step"] >= 2)
            r = await http.delete(f"/api/jobs/{ids[1]}")
            check(r.status_code == 200, "cancel accepted")
            d2 = await recv_until(ws1, lambda m: m["type"] == "done" and m["job"]["id"] == ids[1], 10)
            check(d2["job"]["status"] == "cancelled", "running job cancelled")
            gal = (await http.get("/api/gallery")).json()
            check(len(gal["items"]) == 1, "cancelled job saved nothing")

        up = await http.post("/api/upload", files={"file": (
            "a.png", open(tmp / "outputs" / Path(item["url"]).name, "rb"), "image/png")})
        check(up.status_code == 200 and up.json()["params"]["prompt"] == "1girl", "upload reads somnia params")

        r = await http.post("/api/prompts", json={"name": "p", "family": None, "positive": [], "negative": []})
        pid = r.json()["id"]
        check(len((await http.get("/api/prompts")).json()) == 1, "prompt saved")
        await http.delete(f"/api/prompts/{pid}")
        check((await http.get("/api/prompts")).json() == [], "prompt deleted")

        r = await http.patch("/api/settings", json={"civitaiToken": "abcd1234"})
        check(r.json()["civitaiToken"] == "****1234", "token masked")

    transport = httpx.ASGITransport(app=app, client=("10.0.0.5", 5555))
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as lan:
        r = await lan.get("/api/state")
        check(r.status_code == 403, "LAN middleware blocks non-loopback")
        config.update_settings(lanEnabled=True)
        r = await lan.get("/api/state")
        check(r.status_code == 200, "LAN allowed when enabled")
        r = await lan.patch("/api/settings", json={"port": 7865})
        check(r.status_code == 403, "settings write blocked from LAN")

    server.should_exit = True
    print("ALL PASSED")


asyncio.run(main())
