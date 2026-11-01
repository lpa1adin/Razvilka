from app.core.db import SessionLocal
from app.modules.jobs import queue
from app.modules.jobs.models import JobStatus


def test_claim_takes_oldest_and_skips_locked():
    with SessionLocal() as db:
        first = queue.enqueue(db, "runner", {"type": "ping"})
        queue.enqueue(db, "runner", {"type": "ping"})

    with SessionLocal() as a, SessionLocal() as b:
        taken_a = queue.claim_next(a, "runner")
        taken_b = queue.claim_next(b, "runner")
        assert taken_a.id == first.id
        assert taken_b.id != taken_a.id
        assert taken_a.status is JobStatus.running


def test_claim_ignores_other_kinds():
    with SessionLocal() as db:
        queue.enqueue(db, "agent", {"type": "ping"})
        assert queue.claim_next(db, "runner") is None
