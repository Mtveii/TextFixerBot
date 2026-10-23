"""Vercel serverless entrypoint (webhook-only режим).

Vercel Python runtime требует модуль, экспортирующий верхнеуровневый `app`
(ASGI). Используется минимальный hand-rolled ASGI хендлер (без зависимостей):
он фидит апдейты прямо в aiogram Dispatcher.

Особенности Vercel:
- polling и постоянные процессы не поддерживаются (для этого VPS + main.py);
- состояние процесса эфемерное — задай REDIS_URL, тогда hydrate вернёт
  pending-тексты между тёплыми вызовами;
- обязательно Postgres DATABASE_URL (локальный sqlite на Vercel не живёт).

Сетап webhook после первого деплоя:
  https://api.telegram.org/bot<TOKEN>/setWebhook?url=<vercel-url>&secret_token=<WEBHOOK_SECRET>
"""
from __future__ import annotations

import json
import logging
import os

log = logging.getLogger("vercel_entry")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

MAX_BODY = 1024 * 1024

state_init_lock = None
_bot = None
_dp = None


def _get_settings():
    from app.core.config import get_settings

    return get_settings()


async def _ainit() -> None:
    """Единоразовый init тёплого процесса: bot + dispatcher (+ redis для PENDING)."""
    global state_init_lock, _bot, _dp
    if state_init_lock is None:
        import asyncio

        state_init_lock = asyncio.Lock()
    if _dp is not None:
        return
    async with state_init_lock:
        if _dp is not None:
            return
        from aiogram import Bot
        from aiogram.client.default import DefaultBotProperties
        from aiogram.enums import ParseMode

        import app.bot.state as bstate
        from app.bot.state import PENDING
        from app.core.db import init_db
        from app.core.migrations import ensure_schema
        from app.main import build_dispatcher

        settings = _get_settings()
        init_db(settings.database_url)
        await ensure_schema()
        _bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        _dp = build_dispatcher()
        bstate.BOT = _bot
        if settings.redis_url:
            try:
                from app.core.redis_client import get_redis

                rclient = await get_redis(settings.redis_url)
                if rclient is not None:
                    PENDING.attach_redis(rclient)
            except Exception:
                log.exception("redis attach failed, PENDING in-process")
        log.info("vercel warm process initialised")


async def app(scope, receive, send) -> None:
    if scope["type"] != "http":
        raise RuntimeError("only http scope supported")
    body = b""
    while True:
        message = await receive()
        if message["type"] == "http.request":
            body += message.get("body", b"")
            if not message.get("more_body") or len(body) > MAX_BODY:
                break
        else:  # http.disconnect
            break

    path = scope["path"]
    if scope["method"] == "GET" and path in ("/", "/health"):
        await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"text/plain")]})
        await send({"type": "http.response.body", "body": b"ok"})
        return

    await _ainit()
    try:
        if not body:
            status, payload = 400, {"ok": False, "error": "empty body"}
        else:
            try:
                data = json.loads(body)
            except (ValueError, UnicodeDecodeError):
                log.warning("webhook: bad json (%d bytes)", len(body))
                await send({"type": "http.response.start", "status": 400, "headers": [(b"content-type", b"application/json")]})
                await send({"type": "http.response.body", "body": b'{"ok":false,"error":"bad json"}'})
                return
            if not isinstance(data, dict) or "update_id" not in data:
                await send({"type": "http.response.start", "status": 400, "headers": [(b"content-type", b"application/json")]})
                await send({"type": "http.response.body", "body": b'{"ok":false,"error":"not a telegram update"}'})
                return
            # secret webhook-токен (если задан) — защита от посторонних POST
            expected_secret = _get_settings().webhook_secret or ""
            if expected_secret:
                hdrs = {k.lower(): v for k, v in scope.get("headers", [])}
                if hdrs.get(b"x-telegram-bot-api-secret-token") != expected_secret.encode():
                    log.warning("webhook: bad secret token")
                    await send({"type": "http.response.start", "status": 403, "headers": [(b"content-type", b"application/json")]})
                    await send({"type": "http.response.body", "body": b'{"ok":false,"error":"forbidden"}'})
                    return
            from aiogram.types import Update

            update = Update.model_validate(data, context={"bot": _bot})
            try:
                await _dp.feed_update(_bot, update)
            except Exception:
                # 200 уходит даже при ошибке хендлера — иначе Telegram ретраит апдейт бесконечно
                log.exception("handler failed for update_id=%s", data.get("update_id"))
            status, payload = 200, {"ok": True}
    except Exception:
        log.exception("webhook plumbing failed")
        status, payload = 500, {"ok": False, "error": "internal"}

    data = json.dumps(payload).encode()
    await send({"type": "http.response.start", "status": status, "headers": [(b"content-type", b"application/json")]})
    await send({"type": "http.response.body", "body": data})
