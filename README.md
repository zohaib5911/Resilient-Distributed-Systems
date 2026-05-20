# M Zohaib Sajjad - bscs23098

Parallel and Distributed Computing - Assignment 4
Building Resilient Distributed Systems (StudySync)

## What's in here

A minimal FastAPI backend that demonstrates three distributed-systems
failure modes and the patterns that fix them. Each fixed route lives
under its real path (`/documents`, `/webhooks`, `/llm`); the original
buggy versions are kept under `/naive/*` so the demo can hit both
within the same running server.

| Problem | Pattern | Code |
|---|---|---|
| 1. Lost update on concurrent edits | Optimistic locking (version field, 409 on stale) | `app/documents.py` |
| 2. Dropped Clerk webhook leaves user premium | Idempotency key + retry queue + DLQ | `app/webhooks.py` |
| 3. Synchronous LLM hang blocks all workers | Circuit breaker (closed/open/half-open) + timeout + fallback | `app/llm.py` |

The required `X-Student-ID: bscs23098` middleware lives in `app/main.py`.

## Run it

```bash
# 1. set up
python3 -m venv .venv
source .venv/bin/activate            # fish: source .venv/bin/activate.fish
pip install -r requirements.txt

# 2. start the server
uvicorn app.main:app --port 8000

# 3. in another terminal, run the demo
python demo.py            # all three problems
python demo.py sync       # just Problem 1
python demo.py webhook    # just Problem 2
python demo.py breaker    # just Problem 3
```

Quick sanity check that the rubric header is present:

```bash
curl -sI http://127.0.0.1:8000/ | grep -i x-student-id
# -> x-student-id: bscs23098
```

## Run the tests

```bash
source .venv/bin/activate
pytest -v
```

Seven tests, each one first reproduces the bug against `/naive/*` and
then proves the fixed route handles it correctly. Includes a guard
test that the `X-Student-ID` header is on every response.

## Layout

```
app/
  main.py         FastAPI app + X-Student-ID middleware
  documents.py    Problem 1 - optimistic locking
  webhooks.py     Problem 2 - idempotent webhook + DLQ
  llm.py          Problem 3 - circuit breaker
  naive.py        Buggy "before" routes for the demo
tests/
  test_problems.py
demo.py           Scripted before/after walkthrough used in the video
docs/
  report.pdf      Parts 1 and 2 (analysis + design + UML)
```
