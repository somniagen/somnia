from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import uuid
from pathlib import Path

from . import config

_lock = threading.RLock()
_db: sqlite3.Connection | None = None
_db_path: Path | None = None


def _conn() -> sqlite3.Connection:
    global _db, _db_path
    path = Path(os.environ.get("SOMNIA_DB") or (config.DATA_DIR / "somnia.db"))
    if _db is None or _db_path != path:
        path.parent.mkdir(parents=True, exist_ok=True)
        _db = sqlite3.connect(path, check_same_thread=False)
        _db_path = path
        _db.execute("create table if not exists prompts (id text primary key, data text not null)")
        _db.execute("create table if not exists gallery (id text primary key, created integer not null, data text not null)")
        _db.execute("create table if not exists grids (id text primary key, created integer not null, data text not null)")
        _db.execute("create index if not exists gallery_created on gallery (created desc)")
        cols = {r[1] for r in _db.execute("pragma table_info(gallery)")}
        if "stack" not in cols:
            _db.execute("alter table gallery add column stack text")
        if "sort" not in cols:
            _db.execute("alter table gallery add column sort integer")
            _db.execute("update gallery set sort = created")
        _db.execute("create index if not exists gallery_stack on gallery (stack)")
        _db.execute("create index if not exists gallery_sort on gallery (sort desc)")
        _backfill_stacks(_db)
        _db.commit()
    return _db


def _backfill_stacks(c: sqlite3.Connection) -> None:
    # results saved by older servers only kept the stack id inside params
    rows = c.execute(
        "select id, created, data from gallery where stack is null and json_extract(data, '$.params.stackId') is not null"
    ).fetchall()
    for gid, created, raw in rows:
        d = json.loads(raw)
        root = d["params"].pop("stackId")
        ok = root != gid and c.execute("select 1 from gallery where id=? and stack is null", (root,)).fetchone()
        d["stackId"] = root if ok else None
        c.execute("update gallery set stack=?, data=? where id=?", (d["stackId"], json.dumps(d), gid))
        if ok:
            c.execute("update gallery set sort = max(coalesce(sort, created), ?) where id=?", (created, root))


def now_ms() -> int:
    return int(time.time() * 1000)


def list_prompts() -> list[dict]:
    with _lock:
        rows = _conn().execute("select data from prompts").fetchall()
    items = [json.loads(r[0]) for r in rows]
    items.sort(key=lambda p: p.get("updatedAt", 0), reverse=True)
    return items


def get_prompt(pid: str) -> dict | None:
    with _lock:
        r = _conn().execute("select data from prompts where id=?", (pid,)).fetchone()
    return json.loads(r[0]) if r else None


def save_prompt(p: dict) -> dict:
    with _lock:
        c = _conn()
        c.execute("insert or replace into prompts (id, data) values (?, ?)", (p["id"], json.dumps(p)))
        c.commit()
    return p


def create_prompt(body: dict) -> dict:
    t = now_ms()
    p = {
        "id": uuid.uuid4().hex[:12],
        "name": body.get("name", ""),
        "family": body.get("family"),
        "positive": body.get("positive", []),
        "negative": body.get("negative", []),
        "createdAt": t,
        "updatedAt": t,
    }
    return save_prompt(p)


def update_prompt(pid: str, body: dict) -> dict | None:
    old = get_prompt(pid)
    if old is None:
        return None
    for k in ("name", "family", "positive", "negative"):
        if k in body:
            old[k] = body[k]
    old["updatedAt"] = now_ms()
    return save_prompt(old)


def delete_prompt(pid: str) -> None:
    with _lock:
        c = _conn()
        c.execute("delete from prompts where id=?", (pid,))
        c.commit()


def add_gallery(item: dict) -> None:
    stack = item.get("stackId")
    with _lock:
        c = _conn()
        if stack and not c.execute("select 1 from gallery where id=? and stack is null", (stack,)).fetchone():
            item["stackId"] = stack = None
        c.execute(
            "insert or replace into gallery (id, created, data, stack, sort) values (?, ?, ?, ?, ?)",
            (item["id"], item["createdAt"], json.dumps(item), stack, item["createdAt"]),
        )
        if stack:
            c.execute("update gallery set sort = max(coalesce(sort, created), ?) where id=?", (item["createdAt"], stack))
        c.commit()


def _with_stacks(c: sqlite3.Connection, items: list[dict]) -> list[dict]:
    ids = [i["id"] for i in items]
    if not ids:
        return items
    marks = ",".join("?" * len(ids))
    counts = {r[0]: r[1] for r in c.execute(f"select stack, count(*) from gallery where stack in ({marks}) group by stack", ids)}
    for it in items:
        n = counts.get(it["id"], 0)
        it["stackCount"] = n
        if n:
            cover = _cover(c, it)
            it["stackCover"] = cover["thumbUrl"] if cover else None
            it["stackCoverId"] = cover["id"] if cover else None
            it["stackCoverAlpha"] = bool(cover and cover.get("alpha"))
            it["stackCoverItem"] = None if cover is it else cover
    return items


def _cover(c: sqlite3.Connection, root: dict) -> dict | None:
    # the chosen cover when it is still in the stack, else the newest child
    cid = root.get("coverId")
    if cid == root["id"]:
        return root
    r = None
    if cid:
        r = c.execute("select data from gallery where id=? and stack=?", (cid, root["id"])).fetchone()
    if not r:
        r = c.execute("select data from gallery where stack=? order by created desc, rowid desc limit 1", (root["id"],)).fetchone()
    return json.loads(r[0]) if r else None


def set_cover(gid: str) -> dict | None:
    # makes a stack member its root's cover and returns the root with stack fields
    with _lock:
        c = _conn()
        r = c.execute("select stack from gallery where id=?", (gid,)).fetchone()
        if not r:
            return None
        root = r[0] or gid
        row = c.execute("select data from gallery where id=?", (root,)).fetchone()
        if not row:
            return None
        d = json.loads(row[0])
        d["coverId"] = gid
        c.execute("update gallery set data=? where id=?", (json.dumps(d), root))
        c.commit()
        return _with_stacks(c, [d])[0]


def _edit_items(c: sqlite3.Connection, ids: list[str], fn) -> list[dict]:
    # applies fn to each stored item dict, saving the ones it reports as changed
    out = []
    for gid in dict.fromkeys(ids):
        r = c.execute("select data from gallery where id=?", (gid,)).fetchone()
        if not r:
            continue
        d = json.loads(r[0])
        if fn(d):
            c.execute("update gallery set data=? where id=?", (json.dumps(d), gid))
        out.append(d)
    return out


def set_favorite(ids: list[str], fav: bool) -> list[dict]:
    def apply(d: dict) -> bool:
        if bool(d.get("favorite")) == fav:
            return False
        if fav:
            d["favorite"] = True
        else:
            d.pop("favorite", None)
        return True

    with _lock:
        c = _conn()
        out = _edit_items(c, ids, apply)
        c.commit()
    return out


def album_name(name: str) -> str:
    return " ".join(str(name).split())[:80]


def edit_albums(ids: list[str], album: str, add: bool) -> list[dict]:
    album = album_name(album)

    def apply(d: dict) -> bool:
        cur = list(d.get("albums") or [])
        if (album in cur) == add:
            return False
        cur = [*cur, album] if add else [a for a in cur if a != album]
        if cur:
            d["albums"] = cur
        else:
            d.pop("albums", None)
        return True

    with _lock:
        c = _conn()
        out = _edit_items(c, ids, apply) if album else []
        c.commit()
    return out


def _album_ids(c: sqlite3.Connection, album: str) -> list[str]:
    return [r[0] for r in c.execute(
        "select distinct gallery.id from gallery, json_each(gallery.data, '$.albums') where json_each.value = ?", (album,)
    )]


def rename_album(old: str, new: str) -> int:
    new = album_name(new)

    def apply(d: dict) -> bool:
        cur = [new if a == old else a for a in d.get("albums") or []]
        d["albums"] = list(dict.fromkeys(cur))
        return True

    with _lock:
        c = _conn()
        out = _edit_items(c, _album_ids(c, old), apply) if new else []
        c.commit()
    return len(out)


def delete_album(album: str) -> int:
    def apply(d: dict) -> bool:
        cur = [a for a in d.get("albums") or [] if a != album]
        if cur:
            d["albums"] = cur
        else:
            d.pop("albums", None)
        return True

    with _lock:
        c = _conn()
        out = _edit_items(c, _album_ids(c, album), apply)
        c.commit()
    return len(out)


def list_albums() -> list[dict]:
    # cover is the thumb of the newest image in the album
    with _lock:
        rows = _conn().execute(
            "select j.value, count(*), (select json_extract(g2.data, '$.thumbUrl') from gallery g2, json_each(g2.data, '$.albums') j2"
            " where j2.value = j.value order by g2.created desc limit 1)"
            " from gallery g, json_each(g.data, '$.albums') j group by j.value order by lower(j.value)"
        ).fetchall()
    return [{"name": n, "count": k, "cover": cov} for n, k, cov in rows]


def list_gallery(cursor: str | None = None, limit: int = 40) -> tuple[list[dict], str | None]:
    # roots only, ordered by their own creation time so adding to a stack does not move it
    q = "select created, rowid, data from gallery where stack is null"
    args: list = []
    if cursor:
        try:
            key, _, rid = cursor.partition(":")
            args += [int(key), int(rid or 0)]
            q += " and (created, rowid) < (?, ?)"
        except ValueError:
            args = []
    q += " order by created desc, rowid desc limit ?"
    args.append(limit + 1)
    with _lock:
        c = _conn()
        rows = c.execute(q, args).fetchall()
        more = len(rows) > limit
        rows = rows[:limit]
        items = _with_stacks(c, [json.loads(r[2]) for r in rows])
    return items, (f"{rows[-1][0]}:{rows[-1][1]}" if more and rows else None)


_HAY = (
    "replace(lower(coalesce(json_extract(data, '$.params.prompt'), '') || ' ' || coalesce(json_extract(data, '$.params.model'), '')"
    " || ' ' || coalesce(json_extract(data, '$.params.loras'), '') || ' ' || coalesce(json_extract(data, '$.editedWith.name'), '')"
    " || ' ' || coalesce(json_extract(data, '$.seed'), '')), '_', ' ')"
)
_SORTS = {
    "newest": "created desc, rowid desc",
    "oldest": "created asc, rowid asc",
    "model": "lower(coalesce(json_extract(data, '$.params.model'), '~')) asc, created desc, rowid desc",
}


def search_gallery(
    q: str = "", model: str = "", sort: str = "newest", offset: int = 0, limit: int = 60, fav: bool = False, album: str = ""
) -> tuple[list[dict], str | None]:
    # filtered or re-sorted listing with offset paging; stacks are kept only when nothing is filtered
    where: list[str] = []
    args: list = []
    for raw in q.split(","):
        term = raw.strip().lower().replace("_", " ")
        neg = term.startswith("-")
        term = term.lstrip("-").strip()
        if not term:
            continue
        like = "%" + term.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"
        where.append(f"{_HAY} {'not ' if neg else ''}like ? escape '!'")
        args.append(like)
    if model:
        where.append("json_extract(data, '$.params.model') = ?")
        args.append(model)
    if fav:
        where.append("json_extract(data, '$.favorite') = 1")
    if album:
        where.append("exists (select 1 from json_each(data, '$.albums') where value = ?)")
        args.append(album)
    stacked = not where
    if stacked:
        where.append("stack is null")
    sql = "select data from gallery" + (" where " + " and ".join(where) if where else "")
    sql += f" order by {_SORTS.get(sort, _SORTS['newest'])} limit ? offset ?"
    with _lock:
        c = _conn()
        rows = c.execute(sql, [*args, limit + 1, offset]).fetchall()
        items = [json.loads(r[0]) for r in rows[:limit]]
        if stacked:
            items = _with_stacks(c, items)
    return items, (f"o:{offset + limit}" if len(rows) > limit else None)


def gallery_models() -> list[dict]:
    with _lock:
        rows = _conn().execute(
            "select json_extract(data, '$.params.model') m, count(*) from gallery where m is not null group by m order by count(*) desc"
        ).fetchall()
    return [{"id": m, "count": n} for m, n in rows]


def list_stack(root: str) -> list[dict]:
    with _lock:
        rows = _conn().execute(
            "select data from gallery where id=? or stack=? order by (stack is not null), created, rowid", (root, root)
        ).fetchall()
    return [json.loads(r[0]) for r in rows]


def recent_gallery(n: int = 20) -> list[dict]:
    with _lock:
        rows = _conn().execute("select data from gallery order by created desc, rowid desc limit ?", (n,)).fetchall()
    return [json.loads(r[0]) for r in rows]


def get_gallery(gid: str) -> dict | None:
    with _lock:
        r = _conn().execute("select data from gallery where id=?", (gid,)).fetchone()
    return json.loads(r[0]) if r else None


def _set_stack(c: sqlite3.Connection, gid: str, stack: str | None, cover: str | None = None) -> None:
    r = c.execute("select data from gallery where id=?", (gid,)).fetchone()
    if not r:
        return
    d = json.loads(r[0])
    d["stackId"] = stack
    if cover:
        d["coverId"] = cover
    c.execute("update gallery set stack=?, data=? where id=?", (stack, json.dumps(d), gid))


def stack_under(root: str, ids: list[str]) -> None:
    # files existing items (and their own stacks) under root
    with _lock:
        c = _conn()
        for gid in ids:
            if gid == root:
                continue
            for (k,) in c.execute("select id from gallery where stack=?", (gid,)).fetchall():
                _set_stack(c, k, root)
            _set_stack(c, gid, root)
        c.execute(
            "update gallery set sort = (select max(created) from gallery where id=? or stack=?) where id=?",
            (root, root, root),
        )
        c.commit()


def save_grid(g: dict) -> None:
    with _lock:
        c = _conn()
        c.execute("insert or replace into grids (id, created, data) values (?, ?, ?)", (g["id"], g["createdAt"], json.dumps(g)))
        c.commit()


def get_grid(gid: str) -> dict | None:
    with _lock:
        r = _conn().execute("select data from grids where id=?", (gid,)).fetchone()
    return json.loads(r[0]) if r else None


def list_grids(n: int = 20) -> list[dict]:
    with _lock:
        rows = _conn().execute("select data from grids order by created desc limit ?", (n,)).fetchall()
    return [json.loads(r[0]) for r in rows]


def delete_grid(gid: str) -> None:
    with _lock:
        c = _conn()
        c.execute("delete from grids where id=?", (gid,))
        c.commit()


def delete_gallery(gid: str) -> None:
    # deleting a stack root promotes its oldest child so the stack survives
    with _lock:
        c = _conn()
        kids = [r[0] for r in c.execute("select id from gallery where stack=? order by created, rowid", (gid,))]
        r = c.execute("select data from gallery where id=?", (gid,)).fetchone()
        cover = json.loads(r[0]).get("coverId") if r else None
        c.execute("delete from gallery where id=?", (gid,))
        if kids:
            head, rest = kids[0], kids[1:]
            _set_stack(c, head, None, cover if cover in rest else None)
            for k in rest:
                _set_stack(c, k, head)
            c.execute(
                "update gallery set sort = (select max(created) from gallery where id=? or stack=?) where id=?",
                (head, head, head),
            )
        c.commit()
