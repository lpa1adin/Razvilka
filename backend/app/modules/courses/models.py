import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class VersionStatus(str, enum.Enum):
    draft = "draft"
    published = "published"
    superseded = "superseded"  # была опубликована, её заменила более новая


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    published_version: Mapped[int | None] = mapped_column(Integer)
    draft_version: Mapped[int | None] = mapped_column(Integer)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)  # снят с публикации, прогресс сохраняется
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class CourseVersion(Base):
    """Снимок курса целиком (ADR-013): правка опубликованного создаёт новый номер, старый не меняется."""

    __tablename__ = "course_versions"
    __table_args__ = (UniqueConstraint("course_id", "number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    status: Mapped[VersionStatus] = mapped_column(Enum(VersionStatus, name="course_version_status"))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    content: Mapped[dict] = mapped_column(JSONB)  # {"modules": [{id, title, lessons: [{id, title, goal, blocks}]}]}
    change_note: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class Enrollment(Base):
    """На какой версии курса учится пользователь: начатое остаётся на своей версии."""

    __tablename__ = "enrollments"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True)
    version_number: Mapped[int] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LessonProgress(Base):
    __tablename__ = "lesson_progress"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True)
    # id урока стабилен между версиями — при переходе на новую версию пройденное сохраняется
    lesson_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
