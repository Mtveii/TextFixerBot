"""Group mode: бот реагирует только на reply-ответы себе или @mention.

В приватных чатах всё работает как раньше. В группах (group/supergroup)
сообщение обрабатывается только если:
  - это reply на сообщение самого бота, ИЛИ
  - текст/caption содержит @username бота (mention вырезается из текста).
"""
from __future__ import annotations

from aiogram.types import Message

GROUP_TYPES = ("group", "supergroup")

MENTION_PLACEHOLDER = ""


def _strip_mention(text: str | None, username: str) -> str | None:
    if not text or not username:
        return text
    cleaned = text.replace(f"@{username}", "").strip()
    # схлопываем двойные пробелы, оставшиеся после вырезания mention
    return " ".join(cleaned.split()) if cleaned != text else cleaned


def group_gate(message: Message, text: str | None = None) -> tuple[bool, str | None]:
    """(allowed, cleaned_text).

    text — исходный текст/каптион; в ЛС всегда allowed и текст не меняется.
    """
    import app.bot.state as state

    if message.chat.type not in GROUP_TYPES:
        return True, text

    # reply на сообщение бота — всегда наш
    reply_from = getattr(message.reply_to_message, "from_user", None)
    if reply_from is not None and state.BOT is not None and reply_from.id == state.BOT.id:
        cleaned = _strip_mention(text, state.BOT_USERNAME or "")
        return True, cleaned

    bot_username = state.BOT_USERNAME
    if bot_username and text and f"@{bot_username}" in text:
        return True, _strip_mention(text, bot_username)

    return False, text
