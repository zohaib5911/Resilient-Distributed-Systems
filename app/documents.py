"""
Problem 1: Lost-update anomaly fix via Optimistic Locking.

Each document carries a monotonically increasing `version`. Clients must
send the version they read; if it doesn't match the current row, we reject
with 409 Conflict instead of silently overwriting the other user's change.
"""
import asyncio
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/documents", tags=["documents"])

# In-memory "DB". A real implementation would use SELECT ... FOR UPDATE
# or a WHERE version = ? guarded UPDATE in Postgres.
_DOCS: dict[str, dict] = {}
_LOCK = asyncio.Lock()


class DocIn(BaseModel):
    content: str
    version: int


class DocOut(BaseModel):
    id: str
    content: str
    version: int


@router.post("", response_model=DocOut)
async def create(doc_id: str, content: str = ""):
    async with _LOCK:
        if doc_id in _DOCS:
            raise HTTPException(409, "already exists")
        _DOCS[doc_id] = {"content": content, "version": 1}
        return DocOut(id=doc_id, content=content, version=1)


@router.get("/{doc_id}", response_model=DocOut)
async def read(doc_id: str):
    if doc_id not in _DOCS:
        raise HTTPException(404, "not found")
    d = _DOCS[doc_id]
    return DocOut(id=doc_id, content=d["content"], version=d["version"])


@router.put("/{doc_id}", response_model=DocOut)
async def update(doc_id: str, body: DocIn):
    # Compare-and-swap under a lock. Without the version check, the second
    # writer would silently clobber the first writer's content.
    async with _LOCK:
        if doc_id not in _DOCS:
            raise HTTPException(404, "not found")
        current = _DOCS[doc_id]
        if body.version != current["version"]:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "version_conflict",
                    "your_version": body.version,
                    "current_version": current["version"],
                },
            )
        current["content"] = body.content
        current["version"] += 1
        return DocOut(id=doc_id, content=current["content"], version=current["version"])


def _reset_for_tests():
    _DOCS.clear()
