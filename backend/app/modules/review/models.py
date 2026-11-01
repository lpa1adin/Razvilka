import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ReviewStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"


class ReviewKind(str, enum.Enum):
    learner = "learner"  # код ученика из песочницы — по кнопке «Ревью кода»
    reference = "reference"  # эталон задания — автопроверка перед публикацией (BRIEF §5.10)
    project = "project"  # сданный проект — шаг 2 конвейера сдачи (BRIEF §5.11)


class ReviewRuleSet(Base):
    """Версия правил Ревьюера. Правку админа сохраняем новой версией: каждое ревью ссылается на ту, по которой проверяли."""

    __tablename__ = "review_rule_sets"

    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column(Integer, unique=True)
    # [{id: "SEC-02", group: "SEC — безопасность", text: "...", enabled: true}]
    rules: Mapped[list] = mapped_column(JSONB)
    note: Mapped[str] = mapped_column(String(500), default="")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Review(Base):
    """Одна независимая проверка. Хранит ровно то, что видел Ревьюер, — отчёт можно перепроверить."""

    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[ReviewKind] = mapped_column(Enum(ReviewKind, name="review_kind"))
    status: Mapped[ReviewStatus] = mapped_column(Enum(ReviewStatus, name="review_status"), default=ReviewStatus.queued)
    requested_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    task_version: Mapped[int | None] = mapped_column(Integer)
    spec_hash: Mapped[str | None] = mapped_column(String(64))  # для эталона: какую версию задания проверяли
    title: Mapped[str] = mapped_column(String(300), default="")
    statement: Mapped[str] = mapped_column(Text, default="")
    files: Mapped[dict] = mapped_column(JSONB, default=dict)
    rules_version: Mapped[int] = mapped_column(Integer)
    verdict: Mapped[str | None] = mapped_column(String(30))  # pass | changes_requested — считает код, а не модель
    findings: Mapped[list] = mapped_column(JSONB, default=list)
    dropped: Mapped[list] = mapped_column(JSONB, default=list)  # замечания, отброшенные проверкой формата
    tokens: Mapped[dict] = mapped_column(JSONB, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    accepted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    accepted_note: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
