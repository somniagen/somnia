from __future__ import annotations

import asyncio

from fastapi import APIRouter, Body, HTTPException, Request, Response

from .. import auth, net

router = APIRouter(prefix="/api/auth")

YEAR = 365 * 24 * 3600


def _loopback(request: Request) -> bool:
    return net.is_loopback(request.client.host if request.client else None)


@router.get("")
def status(request: Request) -> dict:
    required = auth.enabled() and not _loopback(request)
    return {"required": required, "ok": not required or auth.valid(request.cookies.get(auth.COOKIE))}


@router.post("/login")
async def login(request: Request, response: Response, body: dict = Body(...)) -> dict:
    if not auth.enabled():
        return {"required": False, "ok": True}
    pw = body.get("password")
    ok = isinstance(pw, str) and await asyncio.to_thread(auth.check_password, pw)
    if not ok:
        await asyncio.sleep(1.0)
        raise HTTPException(401, "wrong password")
    response.set_cookie(auth.COOKIE, auth.token(), max_age=YEAR, httponly=True, samesite="lax",
                        secure=request.url.scheme == "https", path="/")
    return {"required": not _loopback(request), "ok": True}


@router.post("/logout")
def logout(request: Request, response: Response) -> dict:
    response.delete_cookie(auth.COOKIE, path="/")
    required = auth.enabled() and not _loopback(request)
    return {"required": required, "ok": not required}
