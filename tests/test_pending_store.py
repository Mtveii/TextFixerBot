"""Tests for PendingStore: bounded dict, Redis write-through/hydrate (=stub client)."""
from __future__ import annotations

import asyncio

import pytest

from app.bot.state import MAX_PENDING, PendingStore


class FakeRedis:
    def __init__(self):
        self.h = {}
        self.deleted = []

    async def hset(self, key, field, value):
        self.h.setdefault(key, {})[field] = value

    async def expire(self, key, ttl):
        pass

    async def hget(self, key, field):
        return self.h.get(key, {}).get(field)

    async def hdel(self, key, field):
        self.deleted.append(field)
        self.h.get(key, {}).pop(field, None)


@pytest.mark.asyncio
async def test_no_redis_is_noop():
    s = PendingStore()
    s[1] = {"text": "aa"}
    assert s[1]["text"] == "aa"
    await s.hydrate(1)  # без redis — тихий no-op
    s.pop(1)


@pytest.mark.asyncio
async def test_write_through_and_hydrate():
    r = FakeRedis()
    a = PendingStore()
    a.attach_redis(r)
    a[42] = {"text": "привет", "last_texts": ["x"]}
    await asyncio.sleep(0)  # даём фоновому write-through исполниться
    assert a[42]["text"] == "привет"

    # другой процесс: пустая память, hydrate из Redis
    b = PendingStore()
    b.attach_redis(r)
    await b.hydrate(42)
    assert b[42]["last_texts"] == ["x"]

    # pop чистит и Redis
    a.pop(42)
    await asyncio.sleep(0)  # даём create_task сработать
    assert r.deleted == ["42"]
    fresh = PendingStore()
    fresh.attach_redis(r)
    await fresh.hydrate(42)
    assert 42 not in fresh


@pytest.mark.asyncio
async def test_hydrate_skips_existing_and_bad_json(monkeypatch):
    r = FakeRedis()
    r.h["tfb:pending"] = {"7": "{bad json"}
    s = PendingStore()
    s.attach_redis(r)
    s[7] = {"text": "in-memory"}
    await s.hydrate(7)
    assert s[7]["text"] == "in-memory"  # не затёрто
    del s[7]
    await s.hydrate(7)  # bad json — тихо игнорим
    assert 7 not in s


def test_bounded_dict_eviction():
    s = PendingStore()
    for i in range(MAX_PENDING + 10):
        s[1000000 + i] = {"n": i}
    assert len(s) <= MAX_PENDING
    assert 1000000 not in s  # evict oldest
