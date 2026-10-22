"""Photo/screenshot -> Vision OCR -> rewrite flow."""
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


@router.message(F.photo | F.document)
async def on_photo(message: Message):
    if message.chat.type in ("group", "supergroup"):
        allowed, _ = group_gate(
            message,
            (message.caption or "") if getattr(message, "caption", None) else None,
        )
        if not allowed:
            return
    has_image = bool(message.photo) or (message.document and (message.document.mime_type or "").startswith("image/"))
    if not has_image:
        return
    if state.PROVIDER is None or not state.PROVIDER.configured:
        await message.answer("📸 Фото-текст требует настроенный LLM (Vision). Пока отправь текст вручную 👇")
        return
    # лимит размера файла
    file_size = None
    if message.photo:
        file_size = getattr(message.photo[-1], "file_size", None)
    elif message.document:
        file_size = getattr(message.document, "file_size", None)
    if file_size and file_size > MAX_FILE_SIZE:
        await message.answer("Файл слишком большой (лимит 20MB). Отправь файл поменьше.")
        return
    file_id = message.photo[-1].file_id if message.photo else message.document.file_id
    try:
        tg_file = await message.bot.get_file(file_id)
        buf = await message.bot.download_file(tg_file.file_path)
        img = buf.read() if hasattr(buf, "read") else bytes(buf.getvalue())
        if len(img) > MAX_FILE_SIZE:
            await message.answer("Файл слишком большой (лимит 20MB). Отправь файл поменьше.")
            return
    except Exception:
        await message.answer("Не смог скачать фото.")
        return
    status = await message.answer("🔍 Читаю текст с фото…")
    try:
        text = await state.PROVIDER.extract_text_from_image(img)
    except Exception:
        await status.edit_text("Не смог прочитать текст. Попробуй другое фото или отправь текстом.")
        return
    if not text.strip():
        await status.edit_text("Не нашёл текста на фото.")
        return
    factory = get_session_factory()
    async with factory() as session:
        user = await repo.get_or_create_user(session, message.from_user.id)
        allowed, used, limit = await check_and_bump(session, user.id, kind="vision")
        if not allowed:
            await status.edit_text(f"⏳ Лимит исчерпан ({used}/{limit}).")
            return
    PENDING[message.from_user.id] = {"text": text[:4000]}
    await status.edit_text(f"📝 Нашёл текст:\n<i>{html.escape(text[:800])}</i>\n\nСделать нормально?", parse_mode="HTML",
                           reply_markup=style_choice_kb())
