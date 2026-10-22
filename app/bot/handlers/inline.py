"""Inline mode: @bot <text> -> rewritten variants."""
from __future__ import annotations

import logging
import uuid

from aiogram import Router
from aiogram.types import InlineQuery, InlineQueryResultArticle, InputTextMessageContent

import app.bot.state as state
from app.core.db import get_session_factory
from app.core.rate_limit import check_and_bump
from app.database import repositories as repo
from app.services.rewrite.service import rewrite_text

log = logging.getLogger(__name__)
router = Router()


@router.inline_query()
async def inline_rewrite(query: InlineQuery):
    try:
        text = (query.query or "").strip()
        if len(text) < 3:
            return
        # rate-limit: ищем user по query.from_user.id
        try:
            factory = get_session_factory()
            async with factory() as session:
                user = await repo.get_or_create_user(session, query.from_user.id)
                allowed, used, limit = await check_and_bump(session, user.id, kind="text")
                if not allowed:
                    await query.answer(
                        [
                            InlineQueryResultArticle(
                                id=str(uuid.uuid4()),
                                title="⏳ Лимит исчерпан",
                                description=f"Лимит на сегодня исчерпан ({used}/{limit}). Возвращайся завтра!",
                                input_message_content=InputTextMessageContent(
                                    message_text=f"⏳ Лимит исчерпан ({used}/{limit}). Возвращайся завтра!"
                                ),
                            )
                        ],
                        cache_time=1,
                        is_personal=True,
                    )
                    return
        except Exception as e:
            # если rate-limit упал — не блокируем inline, но факт фиксируем
            log.warning("inline rate-limit check failed: %s", e)
        result = await rewrite_text(state.PROVIDER, text, style="neutral")
        main = result.get("rewritten_text", text)
        alts = result.get("alternatives", [])[:2]
        articles = [
            InlineQueryResultArticle(
                id=str(uuid.uuid4()),
                title="🟢 Нормально",
                description=main[:80],
                input_message_content=InputTextMessageContent(message_text=main),
            )
        ]
        for a in alts:
            articles.append(
                InlineQueryResultArticle(
                    id=str(uuid.uuid4()),
                    title=a.get("style", "вариант"),
                    description=a.get("text", "")[:80],
                    input_message_content=InputTextMessageContent(message_text=a.get("text", "")),
                )
            )
        await query.answer(articles, cache_time=1, is_personal=True)
    except Exception:
        log.exception("inline rewrite failed for user %s", query.from_user.id)
        return
