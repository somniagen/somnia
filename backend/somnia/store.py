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
            r = c.execute("select data from gallery where stack=? order by created desc, rowid desc limit 1", (it["id"],)).fetchone()
            it["stackCover"] = json.loads(r[0])["thumbUrl"] if r else None
    return items


def list_gallery(cursor: str | None = None, limit: int = 40) -> tuple[list[dict], str | None]:
    # roots only, ordered by their latest stack activity
    q = "select coalesce(sort, created), rowid, data from gallery where stack is null"
    args: list = []
    if cursor:
        try:
            key, _, rid = cursor.partition(":")
            args += [int(key), int(rid or 0)]
            q += " and (coalesce(sort, created), rowid) < (?, ?)"
        except ValueError:
            args = []
    q += " order by coalesce(sort, created) desc, rowid desc limit ?"
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


def search_gallery(q: str = "", model: str = "", sort: str = "newest", offset: int = 0, limit: int = 60) -> tuple[list[dict], str | None]:
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


def _set_stack(c: sqlite3.Connection, gid: str, stack: str | None) -> None:
    r = c.execute("select data from gallery where id=?", (gid,)).fetchone()
    if not r:
        return
    d = json.loads(r[0])
    d["stackId"] = stack
    c.execute("update gallery set stack=?, data=? where id=?", (stack, json.dumps(d), gid))


def delete_gallery(gid: str) -> None:
    # deleting a stack root promotes its oldest child so the stack survives
    with _lock:
        c = _conn()
        kids = [r[0] for r in c.execute("select id from gallery where stack=? order by created, rowid", (gid,))]
        c.execute("delete from gallery where id=?", (gid,))
        if kids:
            head, rest = kids[0], kids[1:]
            _set_stack(c, head, None)
            for k in rest:
                _set_stack(c, k, head)
            c.execute(
                "update gallery set sort = (select max(created) from gallery where id=? or stack=?) where id=?",
                (head, head, head),
            )
        c.commit()
