"""Async engine / session factory."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def init_db(database_url: str):
    global _engine, _session_factory
    kwargs = {}
    if database_url.startswith("sqlite"):
        kwargs = {"connect_args": {"check_same_thread": False}}
    _engine = create_async_engine(database_url, echo=False, future=True, **kwargs)
    _session_factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    assert _session_factory is not None, "DB not initialized, call init_db() first"
    return _session_factory


def get_engine():
    assert _engine is not None, "DB not initialized"
    return _engine


async def create_tables():
    from app.database import models  # noqa: F401  (register models)

    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
