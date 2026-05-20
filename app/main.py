"""
StudySync backend - PDC Assignment 4
M Zohaib Sajjad - bscs23098

Routes:
  /documents/*    Problem 1 (Optimistic Locking)
  /webhooks/*     Problem 2 (Idempotent webhook + DLQ)
  /llm/*          Problem 3 (Circuit Breaker)
  /naive/*        The buggy "before" versions used by the demo
"""
from fastapi import FastAPI, Request

from . import documents, webhooks, llm, naive

STUDENT_ID = "bscs23098"

app = FastAPI(title="StudySync (resilient)", version="1.0")


@app.middleware("http")
async def add_student_id_header(request: Request, call_next):
    # Required by the rubric. Missing header = auto-zero on Part 3.
    response = await call_next(request)
    response.headers["X-Student-ID"] = STUDENT_ID
    return response


@app.get("/")
def root():
    return {"app": "StudySync", "student": STUDENT_ID}


@app.post("/admin/reset")
def reset_all():
    """Wipe in-memory state so the demo can be re-run cleanly."""
    documents._reset_for_tests()
    webhooks._reset_for_tests()
    llm._reset_for_tests()
    # Also reset the naive modules' state.
    naive._NAIVE_DOCS.clear()
    naive._NAIVE_USERS.clear()
    naive._NAIVE_DROP_NEXT["flag"] = False
    return {"reset": True}


app.include_router(documents.router)
app.include_router(webhooks.router)
app.include_router(llm.router)
app.include_router(naive.router)
