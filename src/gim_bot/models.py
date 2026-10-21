from datetime import UTC, datetime

from sqlalchemy import JSON, BigInteger, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now():
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Application(Base):
    __tablename__ = 'applications'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default='base')
    cursor: Mapped[int] = mapped_column(Integer, default=0)
    answers: Mapped[dict] = mapped_column(JSON, default=dict)
    followups: Mapped[list] = mapped_column(JSON, default=list)
    followup_cursor: Mapped[int] = mapped_column(Integer, default=0)
    consent_version: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    analysis_status: Mapped[str] = mapped_column(String(30), default='pending', index=True)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    analysis: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    rubric_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    notified_admins: Mapped[list] = mapped_column(JSON, default=list)
    delete_pending: Mapped[bool] = mapped_column(default=False)


class MessageEvent(Base):
    __tablename__ = 'message_events'
    __table_args__ = (UniqueConstraint('user_id', 'event_id'),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    event_id: Mapped[str] = mapped_column(String(150))
    result: Mapped[dict] = mapped_column(JSON)


class ExportRequest(Base):
    __tablename__ = 'export_requests'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    admin_id: Mapped[int] = mapped_column(BigInteger)
    request_key: Mapped[str] = mapped_column(String(180), unique=True)
    status: Mapped[str] = mapped_column(String(20), default='queued')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class RuntimeState(Base):
    __tablename__ = 'runtime_state'
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)
