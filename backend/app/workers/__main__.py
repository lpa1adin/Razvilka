"""Точка входа воркеров: `python -m app.workers <kind> [<kind>…]`.

Один код, разные процессы — так устроен модульный монолит (ADR-001).
Тип задачи «ping» умеет каждый воркер — им проверяется очередь и мониторинг от начала до конца.
Сборщик импортирует источники, runner проверяет задания, agent — генерация в Мастерской (долгие задачи),
chat — ответы наставника, review — независимый Ревьюер и Оценщик сдач. agent-worker запускает их в одном процессе, но
в разных потоках: пока Claude пишет курс, чат и ревью не ждут в очереди.
"""

import logging
import signal
import sys
import threading
import time
from datetime import UTC, datetime, timedelta

from prometheus_client import start_http_server
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.agent.claude import AgentUnavailable
import app.models  # noqa: F401 — все модели должны быть известны SQLAlchemy (внешние ключи между модулями)
from app.core.db import SessionLocal
from app.core.metrics import JOBS_DONE, JOBS_QUEUED, WORKER_HEARTBEAT
from app.modules.jobs import queue
from app.modules.arch import service as arch
from app.modules.assess import service as assess
from app.modules.generation import pipeline
from app.modules.library.importer import ImportStopped, run_import
from app.modules.library.models import Source
from app.modules.library.sources import SOURCES
from app.modules.mentor import service as mentor
from app.modules.review import service as review
from app.modules.practice.runner import verify_task

KINDS = ("agent", "chat", "review", "collector", "runner")
POLL_SECONDS = 5
METRICS_PORT = 9100
SCHEDULE_CHECK_SECONDS = 3600

log = logging.getLogger("worker")


def handle(db: Session, kind: str, payload: dict) -> dict:
    if payload.get("type") == "ping":
        return {"pong": True}
    if kind == "collector" and payload.get("type") == "import_source":
        return run_import(db, payload["source"])
    if kind == "runner" and payload.get("type") == "verify_task":
        return verify_task(db, int(payload["version_id"]))
    if kind == "agent" and payload.get("type", "").startswith("gen_"):
        return pipeline.handle(db, payload)
    if kind == "runner" and payload.get("type") == "verify_stage":
        from app.modules.generation.path_pipeline import verify_stage

        return verify_stage(db, int(payload["assignment_id"]), payload["files"])
    if kind == "runner" and payload.get("type") == "test_submission":
        return assess.run_tests(db, int(payload["submission_id"]))
    if kind == "review" and payload.get("type") == "assess_submission":
        return assess.run_assessment(db, int(payload["submission_id"]))
    if kind == "review" and payload.get("type") == "arch_describe":
        return arch.evaluate_describe(db, int(payload["attempt_id"]))
    if kind == "review" and payload.get("type") == "review":
        return review.run(db, int(payload["review_id"]))
    if kind == "chat" and payload.get("type") == "mentor_reply":
        return mentor.reply(db, int(payload["message_id"]), payload.get("files"))
    raise ValueError(f"Воркер {kind} не умеет задачи типа {payload.get('type')!r}")


def schedule_imports(db: Session) -> None:
    """Источник, который давно не обновлялся (или ещё ни разу), ставится в очередь сам."""
    stale_before = datetime.now(UTC) - timedelta(days=settings.import_every_days)
    imported = {s.slug: s.last_import_at for s in db.scalars(select(Source))}
    for slug in SOURCES:
        last = imported.get(slug)
        if (last is None or last < stale_before) and not queue.has_pending(db, "collector", source=slug):
            queue.enqueue(db, "collector", {"type": "import_source", "source": slug})
            log.info("плановый импорт %s поставлен в очередь", slug)


def heartbeat(kind: str, stopping: threading.Event) -> None:
    """Пульс в отдельном потоке: долгая задача (импорт источника) не делает воркер «мёртвым»."""
    while not stopping.is_set():
        try:
            with SessionLocal() as db:
                queue.beat(db, kind)
                JOBS_QUEUED.labels(kind).set(queue.queued_count(db, kind))
            WORKER_HEARTBEAT.labels(kind).set(time.time())
        except Exception:
            log.exception("не удалось отбить пульс")
        stopping.wait(POLL_SECONDS)


def work(kind: str, stopping: threading.Event) -> None:
    with SessionLocal() as db:
        if requeued := queue.requeue_interrupted(db, kind):
            log.warning("недоделанные задачи %s: %s (бесплатные — снова в очереди, платные — остановлены до запуска вручную)", kind, requeued)
    log.info("воркер %s запущен", kind)
    next_schedule_check = 0.0

    while not stopping.is_set():
        with SessionLocal() as db:
            if kind == "collector" and time.monotonic() >= next_schedule_check:
                schedule_imports(db)
                next_schedule_check = time.monotonic() + SCHEDULE_CHECK_SECONDS

            job = queue.claim_next(db, kind)
            if job is not None:
                try:
                    queue.finish(db, job, result=handle(db, kind, job.payload))
                    JOBS_DONE.labels(kind, "done").inc()
                except Exception as exc:  # задача не должна ронять воркер
                    db.rollback()
                    queue.finish(db, job, error=str(exc))
                    JOBS_DONE.labels(kind, "failed").inc()
                    if isinstance(exc, ImportStopped | AgentUnavailable):
                        log.warning("задача %s остановлена: %s", job.id, exc)
                    else:
                        log.exception("задача %s упала", job.id)
                continue
        stopping.wait(POLL_SECONDS if kind not in ("chat", "review") else 1)


def run(kinds: list[str]) -> None:
    stopping = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stopping.set())
    signal.signal(signal.SIGINT, lambda *_: stopping.set())
    start_http_server(METRICS_PORT)
    threads = []
    for kind in kinds:
        threads.append(threading.Thread(target=heartbeat, args=(kind, stopping), daemon=True))
        threads.append(threading.Thread(target=work, args=(kind, stopping), name=kind))
    for thread in threads:
        thread.start()
    # join с таймаутом: так главный поток остаётся отзывчивым к SIGTERM
    for thread in threads:
        while not thread.daemon and thread.is_alive():
            thread.join(1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    kinds = sys.argv[1:]
    if not kinds or any(k not in KINDS for k in kinds):
        sys.exit(f"Использование: python -m app.workers <{'|'.join(KINDS)}> [ещё вид…]")
    run(kinds)
