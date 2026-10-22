"""DB models: users, styles, requests, results, favorites, templates, usage."""
from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import JSON, BigInteger, Boolean, Date, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    language: Mapped[str] = mapped_column(String(8), default="ru")
    target_lang: Mapped[str | None] = mapped_column(String(8), nullable=True, default=None)
    save_history: Mapped[bool] = mapped_column(Boolean, default=True)
    is_premium: Mapped[bool] = mapped_column(Boolean, default=False)
    style_profile: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    custom_style: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC).replace(tzinfo=None))


class RewriteRequest(Base):
    __tablename__ = "rewrite_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    source_text: Mapped[str] = mapped_column(Text)
    context_text: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    intent: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    language: Mapped[str | None] = mapped_column(String(8), nullable=True, default=None)
    style: Mapped[str | None] = mapped_column(String(32), nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC).replace(tzinfo=None))

    results: Mapped[list["RewriteResult"]] = relationship(back_populates="request", cascade="all, delete-orphan")


class RewriteResult(Base):
    __tablename__ = "rewrite_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("rewrite_requests.id"), index=True)
    style: Mapped[str] = mapped_column(String(32), default="neutral")
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC).replace(tzinfo=None))

    request: Mapped["RewriteRequest"] = relationship(back_populates="results")


class Favorite(Base):
    __tablename__ = "favorites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    style: Mapped[str] = mapped_column(String(32), default="neutral")
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC).replace(tzinfo=None))


class Usage(Base):
    __tablename__ = "usage"
    __table_args__ = (UniqueConstraint("user_id", "day", name="uq_usage_user_day"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    count_text: Mapped[int] = mapped_column(Integer, default=0)
    count_voice: Mapped[int] = mapped_column(Integer, default=0)
    count_vision: Mapped[int] = mapped_column(Integer, default=0)

class Event(Base):
    """Telemetry: llm_error / error (unhandled) / gen (время генерации) / feedback (/report)."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, default=None)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC).replace(tzinfo=None))

