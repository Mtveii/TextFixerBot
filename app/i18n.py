"""UI-строки на ru/uk/en + определение языка пользователя.

Инструкции для LLM остаются на русском (это промпты качества), переводится
только интерфейс: кнопки, ответы, меню. detect_ui_lang смотрит language_code
клиента (ru/uk/en), по умолчанию ru.
"""
from __future__ import annotations

from aiogram.types import User

STRINGS: dict[str, dict[str, str]] = {
    "welcome": {
        "ru": "Привет! Я перепишу твоё сообщение в нужный тоне.\nПришли текст — предложу варианты.",
        "uk": "Привіт! Я перепишу твоє повідомлення в потрібному тоні.\nНадішли текст — запропоную варіанти.",
        "en": "Hi! I'll rewrite your message in the tone you need.\nSend me a text — I'll offer variants.",
    },
    "hint_send_text": {
        "ru": "Пришли любой текст или голосовую 🎙️",
        "uk": "Надішли будь-який текст або голосове 🎙️",
        "en": "Send any text or a voice message 🎙️",
    },
    "which_variant": {
        "ru": "Понял. Какой вариант сделать?",
        "uk": "Зрозумів. Який варіант зробити?",
        "en": "Got it. Which variant should I make?",
    },
    "choose_tone_reply": {
        "ru": "🤔 Похоже, нужно придумать ответ. Какой тон выбрать?",
        "uk": "🤔 Схоже, треба вигадати відповідь. Який тон обрати?",
        "en": "🤔 Looks like you need a reply. Which tone?",
    },
    "short_text": {
        "ru": "Напиши чуть подробнее — хоть пару слов.",
        "uk": "Напиши трошки детальніше — хоч пару слів.",
        "en": "Write a bit more — at least a couple of words.",
    },
    "generating": {
        "ru": "Генерирую…",
        "uk": "Генерую…",
        "en": "Generating…",
    },
    "another": {
        "ru": "Другой вариант",
        "uk": "Інший варіант",
        "en": "Other variant",
    },
    "copy": {"ru": "📋 Скопировать", "uk": "📋 Скопіювати", "en": "📋 Copy"},
    "copy_n": {  # с номером варианта
        "ru": "📋 {n}",
        "uk": "📋 {n}",
        "en": "📋 {n}",
    },
    "restyle": {"ru": "🎭 Стиль", "uk": "🎭 Стиль", "en": "🎭 Style"},
    "restyle_menu": {
        "ru": "Какой стиль поставить?",
        "uk": "Який стиль обрати?",
        "en": "Which style should I apply?",
    },
    "custom_style_prompt": {
        "ru": "Опиши свой стиль одним сообщением. Например: «как другу, но без мата, с юмором».\n(/cancel — отмена)",
        "uk": "Опиши свій стиль одним повідомленням. Наприклад: «як другові, але без мату, з гумором».\n(/cancel — скасувати)",
        "en": "Describe your custom style in one message, e.g. \"like to a friend, no swearing, with humor\".\n(/cancel to cancel)",
    },
    "more": {"ru": "➕ Ещё…", "uk": "➕ Більше…", "en": "➕ More…"},
    "less": {"ru": "➖ Меньше", "uk": "➖ Менше", "en": "➖ Less"},
    "copied_toast": {
        "ru": "Отправил чистый текст — его удобно копировать 👆",
        "uk": "Надіслав чистий текст — зручно копіювати 👆",
        "en": "Sent a clean copyable text 👆",
    },
    "nothing_to_copy": {
        "ru": "Не нашёл текст для копирования.",
        "uk": "Не знайшов текст для копіювання.",
        "en": "Couldn't find text to copy.",
    },
    "bad_data": {
        "ru": "Некорректные данные",
        "uk": "Некоректні дані",
        "en": "Invalid data",
    },
    "not_found": {"ru": "Не найдено", "uk": "Не знайдено", "en": "Not found"},
    "nothing_to_save": {
        "ru": "Нечего сохранять",
        "uk": "Нема чого зберігати",
        "en": "Nothing to save",
    },
    "saved": {"ru": "Сохранил ⭐", "uk": "Зберіг ⭐", "en": "Saved ⭐"},
    "limit_reached": {
        "ru": "⏳ Лимит на сегодня исчерпан ({used}/{limit}). Free — {limit} в день. Возвращайся завтра!\n💎 Premium — без дневного лимита: /premium",
        "uk": "⏳ Денний ліміт вичерпано ({used}/{limit}). Free — {limit} на день. Повертайся завтра!\n💎 Premium — без денного ліміту: /premium",
        "en": "⏳ Daily limit reached ({used}/{limit}). Free is {limit}/day. Come back tomorrow!\n💎 Premium — no daily limit: /premium",
    },
    "premium_active": {
        "ru": "💎 У тебя уже Premium — до <b>500</b> генераций в день.",
        "uk": "💎 У тебе вже Premium — до <b>500</b> генерацій на день.",
        "en": "💎 You already have Premium — up to <b>500</b> generations/day.",
    },
    "premium_invoice_title": {
        "ru": "Сделай нормально — Premium",
        "uk": "Зроби нормально — Premium",
        "en": "Do it properly — Premium",
    },
    "premium_invoice_description": {
        "ru": "500 генераций в день (вместо 20). Приоритетные бэкенды и весь текущий функционал.",
        "uk": "500 генерацій на день (замість 20). Пріоритетні бекенди та весь поточний функціонал.",
        "en": "500 generations/day (instead of 20). Priority backends and all features.",
    },
    "premium_activated": {
        "ru": "💎 Premium активирован — 500 генераций в день. Спасибо за поддержку!",
        "uk": "💎 Premium активовано — 500 генерацій на день. Дякую за підтримку!",
        "en": "💎 Premium activated — 500 generations/day. Thanks for your support!",
    },
    "premium_failed": {
        "ru": "Получил платёж, но не смог привязать Premium. Напиши /report — разберёмся.",
        "uk": "Платіж отримано, але Premium не прив'язано. Напиши /report — розберемось.",
        "en": "Payment received, but Premium wasn't linked. Send /report and we'll fix it.",
    },
    "invoice_error": {
        "ru": "Оплата временно недоступна. Попробуй позже.",
        "uk": "Оплата тимчасово недоступна. Спробуй пізніше.",
        "en": "Payments are temporarily unavailable. Try later.",
    },
    "premium_cmd": {
        "ru": "💎 Premium",
        "uk": "💎 Premium",
        "en": "💎 Premium",
    },
    "voice_need_llm": {
        "ru": "🎙️ Голосовые требуют настроенный LLM (GROQ_API_KEY). Пока отправь текстом 👇",
        "uk": "🎙️ Голосові потребують налаштований LLM (GROQ_API_KEY). Поки надішли текстом 👇",
        "en": "🎙️ Voice needs a configured LLM (GROQ_API_KEY). Send text for now 👇",
    },
    "file_too_big": {
        "ru": "Файл слишком большой (лимит 20MB). Отправь покороче.",
        "uk": "Файл надто великий (ліміт 20MB). Надішли коротший.",
        "en": "File too big (20MB limit). Send a shorter one.",
    },
    "file_too_long": {
        "ru": "Голосовое слишком длинное (лимит 10 минут). Отправь покороче.",
        "uk": "Голосове надто довге (ліміт 10 хвилин). Надішли коротше.",
        "en": "Voice too long (10 min limit). Send a shorter one.",
    },
    "recognized": {
        "ru": "Распознал:\n“{text}”",
        "uk": "Розпізнав:\n“{text}”",
        "en": "Recognized:\n“{text}”",
    },
    "stt_failed": {
        "ru": "Не смог распознать голосовое. Отправь текстом 🙏",
        "uk": "Не вдалося розпізнати голосове. Надішли текстом 🙏",
        "en": "Couldn't transcribe the voice message. Send text 🙏",
    },
    "no_text_in_photo": {
        "ru": "На фото не нашёл текста. Пришли чёткий скрин 👇",
        "uk": "На фото не знайшов тексту. Надішли чіткий скріншот 👇",
        "en": "No text found in the photo. Send a clear screenshot.",
    },
    "found_text": {
        "ru": "📸 Распознал с фото, вот текст:\n“{text}”",
        "uk": "📸 Розпізнав з фото, ось текст:\n“{text}”",
        "en": "📸 Extracted from the photo:\n“{text}”",
    },
    "history_empty": {
        "ru": "📚 История пуста. Отправь мне любой текст!",
        "uk": "📚 Історія порожня. Надішли будь-який!",
        "en": "📚 History is empty. Send me any text!",
    },
    "history_title": {
        "ru": "📚 <b>История</b> — тапни текст для просмотра, 🔁 чтобы использовать снова:",
        "uk": "📚 <b>Історія</b> — натисни на текст для перегляду, 🔁 щоб повторити:",
        "en": "📚 <b>History</b> — tap a text to preview, 🔁 to reuse:",
    },
    "favorites_empty": {
        "ru": "⭐ Избранного пока нет. Нажми «⭐ Сохранить» под результатом.",
        "uk": "⭐ Зашлюблених нема. Тисни «⭐ Сохранить» під результатом.",
        "en": "⭐ No favorites yet. Tap \"⭐ Save\" under a result.",
    },
    "favorites_title": {
        "ru": "⭐ <b>Избранное</b> — тапни для просмотра, ⛔ чтобы удалить:",
        "uk": "⭐ <b>Зашлюблене</b> — натисни для перегляду, ⛔ щоб видалити:",
        "en": "⭐ <b>Favorites</b> — tap to preview, ⛔ to remove:",
    },
    "deleted": {"ru": "Удалил ⭐", "uk": "Видалив ⭐", "en": "Removed ⭐"},
    "cancel_mode": {
        "ru": "↪️ Режим отменён. Просто напиши текст — я сработаю как обычно.",
        "uk": "↪️ Режим скасовано. Просто надішли текст — працюватиму як завжди.",
        "en": "↪️ Mode cancelled. Just send text — I'll work as usual.",
    },
    "cancel_hint": {
        "ru": "(/cancel — отмена)",
        "uk": "(/cancel — скасувати)",
        "en": "(/cancel to cancel)",
    },
    "lang_set": {
        "ru": "🌐 Язык интерфейса: Русский",
        "uk": "🌐 Мова інтерфейсу: Українська",
        "en": "🌐 UI language: English",
    },
    "translate_to": {
        "ru": "Перевести на какой язык?",
        "uk": "Перекласти якою мовою?",
        "en": "Translate into which language?",
    },
    "who_for": {
        "ru": "Кому пишешь?",
        "uk": "Кому пишеш?",
        "en": "Who are you writing to?",
    },
}


def lang_of(user: User | None) -> str:
    if user is None:
        return "ru"
    code = (user.language_code or "")[:2]
    return code if code in STRINGS.get("welcome", {}) else "ru"
    # NB: все ключи имеют одинаковый набор языков, поэтому проверка по welcome ок


def t(key: str, lang: str = "ru", **fmt) -> str:
    return STRINGS.get(key, {}).get(lang) or STRINGS.get(key, {}).get("ru", key)


def fmt(key: str, lang: str = "ru", **kwargs) -> str:
    return t(key, lang).format(**kwargs)
