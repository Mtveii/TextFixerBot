"""Schema bootstrap: fresh DB gets tables + alembic_version; reruns are idempotent."""
from __future__ import annotations

import pytest

pytest.importorskip("alembic")

from sqlalchemy import inspect, text

from app.core.db import Base, init_db


async def _snapshot(url):
    from app.core.db import get_engine

    engine = get_engine()

    def f(sc):
        insp = inspect(sc)
        tables = sorted(insp.get_table_names())
        ver = None
        if "alembic_version" in tables:
            row = sc.execute(text("select version_num from alembic_version")).first()
            ver = row[0] if row else None
        return tables, ver

    async with engine.connect() as conn:
        return await conn.run_sync(f)


@pytest.mark.asyncio
async def test_fresh_db_migrated(tmp_path):
    from app.core.migrations import ensure_schema

    url = f"sqlite+aiosqlite:///{tmp_path}/fresh.db"
    init_db(url)
    await ensure_schema()
    tables, version = await _snapshot(url)
    assert "users" in tables and "usage" in tables
    assert version  # stamped at head


@pytest.mark.asyncio
async def test_rerun_is_idempotent(tmp_path):
    from app.core.migrations import ensure_schema

    url = f"sqlite+aiosqlite:///{tmp_path}/rerun.db"
    init_db(url)
    await ensure_schema()
    first = await _snapshot(url)
    init_db(url)
    await ensure_schema()
    assert await _snapshot(url) == first


@pytest.mark.asyncio
async def test_legacy_tables_without_version_are_stamped(tmp_path):
    """create_tables()-style DB (no alembic_version) must be stamped, not recreated."""
    from app.core.migrations import ensure_schema

    url = f"sqlite+aiosqlite:///{tmp_path}/legacy.db"
    engine = init_db(url)
    # simulate legacy: raw create_all, no alembic
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await ensure_schema()
    tables, version = await _snapshot(url)
    assert "alembic_version" in tables
    assert version
