from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import downloads, hf

router = APIRouter(prefix="/api/hf", tags=["hf"])


def _wrap(e: hf.HfError) -> HTTPException:
    return HTTPException(e.status if 400 <= e.status < 600 else 502, str(e))


@router.get("/search")
async def search(query: str | None = None, category: str = "", sort: str = "downloads", cursor: str | None = None, limit: int = 24):
    try:
        return await hf.search(query, category, sort, cursor, limit)
    except hf.HfError as e:
        raise _wrap(e)


@router.get("/repo/{repo_id:path}")
async def repo(repo_id: str, category: str = ""):
    try:
        return await hf.repo(repo_id, category)
    except hf.HfError as e:
        raise _wrap(e)


class DownloadReq(BaseModel):
    repo: str
    path: str
    kind: str
    sub: str | None = None
    size: int = 0


@router.post("/download")
async def download(req: DownloadReq):
    try:
        return await downloads.start_hf(req.repo, req.path, req.kind, req.sub, req.size)
    except hf.HfError as e:
        raise _wrap(e)
