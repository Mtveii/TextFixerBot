"""Formatting helpers: result cards, copy-safe messages."""
from __future__ import annotations

import html

from app.services.styles.service import style_label


def format_result(style: str, text: str, index: int = 0) -> str:
    label = style_label(style)
    return f"{html.escape(label)}:\n“{html.escape(text)}”"


VARIANT_NUMS = ("1️⃣", "2️⃣", "3️⃣")


def format_multi(main_style: str, main_text: str, alternatives: list[dict]) -> str:
    variants = [(main_style, main_text)]
    variants += [(a.get("style", "neutral"), a.get("text", "")) for a in alternatives[:2]]
    blocks = []
    for i, (style, text) in enumerate(variants):
        num = VARIANT_NUMS[i] if i < len(VARIANT_NUMS) else f"{i + 1}."
        blocks.append(f"{num} <b>{html.escape(style_label(style))}</b>:\n“{html.escape(text)}”")
    return "\n".join(blocks)


def copyable_text(text: str) -> str:
    # <pre> is monospace + tap-to-copy in Telegram clients.
    # HTML escaping keeps arbitrary text (backticks, quotes) from breaking parsing.
    return f"<pre>{html.escape(text)}</pre>"
