from __future__ import annotations

import asyncio

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import FileResponse

from .. import jobs, push

router = APIRouter(prefix="/api/push")


def startup() -> None:
    if push.on_finish not in jobs.on_finish:
        jobs.on_finish.append(push.on_finish)


@router.get("/key")
def key() -> dict:
    return {"key": push.public_key()}


@router.post("/subscribe")
def subscribe(body: dict = Body(...)) -> dict:
    sub = body.get("subscription") or {}
    keys = sub.get("keys") or {}
    if not isinstance(sub.get("endpoint"), str) or not sub["endpoint"].startswith("https://") or not keys.get("p256dh") or not keys.get("auth"):
        raise HTTPException(400, "invalid subscription")
    e = push.subscribe({"endpoint": sub["endpoint"], "keys": {"p256dh": keys["p256dh"], "auth": keys["auth"]}}, str(body.get("label") or ""))
    return {"endpoint": e["endpoint"], "label": e["label"]}


@router.delete("/subscribe")
def unsubscribe(body: dict = Body(...)) -> dict:
    return {"removed": push.unsubscribe(str(body.get("endpoint") or ""))}


@router.post("/test")
async def test(body: dict = Body(default={})) -> dict:
    ep = body.get("endpoint")
    if ep and not any(s["endpoint"] == ep for s in push.subscriptions()):
        raise HTTPException(404, "not subscribed")
    msg = {"title": "Somnia", "body": "Notifications are on", "tag": "somnia-test", "url": "/", "force": True}
    return {"sent": await asyncio.to_thread(push.send, msg, ep)}


@router.get("/image/{item_id}")
def image(item_id: str, sig: str = "") -> FileResponse:
    f = push.image_path(item_id, sig)
    if f is None:
        raise HTTPException(404)
    return FileResponse(f, media_type="image/webp", headers={"Cache-Control": "private, max-age=86400"})
