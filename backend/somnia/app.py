from __future__ import annotations

import asyncio
import importlib
import inspect
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import config, jobs, net
from .hub import hub
from .hub import router as hub_router

ROUTERS = ["jobs", "gallery", "settings", "prompts", "models", "civitai", "tags", "inpaint", "editors"]
DIST = config.ROOT / "web" / "dist"


class LanGuard:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket") and not config.settings().lanEnabled:
            client = scope.get("client")
            if not net.is_loopback(client[0] if client else None):
                if scope["type"] == "websocket":
                    await send({"type": "websocket.close", "code": 1008})
                else:
                    body = b'{"detail":"LAN access is disabled"}'
                    await send({"type": "http.response.start", "status": 403,
                                "headers": [(b"content-type", b"application/json"),
                                            (b"content-length", str(len(body)).encode())]})
                    await send({"type": "http.response.body", "body": body})
                return
        await self.app(scope, receive, send)


def create_app() -> FastAPI:
    modules = []
    for name in ROUTERS:
        try:
            modules.append(importlib.import_module(f"somnia.api.{name}"))
        except ImportError as e:
            print(f"[somnia] api module '{name}' not loaded: {e}", file=sys.stderr)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        hub.loop = asyncio.get_running_loop()
        jobs.start()
        for m in modules:
            fn = getattr(m, "startup", None)
            if fn:
                r = fn()
                if inspect.isawaitable(r):
                    await r
        yield

    app = FastAPI(title="somnia", lifespan=lifespan)
    out = Path(config.settings().outputDir)
    (out / "thumbs").mkdir(parents=True, exist_ok=True)
    up = config.DATA_DIR / "uploads"
    up.mkdir(parents=True, exist_ok=True)
    app.mount("/outputs", StaticFiles(directory=out), name="outputs")
    app.mount("/files/uploads", StaticFiles(directory=up), name="uploads")
    app.include_router(hub_router)
    for m in modules:
        r = getattr(m, "router", None)
        if r is not None:
            app.include_router(r)

    if DIST.exists():
        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            if path.startswith(("api/", "outputs/", "files/")):
                raise HTTPException(404)
            f = (DIST / path).resolve()
            if path and f.is_file() and DIST.resolve() in f.parents:
                return FileResponse(f)
            return FileResponse(DIST / "index.html")

    app.add_middleware(LanGuard)
    return app
