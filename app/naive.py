"""
The intentionally-broken "before" implementations.

These are kept side-by-side with the fixed routes so the demo can hit
both under the same FastAPI server and show the failure vs. the fix
without restarting anything.
"""
import asyncio
from fastapi import APIRouter
from pydantic import BaseModel

from . import llm as llm_mod

router = APIRouter(prefix="/naive", tags=["naive (buggy)"])

# --- naive documents: last-write-wins, no version check -----------------------
_NAIVE_DOCS: dict[str, str] = {}


class NaiveDocIn(BaseModel):
    content: str


@router.post("/documents")
def naive_create(doc_id: str, content: str = ""):
    _NAIVE_DOCS[doc_id] = content
    return {"id": doc_id, "content": content}


@router.get("/documents/{doc_id}")
def naive_read(doc_id: str):
    return {"id": doc_id, "content": _NAIVE_DOCS.get(doc_id, "")}


@router.put("/documents/{doc_id}")
async def naive_update(doc_id: str, body: NaiveDocIn):
    # Read-modify-write with an artificial pause - this is what makes the
    # lost-update window observable in a demo. A real DB without locking
    # has the same gap, just much smaller.
    _ = _NAIVE_DOCS.get(doc_id, "")
    await asyncio.sleep(0.1)
    _NAIVE_DOCS[doc_id] = body.content
    return {"id": doc_id, "content": body.content}


# --- naive webhook: no idempotency, no retries --------------------------------
_NAIVE_USERS: dict[str, str] = {}
_NAIVE_DROP_NEXT = {"flag": False}


class NaiveEvent(BaseModel):
    svix_id: str
    event_type: str
    user_id: str


@router.post("/webhooks/_drop_next")
def naive_drop_next():
    """Simulate the network dropping the next webhook delivery."""
    _NAIVE_DROP_NEXT["flag"] = True
    return {"will_drop": True}


@router.post("/webhooks/clerk")
def naive_webhook(event: NaiveEvent):
    if _NAIVE_DROP_NEXT["flag"]:
        _NAIVE_DROP_NEXT["flag"] = False
        # Pretend the request never arrived. No retry, no DLQ, just lost.
        raise RuntimeError("network drop")
    if event.event_type == "subscription.cancelled":
        _NAIVE_USERS[event.user_id] = "free"
    elif event.event_type == "subscription.created":
        _NAIVE_USERS[event.user_id] = "premium"
    return {"ok": True}


@router.get("/webhooks/users/{user_id}")
def naive_get_user(user_id: str):
    return {"user_id": user_id, "plan": _NAIVE_USERS.get(user_id, "premium")}
    # Note the "premium" default: this is the bug from the brief - once
    # they were premium, a dropped cancel leaves them premium forever.


# --- naive LLM: synchronous, no breaker ---------------------------------------
@router.post("/llm/ask")
async def naive_llm_ask(body: dict):
    # Just await the upstream directly. If it hangs, this request hangs,
    # and so does every other worker thread waiting on the same call.
    answer = await llm_mod._upstream_llm(body.get("prompt", ""))
    return {"source": "llm-naive", "answer": answer}
