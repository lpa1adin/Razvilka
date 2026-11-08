from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.modules.jobs.models import Job, JobStatus, WorkerHeartbeat


def enqueue(db: Session, kind: str, payload: dict) -> Job:
    job = Job(kind=kind, payload=payload)
    db.add(job)
    db.commit()
    return job


def claim_next(db: Session, kind: str) -> Job | None:
    """Забирает самую старую задачу. SKIP LOCKED — два воркера не возьмут одну задачу."""
    job = db.scalar(
        select(Job)
        .where(Job.kind == kind, Job.status == JobStatus.queued)
        .order_by(Job.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if job is None:
        db.rollback()
        return None
    job.status = JobStatus.running
    job.started_at = datetime.now(UTC)
    db.commit()
    return job


def finish(db: Session, job: Job, result: dict | None = None, error: str | None = None) -> None:
    job.status = JobStatus.failed if error else JobStatus.done
    job.result = result
    job.error = error
    job.finished_at = datetime.now(UTC)
    db.commit()


# Эти очереди тратят лимит подписки Claude: прерванное в них не повторяем без админа
PAID_KINDS = ("agent", "review", "chat")


def requeue_interrupted(db: Session, kind: str) -> int:
    """При старте воркера: задачи, которые он не доделал перед падением, возвращаются в очередь.
    Безопасно, пока у каждого вида воркера один экземпляр (так в docker-compose.yml)."""
    jobs = db.scalars(select(Job).where(Job.kind == kind, Job.status == JobStatus.running)).all()
    for job in jobs:
        if kind in PAID_KINDS:
            # Платную работу (Claude) после перезапуска не повторяем молча: админ решает, тратить ли лимит
            job.status = JobStatus.failed
            job.error = "Прервано перезапуском воркера — запустите заново, когда нужно"
            job.finished_at = datetime.now(UTC)
            _stop_owner(db, job)
            continue
        job.status = JobStatus.queued
        job.started_at = None
    db.commit()
    return len(jobs)


def has_pending(db: Session, kind: str, **payload: str) -> bool:
    """Есть ли уже в очереди или в работе задача этого вида с такими полями payload."""
    query = select(func.count()).select_from(Job).where(
        Job.kind == kind, Job.status.in_([JobStatus.queued, JobStatus.running])
    )
    for key, value in payload.items():
        query = query.where(Job.payload[key].astext == value)
    return bool(db.scalar(query))


def queued_count(db: Session, kind: str) -> int:
    return db.scalar(
        select(func.count()).select_from(Job).where(Job.kind == kind, Job.status == JobStatus.queued)
    )


def beat(db: Session, worker: str) -> None:
    now = datetime.now(UTC)
    db.execute(
        insert(WorkerHeartbeat)
        .values(worker=worker, seen_at=now)
        .on_conflict_do_update(index_elements=["worker"], set_={"seen_at": now})
    )
    db.commit()


def _stop_owner(db: Session, job: Job) -> None:
    """Прерванная генерация встаёт на паузу: «Продолжить» на экране заявки запустит её дальше."""
    if job.payload.get("type") != "gen_draft":
        return
    from app.modules.generation.models import GenRequest, GenStatus  # без цикла импортов

    req = db.get(GenRequest, int(job.payload["request_id"]))
    if req is not None and req.status is GenStatus.drafting:
        req.status = GenStatus.paused
        req.result = {**req.result, "resume": {k: job.payload.get(k, "") for k in ("lesson_id", "instruction") if job.payload.get(k)}}
        req.steps = [{**s, "state": "pending", "detail": "прервано перезапуском — нажмите «Продолжить»"} if s["state"] == "running" else s
                     for s in req.steps]
