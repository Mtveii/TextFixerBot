"""Schema management: alembic migrations with create_tables() fallback.

Legacy databases (created by Base.metadata.create_all before alembic was
introduced) contain schema tables but no alembic_version row — those are
stamped at head before upgrading, so migrations never re-create existing
tables. If alembic fails for any reason the code falls back to
create_tables(), keeping the bot startable in every environment.
"""
from __future__ import annotations

import asyncio
import logging
import os

from app.core.db import create_tables

log = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _alembic_config(url: str):
    from alembic.config import Config

    cfg = Config(os.path.join(_PROJECT_ROOT, "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return cfg


def _stamp_head_sync(url: str) -> None:
    from alembic import command

    command.stamp(_alembic_config(url), "head")


def _upgrade_head_sync(url: str) -> None:
    from alembic import command

    command.upgrade(_alembic_config(url), "head")


async def ensure_schema() -> None:
    """Bring the database schema to the current head revision."""
    from sqlalchemy import inspect, text

    from app.core.db import get_engine

    def _snapshot(sync_conn) -> tuple[list[str], str | None]:
        insp = inspect(sync_conn)
        tables = insp.get_table_names()
        version: str | None = None
        if "alembic_version" in tables:
            row = sync_conn.execute(text("select version_num from alembic_version")).first()
            version = row[0] if row else None
        return tables, version

    try:
        engine = get_engine()
        async with engine.connect() as conn:
            tables, version = await conn.run_sync(_snapshot)
    except Exception as e:
        log.warning("Cannot inspect schema (%s), falling back to create_tables", e)
        await create_tables()
        return

    stamped = bool(version)
    has_schema = any(t != "alembic_version" for t in tables)
    legacy = has_schema and not stamped
    runtime_url = str(engine.url)

    try:
        # alembic's async env runs its own event loop -> run in a worker thread.
        if legacy:
            log.info("Unversioned schema detected, stamping alembic head (legacy DB)")
            await asyncio.to_thread(_stamp_head_sync, runtime_url)
        await asyncio.to_thread(_upgrade_head_sync, runtime_url)
        log.info("Schema is at head revision%s", f" ({version})" if version else "")
        # Repair-pass: legacy DB stamped at the initial revision would get
        # upgrade to head, but tables added AFTER that stamp cycle (e.g. events)
        # may still be missing if migration comparisons mis-detect them. Idempotent.
        await create_tables()
    except Exception as e:
        log.warning("Alembic failed (%s), falling back to create_tables", e)
        await create_tables()
