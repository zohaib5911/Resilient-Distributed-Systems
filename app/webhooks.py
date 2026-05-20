"""
Problem 2: Coordination - never drop a Clerk webhook again.

Three layers of defence:
  1. Idempotency key on each event (Clerk's svix_id). Replaying a
     delivered event is a no-op; replays are how we recover from drops.
  2. In-process retry queue with exponential backoff for handler failures.
  3. Dead-letter queue for poison events that exceed max retries, so a
     human can inspect them instead of silently losing state.
"""
import asyncio
import time
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

# State that would normally live in Postgres/Redis.
_PROCESSED: dict[str, dict] = {}      # idempotency_key -> response
_USERS: dict[str, str] = {}           # user_id -> plan ("free" | "premium")
_RETRY_QUEUE: list[dict] = []
_DLQ: list[dict] = []
MAX_RETRIES = 3


class ClerkEvent(BaseModel):
    svix_id: str          # idempotency key
    event_type: str       # e.g. "subscription.cancelled"
    user_id: str
    # In a real handler we'd also verify the svix signature here.


@router.post("/clerk")
async def clerk(event: ClerkEvent):
    # Idempotency: if we've already processed this svix_id, return the
    # original 200 response. This is what makes the "retry until 2xx"
    # delivery contract safe.
    if event.svix_id in _PROCESSED:
        return {"status": "duplicate", **_PROCESSED[event.svix_id]}

    try:
        result = _apply(event)
    except Exception as e:
        # Transient failure - schedule a retry instead of dropping.
        _RETRY_QUEUE.append({
            "event": event.model_dump(),
            "attempts": 1,
            "next_at": time.time() + 1,
            "last_error": str(e),
        })
        raise HTTPException(503, f"queued for retry: {e}")

    _PROCESSED[event.svix_id] = result
    return {"status": "ok", **result}


def _apply(event: ClerkEvent) -> dict:
    if event.event_type == "subscription.cancelled":
        _USERS[event.user_id] = "free"
        return {"user_id": event.user_id, "plan": "free"}
    if event.event_type == "subscription.created":
        _USERS[event.user_id] = "premium"
        return {"user_id": event.user_id, "plan": "premium"}
    raise ValueError(f"unknown event_type {event.event_type!r}")


@router.get("/users/{user_id}")
def get_user(user_id: str):
    return {"user_id": user_id, "plan": _USERS.get(user_id, "free")}


@router.get("/_debug/dlq")
def debug_dlq():
    return {"retry_queue": _RETRY_QUEUE, "dead_letter": _DLQ}


async def retry_worker():
    """Background task: drain _RETRY_QUEUE with exponential backoff."""
    while True:
        now = time.time()
        # Walk a copy so we can mutate the list in place.
        for item in list(_RETRY_QUEUE):
            if item["next_at"] > now:
                continue
            _RETRY_QUEUE.remove(item)
            event = ClerkEvent(**item["event"])
            if event.svix_id in _PROCESSED:
                continue  # someone else delivered it already
            try:
                result = _apply(event)
                _PROCESSED[event.svix_id] = result
            except Exception as e:
                item["attempts"] += 1
                item["last_error"] = str(e)
                if item["attempts"] > MAX_RETRIES:
                    _DLQ.append(item)
                else:
                    item["next_at"] = now + 2 ** item["attempts"]
                    _RETRY_QUEUE.append(item)
        await asyncio.sleep(0.2)


def _reset_for_tests():
    _PROCESSED.clear()
    _USERS.clear()
    _RETRY_QUEUE.clear()
    _DLQ.clear()
