""" /start, /help, /privacy, /language, main menu commands."""
from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.bot.keyboards.main import language_kb
from app.bot.state import PENDING
from app.core.config import get_settings
from app.core.db import get_session_factory
from app.database import repositories as repo

router = Router()

_SETTINGS = get_settings()


def _sibling_kb() -> InlineKeyboardMarkup | None:
    username = (_SETTINGS.sibling_bot_username or "").strip().lstrip("@")
    if not username:
        return None
    label = _SETTINGS.sibling_bot_label or username
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=f"🔗 {label}", url=f"https://t.me/{username}")]]
    )


WELCOME = (
    "✍️ <b>TextFixerBot</b> — превращает сырой текст в нормальный вариант в нужном стиле.\n\n"
    "🔧 <b>Технологии:</b>\n"
    "• LLM: Groq → Gemini → OpenAI (авто-фейловер)\n"
    "• STT: Groq Whisper (голосовые) + Vision OCR (фото)\n"
    "• 6 стилей + свой стиль, 3 варианта результата\n\n"
    "✨ <b>Функции:</b>\n"
    "• 🟢 Нормально / 💼 Официально / 🙂 Дружелюбно / ❤️ Мягко / ⚡ Коротко / 🔥 Уверенно\n"
    "• 📋 Копировать, 🔄 Другой вариант, ✂️ Короче, ❤️ Мягче, 💼 Офиц.\n"
    "• 📚 История, ⭐ Избранное, 🧬 Мой стиль, 🌐 Язык результата\n"
    "• Голосовые 🎙️ и фото 📸 тоже понимаю\n\n"
    "🆓 Бесплатно, открыто. Подробнее: /help • /about\n\n"
    "Просто отправь любой текст — а дальше выбери стиль."
)

HELP = (
    "ℹ️ Как пользоваться:\n"
    "1. Напиши как попало — я пойму смысл.\n"
    "2. Выбери стиль кнопкой.\n"
    "3. Получи 3 варианта + умные подсказки.\n"
    "4. Кнопки под результатом: 📋 Скопировать, 🔄 Другой вариант, 🎭 Стиль, ✂️ Короче, ❤️ Мягче, 💼 Офиц., 🔤 Исправить ошибки, ⭐ Сохранить.\n\n"
    "Фишки:\n"
    "• Ответь на чужое сообщение (reply) — предложу 💬 Ответить.\n"
    "• Перешли сообщение друга + свой черновик — пойму контекст.\n"
    "• «она пишет: …» — режим «Что ответить?».\n"
    "• Голосовые 🎙️ и фото 📸 тоже понимаю.\n"
    "• Inline: в любом чате набери <code>@бот текст</code>.\n"
    "• Застрял в режиме «свой стиль» или сценария? <code>/cancel</code> — вернёмся к обычному режиму.\n\n"
    "—\nБесплатно, открыто: /about — GitHub, если захочешь поддержать ☕"
)

ABOUT = (
    "🤖 <b>TextFixerBot</b> — превращает сырой текст в нормальный вариант в нужном стиле.\n\n"
    "🔧 <b>Технологии:</b>\n"
    "• LLM: Groq → Gemini → OpenAI (авто-фейловер)\n"
    "• STT: Groq Whisper (голосовые) + Vision OCR (фото)\n"
    "• 6 стилей + свой стиль, 3 варианта результата\n\n"
    "✨ <b>Функции:</b>\n"
    "• 🟢 Нормально / 💼 Официально / 🙂 Дружелюбно / ❤️ Мягко / ⚡ Коротко / 🔥 Уверенно\n"
    "• 📚 История, ⭐ Избранное, 🧬 Мой стиль, 🌐 Язык результата\n"
    "• Голосовые 🎙️ и фото 📸 тоже понимаю\n\n"
    "🆓 Бесплатно, открыто, без слежки.\n"
    "Если проект полезен — можно поддержать разработку ☕ (полностью добровольно)"
)


@router.message(CommandStart())
async def start(message: Message, state: FSMContext):
    # выход из состояний «свой стиль» / сценария — /start работает как обычный сброс
    await state.clear()
    PENDING.pop(message.from_user.id, None)
    factory = get_session_factory()
    async with factory() as session:
        await repo.get_or_create_user(session, message.from_user.id)
    kb = _sibling_kb()
    if kb:
        await message.answer(WELCOME, parse_mode="HTML", reply_markup=kb)
    else:
        await message.answer(WELCOME, parse_mode="HTML")


@router.message(Command("cancel"))
async def cancel_cmd(message: Message, state: FSMContext):
    """Выход из ловушки «ожидаю описание стиля / сценарий» — любой следующий текст снова текст."""
    await state.clear()
    PENDING.pop(message.from_user.id, None)
    await message.answer("↪️ Отменил. Просто отправь текст — сделаю нормально 👇")


@router.message(Command("help"))
async def help_cmd(message: Message):
    await message.answer(HELP, parse_mode="HTML")


@router.message(Command("about"))
async def about_cmd(message: Message):
    kb = _sibling_kb()
    if kb:
        await message.answer(ABOUT, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)
    else:
        await message.answer(ABOUT, parse_mode="HTML", disable_web_page_preview=True)


@router.message(Command("privacy"))
async def privacy(message: Message):
    await message.answer(
        "🔒 <b>Приватность</b>\n\n"
        "По умолчанию история сохраняется, чтобы работало /history. "
        "Содержимое не используется для обучения без согласия.\n\n"
        "/forget — удалить историю\n"
        "/noprivacy — выключить сохранение истории\n"
        "/yesprivacy — включить сохранение истории",
        parse_mode="HTML",
    )


@router.message(Command("noprivacy"))
async def no_history(message: Message):
    factory = get_session_factory()
    async with factory() as session:
        user = await repo.get_or_create_user(session, message.from_user.id)
        user.save_history = False
        await session.commit()
    await message.answer("Ок, больше не сохраняю историю. /yesprivacy — включить обратно.")


@router.message(Command("yesprivacy"))
async def yes_history(message: Message):
    factory = get_session_factory()
    async with factory() as session:
        user = await repo.get_or_create_user(session, message.from_user.id)
        user.save_history = True
        await session.commit()
    await message.answer("Ок, сохраняю историю. /forget — удалить её в любой момент.")


@router.message(Command("language"))
async def language(message: Message):
    await message.answer("🌐 Выбери язык результата:", reply_markup=language_kb())
