"""Bot entrypoint: polling/webhook, commands, wiring."""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, ErrorEvent, Message

from app.bot.handlers import (
    admin,
    feedback,
    history,
    inline,
    photo,
    premium,
    rewrite,
    scenarios,
    start,
    voice,
)
from app.bot.keyboards.main import recipient_kb
from app.core.config import get_settings
from app.core.db import get_session_factory, init_db
from app.core.migrations import ensure_schema
from app.database import repositories as repo

settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger(__name__)


async def set_commands(bot: Bot):
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Начать"),
            BotCommand(command="history", description="📚 История"),
            BotCommand(command="favorites", description="⭐ Избранное"),
            BotCommand(command="situations", description="📚 Ситуации"),
            BotCommand(command="decline", description="❌ Отказать"),
            BotCommand(command="congrats", description="🎉 Поздравление"),
            BotCommand(command="apology", description="🙏 Извинение"),
            BotCommand(command="ask", description="🙌 Просьба"),
            BotCommand(command="mystyle", description="🧬 Мой стиль"),
            BotCommand(command="cancel", description="↪️ Отменить режим"),
            BotCommand(command="language", description="🌐 Язык"),
            BotCommand(command="premium", description="💎 Premium"),
            BotCommand(command="forget", description="🗑️ Удалить историю"),
            BotCommand(command="privacy", description="🔒 Приватность"),
            BotCommand(command="to", description="👤 Кому (получатель)"),
            BotCommand(command="help", description="Помощь"),
        ]
    )


def _log_webhook_task(task: "asyncio.Task") -> None:
    if task.cancelled():
        return
    exc = task.exception()
    if exc:
        log.error("Webhook update processing failed", exc_info=exc)


async def run_webhook(bot: Bot, dp, settings_, handle_signals: bool = True) -> None:
    """Minimal aiohttp webhook server (aiogram 3 has no built-in one).

    - POST <webhook_path>: Telegram updates, validated by secret token header
    - GET  /health: liveness endpoint for LB / docker healthcheck
    """
    from aiohttp import web

    async def on_update(request: web.Request) -> web.Response:
        secret = settings_.webhook_secret
        if secret and request.headers.get("X-Telegram-Bot-Api-Secret-Token") != secret:
            return web.Response(status=403)
        try:
            data = await request.json()
        except Exception:
            return web.Response(status=400)
        task = asyncio.create_task(dp.feed_webhook_update(bot, data))
        task.add_done_callback(_log_webhook_task)
        # answer Telegram immediately: handlers run in background (aiogram
        # warns if a webhook response takes >55s)
        return web.Response(text="ok")

    async def health(_: web.Request) -> web.Response:
        return web.Response(text="ok")

    app = web.Application()
    app.router.add_post(settings_.webhook_path, on_update)
    app.router.add_get("/health", health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=settings_.webhook_port)
    await site.start()
    log.info("Webhook server on 0.0.0.0:%s%s (health: /health)", settings_.webhook_port, settings_.webhook_path)

    import signal

    stop = asyncio.Event()
    if handle_signals:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, stop.set)
            except (NotImplementedError, RuntimeError):
                pass
    try:
        await stop.wait()
    finally:
        log.info("Stopping webhook server…")
        await runner.cleanup()


def build_dispatcher(storage=None) -> Dispatcher:
    """Dispatcher + хуки телеметрии + роутеры. Используется main() и vercel_entry.py."""
    import app.bot.state as state
    from app.ai.provider import LLMProvider

    dp = Dispatcher(storage=storage or MemoryStorage())

    factory = get_session_factory()

    async def _record(kind: str, detail: str, user_id: int | None = None) -> None:
        try:
            async with factory() as session:
                await repo.add_event(session, kind, user_id=user_id, detail=detail[:900])
        except Exception:
            log.exception("failed to record event %s", kind)

    def _update_user_id(event: ErrorEvent) -> int | None:
        update = event.update
        from_user = getattr(update, "from_user", None) or getattr(
            getattr(update, "message", None), "from_user", None
        )
        return from_user.id if from_user else None

    if state.PROVIDER is None:
        state.PROVIDER = LLMProvider.from_settings(get_settings())

    state.PROVIDER.error_callback = lambda backend, op, exc: _record(
        "llm_error", f"{backend}/{op}: {exc!r}"
    )

    @dp.errors()
    async def on_error(event: ErrorEvent):
        log.exception("Unhandled update error: %s", event.exception)
        await _record("error", repr(event.exception), user_id=_update_user_id(event))
        return True

    @dp.message(Command("to"))
    async def to_cmd(message: Message):
        await message.answer("👤 Кому отправляешь? Выбери получателя:", reply_markup=recipient_kb())

    dp.include_routers(
        start.router,
        scenarios.router,
        history.router,
        voice.router,
        photo.router,
        premium.router,
        rewrite.router,
        admin.router,
        feedback.router,
        inline.router,
    )
    return dp


async def main():
    settings = get_settings()
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is empty. Copy .env.example to .env and fill it.")

    init_db(settings.database_url)
    await ensure_schema()

    import app.bot.state as state
    from app.ai.provider import LLMProvider
    from app.bot.state import PENDING

    state.PROVIDER = LLMProvider.from_settings(settings)
    if not state.PROVIDER.configured:
        log.warning("No LLM keys (GROQ/GEMINI/OPENAI) — bot runs in OFFLINE fallback mode (no AI quality).")
    else:
        log.info("LLM backends: %s", state.PROVIDER.backend_names)

    storage = MemoryStorage()
    _redis_storage = None
    if settings.redis_url:
        try:
            from aiogram.fsm.storage.redis import RedisStorage

            _redis_storage = RedisStorage.from_url(settings.redis_url)
            log.info("Using Redis FSM storage")
        except Exception as e:
            log.warning("Redis unavailable, using memory: %s", e)
        try:
            from app.core.redis_client import get_redis

            rclient = await get_redis(settings.redis_url)
            if rclient is not None:
                PENDING.attach_redis(rclient)
                log.info("PENDING store: Redis-backed")
        except Exception as e:
            log.warning("PENDING stays in-process: %s", e)

    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = build_dispatcher(storage=_redis_storage or storage)

    state.BOT = bot
    state.DP = dp
    try:
        me = await bot.get_me()
        state.BOT_USERNAME = me.username or ""
    except Exception:
        log.warning("get_me failed, group mentions disabled for this run")
        state.BOT_USERNAME = ""
    await set_commands(bot)
    log.info("Starting %s…", "webhook" if settings.webhook_url else "polling")

    if settings.webhook_url:
        await bot.set_webhook(
            settings.webhook_url,
            secret_token=settings.webhook_secret or None,
            drop_pending_updates=True,
        )
        await run_webhook(bot, dp, settings)
    else:
        await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
