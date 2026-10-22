"""Style catalogue: 6 core styles + extra actions."""
from __future__ import annotations

STYLES: dict[str, dict] = {
    "neutral": {
        "emoji": "🟢",
        "title": "Нормально", "titles": {"uk": "Нормально", "en": "Normal"},
        "instruction": "Обычный естественный текст. Не слишком официальный и не слишком эмоциональный.",
    },
    "formal": {
        "emoji": "💼",
        "title": "Официально", "titles": {"uk": "Офіційно", "en": "Formal"},
        "instruction": "Вежливый официальный тон для преподавателя, работодателя, клиента. Без лишней бюрократии и канцелярита.",
    },
    "friendly": {
        "emoji": "🙂",
        "title": "Дружелюбно", "titles": {"uk": "Дружньо", "en": "Friendly"},
        "instruction": "Тёплая естественная разговорная речь, как другу. Можно лёгкие эмодзи если уместно.",
    },
    "soft": {
        "emoji": "❤️",
        "title": "Мягко", "titles": {"uk": "М'яко", "en": "Gentle"},
        "instruction": "Максимально мягко: для конфликтов, извинений, неприятных новостей. Убрать резкость, сохранить смысл и честность.",
    },
    "short": {
        "emoji": "⚡",
        "title": "Коротко", "titles": {"uk": "Коротко", "en": "Concise"},
        "instruction": "Максимально сжать, оставив только суть. Убрать воду и повторы.",
    },
    "confident": {
        "emoji": "🔥",
        "title": "Уверенно", "titles": {"uk": "Впевнено", "en": "Confident"},
        "instruction": "Уверенно и прямо: убрать лишние оправдания, неуверенные формулировки и чрезмерные извинения, сохранив вежливость.",
    },
}

EXTRA_ACTIONS: dict[str, dict] = {
    "fix": {"emoji": "🔤", "title": "Исправить ошибки", "titles": {"uk": "Виправити помилки", "en": "Fix typos"}, "instruction": "Исправь ТОЛЬКО орфографию и пунктуацию. Не меняй стиль, слова и тон."},
    "softer": {"emoji": "❤️", "title": "Сделать мягче", "titles": {"uk": "Зробити м'якше", "en": "Softer"}, "instruction": "Перепиши мягче, убери резкость."},
    "shorter": {"emoji": "✂️", "title": "Сделать короче", "titles": {"uk": "Зробити коротше", "en": "Shorter"}, "instruction": "Сократи текст минимум в 2 раза, сохранив смысл."},
    "formal_more": {"emoji": "💼", "title": "Официальнее", "titles": {"uk": "Офіційніше", "en": "More formal"}, "instruction": "Сделай заметно официальнее."},
    "expand": {"emoji": "📝", "title": "Расширить", "titles": {"uk": "Розширити", "en": "Expand"}, "instruction": "Сделай текст чуть подробнее и теплее, НЕ добавляя новых фактов."},
    "natural": {"emoji": "🌿", "title": "Естественно", "titles": {"uk": "Природно", "en": "Natural"}, "instruction": "Убери AI-шаблонность: канцелярит, 'я надеюсь, данное сообщение', лишнюю вежливость, повторы."},
    "firm": {"emoji": "🧱", "title": "Жёстко, но нормально", "titles": {"uk": "Твердо, але нормально", "en": "Firm but fair"}, "instruction": "Твёрдо обозначь границу, без оскорблений и угроз."},
    "no_apologies": {"emoji": "🚫", "title": "Без лишних извинений", "titles": {"uk": "Без зайвих вибачень", "en": "No over-apologies"}, "instruction": "Убери чрезмерные оправдания, оставь спокойную вежливость."},
}

STYLE_ORDER = ["neutral", "formal", "friendly", "soft", "short", "confident"]

LANG_NAMES = {"ru": "русский", "uk": "українська", "en": "English"}


def style_label(code: str, lang: str = "ru") -> str:
    s = STYLES.get(code) or EXTRA_ACTIONS.get(code) or {}
    title = s.get("title", code)
    if lang in ("uk", "en") and s.get("titles"):
        title = s["titles"].get(lang, title)
    return f"{s.get('emoji', '')} {title}".strip()


def detect_language(text: str) -> str:
    """Fast heuristic language detection: uk / en / ru."""
    t = text.lower()
    if any(ch in t for ch in "іїєґ"):
        return "uk"
    latin = sum(1 for ch in t if "a" <= ch <= "z")
    cyr = sum(1 for ch in t if "а" <= ch <= "я" or ch in "ёіїєґ")
    if latin > cyr and latin > 3:
        return "en"
    return "ru"


def detect_intent_hint(text: str) -> str:
    t = text.lower()
    if any(w in t for w in ["извини", "прости", "сорян", "вибач", "sorry"]):
        return "apology"
    if any(w in t for w in ["не смогу", "не приду", "не получится", "перенес", "отмен", "не зможу"]):
        return "cancellation"
    if any(w in t for w in ["спасибо", "дякую", "благодарю", "thanks", "thank"]):
        return "thanks"
    if any(w in t for w in ["поздрав", "с днём", "с днем", "вітаю", "happy birthday"]):
        return "congrats"
    if any(w in t for w in ["пожалуйста", "прошу", "помоги", "можешь", "будь ласка", "please"]):
        return "request"
    if any(w in t for w in ["приглашаю", "приходи", "ждём", "ждем"]):
        return "invitation"
    if text.strip().endswith("?"):
        return "question"
    return "other"


INTENT_SUGGESTIONS = {
    "cancellation": "Похоже, это отказ/перенос встречи. Могу добавить причину или предложить другую дату.",
    "apology": "Похоже, это извинение. Могу сделать мягче.",
    "request": "Похоже, это просьба. Могу сделать вежливее или короче.",
    "thanks": "Похоже, это благодарность. Могу сделать теплее.",
    "congrats": "Похоже, это поздравление. Могу сделать торжественнее.",
}
