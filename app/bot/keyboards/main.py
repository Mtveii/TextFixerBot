"""Inline keyboards."""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.services.styles.service import STYLE_ORDER, STYLES


def style_choice_kb() -> InlineKeyboardMarkup:
    """6 базовых стилей в 2 колонки + свой стиль (вместо 7 рядов по одной кнопке)."""
    pair = []
    for code in STYLE_ORDER:
        s = STYLES[code]
        pair.append(InlineKeyboardButton(text=f"{s['emoji']} {s['title']}", callback_data=f"style:{code}"))
    rows = [pair[i : i + 2] for i in range(0, len(pair), 2)]
    rows.append([InlineKeyboardButton(text="➕ Свой стиль", callback_data="style:custom")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def result_actions_kb(
    request_id: int = 0,
    intent: str | None = None,
    expanded: bool = False,
    variants: int = 1,
) -> InlineKeyboardMarkup:
    """Карточка результата. Основные действия сразу, остальное — за «➕ Ещё…».

    expanded=True раскрывает дополнительные кнопки (кнопка становится «➖ Меньше»).
    variants>=2 — копирование по номерам вариантов (📋 1️⃣ / 2️⃣ / 3️⃣) + ⭐1/⭐2/⭐3 в expanded.
    intent-подсказки («➕ Другая дата» при отмене) рендерятся в карточку напрямую.
    """
    if variants >= 2:
        copy_row = [
            InlineKeyboardButton(text=f"📋 {n}", callback_data=f"copy:{request_id}:{i}")
            for i, n in enumerate(("1️⃣", "2️⃣", "3️⃣"))
            if i < variants
        ]
    else:
        copy_row = [InlineKeyboardButton(text="📋 Скопировать", callback_data=f"copy:{request_id}:0")]
    rows = [
        copy_row + [InlineKeyboardButton(text="🔄 Другой вариант", callback_data=f"another:{request_id}")],
        [
            InlineKeyboardButton(text="✂️ Короче", callback_data=f"quick:shorter:{request_id}"),
            InlineKeyboardButton(text="❤️ Мягче", callback_data=f"quick:softer:{request_id}"),
            InlineKeyboardButton(text="💼 Офиц.", callback_data=f"quick:formal_more:{request_id}"),
        ],
        [
            InlineKeyboardButton(text="🎭 Стиль", callback_data=f"restyle:{request_id}"),
            InlineKeyboardButton(
                text="➖ Меньше" if expanded else "➕ Ещё…",
                callback_data=f"{'less' if expanded else 'more'}:{request_id}",
            ),
        ],
    ]
    if expanded:
        if variants >= 2:
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"⭐ {i + 1}", callback_data=f"fav:{request_id}:{i}"
                    )
                    for i in range(min(variants, 3))
                ]
            )
        else:
            rows.append(
                [InlineKeyboardButton(text="⭐ Сохранить", callback_data=f"fav:{request_id}:0")]
            )
        rows.append(
            [
                InlineKeyboardButton(text="🔤 Исправить ошибки", callback_data=f"quick:fix:{request_id}"),
                InlineKeyboardButton(text="💬 Ответить", callback_data=f"reply:{request_id}"),
                InlineKeyboardButton(text="🌐 Перевести", callback_data=f"translate:{request_id}"),
            ]
        )
    if intent == "cancellation":
        rows.append([InlineKeyboardButton(text="➕ Другая дата", callback_data="smart:reschedule")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def recipient_kb() -> InlineKeyboardMarkup:
    items = [
        ("👥 Друг", "Друг"),
        ("❤️ Партнёр", "Партнёр"),
        ("👨‍👩‍👦 Родители", "Родители"),
        ("👨‍🏫 Преподаватель", "Преподаватель"),
        ("💼 Работодатель", "Работодатель"),
        ("🏢 Клиент", "Клиент"),
    ]
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=t, callback_data=f"recipient:{v}")] for t, v in items]
    )


def language_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang:ru"),
                InlineKeyboardButton(text="🇺🇦 Українська", callback_data="lang:uk"),
                InlineKeyboardButton(text="🇬🇧 English", callback_data="lang:en"),
            ]
        ]
    )


def history_item_kb(req_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔄 Использовать снова", callback_data=f"reuse:{req_id}"),
            ]
        ]
    )


def history_list_kb(
    items: list,
    total: int,
    page: int = 0,
    page_size: int = 5,
) -> InlineKeyboardMarkup:
    """Пагинация истории: превью-кнопка (тост) + 🔁 reuse на каждом элементе."""
    rows: list[list[InlineKeyboardButton]] = []
    for r in items:
        preview = r.source_text[:30] + ("…" if len(r.source_text) > 30 else "")
        rows.append(
            [
                InlineKeyboardButton(text=preview, callback_data=f"histshow:{r.id}"),
                InlineKeyboardButton(text="🔁", callback_data=f"reuse:{r.id}"),
            ]
        )
    pages = max(1, (total + page_size - 1) // page_size)
    if pages > 1:
        nav: list[InlineKeyboardButton] = []
        if page > 0:
            nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"hist:{page - 1}"))
        nav.append(InlineKeyboardButton(text=f"📄 {page + 1}/{pages}", callback_data="hist:noop"))
        if page < pages - 1:
            nav.append(InlineKeyboardButton(text="➡️", callback_data=f"hist:{page + 1}"))
        rows.append(nav)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def favorites_kb(favs: list) -> InlineKeyboardMarkup:
    """Избранное: кнопка-превью (тост с полным текстом) + ⛔ удаление inline."""
    rows: list[list[InlineKeyboardButton]] = []
    for f in favs:
        preview = f.text[:44] + ("…" if len(f.text) > 44 else "")
        rows.append(
            [
                InlineKeyboardButton(text=f"⭐ {preview}", callback_data=f"favshow:{f.id}"),
                InlineKeyboardButton(text="⛔", callback_data=f"delfavcb:{f.id}"),
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)
