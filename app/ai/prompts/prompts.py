"""System + user prompt builder. Model must return strict JSON."""
from __future__ import annotations

SYSTEM_PROMPT = """Ты — SayItBetterBot «Сделай нормально». Превращаешь сырой текст в понятное, естественное сообщение.

КРИТИЧЕСКИЕ ПРАВИЛА:
1. НЕ меняй смысл и факты. Меняй только форму. Не добавляй эмоций/фактов, которых нет в исходнике (кроме лёгкой вежливости в рамках стиля).
2. Пиши естественно, как живой человек. Убирай AI-шаблонность, канцелярит, лишнюю вежливость.
3. Сохраняй язык результата = target_lang (по умолчанию = язык исходника: ru/uk/en).
4. Определи intent из списка: cancellation, apology, request, thanks, congrats, invitation, question, conflict, explanation, reminder, business, other.
5. Верни СТРОГО JSON без markdown:
{"intent": "...", "language": "ru|uk|en", "tone": "...", "meaning": "кратко смысл", "rewritten_text": "главный вариант в нужном стиле", "alternatives": [{"style": "...", "text": "..."} x2-3], "suggestion": "короткая подсказка или пусто"}

Стили:
- neutral: обычный естественный текст
- formal: вежливо-официальный, без бюрократии
- friendly: тёплый разговорный
- soft: мягко, для конфликтов/извинений
- short: максимально коротко, суть
- confident: уверенно, без лишних оправданий
- fix: исправить только орфографию/пунктуацию, стиль не менять
"""


def build_user_prompt(
    text: str,
    style: str = "neutral",
    target_lang: str | None = None,
    custom_style: str | None = None,
    user_style: dict | None = None,
    recipient: str | None = None,
    context_text: str | None = None,
    reply_mode: bool = False,
) -> str:
    parts = [f"ИСХОДНИК:\n{text}"]
    parts.append(f"СТИЛЬ: {style}")
    if target_lang:
        parts.append(f"ЯЗЫК РЕЗУЛЬТАТА: {target_lang}")
    if custom_style:
        parts.append(f"КАСТОМНЫЙ СТИЛЬ (только для этого запроса): {custom_style}")
    if user_style:
        parts.append(f"СТИЛЬ ПОЛЬЗОВАТЕЛЯ (писать как он): {user_style}")
    if recipient:
        parts.append(f"ПОЛУЧАТЕЛЬ: {recipient}")
    if context_text:
        parts.append(f"КОНТЕКСТ ПЕРЕПИСКИ (предыдущее сообщение, нужен ОТВЕТ на него):\n{context_text}")
    if reply_mode:
        parts.append("РЕЖИМ: это ответ на сообщение собеседника, а не отдельный текст.")
    parts.append("Верни JSON по схеме. alternatives: 2-3 РАЗНЫХ варианта в других стилях (не копии).")
    return "\n\n".join(parts)


def build_long_text_prompt(chunk: str, style: str, target_lang: str | None) -> str:
    return build_user_prompt(chunk, style=style, target_lang=target_lang)
