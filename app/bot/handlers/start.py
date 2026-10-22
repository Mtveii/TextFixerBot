""" /start, /help, /privacy, /language, main menu commands."""
from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.bot.keyboards.main import language_kb
from app.bot.state import PENDING
from app.core.db import get_session_factory
from app.database import repositories as repo

router = Router()

WELCOME = (
    "✍️ <b>Сделай нормально</b>\n\n"
    "Напиши мне как есть — хоть с ошибками, сленгом или в двух словах. "
    "Я превращу это в нормальный текст.\n\n"
    "Пример:\n"
    "<i>«привет я сегодня не смогу прийти потому что надо помочь дома»</i>\n\n"
    "Просто отправь любой текст, голосовое или фото текста — "
    "а дальше выбери стиль: 🟢 Нормально, 💼 Официально, 🙂 Дружелюбно, ❤️ Мягко, ⚡ Коротко, 🔥 Уверенно.\n\n"
    "Команды:\n"
    "/history — 📚 история\n"
    "/favorites — ⭐ избранное\n"
    "/situations — 📚 ситуации и шаблоны\n"
    "/mystyle — 🧬 мой стиль\n"
    "/language — 🌐 язык результата\n"
    "/privacy — 🔒 приватность\n"
    "/help — помощь"
)

HELP = (
    "Как пользоваться:\n\n"
    "1. Напиши как попало — я пойму смысл.\n"
    "2. Выбери стиль кнопкой.\n"
    "3. Получи 3 варианта + умные подсказки.\n"
    "4. Кнопки под результатом: 📋 Скопировать (пришлю чистый текст), "
    "🔄 Другой вариант, 🎭 Изменить стиль, ✂️ Короче, ❤️ Мягче, 💼 Официальнее, 🔤 Исправить ошибки, ⭐ Сохранить.\n\n"
    "Фишки:\n"
    "• Ответь на чужое сообщение (reply) — предложу 💬 Ответить.\n"
    "• Перешли сообщение друга + свой черновик — пойму контекст.\n"
    "• «она пишет: …» — режим «Что ответить?».\n"
    "• Голосовые 🎙️ и фото 📸 тоже понимаю.\n"
    "• Inline: в любом чате набери <code>@бот текст</code>."
    "• Застрял в режиме «свой стиль» или сценария? <code>/cancel</code> — вернёмся к обычному режиму."
)


@router.message(CommandStart())
async def start(message: Message, state: FSMContext):
    # выход из состояний «свой стиль» / сценария — /start работает как обычный сброс
    await state.clear()
    PENDING.pop(message.from_user.id, None)
    factory = get_session_factory()
    async with factory() as session:
        await repo.get_or_create_user(session, message.from_user.id)
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
