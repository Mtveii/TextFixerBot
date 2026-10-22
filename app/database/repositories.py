"""Async repositories (thin wrappers over SQLAlchemy)."""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import delete, desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Event, Favorite, RewriteRequest, RewriteResult, Usage, User


async def get_or_create_user(session: AsyncSession, telegram_id: int, language: str = "ru") -> User:
    user = (await session.execute(select(User).where(User.telegram_id == telegram_id))).scalar_one_or_none()
    if user is None:
        user = User(telegram_id=telegram_id, language=language)
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


async def get_user_by_tg(session: AsyncSession, telegram_id: int) -> User | None:
    return (await session.execute(select(User).where(User.telegram_id == telegram_id))).scalar_one_or_none()


async def create_request(
    session: AsyncSession,
    user_id: int,
    source_text: str,
    style: str | None = None,
    intent: str | None = None,
    language: str | None = None,
    context_text: str | None = None,
) -> RewriteRequest:
    req = RewriteRequest(
        user_id=user_id,
        source_text=source_text,
        style=style,
        intent=intent,
        language=language,
        context_text=context_text,
    )
    session.add(req)
    await session.commit()
    await session.refresh(req)
    return req


async def save_results(session: AsyncSession, request_id: int, items: list[dict]) -> list[RewriteResult]:
    out = []
    for it in items:
        r = RewriteResult(request_id=request_id, style=it.get("style", "neutral"), text=it["text"])
        session.add(r)
        out.append(r)
    await session.commit()
    return out


async def get_history(
    session: AsyncSession, user_id: int, limit: int = 10, offset: int = 0
) -> list[RewriteRequest]:
    q = (
        select(RewriteRequest)
        .where(RewriteRequest.user_id == user_id)
        .order_by(desc(RewriteRequest.id))
        .limit(limit)
        .offset(offset)
    )
    return list((await session.execute(q)).scalars().all())


async def count_history(session: AsyncSession, user_id: int) -> int:
    q = select(func.count(RewriteRequest.id)).where(RewriteRequest.user_id == user_id)
    return (await session.execute(q)).scalar() or 0


async def get_results_for_request(session: AsyncSession, request_id: int) -> list[RewriteResult]:
    q = select(RewriteResult).where(RewriteResult.request_id == request_id).order_by(RewriteResult.id)
    return list((await session.execute(q)).scalars().all())


async def clear_history(session: AsyncSession, user_id: int) -> int:
    reqs = (await session.execute(select(RewriteRequest).where(RewriteRequest.user_id == user_id))).scalars().all()
    n = 0
    for r in reqs:
        await session.delete(r)
        n += 1
    await session.commit()
    return n


async def add_favorite(session: AsyncSession, user_id: int, text: str, style: str) -> Favorite:
    fav = Favorite(user_id=user_id, text=text, style=style)
    session.add(fav)
    await session.commit()
    await session.refresh(fav)
    return fav


async def list_favorites(session: AsyncSession, user_id: int, limit: int = 20) -> list[Favorite]:
    q = select(Favorite).where(Favorite.user_id == user_id).order_by(desc(Favorite.id)).limit(limit)
    return list((await session.execute(q)).scalars().all())


async def delete_favorite(session: AsyncSession, fav_id: int, user_id: int) -> bool:
    fav = (await session.execute(select(Favorite).where(Favorite.id == fav_id, Favorite.user_id == user_id))).scalar_one_or_none()
    if not fav:
        return False
    await session.delete(fav)
    await session.commit()
    return True


async def get_usage_today(session: AsyncSession, user_id: int) -> Usage:
    today = date.today()
    u = (
        await session.execute(select(Usage).where(Usage.user_id == user_id, Usage.day == today))
    ).scalar_one_or_none()
    if u is None:
        try:
            u = Usage(user_id=user_id, day=today)
            session.add(u)
            await session.commit()
            await session.refresh(u)
        except IntegrityError:
            await session.rollback()
            u = (
                await session.execute(select(Usage).where(Usage.user_id == user_id, Usage.day == today))
            ).scalar_one_or_none()
            if u is None:
                raise
    return u


async def bump_usage(session: AsyncSession, user_id: int, kind: str = "text") -> Usage:
    # Атомарный bump во избежание race condition: UPDATE ... SET count=count+1
    # вместо read-modify-write в Python (иначе параллельные запросы теряют инкременты).
    from sqlalchemy import update

    u = await get_usage_today(session, user_id)
    if kind == "voice":
        await session.execute(
            update(Usage).where(Usage.id == u.id).values(count_voice=Usage.count_voice + 1)
        )
    elif kind == "vision":
        await session.execute(
            update(Usage).where(Usage.id == u.id).values(count_vision=Usage.count_vision + 1)
        )
    else:
        await session.execute(
            update(Usage).where(Usage.id == u.id).values(count_text=Usage.count_text + 1)
        )
    await session.commit()
    await session.refresh(u)
    return u


async def stats_overview(session: AsyncSession) -> dict:
    users = (await session.execute(select(func.count(User.id)))).scalar() or 0
    reqs = (await session.execute(select(func.count(RewriteRequest.id)))).scalar() or 0
    favs = (await session.execute(select(func.count(Favorite.id)))).scalar() or 0
    today = date.today()
    today_reqs = (
        await session.execute(select(func.count(RewriteRequest.id)).where(func.date(RewriteRequest.created_at) == today))
    ).scalar() or 0
    return {"users": users, "requests": reqs, "favorites": favs, "today_requests": today_reqs}

# ---------- events (telemetry) ----------


async def add_event(
    session: AsyncSession,
    kind: str,
    *,
    user_id: int | None = None,
    detail: str | None = None,
    duration_ms: int | None = None,
) -> None:
    session.add(Event(kind=kind, user_id=user_id, detail=detail, duration_ms=duration_ms))
    await session.commit()


async def count_events_24h(session: AsyncSession, kind: str) -> int:
    since = datetime.now(UTC) - timedelta(days=1)
    q = select(func.count(Event.id)).where(Event.kind == kind, Event.created_at >= since)
    return (await session.execute(q)).scalar() or 0


async def recent_events(session: AsyncSession, kind: str | None = None, limit: int = 5) -> list[Event]:
    if kind is None:
        q = select(Event).order_by(desc(Event.id)).limit(limit)
    else:
        q = select(Event).where(Event.kind == kind).order_by(desc(Event.id)).limit(limit)
    return list((await session.execute(q)).scalars().all())


async def avg_gen_ms_24h(session: AsyncSession) -> int | None:
    since = datetime.now(UTC) - timedelta(days=1)
    q = select(func.avg(Event.duration_ms)).where(Event.kind == "gen", Event.created_at >= since)
    v = (await session.execute(q)).scalar()
    return int(v) if v is not None else None


async def prune_events(session: AsyncSession, older_than_days: int = 3) -> int:
    since = datetime.now(UTC) - timedelta(days=older_than_days)
    res = await session.execute(delete(Event).where(Event.created_at < since))
    await session.commit()
    return res.rowcount or 0


async def top_styles(session: AsyncSession, limit: int = 5) -> list[tuple[str, int]]:
    q = (
        select(RewriteRequest.style, func.count(RewriteRequest.id))
        .group_by(RewriteRequest.style)
        .order_by(desc(func.count(RewriteRequest.id)))
        .limit(limit)
    )
    return [(r[0], r[1]) for r in (await session.execute(q)).all()]

