"""Интеграционные тесты LLM-провайдера на httpx.MockTransport:
retry-цепочка моделей, фолбэк бэкендов, JSON-режим, STT/Vision, телеметрия ошибок."""
from __future__ import annotations

import json

import httpx
import pytest

from app.ai.provider import Backend, LLMProvider

GROQ_OK = {
    "intent": "cancellation",
    "language": "ru",
    "tone": "neutral",
    "meaning": "s",
    "rewritten_text": "Готово",
    "alternatives": [{"style": "soft", "text": "Мягко"}],
    "suggestion": "",
}


class Router:
    """Мок-роутер: очередь ответов per-host + лог запросов."""

    def __init__(self):
        self.queue: dict[str, list] = {}
        self.requests: list[httpx.Request] = []

    def add(self, host: str, response):
        self.queue.setdefault(host, []).append(response)

    def transport(self):
        async def handler(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            host = request.url.host
            item = self.queue.get(host)
            if not item:
                return httpx.Response(500, json={"error": "no scripted response"})
            resp = item.pop(0)
            if isinstance(resp, httpx.Response):
                return resp
            return httpx.Response(200, json=resp)

        return httpx.MockTransport(handler)

    def provider(self, extra=()) -> LLMProvider:
        backends = [
            Backend("groq", "k1", "https://groq.example/v1", "g-main", stt_model="whisper-x", timeout=5),
            Backend("gemini", "k2", "https://gemini.example/v1", "gem-main", alt_models=["gem-alt"], timeout=5),
            *extra,
        ]
        return LLMProvider(backends=backends, transport=self.transport())


def _json(request: httpx.Request) -> dict:
    try:
        return json.loads(request.content.decode())
    except Exception:
        return {}


def _chat_body(d: dict | None = None) -> dict:
    content = json.dumps(GROQ_OK if d is None else d)
    return {"choices": [{"message": {"content": content}}]}


# ---------- happy path ----------


@pytest.mark.asyncio
async def test_primary_backend_success():
    r = Router()
    p = r.provider()
    r.add("groq.example", _chat_body(None))
    out = await p.rewrite("текст", style="short")
    assert out["rewritten_text"] == "Готово"
    assert out["_backend"] == "groq"
    assert out["alternatives"][0]["text"] == "Мягко"


# ---------- retry / fallback ----------


@pytest.mark.asyncio
async def test_backend_fallback_on_503():
    r = Router()
    p = r.provider()
    r.add("groq.example", httpx.Response(503))
    r.add("gemini.example", _chat_body(None))
    out = await p.rewrite("текст", style="neutral")
    assert out["_backend"] == "gemini"


@pytest.mark.asyncio
async def test_alt_model_retry_on_429():
    r = Router()
    p = r.provider()
    r.add("gemini.example", httpx.Response(429))
    r.add("gemini.example", _chat_body(None))
    out = await p.rewrite("текст", style="neutral")
    assert out["_backend"] == "gemini"
    assert r.requests[-1].url.host == "gemini.example"


@pytest.mark.asyncio
async def test_json_mode_rejected_then_plain_retry():
    r = Router()
    p = r.provider()
    # первый POST (json_object) — 400; второй (plain) — 200
    r.add("groq.example", httpx.Response(400, json={"error": "response_format not supported"}))
    r.add("groq.example", _chat_body(None))
    out = await p.rewrite("текст", style="neutral")
    assert out["rewritten_text"] == "Готово"
    assert len(r.requests) == 2
    assert "response_format" not in _json(r.requests[1])


@pytest.mark.asyncio
async def test_all_backends_fail_offline_fallback():
    r = Router()
    p = r.provider()
    r.add("groq.example", httpx.Response(500))
    r.add("gemini.example", httpx.Response(429))
    out = await p.rewrite("я завтра не приду", style="neutral")
    assert out["rewritten_text"]  # offline fallback сохранил текст


@pytest.mark.asyncio
async def test_error_callback_called_for_failed_backend():
    r = Router()
    p = r.provider()
    seen: list[tuple] = []

    async def cb(name, op, exc):
        seen.append((name, op, type(exc).__name__))

    p.error_callback = cb
    r.add("groq.example", httpx.Response(500))
    r.add("gemini.example", _chat_body(None))
    await p.rewrite("текст", style="neutral")
    assert len(seen) == 1
    assert seen[0][0] == "groq" and seen[0][1] == "rewrite" and "HTTPStatusError" in seen[0][2]


# ---------- STT / Vision ----------


@pytest.mark.asyncio
async def test_transcribe_voice_success():
    r = Router()
    p = r.provider()
    r.add("groq.example", {"text": "Привет, как дела"})
    text = await p.transcribe_voice(b"audio-bytes", "voice.ogg")
    assert text == "Привет, как дела"
    assert r.requests[-1].url.path.endswith("/audio/transcriptions")


@pytest.mark.asyncio
async def test_vision_success():
    r = Router()
    p = r.provider()
    r.add("groq.example", {"choices": [{"message": {"content": "Текст с фото"}}]})
    text = await p.extract_text_from_image(b"img")
    assert text == "Текст с фото"
