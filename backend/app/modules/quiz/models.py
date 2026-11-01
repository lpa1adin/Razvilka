import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class QuestionType(str, enum.Enum):
    single = "single"  # один ответ (сюда же «найди ошибку в коде» — вопрос с кодом)
    multiple = "multiple"  # несколько ответов, засчитывается только точное совпадение
    order = "order"  # расставить шаги по порядку
    match = "match"  # сопоставить левый и правый столбцы


class QuestionStatus(str, enum.Enum):
    draft = "draft"
    published = "published"
    archived = "archived"


class AttemptStatus(str, enum.Enum):
    in_progress = "in_progress"
    finished = "finished"


class QuizTopic(Base):
    __tablename__ = "quiz_topics"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    published: Mapped[bool] = mapped_column(Boolean, default=False)
    size: Mapped[int] = mapped_column(Integer, default=10)  # сколько вопросов в одном тесте
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Question(Base):
    """Вопрос банка. Попытка хранит снимок вопроса, поэтому правка не меняет уже пройденные тесты (ADR-016)."""

    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("quiz_topics.id", ondelete="CASCADE"), index=True)
    type: Mapped[QuestionType] = mapped_column(Enum(QuestionType, name="question_type"))
    prompt: Mapped[str] = mapped_column(Text)  # markdown
    code: Mapped[str] = mapped_column(Text, default="")  # фрагмент кода к вопросу (найди ошибку, docker-compose…)
    code_lang: Mapped[str] = mapped_column(String(20), default="")
    options: Mapped[dict] = mapped_column(JSONB)  # single/multiple/order: {"items": [...]}; match: {"left": [...], "right": [...]}
    answer: Mapped[dict] = mapped_column(JSONB)  # {"correct": [...]} | {"order": [...]} | {"pairs": {...}}
    explanation: Mapped[str] = mapped_column(Text, default="")  # почему так — показывается после теста
    fragment_id: Mapped[int | None] = mapped_column(ForeignKey("fragments.id", ondelete="SET NULL"))  # источник
    subtopic: Mapped[str] = mapped_column(String(120), default="")
    difficulty: Mapped[int] = mapped_column(Integer, default=2)  # 1 — база, 2 — средне, 3 — сложно
    status: Mapped[QuestionStatus] = mapped_column(Enum(QuestionStatus, name="question_status"), default=QuestionStatus.draft)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("quiz_topics.id", ondelete="CASCADE"), index=True)
    status: Mapped[AttemptStatus] = mapped_column(Enum(AttemptStatus, name="quiz_attempt_status"), default=AttemptStatus.in_progress)
    mistakes_only: Mapped[bool] = mapped_column(Boolean, default=False)  # «Повторить ошибки»
    score: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class QuizAttemptItem(Base):
    __tablename__ = "quiz_attempt_items"
    __table_args__ = (UniqueConstraint("attempt_id", "position"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    attempt_id: Mapped[int] = mapped_column(ForeignKey("quiz_attempts.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    question_id: Mapped[int | None] = mapped_column(ForeignKey("questions.id", ondelete="SET NULL"), index=True)
    snapshot: Mapped[dict] = mapped_column(JSONB)  # вопрос как он был в момент теста, варианты уже перемешаны
    response: Mapped[dict | None] = mapped_column(JSONB)
    correct: Mapped[bool | None] = mapped_column(Boolean)
