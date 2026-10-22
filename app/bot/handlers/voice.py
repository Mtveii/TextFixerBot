"""Voice -> STT -> rewrite flow."""
from __future__ import annotations

import html

from aiogram import F, Router
from aiogram.types import Message

import app.bot.state as state
from app.bot.group_gate import group_gate
from app.bot.keyboards.main import style_choice_kb
from app.bot.state import PENDING
from app.core.db import get_session_factory
from app.core.rate_limit import check_and_bump
from app.database import repositories as repo

router = Router()

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB
MAX_VOICE_DURATION = 600  # 10 минут


@router.message(F.voice | F.audio)
async def on_voice(message: Message):
    if message.chat.type in ("group", "supergroup"):
        allowed, _ = group_gate(
            message,
            (message.caption or "") if getattr(message, "caption", None) else None,
        )
        if not allowed:
            return
    if state.PROVIDER is None or not state.PROVIDER.configured:
        await message.answer("🎙️ Голосовые требуют настроенный LLM (GROQ_API_KEY). Пока отправь текстом 👇")
        return
    obj = message.voice or message.audio
    # лимит размера файла
    file_size = getattr(obj, "file_size", None)
    if file_size and file_size > MAX_FILE_SIZE:
        await message.answer("Файл слишком большой (лимит 20MB). Отправь покороче.")
        return
    # лимит длительности голосового, если доступна
    duration = getattr(obj, "duration", None)
    if duration and duration > MAX_VOICE_DURATION:
        await message.answer("Голосовое слишком длинное (лимит 10 минут). Отправь покороче.")
        return
    try:
        tg_file = await message.bot.get_file(obj.file_id)
        buf = await message.bot.download_file(tg_file.file_path)
        audio_bytes = buf.read() if hasattr(buf, "read") else bytes(buf.getvalue())
        if len(audio_bytes) > MAX_FILE_SIZE:
            await message.answer("Файл слишком большой (лимит 20MB). Отправь покороче.")
            return
    except Exception:
        await message.answer("Не смог скачать голосовое. Попробуй ещё раз.")
        return
    status = await message.answer("🎧 Расшифровываю…")
    try:
        text = await state.PROVIDER.transcribe_voice(audio_bytes)
    except Exception:
        await status.edit_text("Не смог расшифровать голосовое. Проверь API-ключ или отправь текстом.")
        return
    if not text.strip():
        await status.edit_text("Не расслышал. Попробуй ещё раз или напиши текстом.")
        return
    factory = get_session_factory()
    async with factory() as session:
        user = await repo.get_or_create_user(session, message.from_user.id)
        allowed, used, limit = await check_and_bump(session, user.id, kind="voice")
        if not allowed:
            await status.edit_text(f"⏳ Лимит исчерпан ({used}/{limit}).")
            return
    PENDING[message.from_user.id] = {"text": text[:4000]}
    await status.edit_text(f"📝 Услышал:\n<i>{html.escape(text[:500])}</i>\n\nКакой вариант сделать?", parse_mode="HTML",
                           reply_markup=style_choice_kb())
