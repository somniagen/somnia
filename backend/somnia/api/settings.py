from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Body, HTTPException, Request

from .. import auth, config, net
from ..hub import hub

router = APIRouter(prefix="/api")


def masked() -> dict:
    d = asdict(config.settings())
    t = d.get("civitaiToken") or ""
    if t:
        d["civitaiToken"] = "****" + t[-4:]
    d["lanPassword"] = auth.MASK if d.get("lanPassword") else ""
    return d


@router.get("/settings")
def get_settings() -> dict:
    return masked()


@router.patch("/settings")
def patch_settings(request: Request, body: dict = Body(...)) -> dict:
    if not net.is_loopback(request.client.host if request.client else None):
        raise HTTPException(403, "settings can only be changed from this machine")
    tok = body.get("civitaiToken")
    if isinstance(tok, str) and tok.startswith("****"):
        body.pop("civitaiToken")
    pw = body.pop("lanPassword", None)
    if isinstance(pw, str) and pw != auth.MASK:
        body["lanPassword"] = auth.hash_password(pw) if pw else ""
    config.update_settings(**body)
    if body.get("lanPassword"):
        hub.kick_remote()
    m = masked()
    hub.broadcast({"type": "settings", "settings": m})
    return m


@router.get("/net")
def get_net() -> dict:
    s = config.settings()
    return {"lanEnabled": s.lanEnabled, "urls": net.lan_urls(s.port)}
