"""Rate limiting: FREE_DAILY_LIMIT / PREMIUM_DAILY_LIMIT per day (text+voice+vision)."""
from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.database import repositories as repo
from app.database.models import Usage, User


async def check_and_bump(session: AsyncSession, user_id: int, kind: str = "text") -> tuple[bool, int, int]:
    """Returns (allowed, used, limit). Atomically bumps counter when allowed."""
    settings = get_settings()
    user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        return False, 0, settings.free_daily_limit
    limit = settings.premium_daily_limit if user.is_premium else settings.free_daily_limit

    usage = await repo.get_usage_today(session, user_id)
    col = {"voice": "count_voice", "vision": "count_vision"}.get(kind, "count_text")

    # Atomic conditional increment: only succeeds if total < limit.
    stmt = (
        update(Usage)
        .where(Usage.id == usage.id)
        .where(Usage.count_text + Usage.count_voice + Usage.count_vision < limit)
        .values(**{col: getattr(Usage, col) + 1})
    )
    res = await session.execute(stmt)
    await session.commit()

    # Re-read to report accurate used count.
    usage = await repo.get_usage_today(session, user_id)
    used = usage.count_text + usage.count_voice + usage.count_vision
    if res.rowcount == 0:
        return False, used, limit
    return True, used, limit
