import enum
from datetime import datetime

from sqlalchemy import Boolean, Computed, DateTime, Enum, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class LicenseMode(str, enum.Enum):
    # Как показывать текст, решает лицензия источника (BRIEF §3.1, ADR-010)
    full_text = "full_text"  # открытая лицензия: полный текст с атрибуцией
    reference = "reference"  # без права копирования: ссылка, оглавление, заметка админа


class LicenseStatus(str, enum.Enum):
    ok = "ok"
    needs_review = "needs_review"  # файл лицензии изменился — импорт остановлен до проверки админом


class FragmentStatus(str, enum.Enum):
    active = "active"
    removed = "removed"  # исчез из источника при последнем импорте


class RunStatus(str, enum.Enum):
    running = "running"
    done = "done"
    failed = "failed"


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    author: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(32))  # docs | tutorial | book | course
    homepage: Mapped[str] = mapped_column(String(300))
    license_name: Mapped[str] = mapped_column(String(120))
    license_url: Mapped[str] = mapped_column(String(300))
    license_mode: Mapped[LicenseMode] = mapped_column(Enum(LicenseMode, name="license_mode"))
    license_note: Mapped[str] = mapped_column(Text, default="")
    license_hash: Mapped[str | None] = mapped_column(String(64))
    license_status: Mapped[LicenseStatus] = mapped_column(
        Enum(LicenseStatus, name="license_status"), default=LicenseStatus.ok
    )
    last_commit: Mapped[str | None] = mapped_column(String(40))
    last_commit_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_import_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Fragment(Base):
    """Фрагмент теории = одна статья источника."""

    __tablename__ = "fragments"
    __table_args__ = (
        UniqueConstraint("source_id", "external_id"),
        Index("ix_fragments_search", "search", postgresql_using="gin"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    external_id: Mapped[str] = mapped_column(String(400))  # путь файла в репозитории источника
    title: Mapped[str] = mapped_column(String(300))
    section: Mapped[str] = mapped_column(String(300), default="")
    url: Mapped[str] = mapped_column(String(500))
    content_html: Mapped[str | None] = mapped_column(Text)  # только для full_text, уже очищен от опасного HTML
    outline: Mapped[list] = mapped_column(JSONB, default=list)  # заголовки разделов статьи
    excerpt: Mapped[str] = mapped_column(Text, default="")
    plain_text: Mapped[str] = mapped_column(Text, default="")
    search = mapped_column(
        TSVECTOR,
        Computed(
            "setweight(to_tsvector('russian', coalesce(title, '')), 'A') || "
            "setweight(to_tsvector('russian', coalesce(section, '')), 'B') || "
            "setweight(to_tsvector('russian', coalesce(plain_text, '')), 'C')",
            persisted=True,
        ),
    )
    content_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[FragmentStatus] = mapped_column(
        Enum(FragmentStatus, name="fragment_status"), default=FragmentStatus.active
    )
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    source_commit: Mapped[str] = mapped_column(String(40))
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    source: Mapped[Source] = relationship()


class ImportRun(Base):
    __tablename__ = "import_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    status: Mapped[RunStatus] = mapped_column(Enum(RunStatus, name="import_run_status"), default=RunStatus.running)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    commit: Mapped[str | None] = mapped_column(String(40))
    added: Mapped[int] = mapped_column(Integer, default=0)
    changed: Mapped[int] = mapped_column(Integer, default=0)
    removed: Mapped[int] = mapped_column(Integer, default=0)
    unchanged: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
