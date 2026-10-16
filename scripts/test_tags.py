import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from somnia import tags as core
from somnia.api import tags as api

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("PASS " if ok else "FAIL ") + label + ("" if ok or not detail else f" -> {detail}"))
    if not ok:
        failures.append(label)


def names_of(res: list[dict]) -> list[str]:
    return [t["name"] for t in res]


def main() -> int:
    app = FastAPI()
    app.include_router(api.router)
    client = TestClient(app)

    index = core.get_index()
    check("csv loaded", index is not None and len(index.names) > 1000)
    if index is None:
        return 1

    for q in ["long h", "1gi", "blue_e", "blue e"]:
        r = client.get("/api/tags/search", params={"q": q}).json()
        expect = {"long h": "long_hair", "1gi": "1girl", "blue_e": "blue_eyes", "blue e": "blue_eyes"}[q]
        check(f"search {q!r}", expect in names_of(r), str(names_of(r)[:8]))

    rank = next(i for i, al in enumerate(index.aliases) if al)
    alias = index.aliases[rank][0]
    r = client.get("/api/tags/search", params={"q": alias, "limit": 200}).json()
    hit = next((t for t in r if t["name"] == index.names[rank]), None)
    check(f"alias search {alias!r}", hit is not None, str(names_of(r)[:8]))

    r = client.get("/api/tags/lookup", params={"names": "long hair,(1girl:1.2),zzz_nope_tag_xyz"}).json()
    check("lookup", r.get("long_hair") == 0 and "1girl" in r and "zzz_nope_tag_xyz" not in r, str(r))

    md = core.dtext_to_markdown('[[long_hair|long hair]]\nh4. Note\n[b]bold[/b] "post #1":/posts/1 [[1girl]]')
    check("dtext", "long hair" in md and "**Note**" in md and "**bold**" in md and "post #1" in md and "[[" not in md, md)

    res = client.get("/api/tags/wiki/long_hair")
    body = res.json()
    check("wiki long_hair", res.status_code == 200 and body["name"] == "long_hair" and len(body["body"]) > 0 and body["category"] == 0, str(body)[:200])

    res = client.get("/api/tags/wiki/zzz_nope_tag_xyz")
    check("wiki missing", res.status_code == 200 and res.json()["body"] == "", res.text[:200])

    queries = ["long h", "1gi", "blue_e", "a", "1", "girl", "sky", "hair_o", "zzqx"]
    worst = 0.0
    for q in queries:
        core.search(q, 20)
        started = time.perf_counter()
        for _ in range(200):
            core.search(q, 20)
        mean_ms = (time.perf_counter() - started) / 200 * 1000
        worst = max(worst, mean_ms)
        print(f"     search {q!r}: {mean_ms:.3f} ms")
    check("search under 5 ms", worst < 5, f"worst {worst:.3f} ms")

    return 1 if failures else 0


if __name__ == "__main__":
    code = main()
    print("ALL PASS" if code == 0 else f"{len(failures)} FAILED")
    sys.exit(code)
