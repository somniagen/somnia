import asyncio
import collections
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from somnia import civitai, downloads, models
from somnia.config import settings


async def main():
    r = await civitai.search({"query": "WAI illustrious", "types": "Checkpoint", "limit": 5})
    assert r["items"], "no search results"
    m = r["items"][0]
    print("search:", [(x["id"], x["name"]) for x in r["items"]], "next:", r["nextCursor"])
    assert m["versions"] and m["versions"][0]["files"]

    d = await civitai.get_model(m["id"])
    v = d["versions"][0]
    print("detail:", d["name"], d["type"], len(d["versions"]), "versions;", v["name"], v["baseModel"], len(v["images"]), "images")
    assert d["id"] == m["id"]

    imgs = await civitai.get_images(v["id"], limit=40)
    withmeta = [i for i in imgs["items"] if i["meta"] and i["meta"].get("prompt")]
    print("images:", len(imgs["items"]), "with prompt:", len(withmeta), "thumb:", imgs["items"][0]["thumb"][:90] if imgs["items"] else None)
    assert imgs["items"]
    if withmeta:
        print("sample prompt:", withmeta[0]["meta"]["prompt"][:80])
    else:
        print("WARNING: civitai returned no image meta (public api hides it without a token)")
        assert not settings().civitaiToken, "meta missing even with token"

    s = await civitai.search({"types": "LORA", "baseModels": "Illustrious", "sort": "Most Downloaded", "limit": 30})
    assert s["items"]
    print("lora search:", len(s["items"]), "next:", s["nextCursor"])

    ms = models.rescan()
    print("local models:", len(ms))
    print("family counts:", dict(collections.Counter((x["kind"], x["family"]) for x in ms)))
    for k in models.KIND_FOLDERS:
        print(" ", k, len(models.list_models(k)))
    for x in models.list_models("lora"):
        n = x["name"].lower()
        if "anima" in n or "ilxl" in n:
            exp = "anima" if "anima" in n else "illustrious"
            assert x["family"] == exp, (x["name"], x["family"])
    assert any(x["family"] == "anima" for x in models.list_models("lora"))
    assert any(x["name"].endswith("(bbox)") for x in models.list_models("detector"))
    inst = [x for x in ms if x["civitai"] and x["civitai"]["versionId"]]
    print("with civitai info:", len(inst), "trained words example:", inst[0]["civitai"]["trainedWords"][:2] if inst else None)
    assert inst and any(x["civitai"]["trainedWords"] for x in inst)
    assert models.resolve(ms[0]["id"]).exists()

    cands = []
    for it in s["items"]:
        for ver in it["versions"]:
            for f in ver["files"]:
                kb = f["sizeKB"]
                if f["primary"] and f["format"] == "SafeTensor" and 8000 < kb < 50000:
                    cands.append((it, ver, f))
    cands.sort(key=lambda c: -c[2]["sizeKB"])
    assert cands, "no small lora found"

    tmp = Path(tempfile.mkdtemp(prefix="somnia_dl_"))
    settings().downloadRoot = str(tmp)
    dl = None
    for it, ver, f in cands:
        dl = await downloads.start(ver["id"], f["id"])
        for _ in range(500):
            await asyncio.sleep(0.02)
            cur = next(x for x in downloads.list_downloads() if x["id"] == dl["id"])
            if cur["received"] > 0 or cur["status"] in ("error", "done"):
                break
        if cur["status"] == "error":
            print("skip", it["name"], cur["error"])
            continue
        break
    else:
        print("WARNING: no anonymously downloadable candidate, set a civitai token to test downloads")
        print("OK (download skipped)")
        return
    print("download candidate:", it["name"], ver["name"], f["name"], f["sizeKB"], "KB")
    print("before cancel:", cur["status"], cur["received"], "/", cur["total"])
    downloads.cancel(dl["id"])
    await downloads.wait(dl["id"])
    cur = next(x for x in downloads.list_downloads() if x["id"] == dl["id"])
    parts = list(tmp.rglob("*.part"))
    print("after cancel:", cur["status"], cur["received"], [p.stat().st_size for p in parts])
    if cur["status"] == "cancelled":
        assert parts

    dl2 = await downloads.start(ver["id"], f["id"])
    await downloads.wait(dl2["id"])
    cur = next(x for x in downloads.list_downloads() if x["id"] == dl2["id"])
    print("resume result:", cur["status"], cur["received"], "/", cur["total"], cur["error"])
    assert cur["status"] == "done", cur
    files = [p for p in tmp.rglob("*") if p.is_file()]
    print("files:", [(p.name, p.stat().st_size) for p in files])
    st = [p for p in files if p.suffix == ".safetensors"][0]
    assert st.stat().st_size >= f["sizeKB"] * 1024 * 0.98
    assert (st.with_suffix("").with_name(st.stem + ".civitai.json")).exists()
    assert models.read_header(st) is not None
    mm = [x for x in models.list_models("lora") if x["civitai"] and x["civitai"]["versionId"] == ver["id"]]
    print("rescanned as:", [(x["id"], x["family"], x["previewUrl"]) for x in mm])
    assert mm and mm[0]["civitai"]["trainedWords"] == ver["trainedWords"]

    import shutil
    shutil.rmtree(tmp)
    print("OK")


asyncio.run(main())
