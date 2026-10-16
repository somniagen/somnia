from __future__ import annotations

import bisect
import csv
import heapq
import json
import logging
import os
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

import httpx
import numpy as np

from somnia.config import DATA_DIR

log = logging.getLogger("somnia.tags")

CSV_URL = "https://raw.githubusercontent.com/DominikDoom/a1111-sd-webui-tagcomplete/main/tags/danbooru.csv"
WIKI_API = "https://danbooru.donmai.us/wiki_pages/{name}.json"
WIKI_PAGE = "https://danbooru.donmai.us/wiki_pages/{name}"
RELATED_API = "https://danbooru.donmai.us/related_tag.json"
USER_AGENT = "Somnia/0.1 (local image-gen webui)"

TAG_DIR = DATA_DIR / "tags"
CSV_PATH = TAG_DIR / "danbooru.csv"
WIKI_DIR = TAG_DIR / "wiki"

CONTAINS_CAP = 2000
MAX_CHAR = chr(0x10FFFF)

_spaces = re.compile(r"\s+")
_weight = re.compile(r":\s*-?\d+(?:\.\d+)?\s*$")
_tag_link = re.compile(r"\[\[([^\]|]+)\|([^\]]+)\]\]")
_plain_link = re.compile(r"\[\[([^\]]+)\]\]")
_quoted_link = re.compile(r'"([^"\n]+)":(?:https?://|/)\S+')
_header = re.compile(r"^h[1-6]\.\s*(.+)$", re.M)
_bold = re.compile(r"\[b\](.*?)\[/b\]", re.S)
_italic = re.compile(r"\[i\](.*?)\[/i\]", re.S)
_code = re.compile(r"\[code\](.*?)\[/code\]", re.S)
_other_tags = re.compile(r"\[/?(?:color|spoiler|expand|quote|u|s|tn|center|table|tr|td|th)(?:=[^\]]*)?\]", re.I)
_blank_lines = re.compile(r"\n{3,}")


class WikiError(Exception):
    pass


@dataclass
class _Index:
    names: list[str]
    name_keys: list[str]
    cats: list[int]
    counts: list[int]
    aliases: list[list[str]]
    name_rank: dict[str, int]
    alias_rank: dict[str, int]
    keys: list[str]
    key_rank: np.ndarray
    hay: str
    starts: list[int]


_index: _Index | None = None
_loaded = False
_lock = threading.Lock()


def normalize(text: str) -> str:
    return _spaces.sub("_", text.replace("\\", "").strip().lower())


def _unwrap(text: str) -> str:
    s = text.strip()
    while len(s) > 1 and s[0] in "([{" and s[-1] in ")]}":
        inner = s[1:-1]
        opened = inner.count("(") + inner.count("[") + inner.count("{")
        closed = inner.count(")") + inner.count("]") + inner.count("}")
        if opened != closed:
            break
        s = inner.strip()
    return s


def clean_prompt_tag(text: str) -> str:
    s = _weight.sub("", _unwrap(text))
    return normalize(_unwrap(s))


def download_csv() -> Path:
    TAG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CSV_PATH.with_suffix(".csv.part")
    with httpx.stream("GET", CSV_URL, headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=60) as r:
        r.raise_for_status()
        with tmp.open("wb") as f:
            for chunk in r.iter_bytes():
                f.write(chunk)
    os.replace(tmp, CSV_PATH)
    return CSV_PATH


def _build(rows) -> _Index:
    parsed = []
    for row in rows:
        if len(row) < 3:
            continue
        name = row[0].strip()
        try:
            cat = int(row[1])
            count = int(row[2])
        except ValueError:
            continue
        aliases = [a.strip() for a in ",".join(row[3:]).split(",") if a.strip()]
        if name:
            parsed.append((count, name, cat, aliases))
    parsed.sort(key=lambda p: -p[0])

    names, name_keys, cats, counts, aliases = [], [], [], [], []
    name_rank: dict[str, int] = {}
    alias_rank: dict[str, int] = {}
    entries: list[tuple[str, int]] = []
    for rank, (count, name, cat, al) in enumerate(parsed):
        nk = normalize(name)
        names.append(name)
        name_keys.append(nk)
        cats.append(cat)
        counts.append(count)
        aliases.append(al)
        name_rank.setdefault(nk, rank)
        entries.append((nk, rank))
        for a in al:
            ak = normalize(a)
            alias_rank.setdefault(ak, rank)
            entries.append((ak, rank))

    entries.sort(key=lambda e: e[0])
    keys = [e[0] for e in entries]
    key_rank = np.array([e[1] for e in entries], dtype=np.int32)
    starts = []
    pos = 0
    for k in keys:
        starts.append(pos)
        pos += len(k) + 1
    return _Index(
        names=names,
        name_keys=name_keys,
        cats=cats,
        counts=counts,
        aliases=aliases,
        name_rank=name_rank,
        alias_rank=alias_rank,
        keys=keys,
        key_rank=key_rank,
        hay="\n".join(keys),
        starts=starts,
    )


def _load() -> _Index:
    if not CSV_PATH.exists():
        log.info("downloading danbooru tag csv")
        download_csv()
    started = time.perf_counter()
    with CSV_PATH.open(encoding="utf-8", newline="") as f:
        index = _build(csv.reader(f))
    log.info("loaded %d tags in %.2fs", len(index.names), time.perf_counter() - started)
    return index


def get_index() -> _Index | None:
    global _index, _loaded
    if _loaded:
        return _index
    with _lock:
        if not _loaded:
            try:
                _index = _load()
            except Exception:
                log.exception("tag index load failed")
            _loaded = True
    return _index


def start_background_load() -> None:
    threading.Thread(target=get_index, name="somnia-tags", daemon=True).start()


def search(query: str, limit: int = 20) -> list[dict]:
    q = normalize(query)
    index = get_index()
    if not q or index is None:
        return []
    limit = max(1, min(int(limit), 200))

    lo = bisect.bisect_left(index.keys, q)
    hi = bisect.bisect_left(index.keys, q + MAX_CHAR, lo)
    span = index.key_rank[lo:hi]
    keep = limit * 4 + 20
    if span.size > keep:
        span = np.partition(span, keep)[:keep]
    ranks = set(span.tolist())

    if len(ranks) < limit:
        pos = index.hay.find(q)
        hits = 0
        while pos != -1 and hits < CONTAINS_CAP:
            i = bisect.bisect_right(index.starts, pos) - 1
            ranks.add(int(index.key_rank[i]))
            hits += 1
            pos = index.hay.find(q, pos + 1)

    out = []
    for r in heapq.nsmallest(limit, ranks):
        matched = None
        if q not in index.name_keys[r]:
            matched = next((a for a in index.aliases[r] if q in normalize(a)), None)
        out.append({
            "name": index.names[r],
            "category": index.cats[r],
            "count": index.counts[r],
            "aliases": index.aliases[r],
            "matchedAlias": matched,
        })
    return out


def _rank(index: _Index, key: str) -> int | None:
    r = index.name_rank.get(key)
    if r is None:
        r = index.alias_rank.get(key)
    return r


def lookup(names: list[str]) -> dict[str, int]:
    index = get_index()
    if index is None:
        return {}
    out: dict[str, int] = {}
    for raw in names:
        key = clean_prompt_tag(raw)
        if not key or key in out:
            continue
        r = _rank(index, key)
        if r is not None:
            out[key] = index.cats[r]
    return out


def dtext_to_markdown(text: str) -> str:
    s = _tag_link.sub(r"\2", text)
    s = _plain_link.sub(lambda m: m.group(1).replace("_", " "), s)
    s = _quoted_link.sub(r"\1", s)
    s = _header.sub(r"**\1**", s)
    s = _bold.sub(r"**\1**", s)
    s = _italic.sub(r"*\1*", s)
    s = _code.sub(r"`\1`", s)
    s = _other_tags.sub("", s)
    s = s.replace("\r\n", "\n")
    return _blank_lines.sub("\n\n", s).strip()


def _fetch_wiki(key: str) -> dict | None:
    url = WIKI_API.format(name=quote(key, safe="()"))
    try:
        r = httpx.get(url, headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=15)
    except httpx.HTTPError as e:
        raise WikiError(str(e)) from e
    if r.status_code == 404:
        return None
    if r.status_code != 200:
        raise WikiError(f"danbooru returned {r.status_code}")
    return r.json()


def _wiki_raw(key: str) -> dict | None:
    WIKI_DIR.mkdir(parents=True, exist_ok=True)
    path = WIKI_DIR / (quote(key, safe="()-_.") + ".json")
    if path.exists():
        return json.loads(path.read_text("utf-8")).get("wiki")
    raw = _fetch_wiki(key)
    path.write_text(json.dumps({"wiki": raw}), "utf-8")
    return raw


def wiki(name: str) -> dict:
    key = normalize(name)
    raw = _wiki_raw(key)
    index = get_index()
    cat = None
    if index is not None:
        r = _rank(index, key)
        if r is not None:
            cat = index.cats[r]
    return {
        "name": key,
        "category": cat,
        "body": dtext_to_markdown(raw.get("body") or "") if raw else "",
        "otherNames": list(raw.get("other_names") or []) if raw else [],
        "url": WIKI_PAGE.format(name=quote(key, safe="()")),
    }


def _fetch_related(key: str) -> list[dict]:
    try:
        r = httpx.get(
            RELATED_API,
            params={"query": key, "limit": 60},
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
            timeout=15,
        )
    except httpx.HTTPError as e:
        raise WikiError(str(e)) from e
    if r.status_code != 200:
        raise WikiError(f"danbooru returned {r.status_code}")
    data = r.json()
    base = data.get("post_count") or 0
    out = []
    for item in data.get("related_tags") or []:
        t = item.get("tag") or {}
        name = t.get("name")
        # meta tags (highres, absurdres...) co-occur with everything and say nothing
        if not name or name == key or t.get("category") == 5 or t.get("is_deprecated"):
            continue
        # near universal tags (1girl, solo...) only crowd out the useful ones
        if (t.get("post_count") or 0) > max(3_000_000, base * 2):
            continue
        out.append({"name": name, "category": t.get("category"), "count": t.get("post_count") or 0,
                    "score": float(item.get("cosine_similarity") or 0)})
    out.sort(key=lambda d: -d["score"])
    return out


def related(name: str, limit: int = 16) -> list[dict]:
    # tags that commonly appear together with name, most similar first (cached on disk)
    key = normalize(name)
    d = TAG_DIR / "related"
    d.mkdir(parents=True, exist_ok=True)
    path = d / (quote(key, safe="()-_.") + ".json")
    if path.exists():
        items = json.loads(path.read_text("utf-8"))
    else:
        items = _fetch_related(key)
        path.write_text(json.dumps(items), "utf-8")
    return [{k: v for k, v in i.items() if k != "score"} for i in items[:limit]]
