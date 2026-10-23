"""Async engine / session factory."""
from __future__ import annotations

import re

from sqlalchemy import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _normalize_postgres_url(u: str) -> str:
    """asyncpg не понимает libpq-параметры из query-строки (sslmode/channel_binding):
    вырезаем их из URL и возвращаем чистый DSN (ssl задаётся через connect_args)."""
    u = re.sub(r"[?&](channel_binding|sslmode|ssl)=[^&]*", "", u)
    return u.rstrip("?&")


def init_db(database_url: str):
    global _engine, _session_factory
    kwargs = {}
    if database_url.startswith("sqlite"):
        kwargs = {"connect_args": {"check_same_thread": False}}
        final_url = database_url
    else:
        url = make_url(_normalize_postgres_url(database_url))
        if url.drivername.startswith("postgres"):
            url = url.set(drivername="postgresql+asyncpg")
            local = url.host in ("localhost", "127.0.0.1", "::1") or url.host is None
            kwargs = {"connect_args": {} if local else {"ssl": "require"}}
        final_url = str(url)
    _engine = create_async_engine(final_url, echo=False, future=True, **kwargs)
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
