import asyncio
import json
import os
import struct
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

tmp = Path(tempfile.mkdtemp(prefix="somnia-models-"))
os.environ["SOMNIA_DB"] = str(tmp / "test.db")

from fastapi.testclient import TestClient

from somnia import civitai, config, identify, models

config.DATA_DIR = tmp
config.SETTINGS_FILE = tmp / "settings.json"
models.CACHE_FILE = tmp / "models_cache.json"
root = tmp / "models"
config._settings = config.Settings(outputDir=str(tmp / "outputs"), modelRoots=[str(root)], downloadRoot=str(root))


def fake_safetensors(p: Path, payload: bytes) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    head = json.dumps({"__metadata__": {}}).encode()
    p.write_bytes(struct.pack("<Q", len(head)) + head + payload)


fake_safetensors(root / "checkpoints" / "known.safetensors", b"known")
fake_safetensors(root / "checkpoints" / "unknown.safetensors", b"unknown")
fake_safetensors(root / "loras" / "style.safetensors", b"style")
(root / "upscale_models").mkdir(parents=True)
(root / "upscale_models" / "4x.pth").write_bytes(b"upscaler")

calls = {"hash": 0, "model": 0}
known = identify.hashlib.sha256((root / "checkpoints" / "known.safetensors").read_bytes()).hexdigest()
up = identify.hashlib.sha256(b"upscaler").hexdigest()
VERSIONS = {
    known: {"id": 11, "modelId": 1, "name": "v1", "baseModel": "Illustrious", "trainedWords": [], "model": {"name": "Known"}},
    up: {"id": 31, "modelId": 3, "name": "x4", "baseModel": "Other", "trainedWords": [], "model": {"name": "Up"}},
}
MODELS = {
    1: {"id": 1, "name": "Known", "modelVersions": [
        {"id": 13, "name": "v3 pony", "baseModel": "Pony"},
        {"id": 12, "name": "v2", "baseModel": "Illustrious"},
        {"id": 11, "name": "v1", "baseModel": "Illustrious"},
    ]},
    3: {"id": 3, "name": "Up", "modelVersions": [{"id": 31, "name": "x4", "baseModel": "Other"}]},
}


async def by_hash(h):
    calls["hash"] += 1
    return VERSIONS.get(h)


async def get_model_raw(mid):
    calls["model"] += 1
    return MODELS[mid]


civitai.by_hash = by_hash
civitai.get_model_raw = get_model_raw

from somnia.app import create_app


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        sys.exit(1)


def wait_idle(c, timeout=10):
    t = time.time()
    while time.time() - t < timeout:
        time.sleep(0.1)
        if identify._task is not None and identify._task.done() and not c.get("/api/models/identify").json()["running"]:
            return
    raise TimeoutError


with TestClient(create_app()) as c:
    with c.websocket_connect("/ws") as ws:
        check(ws.receive_json()["type"] == "snapshot", "ws snapshot")
        wait_idle(c)
        msgs = []
        ms = {m["id"]: m for m in c.get("/api/models").json()}
        check(ms["checkpoint:known.safetensors"]["civitai"]["versionId"] == 11, "startup auto identify found the checkpoint")
        check(ms["upscaler:4x.pth"]["civitai"]["versionId"] == 31, "upscalers are identified too")
        check(ms["checkpoint:unknown.safetensors"]["civitai"] is None, "unknown stays unidentified")
        check((root / "checkpoints" / "known.civitai.json").exists(), "sidecar written")
        check(calls["hash"] == 4, f"all 4 files looked up ({calls['hash']})")
        cv = ms["checkpoint:known.safetensors"]["civitai"]
        check(cv["updateVersionId"] == 12 and cv["updateVersionName"] == "v2", "update with same base model exposed")
        check(ms["upscaler:4x.pth"]["civitai"]["updateVersionId"] is None, "no update when current is newest")
        for _ in range(40):
            m = ws.receive_json()
            msgs.append(m)
            if m["type"] == "identify" and not m["running"]:
                break
        idm = [m for m in msgs if m["type"] == "identify"]
        check(len(idm) >= 2 and idm[0]["running"] and idm[-1]["done"] == idm[-1]["total"] == 4, "identify progress broadcast")

        before = calls["hash"]
        c.post("/api/models/rescan")
        wait_idle(c)
        check(calls["hash"] == before, "auto identify skips known misses after rescan")
        fake_safetensors(root / "loras" / "new.safetensors", b"new")
        c.post("/api/models/rescan")
        wait_idle(c)
        check(calls["hash"] == before + 1, "auto identify picks up a new file")
        c.post("/api/models/identify")
        wait_idle(c)
        check(calls["hash"] == before + 4, "manual identify retries all unidentified")
        mc = calls["model"]
        asyncio.run(identify.check_updates())
        check(calls["model"] == mc, "update check cached for a day")

        config._settings.autoIdentify = False
        fake_safetensors(root / "loras" / "new2.safetensors", b"new2")
        c.post("/api/models/rescan")
        wait_idle(c)
        check(calls["hash"] == before + 4, "autoIdentify off disables auto runs")

        check(c.get("/api/models/defaults").json() == {}, "defaults empty")
        body = {"params": {"steps": 30, "cfg": 5.5, "sampler": "euler_a", "pag": {"enabled": True, "scale": 3}, "seed": 5, "vae": None}}
        r = c.put("/api/models/defaults/checkpoint:known.safetensors", json=body)
        check(r.status_code == 200 and "seed" not in r.json()["params"] and r.json()["params"]["pag"]["scale"] == 3.0, "put checkpoint defaults filters keys")
        m = ws.receive_json()
        while m["type"] != "model_defaults":
            m = ws.receive_json()
        check("checkpoint:known.safetensors" in m["defaults"], "defaults broadcast")
        c.put("/api/models/defaults/lora:sub/style.safetensors", json={"weight": 0.7})
        d = c.get("/api/models/defaults").json()
        check(d["lora:sub/style.safetensors"]["weight"] == 0.7 and d["checkpoint:known.safetensors"]["params"]["steps"] == 30, "get defaults")
        check(c.put("/api/models/defaults/lora:x", json={"params": {"seed": 1}}).status_code == 400, "empty defaults rejected")
        c.delete("/api/models/defaults/lora:sub/style.safetensors")
        check("lora:sub/style.safetensors" not in c.get("/api/models/defaults").json(), "delete defaults")
        check(json.loads((tmp / "model_defaults.json").read_text())["checkpoint:known.safetensors"]["params"]["cfg"] == 5.5, "defaults persisted")
        check(c.get("/api/models").status_code == 200 and (root / "checkpoints" / "known.safetensors").exists(), "model delete route not shadowed")

print("all ok")
