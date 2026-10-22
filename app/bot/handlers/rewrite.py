"""Core flow: any text -> style choice -> 3 variants -> actions."""
from __future__ import annotations

import asyncio
import html
import logging
import time

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import app.bot.state as state
from app.bot.formatting import copyable_text, format_multi
from app.bot.group_gate import group_gate
from app.bot.keyboards.main import language_kb, result_actions_kb, style_choice_kb
from app.bot.state import PENDING
from app.core.db import get_session_factory
from app.core.rate_limit import check_and_bump
from app.database import repositories as repo
from app.services.rewrite.service import rewrite_text
from app.services.styles.service import (
    EXTRA_ACTIONS,
    INTENT_SUGGESTIONS,
    STYLES,
    detect_intent_hint,
    detect_language,
    style_label,
)

ALLOWED_LANGS = {"ru", "uk", "en"}
ALLOWED_STYLES = set(STYLES) | set(EXTRA_ACTIONS) | {"custom", "custom_saved", "neutral"}

log = logging.getLogger(__name__)
router = Router()


class CustomStyleStates(StatesGroup):
    waiting_custom = State()
    waiting_recipient = State()


REPLY_TRIGGERS = ("она пишет:", "он пишет:", "они пишут:", "пишет:")


def _is_reply_request(text: str) -> bool:
    t = text.lower().strip()
    return t.startswith(REPLY_TRIGGERS)


async def _keep_typing(bot, chat_id: int) -> None:
    """Chat action «typing…» каждые ~4.5s, пока идёт запрос к LLM."""
    try:
        while True:
            await bot.send_chat_action(chat_id, "typing")
            await asyncio.sleep(4.5)
    except asyncio.CancelledError:
        raise
    except Exception:
        return


async def _do_rewrite(
    message_or_query,
    user_tg_id: int,
    style: str,
    use_pending: bool = True,
    extra_style: str | None = None,
    edit_message=None,
):
    """Run rewrite for pending text. Returns (request_id, main_text).

    edit_message — сообщение, которое редактируется в карточку результата
    (выбор стиля / «Другой вариант» / быстрые действия — вместо новых сообщений).
    """

    async def _warn(body: str):
        try:
            if edit_message is not None:
                await edit_message.edit_text(body)
            elif isinstance(message_or_query, Message):
                await message_or_query.answer(body)
            else:
                await message_or_query.message.answer(body)
        except Exception:
            pass

    factory = get_session_factory()
    pending = PENDING.get(user_tg_id, {})
    text = pending.get("text", "")
    context_text = pending.get("context_text")
    reply_mode = pending.get("reply_mode", False) or _is_reply_request(text)
    if not text:
        # pending text was lost (bot restart / eviction / stale callback)
        await _warn("⌛ Сессия устарела — отправь текст ещё раз.")
        return None, ""

    async with factory() as session:
        user = await repo.get_or_create_user(session, user_tg_id)
        allowed, used, limit = await check_and_bump(session, user.id, kind="text")
        if not allowed:
            from app.i18n import fmt as tf

            await _warn(tf("limit_reached", user.language or "ru", used=used, limit=limit))
            return None, ""
        target_lang = user.target_lang
        user_style = user.style_profile
        custom = user.custom_style if style == "custom_saved" else pending.get("custom_style")

        eff_style = extra_style or style
        if eff_style in ("custom", "custom_saved"):
            eff_style = "neutral"

        # «typing» на время вызова LLM (воспринимаемая скорость)
        typing_task = None
        bot = state.BOT
        if bot is not None:
            chat_id = (
                message_or_query.chat.id
                if isinstance(message_or_query, Message)
                else message_or_query.message.chat.id
            )
            typing_task = asyncio.create_task(_keep_typing(bot, chat_id))
        t0 = time.monotonic()
        try:
            result = await rewrite_text(
                state.PROVIDER,
                text,
                style=eff_style,
                target_lang=target_lang,
                custom_style=custom,
                user_style=user_style,
                recipient=pending.get("recipient"),
                context_text=context_text,
                reply_mode=reply_mode,
            )
        finally:
            if typing_task is not None:
                typing_task.cancel()
        gen_ms = int((time.monotonic() - t0) * 1000)
        main_text = result.get("rewritten_text", "")
        alts = result.get("alternatives", []) or []
        intent = result.get("intent") or detect_intent_hint(text)
        lang = result.get("language") or detect_language(text)

        req = None
        if user.save_history:
            req = await repo.create_request(
                session, user.id, text, style=eff_style, intent=intent, language=lang, context_text=context_text
            )
            items = [{"style": eff_style, "text": main_text}] + [
                {"style": a.get("style", "neutral"), "text": a.get("text", "")} for a in alts[:2]
            ]
            await repo.save_results(session, req.id, [i for i in items if i["text"]])
        else:
            # privacy: save_history=False — НЕ делаем INSERT вообще, работаем in-memory.
            # Историю не пишем, usage уже bump-нут через check_and_bump выше.
            req = None
        await repo.add_event(
            session, "gen", user_id=user.id,
            detail=f"{eff_style}/{len(text)}",
            duration_ms=gen_ms,
        )
    # карточка результата: редактируем сообщение вместо инициализации новых
    body = format_multi(eff_style, main_text, alts)
    suggestion = result.get("suggestion") or INTENT_SUGGESTIONS.get(intent, "")
    if suggestion:
        body += f"\n\n🤔 {html.escape(suggestion)}"
    kb = result_actions_kb(req.id if req else 0, intent=intent, variants=len(items))
    try:
        if edit_message is not None:
            await edit_message.edit_text(body, parse_mode="HTML", reply_markup=kb)
        elif isinstance(message_or_query, Message):
            await message_or_query.answer(body, parse_mode="HTML", reply_markup=kb)
        else:
            await message_or_query.message.answer(body, parse_mode="HTML", reply_markup=kb)
    except Exception:
        log.exception("failed to render result card")
    # remember last result for copy/fav
    PENDING[user_tg_id] = {
        **pending,
        "last_request_id": req.id if req else 0,
        "last_texts": [main_text] + [a.get("text", "") for a in alts[:2]],
        "last_style": eff_style,
        "text": text,  # keep for restyle
    }
    return (req.id if req else 0), main_text


@router.message(F.text, ~F.text.startswith("/"))
async def on_text(message: Message, state: FSMContext):
    custom_input = False
    # custom style input?
    cur = await state.get_state()
    if cur == CustomStyleStates.waiting_custom.state:
        custom_input = True
        await PENDING.hydrate(message.from_user.id)
        PENDING.setdefault(message.from_user.id, {})["custom_style"] = message.text.strip()[:500]
        await state.clear()
        # без промежуточного «Генерирую…» — typing-индикатор прямо из _do_rewrite
        await _do_rewrite(message, message.from_user.id, style="neutral")
        return

    text = message.text.strip()
    # групповой гейт: работаем только на reply боту или @mention (state-flow продолжаем внутри).
    if not custom_input:
        allowed, text = group_gate(message, text)
        if not allowed:
            return
    if len(text) < 2:
        await message.answer("Напиши чуть подробнее — хоть пару слов.")
        return

    context_text = None
    if message.reply_to_message and (message.reply_to_message.text or message.reply_to_message.caption):
        context_text = message.reply_to_message.text or message.reply_to_message.caption

    PENDING[message.from_user.id] = {"text": text[:4000], "context_text": (context_text or "")[:2000] or None,
                                     "reply_mode": bool(context_text) or _is_reply_request(text)}
    if _is_reply_request(text):
        await message.answer(
            "🤔 Похоже, нужно придумать ответ. Какой тон выбрать?",
            reply_markup=style_choice_kb(),
        )
    elif context_text:
        await message.answer(
            "Понял контекст переписки — это будет ответ на сообщение выше. Какой вариант сделать?",
            reply_markup=style_choice_kb(),
        )
    else:
        await message.answer("Понял. Какой вариант сделать?", reply_markup=style_choice_kb())


@router.callback_query(F.data.startswith("style:"))
async def on_style(query: CallbackQuery, state: FSMContext):
    try:
        code = query.data.split(":", 1)[1]
    except (IndexError, AttributeError, ValueError):
        try:
            await query.answer("Некорректные данные", show_alert=True)
        except Exception:
            pass
        return
    if code not in ALLOWED_STYLES:
        try:
            await query.answer("Неизвестный стиль", show_alert=True)
        except Exception:
            pass
        return
    if code == "custom":
        await state.set_state(CustomStyleStates.waiting_custom)
        await query.message.answer(
            "Опиши свой стиль одним сообщением. Например: «как другу, но без мата, с юмором».\n(/cancel — отмена)"
        )
        try:
            await query.answer()
        except Exception:
            pass
        return
    try:
        await query.answer(f"Делаю {style_label(code)}…")
    except Exception:
        pass
    await _do_rewrite(query, query.from_user.id, style=code, edit_message=query.message)


@router.callback_query(F.data.startswith("another:"))
async def on_another(query: CallbackQuery):
    try:
        req_id = int(query.data.split(":")[1])
    except (IndexError, AttributeError, ValueError):
        try:
            await query.answer("Некорректные данные", show_alert=True)
        except Exception:
            pass
        return
    _ = req_id  # id из кнопки не используется для чтения чужих данных, стиль берём из PENDING
    await PENDING.hydrate(query.from_user.id)
    pending = PENDING.get(query.from_user.id, {})
    style = pending.get("last_style", "neutral")
    if style not in ALLOWED_STYLES:
        style = "neutral"
    try:
        await query.answer("Генерирую другой вариант…")
    except Exception:
        pass
    # pass a nudge via custom_style to force difference
    pending["custom_style"] = "Совсем другой вариант, не похожий на предыдущий, но с тем же смыслом."
    await _do_rewrite(query, query.from_user.id, style=style, edit_message=query.message)
    pending.pop("custom_style", None)


@router.callback_query(F.data.startswith("restyle:"))
async def on_restyle(query: CallbackQuery):
    try:
        await query.message.edit_text("Выбери новый стиль:", reply_markup=style_choice_kb())
        await query.answer()
    except Exception:
        # карта могла уйти (старый апдейт) — просто показать выбор стиля
        try:
            await query.message.answer("Выбери новый стиль:", reply_markup=style_choice_kb())
            await query.answer()
        except Exception:
            pass


@router.callback_query(F.data.startswith("quick:"))
async def on_quick(query: CallbackQuery):
    try:
        _, action, req_id = query.data.split(":")
    except (ValueError, AttributeError):
        try:
            await query.answer("Некорректные данные", show_alert=True)
        except Exception:
            pass
        return
    if action not in EXTRA_ACTIONS:
        try:
            await query.answer("Неизвестное действие", show_alert=True)
        except Exception:
            pass
        return
    labels = {"shorter": "✂️ Короче", "softer": "❤️ Мягче", "formal_more": "💼 Официальнее", "fix": "🔤 Без смены стиля"}
    try:
        await query.answer(f"Делаю: {labels.get(action, action)}…")
    except Exception:
        pass
    style = PENDING.get(query.from_user.id, {}).get("last_style", "neutral")
    if style not in ALLOWED_STYLES:
        style = "neutral"
    await _do_rewrite(query, query.from_user.id, style=style,
                      extra_style=action, edit_message=query.message)


@router.callback_query(F.data.in_({"more", "less"}) | F.data.startswith(("more:", "less:")))
async def on_more_less(query: CallbackQuery):
    """Expand/collapse the additional buttons on the result card."""
    try:
        req_id = int(query.data.split(":")[1])
    except (IndexError, AttributeError, ValueError):
        try:
            await query.answer("Некорректные данные", show_alert=True)
        except Exception:
            pass
        return
    expanded = query.data.startswith("more")
    try:
        await query.message.edit_reply_markup(reply_markup=result_actions_kb(req_id, expanded=expanded))
        await query.answer()
    except Exception:
        try:
            await query.answer()
        except Exception:
            pass


@router.callback_query(F.data.startswith("copy:"))
async def on_copy(query: CallbackQuery):
    try:
        _, req_id, idx = query.data.split(":")
    except (ValueError, AttributeError):
        try:
            await query.answer("Некорректные данные", show_alert=True)
        except Exception:
            pass
        return
    await PENDING.hydrate(query.from_user.id)
    pending = PENDING.get(query.from_user.id, {})
    texts = pending.get("last_texts", [])
    try:
        i = int(idx)
    except ValueError:
        i = 0
    try:
        req_id_int = int(req_id)
    except ValueError:
        req_id_int = 0
    if texts:
        # один tap-to-copy блок (моноширинный) — вместо двух сообщений
        chosen = texts[i] if 0 <= i < len(texts) else texts[0]
        await query.message.answer(copyable_text(chosen))
    elif req_id_int != 0:
        factory = get_session_factory()
        async with factory() as session:
            # IDOR fix: проверяем владельца запроса
            from sqlalchemy import select

            from app.database.models import RewriteRequest

            user = await repo.get_or_create_user(session, query.from_user.id)
            owned = (await session.execute(
                select(RewriteRequest).where(
                    RewriteRequest.id == req_id_int, RewriteRequest.user_id == user.id
                )
            )).scalar_one_or_none()
            if not owned:
                await query.message.answer("Не найдено.")
                try:
                    await query.answer()
                except Exception:
                    pass
                return
            results = await repo.get_results_for_request(session, req_id_int)
            if results:
                await query.message.answer(copyable_text(results[0].text))
            else:
                await query.message.answer("Не нашёл текст для копирования.")
    else:
        await query.message.answer("Не нашёл текст для копирования.")
    try:
        await query.answer("Отправил чистый текст — его удобно копировать 👆")
    except Exception:
        pass


@router.callback_query(F.data.startswith("fav:"))
async def on_fav(query: CallbackQuery):
    try:
        _, req_id, idx = query.data.split(":")
    except (ValueError, AttributeError):
        try:
            await query.answer("Некорректные данные", show_alert=True)
        except Exception:
            pass
        return
    try:
        req_id_int = int(req_id)
    except ValueError:
        req_id_int = 0
    await PENDING.hydrate(query.from_user.id)
    pending = PENDING.get(query.from_user.id, {})
    texts = pending.get("last_texts", [])
    try:
        i = int(idx)
    except ValueError:
        i = 0
    text = texts[i] if 0 <= i < len(texts) else (texts[0] if texts else "")
    # стиль варианта: альтернативы хранятся в pending["last_alts"] как [{style,text}]
    if 0 < i < len(texts):
        style = pending.get("last_style", "neutral") if i == 0 else "neutral"
        if style not in ALLOWED_STYLES:
            style = "neutral"
    else:
        style = pending.get("last_style", "neutral")
        if style not in ALLOWED_STYLES:
            style = "neutral"
    if not text and req_id_int != 0:
        factory = get_session_factory()
        async with factory() as session:
            # IDOR fix: проверяем владельца запроса
            from sqlalchemy import select

            from app.database.models import RewriteRequest

            user_tmp = await repo.get_or_create_user(session, query.from_user.id)
            owned = (await session.execute(
                select(RewriteRequest).where(
                    RewriteRequest.id == req_id_int, RewriteRequest.user_id == user_tmp.id
                )
            )).scalar_one_or_none()
            if not owned:
                await query.answer("Не найдено", show_alert=True)
                return
            results = await repo.get_results_for_request(session, req_id_int)
            if results:
                text, style = results[0].text, results[0].style
    if not text:
        await query.answer("Нечего сохранять", show_alert=True)
        return
    factory = get_session_factory()
    async with factory() as session:
        user = await repo.get_or_create_user(session, query.from_user.id)
        await repo.add_favorite(session, user.id, text, style)
    try:
        await query.answer("⭐ Сохранил в избранное!")
    except Exception:
        pass


@router.callback_query(F.data.startswith("reply:"))
async def on_reply(query: CallbackQuery):
    PENDING.setdefault(query.from_user.id, {})["reply_mode"] = True
    try:
        await query.message.edit_text("В каком тоне ответить?", reply_markup=style_choice_kb())
        await query.answer()
    except Exception:
        try:
            await query.message.answer("В каком тоне ответить?", reply_markup=style_choice_kb())
            await query.answer()
        except Exception:
            pass


@router.callback_query(F.data.startswith("translate:"))
async def on_translate(query: CallbackQuery):
    try:
        await query.message.edit_text("🌐 На какой язык перевести?", reply_markup=language_kb())
        await query.answer()
    except Exception:
        try:
            await query.message.answer("🌐 На какой язык перевести?", reply_markup=language_kb())
            await query.answer()
        except Exception:
            pass


@router.callback_query(F.data.startswith("lang:"))
async def on_lang(query: CallbackQuery):
    try:
        lang = query.data.split(":")[1]
    except (IndexError, AttributeError, ValueError):
        try:
            await query.answer("Некорректные данные", show_alert=True)
        except Exception:
            pass
        return
    if lang not in ALLOWED_LANGS:
        try:
            await query.answer("Неизвестный язык", show_alert=True)
        except Exception:
            pass
        return
    factory = get_session_factory()
    async with factory() as session:
        user = await repo.get_or_create_user(session, query.from_user.id)
        user.target_lang = lang
        await session.commit()
    names = {"ru": "русский 🇷🇺", "uk": "українська 🇺🇦", "en": "English 🇬🇧"}
    try:
        await query.message.edit_text(
            f"Ок! Язык результата: {names.get(lang, lang)}. Теперь выбери стиль:",
            reply_markup=style_choice_kb(),
        )
        await query.answer()
    except Exception:
        try:
            await query.message.answer(
                f"Ок! Язык результата: {names.get(lang, lang)}. Теперь выбери стиль:",
                reply_markup=style_choice_kb(),
            )
            await query.answer()
        except Exception:
            pass


ALLOWED_RECIPIENTS = {"Друг", "Партнёр", "Родители", "Преподаватель", "Работодатель", "Клиент"}


@router.callback_query(F.data.startswith("recipient:"))
async def on_recipient(query: CallbackQuery):
    try:
        value = query.data.split(":", 1)[1]
    except (IndexError, AttributeError, ValueError):
        try:
            await query.answer("Некорректные данные", show_alert=True)
        except Exception:
            pass
        return
    value = value.strip()[:64]
    if value not in ALLOWED_RECIPIENTS:
        try:
            await query.answer("Неизвестный получатель", show_alert=True)
        except Exception:
            pass
        return
    PENDING.setdefault(query.from_user.id, {})["recipient"] = value
    try:
        await query.message.edit_text(f"Ок, получатель: {html.escape(value)}. Какой стиль?", reply_markup=style_choice_kb())
        await query.answer()
    except Exception:
        try:
            await query.message.answer(f"Ок, получатель: {html.escape(value)}. Какой стиль?", reply_markup=style_choice_kb())
            await query.answer()
        except Exception:
            pass


@router.callback_query(F.data.startswith("reuse:"))
async def on_reuse(query: CallbackQuery):
    try:
        req_id = int(query.data.split(":")[1])
    except (IndexError, AttributeError, ValueError):
        try:
            await query.answer("Некорректные данные", show_alert=True)
        except Exception:
            pass
        return
    factory = get_session_factory()
    async with factory() as session:
        from sqlalchemy import select

        from app.database.models import RewriteRequest

        user = await repo.get_or_create_user(session, query.from_user.id)
        r = (await session.execute(
            select(RewriteRequest).where(
                RewriteRequest.id == req_id, RewriteRequest.user_id == user.id
            )
        )).scalar_one_or_none()
        if not r:
            await query.answer("Не найдено", show_alert=True)
            return
        PENDING[query.from_user.id] = {"text": r.source_text, "context_text": r.context_text}
    await query.message.answer("Взял текст из истории. Какой вариант сделать?", reply_markup=style_choice_kb())
    try:
        await query.answer()
    except Exception:
        pass


@router.callback_query(F.data.startswith("smart:"))
async def on_smart(query: CallbackQuery):
    try:
        action = query.data.split(":")[1]
    except (IndexError, AttributeError, ValueError):
        try:
            await query.answer("Некорректные данные", show_alert=True)
        except Exception:
            pass
        return
    mapping = {"softer": "softer", "reschedule": "neutral", "formal": "formal_more"}
    if action not in mapping:
        try:
            await query.answer("Неизвестное действие", show_alert=True)
        except Exception:
            pass
        return
    style = PENDING.get(query.from_user.id, {}).get("last_style", "neutral")
    if style not in ALLOWED_STYLES:
        style = "neutral"
    try:
        await query.answer("Применяю улучшение…")
    except Exception:
        pass
    await _do_rewrite(query, query.from_user.id,
                      style=style,
                      extra_style=mapping.get(action, "neutral"),
                      edit_message=query.message)
