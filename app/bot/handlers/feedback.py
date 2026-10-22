"""Обратная связь: /report — пишет Event(kind="feedback"), виден в /admin."""
from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from app.core.db import get_session_factory
from app.database import repositories as repo

router = Router()


@router.message(Command("report"))
async def report_cmd(message: Message, command: CommandObject):
    text = (command.args or "").strip()
    if not text:
        await message.answer("Опиши проблему: <code>/report что не так</code>")
        return
    factory = get_session_factory()
    async with factory() as session:
        user = await repo.get_or_create_user(session, message.from_user.id)
        await repo.add_event(
            session, "feedback", user_id=user.id,
            detail=f"{message.from_user.username or message.from_user.full_name}: {text}",
        )
    await message.answer("Спасибо! Проблема записана — разберусь в ближайшее время. 💛")
