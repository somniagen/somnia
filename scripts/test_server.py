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
config._settings = config.Settings(outputDir=str(tmp / "outputs"), autoIdentify=False)



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

import somnia.bgremove as bgremove

bgremove.remove_background = lambda img, cpu=False: Image.merge("RGBA", (*img.convert("RGB").split(), Image.new("L", img.size, 128)))

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

        gid = item["id"]
        r = await http.put(f"/api/gallery/{gid}/favorite", json={"favorite": True})
        check(r.status_code == 200 and r.json()["favorite"] is True, "favorite set")
        favs = (await http.get("/api/gallery", params={"fav": 1})).json()["items"]
        check([i["id"] for i in favs] == [gid], "fav filter")
        await http.post("/api/gallery/favorite", json={"ids": [gid], "favorite": False})
        check((await http.get("/api/gallery", params={"fav": 1})).json()["items"] == [], "bulk unfavorite")
        r = await http.post("/api/gallery/albums/add", json={"ids": [gid], "album": "  Best   shots "})
        check(r.json()[0]["albums"] == ["Best shots"], "album add normalizes the name")
        al = (await http.get("/api/gallery/albums")).json()
        check(al == [{"name": "Best shots", "count": 1, "cover": item["thumbUrl"]}], "albums listed with count and cover")
        check([i["id"] for i in (await http.get("/api/gallery", params={"album": "Best shots"})).json()["items"]] == [gid], "album filter")
        r = await http.put("/api/gallery/albums/Best shots", json={"name": "Keepers"})
        check([a["name"] for a in r.json()] == ["Keepers"], "album renamed")
        check((await http.get("/api/gallery", params={"album": "Keepers"})).json()["items"][0]["albums"] == ["Keepers"], "renamed album on items")
        await http.post("/api/gallery/albums/remove", json={"ids": [gid], "album": "Keepers"})
        check((await http.get("/api/gallery/albums")).json() == [], "album removed when empty")
        await http.post("/api/gallery/albums/add", json={"ids": [gid], "album": "Tmp"})
        r = await http.delete("/api/gallery/albums/Tmp")
        check(r.json() == [] and "albums" not in (await http.get(f"/api/gallery/{gid}/stack")).json()[0], "album deleted")

        r = await http.post(f"/api/gallery/{gid}/remove-bg")
        nb = r.json()
        check(r.status_code == 200 and nb["alpha"] is True and nb["stackId"] == gid and nb["sourceId"] == gid, "remove-bg makes a stacked alpha item")
        check(nb["params"]["prompt"] == "1girl", "remove-bg copies params")
        with Image.open(__import__("io").BytesIO((await http.get(nb["url"])).content)) as im:
            check(im.mode == "RGBA", "remove-bg png keeps alpha")
        with Image.open(__import__("io").BytesIO((await http.get(nb["thumbUrl"])).content)) as im:
            check("A" in im.getbands(), "remove-bg thumb keeps alpha")
        check((await http.post("/api/gallery/nope/remove-bg")).status_code == 404, "remove-bg 404")

        async with websockets.connect(f"ws://127.0.0.1:{port}/ws") as ws3:
            json.loads(await ws3.recv())
            axes = [
                {"kind": "cfg", "label": "CFG", "values": [{"label": "4", "patch": {"cfg": 4}}, {"label": "7", "patch": {"cfg": 7}}]},
                {"kind": "prompt", "label": "Prompt S/R", "values": [
                    {"label": "1girl", "patch": {"$sr": ["1girl", "1girl"]}},
                    {"label": "1boy", "patch": {"$sr": ["1girl", "1boy"]}},
                ]},
            ]
            r = await http.post("/api/grids", json={"base": PARAMS, "axes": axes})
            g = r.json()
            check(r.status_code == 200 and len(g["cells"]) == 4 and g["status"] == "running", "grid queued 4 cells")
            q = (await http.get("/api/state")).json()["queue"]
            cells = [j for j in q if (j.get("grid") or {}).get("id") == g["id"]]
            check(len(cells) == 4 and len({j["params"]["seed"] for j in cells}) == 1, "grid cells share one seed")
            check(any(j["params"]["prompt"] == "1boy" and j["params"]["cfg"] == 7 for j in cells), "cell patches applied")
            m = await recv_until(ws3, lambda m: m["type"] == "grid" and m["grid"]["id"] == g["id"] and m["grid"]["status"] == "done", 30)
            g = m["grid"]
            check(all(c["status"] == "done" and c["item"] for c in g["cells"]) and len(g["images"]) == 1, "grid done with composed image")
            root = g["images"][0]
            cell_ids = {c["item"]["id"] for c in g["cells"]}
            stack = (await http.get(f"/api/gallery/{root['id']}/stack")).json()
            check(stack[0]["id"] == root["id"] and {s["id"] for s in stack[1:]} == cell_ids, "cells stacked under the grid image")
            gal = (await http.get("/api/gallery")).json()["items"]
            top = next((i for i in gal if i["id"] == root["id"]), None)
            check(top is not None and top["stackCount"] == 4 and top["stackCoverId"] == root["id"], "grid image is its own stack cover")
            check(not any(i["id"] in cell_ids for i in gal), "cells hidden inside the stack")
            png = await http.get(root["url"])
            with Image.open(__import__("io").BytesIO(png.content)) as im:
                check(png.status_code == 200 and im.width > 256 and im.height > 192, f"composed grid image {im.width}x{im.height}")
            check((await http.get("/api/grids")).json()[0]["id"] == g["id"], "grid listed")

            r = await http.post("/api/grids", json={"base": PARAMS, "axes": [axes[0]]})
            g2 = r.json()
            await recv_until(ws3, lambda m: m["type"] == "progress")
            r = await http.delete(f"/api/grids/{g2['id']}")
            check(r.status_code == 200, "grid delete accepted")
            await recv_until(ws3, lambda m: m["type"] == "grid_removed" and m["id"] == g2["id"])
            for _ in range(40):
                q = (await http.get("/api/state")).json()["queue"]
                if not q:
                    break
                await asyncio.sleep(0.1)
            check(q == [] and (await http.get(f"/api/grids/{g2['id']}")).status_code == 404, "deleted grid cancels its jobs")
            r = await http.post("/api/grids", json={"base": PARAMS, "axes": []})
            check(r.status_code == 400, "grid without axes rejected")

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
