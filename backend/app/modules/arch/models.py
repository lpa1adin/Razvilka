from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ArchAttempt(Base):
    """Попытка в тренажёре архитектуры. Задания живут в коде (exercises.py) вместе с материалами, попытки — в базе."""

    __tablename__ = "arch_attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    slug: Mapped[str] = mapped_column(String(80), index=True)
    answer: Mapped[dict] = mapped_column(JSONB)
    result: Mapped[dict | None] = mapped_column(JSONB)
    score: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(12), default="done")  # done | evaluating | failed
    # Засчитывается только первый ответ: после него виден разбор, и повтор — уже тренировка, а не знание
    counted: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
