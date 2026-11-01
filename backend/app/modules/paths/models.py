"""Пути «напиши заново сам» (BRIEF §5.5): проект владельца, разложенный на этапы.

Этап — это практикум (assess.Assignment с path_id): условие, развилки с ответом автора, автотесты. Сдаётся
из рабочей папки ученика тем же конвейером автотесты → Ревьюер → Оценщик (этап 6).
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ProjectPath(Base):
    __tablename__ = "project_paths"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    project: Mapped[str] = mapped_column(String(200))  # папка в ProjectsWithClaude — оригинал, только чтение
    kind: Mapped[str] = mapped_column(String(10), default="web")  # web | python — какие автотесты у этапов
    # Карта проекта: граф без Claude + роли частей от Claude ([{path, role}])
    roles: Mapped[list] = mapped_column(JSONB, default=list)
    published: Mapped[bool] = mapped_column(Boolean, default=False)
    gen_request_id: Mapped[int | None] = mapped_column(ForeignKey("gen_requests.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
