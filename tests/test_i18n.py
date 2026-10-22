"""i18n completeness: same key set across ru/uk/en + style_label translations."""
from __future__ import annotations

from aiogram.types import User

from app.i18n import STRINGS, lang_of, t
from app.services.styles.service import STYLE_ORDER, style_label


def test_all_keys_have_all_langs():
    langs = {"ru", "uk", "en"}
    for key, val in STRINGS.items():
        assert langs <= set(val), f"key {key} missing langs: {langs - set(val)}"


def test_t_fallback_to_ru():
    assert t("nonexistent_key", "en") == "nonexistent_key"
    # временный ключ с одним языком — t() фолбэчится на ru (работаем на копии словаря)
    import app.i18n as m

    backup = dict(m.STRINGS)
    try:
        m.STRINGS.clear()
        m.STRINGS.update(backup)
        m.STRINGS["tmp"] = {"ru": "только рус"}
        assert m.t("tmp", "uk") == "только рус"
    finally:
        m.STRINGS.clear()
        m.STRINGS.update(backup)


def test_lang_of_detects_codes():
    assert lang_of(None) == "ru"
    assert lang_of(User(id=1, is_bot=False, first_name="x", language_code="uk")) == "uk"
    assert lang_of(User(id=1, is_bot=False, first_name="x", language_code="en-US")) == "en"
    assert lang_of(User(id=1, is_bot=False, first_name="x", language_code="de")) == "ru"


def test_style_label_translations():
    assert style_label("formal") == "💼 Официально"
    assert style_label("formal", lang="uk") == "💼 Офіційно"
    assert style_label("formal", lang="en") == "💼 Formal"
    for code in STYLE_ORDER:
        for lang in ("ru", "uk", "en"):
            assert style_label(code, lang=lang)
