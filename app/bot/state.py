"""Shared per-process state: bot/dp/provider + pending texts (Redis-backed cache)."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

MAX_PENDING = 5000
PENDING_REDIS_KEY = "tfb:pending"
PENDING_TTL = 24 * 3600


class PendingStore(dict):
    """Bounded dict + опциональный write-through в Redis.

    In-memory — источник правды в рантайме процесса; Redis — персистентный
    кэш для выживания рестарта процесса и горизонтального масштабирования.

    ВАЖНО: write-through только через __setitem__/pop; setdefault в стандартной
    реализации пишет напрямую в dict (это сознательный no-op для Redis), поэтому
    для записи новых uid используй store[uid] = value.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._redis = None
        self._key = PENDING_REDIS_KEY

    def attach_redis(self, client, key: str = PENDING_REDIS_KEY) -> None:
        self._redis = client
        self._key = key

    def _write_through(self, key, value) -> None:
        if self._redis is None:
            return
        try:
            import asyncio

            asyncio.get_running_loop().create_task(self._awrite(key, value))
        except RuntimeError:
            pass  # нет event loop (странный контекст) — память остаётся источником правды

    async def _awrite(self, key, value) -> None:
        try:
            await self._redis.hset(self._key, str(key), json.dumps(value))
            await self._redis.expire(self._key, PENDING_TTL)
        except Exception:
            log.exception("pending redis write-through failed")

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        overflow = len(self) - MAX_PENDING
        if overflow > 0:
            for old_key in list(self)[:overflow]:
                self.pop(old_key, None)
        self._write_through(key, value)

    def pop(self, key, *args):
        super().pop(key, *args)
        if self._redis is not None:
            try:
                import asyncio

                asyncio.get_running_loop().create_task(self._adel(key))
            except RuntimeError:
                pass

    async def _adel(self, key) -> None:
        try:
            await self._redis.hdel(self._key, str(key))
        except Exception:
            log.exception("pending redis hdel failed")

    async def hydrate(self, uid: int) -> None:
        """Подтянуть pending пользователя из Redis, если его нет в памяти (после рестарта)."""
        if self._redis is None or uid in self:
            return
        try:
            raw = await self._redis.hget(self._key, str(uid))
        except Exception:
            raw = None
        if raw is None:
            return
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            log.warning("pending hydrate: bad json for uid=%s", uid)
            return
        if isinstance(data, dict):
            super().__setitem__(uid, data)


PENDING: PendingStore = PendingStore()  # user_id -> {text, context_text, reply_mode, message_id}

BOT = None
DP = None
PROVIDER = None
BOT_USERNAME = ""  # выставляется в main после bot.get_me(); для @-гейта в группах


@dataclass
class AppState:
    pending: dict = field(default_factory=dict)
