"""Admin stats (no message contents) + grant premium + telemetry (events)."""
from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.core.config import get_settings
from app.core.db import get_session_factory
from app.database import repositories as repo

router = Router()


def _fmt_recent_feedback(events) -> str:
    lines = "\n".join(
        f"• {e.detail[:160]}" for e in events if e.detail
    )
    return lines or "—"


@router.message(Command("admin"))
async def admin(message: Message):
    settings = get_settings()
    if message.from_user.id not in settings.admin_id_set:
        await message.answer("Нет доступа.")
        return
    import app.bot.state as state

    factory = get_session_factory()
    async with factory() as session:
        stats = await repo.stats_overview(session)
        styles = await repo.top_styles(session)
        gen = await repo.avg_gen_ms_24h(session)
        gen_n = await repo.count_events_24h(session, "gen")
        llm_n = await repo.count_events_24h(session, "llm_error")
        err_n = await repo.count_events_24h(session, "error")
        fb = await repo.recent_events(session, kind="feedback", limit=5)
        fb_n = await repo.count_events_24h(session, "feedback")
        purchase_n = await repo.count_events_24h(session, "purchase")
        await repo.prune_events(session, older_than_days=3)
    backends = ",".join(state.PROVIDER.backend_names) if state.PROVIDER else "-"
    top = "\n".join(f"• {name}: {cnt}" for name, cnt in styles) or "—"
    gen_line = f"{gen / 1000:.1f}s ({gen_n})" if gen is not None else "—"
    await message.answer(
        "📊 <b>Admin</b>\n"
        f"Users: {stats['users']}\n"
        f"Requests total: {stats['requests']}\n"
        f"Today: {stats['today_requests']}\n"
        f"Favorites: {stats['favorites']}\n"
        f"LLM: {backends} (order: {settings.llm_order})\n\n"
        f"<b>24h</b>\n"
        f"Gen avg: {gen_line}\n"
        f"LLM errors: {llm_n} · Unhandled: {err_n}\n"
        f"Feedback: {fb_n} · Purchases: {purchase_n}\n\n"
        f"<b>Top styles</b>\n{top}\n\n"
        f"<b>Feedback (recent)</b>\n{_fmt_recent_feedback(fb)}",
        parse_mode="HTML",
    )


@router.message(Command("grantprem"))
async def grantprem(message: Message):
    settings = get_settings()
    if message.from_user.id not in settings.admin_id_set:
        await message.answer("Нет доступа.")
        return
    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2 or not args[1].strip().lstrip("-").isdigit():
        await message.answer("Использование: <code>/grantprem telegram_id</code>")
        return
    tg_id = int(args[1].strip())
    factory = get_session_factory()
    async with factory() as session:
        user = await repo.get_user_by_tg(session, tg_id)
        if user is None:
            await message.answer("Пользователь не найден.")
            return
        user.is_premium = True
        await repo.add_event(session, "grant", user_id=user.id, detail=f"by admin {message.from_user.id}")
        await session.commit()
    await message.answer(f"💎 Premium выдан tg_id={tg_id}.")
