from __future__ import annotations

import asyncio
import time
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from . import net, store

router = APIRouter()


def _downloads() -> list[dict]:
    try:
        from . import downloads

        return list(downloads.list_downloads())
    except Exception:
        return []


class Hub:
    def __init__(self) -> None:
        self.loop: asyncio.AbstractEventLoop | None = None
        self.clients: set[asyncio.Queue] = set()
        self.current: dict | None = None
        self._last_progress = 0.0

    def broadcast(self, msg: dict) -> None:
        loop = self.loop
        if loop is None or loop.is_closed():
            return
        loop.call_soon_threadsafe(self._dispatch, msg)

    def kick_remote(self) -> None:
        # lan password changed: drop lan sockets so they log in again
        loop = self.loop
        if loop is None or loop.is_closed():
            return
        loop.call_soon_threadsafe(lambda: [q.put_nowait(None) for q in list(self.clients) if getattr(q, "remote", False)])

    def _dispatch(self, msg: dict) -> None:
        t = msg.get("type")
        if t == "progress":
            now = time.monotonic()
            has_preview = bool(msg.get("preview"))
            final = msg.get("total", 0) > 0 and msg.get("step", 0) >= msg.get("total", 0)
            prev = self.current["preview"] if self.current and self.current.get("jobId") == msg.get("jobId") else None
            self.current = {k: v for k, v in msg.items() if k != "type"}
            if not has_preview:
                self.current["preview"] = prev
            if not has_preview and not final and now - self._last_progress < 0.1:
                return
            self._last_progress = now
        elif t in ("done", "error"):
            self.current = None
        for q in list(self.clients):
            q.put_nowait(msg)

    def snapshot(self) -> dict:
        from . import jobs

        return {
            "type": "snapshot",
            "queue": jobs.queue_list(),
            "paused": jobs.paused(),
            "current": self.current,
            "recent": store.recent_gallery(20),
            "downloads": _downloads(),
        }


hub = Hub()


@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    q: asyncio.Queue = asyncio.Queue()
    q.remote = not net.is_loopback(ws.client.host if ws.client else None)
    q.put_nowait(hub.snapshot())
    hub.clients.add(q)

    async def sender() -> None:
        while True:
            msg = await q.get()
            if msg is None:
                await ws.close(code=4401)
                return
            await ws.send_json(msg)

    async def receiver() -> None:
        while True:
            await ws.receive_text()

    tasks = [asyncio.create_task(sender()), asyncio.create_task(receiver())]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    except Exception:
        pass
    finally:
        hub.clients.discard(q)
        for t in tasks:
            t.cancel()
        try:
            await ws.close()
        except Exception:
            pass
