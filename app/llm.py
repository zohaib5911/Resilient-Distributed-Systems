"""
Problem 3: Fault Tolerance - circuit breaker around the external LLM.

State machine:
  CLOSED    normal: forward call, count failures
  OPEN      fast-fail: return fallback without touching upstream
  HALF_OPEN single probe call; success -> CLOSED, failure -> OPEN

The whole point is that one bad upstream cannot starve our request
workers anymore - we trip after `failure_threshold` and start returning
a fallback in microseconds instead of blocking 60s per request.
"""
import asyncio
import time
from enum import Enum
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/llm", tags=["llm"])


class State(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 3, reset_after: float = 5.0, call_timeout: float = 1.0):
        self.failure_threshold = failure_threshold
        self.reset_after = reset_after
        self.call_timeout = call_timeout
        self.state = State.CLOSED
        self.failures = 0
        self.opened_at = 0.0

    def _trip(self):
        self.state = State.OPEN
        self.opened_at = time.monotonic()

    async def call(self, coro_fn, *args, **kwargs):
        # Fast-fail path.
        if self.state == State.OPEN:
            if time.monotonic() - self.opened_at >= self.reset_after:
                self.state = State.HALF_OPEN
            else:
                raise CircuitOpen("breaker is open")

        try:
            result = await asyncio.wait_for(coro_fn(*args, **kwargs), timeout=self.call_timeout)
        except (asyncio.TimeoutError, Exception) as e:
            self.failures += 1
            if self.state == State.HALF_OPEN or self.failures >= self.failure_threshold:
                self._trip()
            raise

        # Success path.
        self.failures = 0
        self.state = State.CLOSED
        return result


class CircuitOpen(RuntimeError):
    pass


breaker = CircuitBreaker(failure_threshold=3, reset_after=5.0, call_timeout=1.0)


# --- Simulated upstream LLM ----------------------------------------------------
# `_llm_mode` is flipped by /llm/_set_mode in tests/demo so we don't need a
# real Anthropic key to show the breaker working.
_llm_mode = {"mode": "ok"}  # "ok" | "hang" | "error"


async def _upstream_llm(prompt: str) -> str:
    mode = _llm_mode["mode"]
    if mode == "hang":
        await asyncio.sleep(60)        # simulates the 60s hang from the brief
        return "never reached"
    if mode == "error":
        raise RuntimeError("upstream 500")
    await asyncio.sleep(0.05)
    return f"LLM says: {prompt[::-1]}"


def _fallback(prompt: str) -> str:
    return "[cached fallback] We're experiencing degraded service - try again shortly."


# --- HTTP surface -------------------------------------------------------------

class AskIn(BaseModel):
    prompt: str


@router.post("/ask")
async def ask(body: AskIn):
    try:
        answer = await breaker.call(_upstream_llm, body.prompt)
        return {"source": "llm", "answer": answer, "breaker": breaker.state}
    except CircuitOpen:
        return {"source": "fallback", "answer": _fallback(body.prompt), "breaker": breaker.state}
    except (asyncio.TimeoutError, Exception):
        # Counted as a failure inside breaker.call already.
        return {"source": "fallback", "answer": _fallback(body.prompt), "breaker": breaker.state}


@router.get("/state")
def state():
    return {
        "state": breaker.state,
        "failures": breaker.failures,
        "opened_at": breaker.opened_at,
    }


@router.post("/_set_mode")
def set_mode(mode: str):
    """Test hook: 'ok' | 'hang' | 'error'."""
    if mode not in {"ok", "hang", "error"}:
        return {"error": "bad mode"}
    _llm_mode["mode"] = mode
    return {"mode": mode}


def _reset_for_tests():
    breaker.state = State.CLOSED
    breaker.failures = 0
    breaker.opened_at = 0.0
    _llm_mode["mode"] = "ok"
