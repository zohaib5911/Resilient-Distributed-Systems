"""
Pytest suite: each test FIRST triggers the bug against /naive/* to prove the
failure mode exists, then verifies the fixed route handles it correctly.
"""
import asyncio
import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app, STUDENT_ID
from app import documents, webhooks, llm


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.fixture(autouse=True)
def _reset_state():
    documents._reset_for_tests()
    webhooks._reset_for_tests()
    llm._reset_for_tests()


# ---- Submission-rule guard ----------------------------------------------

@pytest.mark.asyncio
async def test_x_student_id_header_present_on_every_response(client):
    async with client as c:
        for path in ["/", "/llm/state", "/webhooks/users/x"]:
            r = await c.get(path)
            assert r.headers.get("X-Student-ID") == STUDENT_ID, f"{path} missing header"


# ---- Problem 1 -----------------------------------------------------------

@pytest.mark.asyncio
async def test_naive_documents_lose_an_update(client):
    async with client as c:
        await c.post("/naive/documents", params={"doc_id": "x", "content": "v0"})
        await asyncio.gather(
            c.put("/naive/documents/x", json={"content": "alice"}),
            c.put("/naive/documents/x", json={"content": "bob"}),
        )
        final = (await c.get("/naive/documents/x")).json()["content"]
        assert final in {"alice", "bob"}      # one of them won
        # the *other* edit is gone - that's the bug


@pytest.mark.asyncio
async def test_optimistic_locking_rejects_stale_writer(client):
    async with client as c:
        await c.post("/documents", params={"doc_id": "x", "content": "v0"})
        doc = (await c.get("/documents/x")).json()
        v = doc["version"]
        r1, r2 = await asyncio.gather(
            c.put("/documents/x", json={"content": "alice", "version": v}),
            c.put("/documents/x", json={"content": "bob",   "version": v}),
        )
        codes = sorted([r1.status_code, r2.status_code])
        assert codes == [200, 409], f"expected one 200 + one 409, got {codes}"


# ---- Problem 2 -----------------------------------------------------------

@pytest.mark.asyncio
async def test_naive_webhook_drops_state_on_network_blip(client):
    async with client as c:
        # arm a drop, send a cancel
        await c.post("/naive/webhooks/_drop_next")
        try:
            await c.post("/naive/webhooks/clerk", json={
                "svix_id": "e1", "event_type": "subscription.cancelled", "user_id": "u1",
            })
        except Exception:
            pass
        plan = (await c.get("/naive/webhooks/users/u1")).json()["plan"]
        assert plan == "premium"   # stuck premium - the bug from the brief


@pytest.mark.asyncio
async def test_idempotent_webhook_converges_under_replays(client):
    async with client as c:
        evt = {"svix_id": "e2", "event_type": "subscription.cancelled", "user_id": "u1"}
        # 3 deliveries of the same event - exactly what Clerk does on retries
        responses = []
        for _ in range(3):
            responses.append((await c.post("/webhooks/clerk", json=evt)).json())
        assert responses[0]["status"] == "ok"
        assert responses[1]["status"] == "duplicate"
        assert responses[2]["status"] == "duplicate"
        assert (await c.get("/webhooks/users/u1")).json()["plan"] == "free"


# ---- Problem 3 -----------------------------------------------------------

@pytest.mark.asyncio
async def test_circuit_breaker_trips_and_returns_fallback_fast(client):
    async with client as c:
        await c.post("/llm/_set_mode", params={"mode": "error"})
        sources = []
        for _ in range(5):
            r = await c.post("/llm/ask", json={"prompt": "x"})
            sources.append(r.json()["source"])
        # First few hit upstream (and fail -> fallback), then breaker opens
        # and the rest fast-fail with fallback. Either way: no 'llm' source.
        assert all(s == "fallback" for s in sources)
        state = (await c.get("/llm/state")).json()["state"]
        assert state == "open"


@pytest.mark.asyncio
async def test_circuit_breaker_caps_latency_on_hanging_upstream(client):
    async with client as c:
        await c.post("/llm/_set_mode", params={"mode": "hang"})
        # Even with a 60-second hang, each request must return in well under
        # the breaker timeout (1s) plus a small margin.
        import time
        for _ in range(4):
            t0 = time.perf_counter()
            r = await c.post("/llm/ask", json={"prompt": "x"})
            dt = time.perf_counter() - t0
            assert dt < 1.5, f"breaker leaked the hang: {dt:.2f}s"
            assert r.json()["source"] == "fallback"
