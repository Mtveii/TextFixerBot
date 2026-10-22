"""History & favorites commands with inline pagination/delete."""
from __future__ import annotations

import html
import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from app.bot.keyboards.main import favorites_kb, history_item_kb, history_list_kb
from app.core.db import get_session_factory
from app.database import repositories as repo
from app.database.models import RewriteRequest

log = logging.getLogger(__name__)
router = Router()

HIST_PAGE_SIZE = 5


@router.message(Command("history"))
async def history(message: Message):
    factory = get_session_factory()
    async with factory() as session:
        user = await repo.get_or_create_user(session, message.from_user.id)
        items = await repo.get_history(session, user.id, limit=HIST_PAGE_SIZE, offset=0)
        total = await repo.count_history(session, user.id)
    if not items:
        await message.answer("📚 История пуста. Отправь мне любой текст!")
        return
    await message.answer(
        "📚 <b>История</b> — тапни текст для просмотра, 🔁 чтобы использовать снова:",
        parse_mode="HTML",
        reply_markup=history_list_kb(items, total, page=0, page_size=HIST_PAGE_SIZE),
    )


@router.message(Command("forget"))
async def forget(message: Message):
    factory = get_session_factory()
    async with factory() as session:
        user = await repo.get_or_create_user(session, message.from_user.id)
        n = await repo.clear_history(session, user.id)
    await message.answer(f"🗑️ Удалил {n} записей из истории.")


@router.message(Command("favorites"))
async def favorites(message: Message):
    factory = get_session_factory()
    async with factory() as session:
        user = await repo.get_or_create_user(session, message.from_user.id)
        favs = await repo.list_favorites(session, user.id)
    if not favs:
        await message.answer("⭐ Избранного пока нет. Нажми «⭐ Сохранить» под результатом.")
        return
    await message.answer(
        "⭐ <b>Избранное</b> — тапни для просмотра, ⛔ чтобы удалить:",
        parse_mode="HTML",
        reply_markup=favorites_kb(favs),
    )


@router.callback_query(F.data.startswith("hist:"))
async def hist_page(query: CallbackQuery):
    page_str = query.data.split(":")[1] if ":" in query.data else "0"
    if page_str == "noop":
        try:
            await query.answer()
        except Exception:
            pass
        return
    try:
        page = max(0, int(page_str))
    except ValueError:
        page = 0
    factory = get_session_factory()
    async with factory() as session:
        user = await repo.get_or_create_user(session, query.from_user.id)
        items = await repo.get_history(session, user.id, limit=HIST_PAGE_SIZE, offset=page * HIST_PAGE_SIZE)
        total = await repo.count_history(session, user.id)
    if not items:
        try:
            await query.answer("Дальше пусто", show_alert=True)
        except Exception:
            pass
        return
    try:
        await query.message.edit_reply_markup(
            reply_markup=history_list_kb(items, total, page=page, page_size=HIST_PAGE_SIZE)
        )
    except Exception:
        log.exception("hist page edit failed")
    try:
        await query.answer()
    except Exception:
        pass


@router.callback_query(F.data.startswith("histshow:"))
async def hist_show(query: CallbackQuery):
    try:
        req_id = int(query.data.split(":")[1])
    except (IndexError, ValueError, AttributeError):
        try:
            await query.answer("Некорректные данные", show_alert=True)
        except Exception:
            pass
        return
    factory = get_session_factory()
    async with factory() as session:
        user = await repo.get_or_create_user(session, query.from_user.id)
        owned = (await session.execute(
            select(RewriteRequest).where(
                RewriteRequest.id == req_id, RewriteRequest.user_id == user.id
            )
        )).scalar_one_or_none()
    if not owned:
        try:
            await query.answer("Не найдено", show_alert=True)
        except Exception:
            pass
        return
    preview = owned.source_text[:180]
    try:
        await query.answer(html.escape(preview), show_alert=False)
    except Exception:
        pass
    await query.message.answer("Взял текст из истории 👇", reply_markup=history_item_kb(req_id))


@router.callback_query(F.data.startswith("favshow:"))
async def fav_show(query: CallbackQuery):
    try:
        fav_id = int(query.data.split(":")[1])
    except (IndexError, ValueError, AttributeError):
        try:
            await query.answer("Некорректные данные", show_alert=True)
        except Exception:
            pass
        return
    factory = get_session_factory()
    async with factory() as session:
        user = await repo.get_or_create_user(session, query.from_user.id)
        favs = await repo.list_favorites(session, user.id)
    fav = next((f for f in favs if f.id == fav_id), None)
    if fav is None:
        try:
            await query.answer("Не найдено", show_alert=True)
        except Exception:
            pass
        return
    preview = fav.text[:180]
    try:
        await query.answer(f"⭐ {fav.style}\n{preview}", show_alert=False)
    except Exception:
        pass


@router.callback_query(F.data.startswith("delfavcb:"))
async def del_fav_inline(query: CallbackQuery):
    try:
        fav_id = int(query.data.split(":")[1])
    except (IndexError, ValueError, AttributeError):
        try:
            await query.answer("Некорректные данные", show_alert=True)
        except Exception:
            pass
        return
    factory = get_session_factory()
    async with factory() as session:
        user = await repo.get_or_create_user(session, query.from_user.id)
        ok = await repo.delete_favorite(session, fav_id, user.id)
        favs = await repo.list_favorites(session, user.id)
    if ok:
        try:
            await query.answer("Удалил ⭐")
        except Exception:
            pass
        if not favs:
            try:
                await query.message.delete()
            except Exception:
                pass
            await query.message.answer("⭐ Избранное очистилось.")
        else:
            try:
                await query.message.edit_reply_markup(reply_markup=favorites_kb(favs))
            except Exception:
                pass
    else:
        try:
            await query.answer("Не нашёл.", show_alert=True)
        except Exception:
            pass


@router.message(F.text.startswith("/delfav_"))
async def del_fav(message: Message):
    try:
        fav_id = int(message.text.split("_", 1)[1])
    except (ValueError, IndexError, AttributeError):
        return
    factory = get_session_factory()
    async with factory() as session:
        user = await repo.get_or_create_user(session, message.from_user.id)
        ok = await repo.delete_favorite(session, fav_id, user.id)
    await message.answer("Удалил ⭐" if ok else "Не нашёл.")
