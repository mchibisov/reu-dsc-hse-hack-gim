"""Технические таблицы скрытой выдачи, без изменения схемы анкет."""

import hashlib
import hmac

from sqlalchemy import JSON, BigInteger, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .models import Base


def code_fingerprint(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def code_matches(provided: str, configured: str) -> bool:
    return bool(configured) and hmac.compare_digest(provided.encode(), configured.encode())


class CodeExportAttempt(Base):
    __tablename__ = 'code_export_attempts'
    digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    request_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class CodeExportLimit(Base):
    __tablename__ = 'code_export_limits'
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    failures: Mapped[list] = mapped_column(JSON, default=list)


class CodeExportPermit(Base):
    __tablename__ = 'code_export_permits'
    request_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger)
    fingerprint: Mapped[str] = mapped_column(String(64))
