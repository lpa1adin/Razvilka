import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class GenStatus(str, enum.Enum):
    """Шаги генерации (BRIEF §5.10). Публикация — не статус заявки: её видно по самому контенту."""

    proposed = "proposed"  # заявка пользователя из чата — ждёт решения админа
    new = "new"  # принята, плана ещё нет
    planning = "planning"  # Claude строит план
    plan_ready = "plan_ready"  # план ждёт правок и утверждения админа
    drafting = "drafting"  # Claude пишет черновик по утверждённому плану, идут автопроверки
    draft_ready = "draft_ready"  # черновик готов: проверка админом → публикация
    paused = "paused"  # админ приостановил черновик (например, кончается лимит подписки) — продолжит кнопкой
    failed = "failed"  # шаг упал — текст ошибки в error, шаг можно повторить
    rejected = "rejected"  # админ отклонил заявку пользователя


class GenWhat(str, enum.Enum):
    course = "course"
    task = "task"  # одно или несколько практических заданий без курса
    quiz = "quiz"  # банк вопросов
    path = "path"  # путь «напиши заново сам» по проекту (BRIEF §5.5)


class GenRequest(Base):
    __tablename__ = "gen_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[GenStatus] = mapped_column(Enum(GenStatus, name="gen_status"), default=GenStatus.new)
    what: Mapped[GenWhat] = mapped_column(Enum(GenWhat, name="gen_what"), default=GenWhat.course)
    origin: Mapped[str] = mapped_column(String(10), default="admin")  # admin | user
    project: Mapped[str] = mapped_column(String(200), default="")  # папка в ProjectsWithClaude; пусто — тема без проекта
    focus: Mapped[str] = mapped_column(String(300), default="")  # часть проекта: папка или файл
    topic: Mapped[str] = mapped_column(String(300), default="")
    level: Mapped[int] = mapped_column(Integer, default=2)  # 1 — новичок, 2 — средний, 3 — продвинутый
    notes: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    plan: Mapped[dict | None] = mapped_column(JSONB)  # Plan — правит админ
    # Ход текущего шага: [{key, label, state: pending|running|done|failed|skipped, detail}]
    steps: Mapped[list] = mapped_column(JSONB, default=list)
    # Что создано: {course_id, topic_ids, lessons: {lesson_id: {task_id, question_ids, notes}}}
    result: Mapped[dict] = mapped_column(JSONB, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    # Запрошенная пауза: "" — нет, after — после текущего урока, now — прервать вызов Claude сразу
    pause: Mapped[str] = mapped_column(String(10), default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
