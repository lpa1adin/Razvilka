import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.modules.courses.models import VersionStatus


class CheckStatus(str, enum.Enum):
    not_checked = "not_checked"
    queued = "queued"
    passed = "passed"
    failed = "failed"


class Task(Base):
    """Практическое задание. Версии устроены как у курсов (ADR-013)."""

    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    published_version: Mapped[int | None] = mapped_column(Integer)
    draft_version: Mapped[int | None] = mapped_column(Integer)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class TaskVersion(Base):
    __tablename__ = "task_versions"
    __table_args__ = (UniqueConstraint("task_id", "number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    status: Mapped[VersionStatus] = mapped_column(Enum(VersionStatus, name="course_version_status", create_type=False))
    spec: Mapped[dict] = mapped_column(JSONB)  # TaskSpec: условие, стартовый код, эталон, тесты, подсказки
    # Автопроверка (BRIEF §5.10, п. 4): эталон проходит тесты, стартовый код — нет
    check_status: Mapped[CheckStatus] = mapped_column(Enum(CheckStatus, name="task_check_status"), default=CheckStatus.not_checked)
    check_report: Mapped[dict | None] = mapped_column(JSONB)
    checked_hash: Mapped[str | None] = mapped_column(String(64))  # хэш spec, который проверяли
    change_note: Mapped[str] = mapped_column(String(1500), default="")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TaskWork(Base):
    """Код пользователя по заданию: автосохранение, версия задания, подсказки, решено ли."""

    __tablename__ = "task_work"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True)
    version_number: Mapped[int] = mapped_column(Integer)
    files: Mapped[dict] = mapped_column(JSONB)
    hints_used: Mapped[int] = mapped_column(Integer, default=0)
    mentor_hints: Mapped[int] = mapped_column(Integer, default=0)  # подсказки наставника в чате
    solved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class TaskAttempt(Base):
    """Каждое нажатие «Проверить». Проверка в песочнице идёт в браузере — для самообучения этого достаточно;
    итоговую проверку при сдаче проекта делает runner (ADR-006)."""

    __tablename__ = "task_attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    passed: Mapped[bool] = mapped_column(Boolean)
    results: Mapped[list] = mapped_column(JSONB)
    hints_used: Mapped[int] = mapped_column(Integer, default=0)
    mentor_hints: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
