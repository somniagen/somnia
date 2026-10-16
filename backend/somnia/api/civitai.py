from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import civitai, downloads

router = APIRouter(prefix="/api", tags=["civitai"])


def _wrap(e: civitai.CivitaiError) -> HTTPException:
    return HTTPException(e.status if 400 <= e.status < 600 else 502, str(e))


@router.get("/civitai/search")
async def search(
    query: str | None = None,
    types: str | None = None,
    sort: str | None = None,
    period: str | None = None,
    baseModels: str | None = None,
    nsfw: bool | None = None,
    cursor: str | None = None,
    limit: int = 24,
):
    try:
        return await civitai.search(
            dict(query=query, types=types, sort=sort, period=period, baseModels=baseModels, nsfw=nsfw, cursor=cursor, limit=limit)
        )
    except civitai.CivitaiError as e:
        raise _wrap(e)


@router.get("/civitai/models/{model_id}")
async def model(model_id: int):
    try:
        return await civitai.get_model(model_id)
    except civitai.CivitaiError as e:
        raise _wrap(e)


@router.get("/civitai/images")
async def images(modelVersionId: int, cursor: str | None = None, limit: int = 24, nsfw: bool | None = None):
    try:
        return await civitai.get_images(modelVersionId, cursor, limit, nsfw)
    except civitai.CivitaiError as e:
        raise _wrap(e)


class DownloadReq(BaseModel):
    versionId: int
    fileId: int | None = None


@router.post("/civitai/download")
async def download(req: DownloadReq):
    try:
        return await downloads.start(req.versionId, req.fileId)
    except civitai.CivitaiError as e:
        raise _wrap(e)


@router.get("/downloads")
async def list_downloads():
    return downloads.list_downloads()


@router.delete("/downloads/{did}")
async def cancel(did: str):
    if not downloads.cancel(did):
        raise HTTPException(404, "download not found")
    return {"ok": True}
