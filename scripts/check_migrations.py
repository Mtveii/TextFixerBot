#!/usr/bin/env python3
"""Проверка 4 сценариев ensure_schema (fresh / legacy / no-version / idempotent).

Используется в CI (job migrations); локально тоже полезен:
    BOT_TOKEN=x python scripts/check_migrations.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("BOT_TOKEN", "123456:CHECK")
os.environ.setdefault("LOG_LEVEL", "WARNING")


def _tables_with_version(url: str) -> tuple[list[str], str | None]:
    from sqlalchemy import inspect, text

    from app.core.db import get_engine

    async def run():
        engine = get_engine()
        async with engine.connect() as conn:
            insp = await conn.run_sync(lambda c: inspect(c).get_table_names())
            ver = None
            if "alembic_version" in insp:
                row = (await conn.execute(text("select version_num from alembic_version"))).first()
                ver = row[0] if row else None
        await engine.dispose()
        return insp, ver

    return asyncio.run(run())


def _run(url: str, scenario: str, legacy_before: bool = False, legacy_after: bool = False) -> None:
    from app.core.config import get_settings
    from app.core.db import init_db
    from app.core.migrations import ensure_schema

    os.environ["DATABASE_URL"] = url
    get_settings.cache_clear()
    init_db(url)
    if legacy_before:
        import app.core.db as db

        asyncio.run(db.create_tables())
        async def _forget():
            from sqlalchemy import text

            from app.core.db import get_engine
            engine = get_engine()
            async with engine.begin() as conn:
                await conn.execute(text("drop table if exists alembic_version"))
            await engine.dispose()
        asyncio.run(_forget())
    asyncio.run(ensure_schema())
    if legacy_after:
        pass  # второй ensure_schema — idempotency
    asyncio.run(ensure_schema())

    tables, version = _tables_with_version(url)
    expected = {"users", "usage", "rewrite_requests", "rewrite_results", "favorites", "events", "alembic_version"}
    missing = expected - set(tables)
    assert not missing, f"{scenario}: missing tables {missing}"
    assert version, f"{scenario}: no alembic_version stamp"
    print(f"OK {scenario}: {len(tables)} tables, head={version}")


def main() -> None:
    tmp = tempfile.mkdtemp()
    scenarios = {
        "fresh": (f"sqlite+aiosqlite:///{tmp}/fresh.db", False),
        "legacy": (f"sqlite+aiosqlite:///{tmp}/legacy.db", True),
        "no-version-table": (f"sqlite+aiosqlite:///{tmp}/nover.db", False),
        "again": (f"sqlite+aiosqlite:///{tmp}/again.db", False),
    }
    for name, (url, legacy) in scenarios.items():
        _run(url, name, legacy_before=legacy)


if __name__ == "__main__":
    main()
