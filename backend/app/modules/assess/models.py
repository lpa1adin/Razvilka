"""Сдачи и Оценщик (BRIEF §5.6, §5.11, ADR-012).

Практикум — то, что сдаётся: условие, развилки (вопросы в формате ADR), автотесты и эталоны.
Сдача хранит ровно то, что видели проверяющие: файлы, ответы, отчёты каждого шага.
"""

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class SubmissionStatus(str, enum.Enum):
    testing = "testing"  # автотесты в runner
    reviewing = "reviewing"  # Ревьюер
    evaluating = "evaluating"  # Оценщик
    done = "done"
    failed = "failed"


class RubricSet(Base):
    """Рубрика Оценщика версиями — как правила Ревьюера: сдача помнит, по какой версии оценена."""

    __tablename__ = "rubric_sets"

    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column(Integer, unique=True)
    # [{id: "R5", block: "reasoning|implementation", title, description}]
    criteria: Mapped[list] = mapped_column(JSONB)
    mismatch_penalty: Mapped[float] = mapped_column(Float, default=0.75)  # сколько баллов итога стоит одно «сказал ≠ сделал»
    note: Mapped[str] = mapped_column(String(500), default="")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReferenceProject(Base):
    """Эталонный открытый проект (BRIEF §3.2): с чем Оценщик сравнивает решения."""

    __tablename__ = "reference_projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    url: Mapped[str] = mapped_column(String(300))
    about: Mapped[str] = mapped_column(Text, default="")  # что в нём показательно и какие решения там приняты


class Assignment(Base):
    __tablename__ = "assignments"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    statement: Mapped[str] = mapped_column(Text, default="")  # markdown
    kind: Mapped[str] = mapped_column(String(10), default="any")  # web | python | any — какие автотесты
    # [{id, question, context, reference}] — reference (ответ автора/эталона) скрыт до оценки
    forks: Mapped[list] = mapped_column(JSONB, default=list)
    tests: Mapped[str] = mapped_column(Text, default="")
    reference_ids: Mapped[list] = mapped_column(JSONB, default=list)
    threshold: Mapped[float] = mapped_column(Float, default=3.0)  # с какого итога сдача засчитывается
    published: Mapped[bool] = mapped_column(Boolean, default=False)
    # Этап пути «напиши заново сам» (этап 8): номер, цель, файлы, теория и автопроверка тестов на оригинале
    path_id: Mapped[int | None] = mapped_column(ForeignKey("project_paths.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    goal: Mapped[str] = mapped_column(Text, default="")
    files_hint: Mapped[list] = mapped_column(JSONB, default=list)
    fragment_ids: Mapped[list] = mapped_column(JSONB, default=list)
    check_status: Mapped[str] = mapped_column(String(12), default="not_checked")  # not_checked | queued | passed | failed
    check_report: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Submission(Base):
    __tablename__ = "submissions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    assignment_id: Mapped[int] = mapped_column(ForeignKey("assignments.id", ondelete="CASCADE"), index=True)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    source: Mapped[str] = mapped_column(String(20))  # zip | folder | workspace
    source_name: Mapped[str] = mapped_column(String(300), default="")
    files: Mapped[dict] = mapped_column(JSONB, default=dict)  # путь → текст (бинарное и секреты отброшены)
    vendor: Mapped[list] = mapped_column(JSONB, default=list)  # библиотеки: для тестов есть, в оценку не идут
    warnings: Mapped[list] = mapped_column(JSONB, default=list)
    answers: Mapped[dict] = mapped_column(JSONB, default=dict)  # fork_id → {choice, alternatives, reasons, risks, revisit}
    summary: Mapped[str] = mapped_column(Text, default="")  # «что сделал и почему»
    status: Mapped[SubmissionStatus] = mapped_column(Enum(SubmissionStatus, name="submission_status"), default=SubmissionStatus.testing)
    steps: Mapped[list] = mapped_column(JSONB, default=list)
    tests: Mapped[dict | None] = mapped_column(JSONB)
    review_id: Mapped[int | None] = mapped_column(ForeignKey("reviews.id", ondelete="SET NULL"))
    rubric_version: Mapped[int] = mapped_column(Integer)
    evaluation: Mapped[dict | None] = mapped_column(JSONB)
    score: Mapped[float | None] = mapped_column(Float)
    passed: Mapped[bool | None] = mapped_column(Boolean)
    error: Mapped[str | None] = mapped_column(Text)
    tokens: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
