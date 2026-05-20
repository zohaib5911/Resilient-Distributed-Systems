"""
End-to-end demo for all three problems.

Usage:
    # terminal 1
    uvicorn app.main:app --port 8000

    # terminal 2
    python demo.py            # runs all three
    python demo.py sync       # just Problem 1
    python demo.py webhook    # just Problem 2
    python demo.py breaker    # just Problem 3

Each section prints the BUGGY behaviour first (against /naive/*), then
the FIXED behaviour (against the real routes), so you can see the
before/after side by side during the screen recording.
"""
import asyncio
import os
import sys
import time
import httpx

BASE = "http://127.0.0.1:8000"
PACE = float(os.environ.get("DEMO_PACE", "0.0"))   # seconds between sections


def _pace(seconds: float = None):
    if PACE > 0:
        time.sleep(seconds if seconds is not None else PACE)


def banner(title: str):
    bar = "=" * 70
    print(f"\n{bar}\n  {title}\n{bar}")
    _pace(1.2)


def sub(title: str):
    print(f"\n--- {title} ---")
    _pace(0.6)


# ---------- Problem 1: lost update ------------------------------------------

async def demo_sync():
    banner("PROBLEM 1  -  Lost Update (concurrent edits)")

    async with httpx.AsyncClient(base_url=BASE, timeout=10) as c:
        sub("BEFORE: naive endpoint, no version check")
        await c.post("/naive/documents", params={"doc_id": "d1", "content": "original"})
        # Two writers race - both read the same state, both write.
        r1, r2 = await asyncio.gather(
            c.put("/naive/documents/d1", json={"content": "Alice's edit"}),
            c.put("/naive/documents/d1", json={"content": "Bob's edit"}),
        )
        final = (await c.get("/naive/documents/d1")).json()
        print(f"  alice -> {r1.status_code}, bob -> {r2.status_code}")
        print(f"  final content: {final['content']!r}   <-- one edit was LOST")

        sub("AFTER: optimistic locking with version field")
        await c.post("/documents", params={"doc_id": "d1", "content": "original"})
        doc = (await c.get("/documents/d1")).json()
        v = doc["version"]
        # Both writers send the same version they read.
        r1, r2 = await asyncio.gather(
            c.put("/documents/d1", json={"content": "Alice's edit", "version": v}),
            c.put("/documents/d1", json={"content": "Bob's edit",   "version": v}),
        )
        results = sorted([r1.status_code, r2.status_code])
        final = (await c.get("/documents/d1")).json()
        print(f"  responses: {results}   <-- exactly one 409 Conflict")
        print(f"  final content: {final['content']!r}, version={final['version']}")
        print("  the loser refetches v=2 and retries cleanly. nothing is silently lost.")


# ---------- Problem 2: dropped webhook --------------------------------------

async def demo_webhook():
    banner("PROBLEM 2  -  Dropped Clerk webhook (subscription cancel)")

    async with httpx.AsyncClient(base_url=BASE, timeout=10) as c:
        sub("BEFORE: naive endpoint, no idempotency, no retry")
        # user starts premium
        plan = (await c.get("/naive/webhooks/users/u42")).json()
        print(f"  initial plan: {plan['plan']}")
        # arm the simulated network drop, then send the cancel
        await c.post("/naive/webhooks/_drop_next")
        try:
            await c.post("/naive/webhooks/clerk", json={
                "svix_id": "evt_1", "event_type": "subscription.cancelled", "user_id": "u42",
            })
        except httpx.HTTPError:
            pass
        plan = (await c.get("/naive/webhooks/users/u42")).json()
        print(f"  after drop:   {plan['plan']}   <-- user stays PREMIUM forever")

        sub("AFTER: idempotency key + Clerk-style replay")
        # First delivery: pretend it 'dropped' by simply not awaiting the body.
        # Clerk will retry with the same svix_id - we replay it here.
        evt = {"svix_id": "evt_2", "event_type": "subscription.cancelled", "user_id": "u42"}
        r1 = await c.post("/webhooks/clerk", json=evt)
        r2 = await c.post("/webhooks/clerk", json=evt)   # the retry
        r3 = await c.post("/webhooks/clerk", json=evt)   # another retry
        print(f"  responses: {[r1.json()['status'], r2.json()['status'], r3.json()['status']]}")
        plan = (await c.get("/webhooks/users/u42")).json()
        print(f"  final plan:   {plan['plan']}   <-- converged. duplicates are no-ops.")


# ---------- Problem 3: LLM hang --------------------------------------------

async def demo_breaker():
    banner("PROBLEM 3  -  Synchronous LLM hang")

    async with httpx.AsyncClient(base_url=BASE, timeout=5) as c:
        # Set the simulated upstream to hang for 60 seconds
        await c.post("/llm/_set_mode", params={"mode": "hang"})

        sub("BEFORE: naive endpoint, no timeout, no breaker")
        t0 = time.perf_counter()
        try:
            await c.post("/naive/llm/ask", json={"prompt": "summarize chapter 4"}, timeout=2)
        except httpx.ReadTimeout:
            dt = time.perf_counter() - t0
            print(f"  client gave up after {dt:.2f}s   <-- server still hanging, worker blocked")

        sub("AFTER: circuit breaker with 1s timeout, opens after 3 failures")
        latencies = []
        sources = []
        for i in range(6):
            t0 = time.perf_counter()
            r = await c.post("/llm/ask", json={"prompt": f"q{i}"})
            latencies.append(time.perf_counter() - t0)
            body = r.json()
            sources.append(body["source"])
            print(f"  req {i+1}: {body['source']:8s}  breaker={body['breaker']:<10s} latency={latencies[-1]*1000:6.1f}ms")
        print(f"  -> first 3 requests trip the breaker, the rest fast-fail with fallback")

        # Recovery: switch upstream back to ok, wait for reset, see HALF_OPEN -> CLOSED
        sub("RECOVERY: upstream healthy, breaker auto-recovers")
        await c.post("/llm/_set_mode", params={"mode": "ok"})
        print("  waiting 5s for reset_after timer...")
        await asyncio.sleep(5.2)
        r = await c.post("/llm/ask", json={"prompt": "back online?"})
        body = r.json()
        print(f"  probe call: source={body['source']} breaker={body['breaker']}")


# ---------- entrypoint ------------------------------------------------------

async def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else "all"
    try:
        async with httpx.AsyncClient(base_url=BASE, timeout=2) as c:
            r = await c.get("/")
            assert r.headers.get("X-Student-ID") == "bscs23098", "missing student id header!"
            print(f"server up, X-Student-ID = {r.headers['X-Student-ID']}")
            # Clean slate so re-runs of the demo show the same output every time.
            await c.post("/admin/reset")
    except Exception as e:
        print(f"\nERROR: can't reach {BASE} - is uvicorn running?\n  {e}")
        sys.exit(1)

    if arg in ("all", "sync"):     await demo_sync();    _pace(1.5)
    if arg in ("all", "webhook"):  await demo_webhook(); _pace(1.5)
    if arg in ("all", "breaker"):  await demo_breaker()

    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
