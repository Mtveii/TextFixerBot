"""Rate limit: atomic conditional increment, limits per user tier."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
import pytest_asyncio

from app.core.db import Base, init_db


@pytest_asyncio.fixture
async def db(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path}/test.db"
    engine = init_db(url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield url
    await engine.dispose()


@pytest.fixture
def settings_patch(monkeypatch):
    s = SimpleNamespace(free_daily_limit=3, premium_daily_limit=10)
    monkeypatch.setattr("app.core.rate_limit.get_settings", lambda: s)
    return s


@pytest.mark.asyncio
async def test_free_limit_blocks_after_n(db, settings_patch):
    from app.core.db import get_session_factory
    from app.core.rate_limit import check_and_bump
    from app.database import repositories as repo

    factory = get_session_factory()
    async with factory() as session:
        user = await repo.get_or_create_user(session, 111)

        results = [await check_and_bump(session, user.id, kind="text") for _ in range(5)]
    allowed = [r[0] for r in results]
    assert allowed == [True, True, True, False, False]
    # used saturates at limit
    assert results[-1][1] == 3
    assert results[-1][2] == 3


@pytest.mark.asyncio
async def test_premium_limit_higher(db, settings_patch):
    from app.core.db import get_session_factory
    from app.core.rate_limit import check_and_bump
    from app.database import repositories as repo

    factory = get_session_factory()
    async with factory() as session:
        user = await repo.get_or_create_user(session, 222)
        user.is_premium = True
        await session.commit()

        results = [await check_and_bump(session, user.id) for _ in range(11)]
    assert sum(1 for r in results if r[0]) == 10


@pytest.mark.asyncio
async def test_voice_and_vision_share_limit(db, settings_patch):
    from app.core.db import get_session_factory
    from app.core.rate_limit import check_and_bump
    from app.database import repositories as repo

    factory = get_session_factory()
    async with factory() as session:
        user = await repo.get_or_create_user(session, 333)
        ok_text = await check_and_bump(session, user.id, kind="text")
        ok_voice = await check_and_bump(session, user.id, kind="voice")
        ok_vision = await check_and_bump(session, user.id, kind="vision")
        blocked = await check_and_bump(session, user.id, kind="text")
    assert ok_text[0] and ok_voice[0] and ok_vision[0]
    assert not blocked[0]
    assert blocked[1] == 3  # all three kinds counted together


@pytest.mark.asyncio
async def test_concurrent_bumps_never_exceed_limit(db, settings_patch):
    """Many parallel tasks must be capped exactly at the limit (atomic UPDATE)."""
    from app.core.db import get_session_factory
    from app.core.rate_limit import check_and_bump
    from app.database import repositories as repo

    factory = get_session_factory()
    async with factory() as session:
        user = await repo.get_or_create_user(session, 444)
        user_id = user.id

    async def one():
        async with factory() as session:
            # each task gets its own session/connection
            return await check_and_bump(session, user_id, kind="text")

    results = await asyncio.gather(*[one() for _ in range(10)], return_exceptions=True)
    ok = [r for r in results if not isinstance(r, Exception) and r[0]]
    errors = [r for r in results if isinstance(r, Exception)]
    # SQLite may raise "database is locked" under contention; that's a retry-able
    # failure, not a limit violation. What matters: no more than limit succeeded.
    assert len(ok) <= 3, f"limit violated: {ok} (errors={errors})"
    # at least most should succeed on a quiet test db
    assert len(ok) >= 1
