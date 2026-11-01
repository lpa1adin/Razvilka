import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class JobStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"


class Job(Base):
    """Очередь фоновых задач прямо в Postgres (ADR-004)."""

    __tablename__ = "jobs"
    __table_args__ = (Index("ix_jobs_pick", "kind", "status", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    # kind = какой воркер забирает задачу: agent, collector, runner
    kind: Mapped[str] = mapped_column(String(32))
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus, name="job_status"), default=JobStatus.queued)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    result: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WorkerHeartbeat(Base):
    """Последний «пульс» каждого воркера — чтобы интерфейс показывал, кто жив."""

    __tablename__ = "worker_heartbeats"

    worker: Mapped[str] = mapped_column(String(32), primary_key=True)
    seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
