"""UX-полировка: компактные клавиатуры, результатная карточка (edit вместо новых сообщений),
typing-фидбек."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ---------- keyboards ----------

def test_style_kb_two_columns():
    from app.bot.keyboards.main import style_choice_kb

    kb = style_choice_kb()
    buttons = [b for row in kb.inline_keyboard for b in row]
    assert len(buttons) == 7  # 6 стилей + свой стиль
    assert len(kb.inline_keyboard) == 4  # 3 ряда × 2 + ряд «Свой стиль»
    assert all(b.callback_data.startswith("style:") for b in buttons)


def test_result_kb_collapsed_hides_advanced():
    from app.bot.keyboards.main import result_actions_kb

    kb = result_actions_kb(5)
    data = {b.callback_data for row in kb.inline_keyboard for b in row}
    assert "copy:5:0" in data and "another:5" in data
    # выезжающие кнопки спрятаны за «Ещё…»
    assert "quick:fix:5" not in data and "reply:5" not in data and "translate:5" not in data
    assert any(b.callback_data == "more:5" and b.text == "➕ Ещё…" for row in kb.inline_keyboard for b in row)


def test_result_kb_expanded_shows_advanced():
    from app.bot.keyboards.main import result_actions_kb

    kb = result_actions_kb(5, expanded=True)
    data = {b.callback_data for row in kb.inline_keyboard for b in row}
    assert {"quick:fix:5", "reply:5", "translate:5"} <= data
    assert any(b.callback_data == "less:5" and b.text == "➖ Меньше" for row in kb.inline_keyboard for b in row)


def test_result_kb_cancellation_smart_row():
    from app.bot.keyboards.main import result_actions_kb

    kb = result_actions_kb(1, intent="cancellation")
    assert any(b.callback_data == "smart:reschedule" for row in kb.inline_keyboard for b in row)
    # без intent — строки нет
    kb2 = result_actions_kb(1, intent="other")
    assert not any(b.callback_data == "smart:reschedule" for row in kb2.inline_keyboard for b in row)


# ---------- _do_rewrite: результат редактирует карточку ----------


class FakeEditMessage:
    def __init__(self):
        self.edits = []

    async def edit_text(self, text, parse_mode=None, reply_markup=None):
        self.edits.append({"text": text, "parse_mode": parse_mode, "reply_markup": reply_markup})
        return self


def _fake_edit():
    return FakeEditMessage()


@pytest.mark.asyncio
async def test_do_rewrite_edits_card_instead_of_new_message(tmp_path, monkeypatch):
    import app.bot.state as bot_state
    from app.ai.provider import LLMProvider
    from app.core.db import Base, init_db

    engine = init_db(f"sqlite+aiosqlite:///{tmp_path}/ux.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    bot_state.PROVIDER = LLMProvider()  # offline fallback (без ключей)
    bot_state.BOT = None  # typing отключён в тесте
    from app.bot.state import PENDING

    PENDING[4242] = {"text": "привет я завтра не приду"}

    edit_target = _fake_edit()
    from app.bot.handlers.rewrite import _do_rewrite

    req_id, main_text = await _do_rewrite(None, 4242, style="short", edit_message=edit_target)
    assert req_id >= 1
    assert main_text
    assert len(edit_target.edits) == 1  # ровно одна карточка, без доп. сообщений
    card = edit_target.edits[0]
    assert card["parse_mode"] == "HTML"
    assert card["reply_markup"] is not None
    # карточка содержит результат
    assert main_text.split("\n")[0][:40] in card["text"]
    # PENDING обновлён для copy/fav
    assert PENDING[4242]["last_texts"] and PENDING[4242]["last_request_id"] == req_id


@pytest.mark.asyncio
async def test_do_rewrite_limit_warn_edits_card(tmp_path, monkeypatch):
    from types import SimpleNamespace

    import app.bot.state as bot_state
    from app.ai.provider import LLMProvider
    from app.bot.state import PENDING
    from app.core.db import Base, init_db

    engine = init_db(f"sqlite+aiosqlite:///{tmp_path}/ux2.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    bot_state.PROVIDER = LLMProvider()
    bot_state.BOT = None
    s = SimpleNamespace(free_daily_limit=0, premium_daily_limit=0)
    monkeypatch.setattr("app.core.rate_limit.get_settings", lambda: s)

    PENDING[5555] = {"text": "привет"}
    edit_target = _fake_edit()
    from app.bot.handlers.rewrite import _do_rewrite

    req_id, main_text = await _do_rewrite(None, 5555, style="short", edit_message=edit_target)
    assert req_id is None and main_text == ""
    assert len(edit_target.edits) == 1
    assert "Лимит" in edit_target.edits[0]["text"]
    assert edit_target.edits[0]["reply_markup"] is None  # предупреждение без кнопок


@pytest.mark.asyncio
async def test_do_rewrite_stale_session_warn(tmp_path):
    import app.bot.state as bot_state
    from app.ai.provider import LLMProvider
    from app.bot.state import PENDING
    from app.core.db import Base, init_db

    engine = init_db(f"sqlite+aiosqlite:///{tmp_path}/ux3.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    bot_state.PROVIDER = LLMProvider()
    bot_state.BOT = None
    PENDING.pop(777, None)
    edit_target = _fake_edit()
    from app.bot.handlers.rewrite import _do_rewrite

    req_id, main_text = await _do_rewrite(None, 777, style="short", edit_message=edit_target)
    assert req_id is None
    assert "устарела" in edit_target.edits[0]["text"]


@pytest.mark.asyncio
async def test_typing_indicator_keeps_running(tmp_path):
    """_keep_typing шлёт chat_action повторно и отменяется без сюрпризов."""
    from app.bot.handlers.rewrite import _keep_typing

    calls = []

    class FakeBot:
        async def send_chat_action(self, chat_id, action):
            calls.append((chat_id, action))

    task = asyncio.create_task(_keep_typing(FakeBot(), 1))
    await asyncio.sleep(0.1)
    assert len(calls) >= 1
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
