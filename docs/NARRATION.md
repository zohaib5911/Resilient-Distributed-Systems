# Demo recording cue sheet (~90 seconds, 2-min hard cap)

## Before you hit record
- Make sure uvicorn is running (`uvicorn app.main:app --port 8000`)
- Have **two terminals** visible side by side, or one big one
- Have `videos/` folder ready — Kooha will save mp4s there

## What to say while running it

**Run command:** `DEMO_PACE=1 python demo.py`
(The `DEMO_PACE=1` adds 1-second pauses between sections so the screen is readable on the recording.)

**Total runtime:** ~30 seconds for the script. Add narration as you go.

---

### 0:00 - Intro (5s)
> "Zohaib, bscs23098. PDC Assignment 4. Three distributed-systems failure
> modes from the StudySync brief, plus the patterns that fix them. Quick
> check: every response carries the required X-Student-ID header."

`curl -sI http://127.0.0.1:8000/ | grep -i x-student-id`

### 0:10 - Problem 1 - Lost Update (20s)
> "Two users edit the same doc concurrently. Without a version check, the
> second writer silently overwrites the first - here Bob's edit wins and
> Alice's is gone. With optimistic locking, Alice succeeds and Bob gets
> a 409 Conflict telling him to refetch. No silent data loss."

### 0:30 - Problem 2 - Dropped Webhook (20s)
> "Clerk sends a cancel webhook, network drops it - the user stays premium
> forever with the naive handler. With idempotency keys, Clerk can safely
> retry the same event: first delivery applies it, duplicates are no-ops,
> the state converges to 'free'."

### 0:50 - Problem 3 - Circuit Breaker (35s)
> "External LLM hangs for 60 seconds. Naive endpoint hangs the worker
> indefinitely. With the breaker: the first three calls hit the 1-second
> timeout and trip the breaker open. Look at the latencies - subsequent
> calls fast-fail in microseconds with a fallback. Once upstream recovers,
> the breaker probes in HALF_OPEN and closes itself automatically."

### 1:25 - Outro (5s)
> "All three patterns - optimistic locking, idempotent retries, and the
> circuit breaker - implemented in FastAPI with a pytest suite that
> reproduces each bug before proving the fix. Repo is
> PDC-Sp24-bscs23098-Sajjad. Thanks."

---

## After recording
- Stop Kooha. Video lands in `~/Videos/Kooha/` by default.
- Move it: `mv ~/Videos/Kooha/<file>.mp4 /home/zohaib/Uni/pdc/PDC-Sp24-bscs23098-Sajjad/videos/demo.mp4`
- Submit `docs/report.pdf` to the classroom, paste the GitHub link, attach the mp4.
