import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class MessageStatus(str, enum.Enum):
    pending = "pending"  # ждёт agent-worker
    streaming = "streaming"  # текст дописывается по мере генерации
    done = "done"
    failed = "failed"


class MentorThread(Base):
    """Переписка с наставником — своя для каждого урока и задания (контекст разный)."""

    __tablename__ = "mentor_threads"
    __table_args__ = (UniqueConstraint("user_id", "context_kind", "context_ref"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    context_kind: Mapped[str] = mapped_column(String(10))  # lesson | task | general
    context_ref: Mapped[str] = mapped_column(String(200), default="")  # «курс/урок» или slug задания
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MentorMessage(Base):
    __tablename__ = "mentor_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    thread_id: Mapped[int] = mapped_column(ForeignKey("mentor_threads.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(10))  # user | assistant
    content: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[MessageStatus] = mapped_column(Enum(MessageStatus, name="mentor_message_status"), default=MessageStatus.done)
    hint: Mapped[bool] = mapped_column(Boolean, default=False)  # просьба о подсказке — считается в попытке задания
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
