from types import SimpleNamespace

import pytest

from app.ai.provider import LLMProvider, _extract_json
from app.services.rewrite.service import split_long_text
from app.services.styles.service import detect_intent_hint, detect_language, style_label


def test_detect_language_ru():
    assert detect_language("привет я сегодня не смогу прийти") == "ru"


def test_detect_language_uk():
    assert detect_language("привіт, я завтра не зможу прийти") == "uk"


def test_detect_language_en():
    assert detect_language("hey bro what's up, can you help me please") == "en"


def test_intent_cancellation():
    assert detect_intent_hint("я завтра не смогу прийти, дела") == "cancellation"


def test_split_short():
    assert split_long_text("короткий текст") == ["короткий текст"]


def test_split_long():
    long = ("Это предложение номер один. " * 300)
    chunks = split_long_text(long)
    assert len(chunks) > 1
    assert all(len(c) <= 3000 for c in chunks)


def test_provider_normalize():
    p = LLMProvider(api_key="", base_url="https://api.openai.com/v1", model="gpt-4o-mini")
    out = p._normalize({"rewritten_text": "Привет!", "alternatives": [{"style": "soft", "text": "Hi"}]}, "neutral")
    assert out["rewritten_text"] == "Привет!"
    assert out["alternatives"][0]["style"] == "soft"


def test_style_label():
    assert "Нормально" in style_label("neutral")


def test_extract_json_plain():
    assert _extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_markdown():
    assert _extract_json('```json\n{"rewritten_text": "Hi"}\n```') == {"rewritten_text": "Hi"}


def test_extract_json_prose_fallback():
    out = _extract_json("just some text")
    assert out["rewritten_text"] == "just some text"


def _fake_settings(**kw):
    base = dict(
        groq_api_key="", groq_base_url="https://api.groq.com/openai/v1",
        groq_model="openai/gpt-oss-20b", groq_vision_model="qwen/qwen3.8-27b",
        groq_stt_model="whisper-large-v3-turbo",
        gemini_api_key="", gemini_base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        gemini_model="gemini-3.6-flash",
        openai_api_key="", openai_base_url="https://api.openai.com/v1",
        openai_model="gpt-4o-mini", openai_timeout=60,
        backend_order=["groq", "gemini", "openai"],
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_from_settings_order_groq_first():

    s = _fake_settings(groq_api_key="g1", gemini_api_key="g2", openai_api_key="o3")
    p = LLMProvider.from_settings(s)
    assert p.backend_names == ["groq", "gemini", "openai"]
    assert p.configured


def test_from_settings_skips_empty():
    s = _fake_settings(gemini_api_key="g2")
    p = LLMProvider.from_settings(s)
    assert p.backend_names == ["gemini"]


def test_gemini_has_alt_models():
    s = _fake_settings(gemini_api_key="g2")
    p = LLMProvider.from_settings(s)
    assert len(p.backends[0].alt_models) >= 3


@pytest.mark.asyncio
async def test_offline_fallback_no_keys():
    s = _fake_settings()
    p = LLMProvider.from_settings(s)
    assert not p.configured
    out = await p.rewrite("я завтра не смогу прийти", style="neutral")
    assert "смогу" in out["rewritten_text"] or "Смогу" in out["rewritten_text"]
