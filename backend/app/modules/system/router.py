from datetime import UTC, datetime, timedelta

from fastapi import APIRouter
from sqlalchemy import select, text

from app.modules.auth.deps import CurrentUser, Db
from app.modules.jobs.models import WorkerHeartbeat

router = APIRouter(prefix="/api", tags=["system"])

WORKERS = ("agent", "chat", "review", "collector", "runner")
# Воркер отбивает пульс каждые 5 с; трижды пропустил — считаем, что он не работает.
ALIVE_WINDOW = timedelta(seconds=15)


@router.get("/health")
def health(db: Db):
    db.execute(text("select 1"))
    return {"status": "ok"}


@router.get("/system/status")
def system_status(db: Db, _: CurrentUser):
    seen = {hb.worker: hb.seen_at for hb in db.scalars(select(WorkerHeartbeat))}
    now = datetime.now(UTC)
    return {
        "api": "ok",
        "workers": [
            {
                "name": name,
                "alive": name in seen and now - seen[name] < ALIVE_WINDOW,
                "seen_at": seen.get(name),
            }
            for name in WORKERS
        ],
    }
