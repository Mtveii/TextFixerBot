"""High-level rewrite orchestration: long-text chunking, validation."""
from __future__ import annotations

from app.services.styles.service import detect_intent_hint, detect_language

MAX_SINGLE_CHARS = 3000
CHUNK_SIZE = 2500


def split_long_text(text: str, chunk_size: int = CHUNK_SIZE) -> list[str]:
    if len(text) <= MAX_SINGLE_CHARS:
        return [text]
    # split by sentences, keep coherence
    import re

    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks, cur = [], ""
    for s in sentences:
        if len(cur) + len(s) + 1 <= chunk_size:
            cur = (cur + " " + s).strip()
        else:
            if cur:
                chunks.append(cur)
            if len(s) > chunk_size:  # hard cut very long sentence
                for i in range(0, len(s), chunk_size):
                    chunks.append(s[i : i + chunk_size])
                cur = ""
            else:
                cur = s
    if cur:
        chunks.append(cur)
    return chunks or [text]


async def rewrite_text(
    provider,
    text: str,
    style: str = "neutral",
    target_lang: str | None = None,
    custom_style: str | None = None,
    user_style: dict | None = None,
    recipient: str | None = None,
    context_text: str | None = None,
    reply_mode: bool = False,
) -> dict:
    lang = detect_language(text)
    intent_hint = detect_intent_hint(text)
    chunks = split_long_text(text)
    if len(chunks) == 1:
        result = await provider.rewrite(
            text, style, target_lang, custom_style, user_style, recipient, context_text, reply_mode
        )
    else:
        parts = []
        last: dict = {}
        for ch in chunks:
            r = await provider.rewrite(ch, style, target_lang, custom_style, user_style, recipient, None, False)
            parts.append(r.get("rewritten_text", ""))
            last = r
        result = dict(last)
        result["rewritten_text"] = "\n\n".join(parts)
        result["alternatives"] = []
    result.setdefault("language", lang)
    if result.get("intent") in (None, "", "other") and intent_hint != "other":
        result["intent"] = intent_hint
    return result
