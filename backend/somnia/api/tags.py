from fastapi import APIRouter, HTTPException, Query

from somnia import tags as core

router = APIRouter(prefix="/api/tags")


@router.get("/search")
def search(q: str = "", limit: int = Query(20, ge=1, le=200), category: int | None = None):
    return core.search(q, limit, category)


@router.get("/wiki/{name}")
def wiki(name: str):
    if not core.normalize(name):
        raise HTTPException(404, "empty tag name")
    try:
        return core.wiki(name)
    except core.WikiError as e:
        raise HTTPException(502, str(e)) from e


@router.get("/related/{name}")
def related(name: str, limit: int = Query(16, ge=1, le=60)):
    if not core.normalize(name):
        raise HTTPException(404, "empty tag name")
    try:
        return core.related(name, limit)
    except core.WikiError as e:
        raise HTTPException(502, str(e)) from e


@router.get("/lookup")
def lookup(names: str = ""):
    return core.lookup([n for n in names.split(",") if n.strip()][:500])


def startup() -> None:
    core.start_background_load()
