"""Optional Redis (FSM storage + cache). Falls back to memory when not configured."""
from __future__ import annotations

_redis = None


async def get_redis(url: str):
    global _redis
    if not url:
        return None
    if _redis is not None:
        return _redis
    try:
        import redis.asyncio as aioredis

        _redis = aioredis.from_url(url, decode_responses=True)
        await _redis.ping()
        return _redis
    except Exception:
        return None
