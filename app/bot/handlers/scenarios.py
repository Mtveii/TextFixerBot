"""Scenarios / templates / generators: situations, congrats, apology, request, decline."""
from __future__ import annotations

import html

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards.main import style_choice_kb
from app.bot.state import PENDING

router = Router()

CATEGORIES = [
    ("💼 Работа", "work"),
    ("🎓 Учёба", "study"),
    ("❤️ Отношения", "love"),
    ("👨‍👩‍👦 Семья", "family"),
    ("👥 Друзья", "friends"),
    ("📅 Встречи", "meetings"),
    ("🙏 Извинения", "apology"),
    ("🎉 Поздравления", "congrats"),
    ("❌ Отказ", "decline"),
]

TEMPLATES: dict[str, list[tuple[str, str]]] = {
    "decline": [
        ("Отказ от встречи", "Привет! К сожалению, завтра не смогу встретиться — появились дела. Давай перенесём на другой день?"),
        ("Отказ от вечеринки (мягко)", "Привет! Спасибо за приглашение, но в этот раз не смогу прийти. Хорошо тебе отдохнуть!"),
    ],
    "apology": [
        ("Короткое извинение", "Прости, я был(а) неправ(а). Понимаю, что задел(а) тебя, такого больше не повторится."),
    ],
    "work": [
        ("Перенос встречи", "Здравствуйте! К сожалению, завтра не смогу присутствовать из-за возникших обстоятельств. Предлагаю перенести встречу на другое удобное время."),
        ("Просьба о помощи", "Здравствуйте! Подскажите, пожалуйста, сможете ли помочь с этим вопросом, когда будет удобно?"),
    ],
    "congrats": [
        ("Другу с ДР", "С днём рождения! Желаю здоровья, удачи и чтобы всё задуманное получалось. Рад, что мы знакомы! 🎉"),
    ],
}


class GenStates(StatesGroup):
    waiting_scenario_text = State()


@router.message(Command("situations"))
async def situations(message: Message):
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=t, callback_data=f"cat:{c}")] for t, c in CATEGORIES]
    )
    await message.answer("📚 <b>Ситуации — выбери категорию:</b>", parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("cat:"))
async def on_cat(query: CallbackQuery):
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    try:
        cat = query.data.split(":")[1]
    except (IndexError, AttributeError, ValueError):
        try:
            await query.answer("Некорректные данные", show_alert=True)
        except Exception:
            pass
        return
    allowed_cats = {c for _, c in CATEGORIES}
    if cat not in allowed_cats:
        try:
            await query.answer("Неизвестная категория", show_alert=True)
        except Exception:
            pass
        return
    items = TEMPLATES.get(cat, [])
    if not items:
        await query.message.answer("В этой категории пока нет шаблонов. Просто отправь свой текст — сделаю нормально 👇")
    else:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text=t, callback_data=f"tpl:{cat}:{i}")] for i, (t, _) in enumerate(items)]
        )
        await query.message.answer("Выбери шаблон:", reply_markup=kb)
    try:
        await query.answer()
    except Exception:
        pass


@router.callback_query(F.data.startswith("tpl:"))
async def on_tpl(query: CallbackQuery):
    try:
        _, cat, idx = query.data.split(":")
        idx_int = int(idx)
    except (ValueError, AttributeError):
        try:
            await query.answer("Некорректные данные", show_alert=True)
        except Exception:
            pass
        return
    if cat not in TEMPLATES:
        try:
            await query.answer("Неизвестный шаблон", show_alert=True)
        except Exception:
            pass
        return
    try:
        title, text = TEMPLATES[cat][idx_int]
    except (IndexError, ValueError):
        try:
            await query.answer("Не найдено", show_alert=True)
        except Exception:
            pass
        return
    PENDING[query.from_user.id] = {"text": text}
    await query.message.answer(f"📄 Шаблон «{html.escape(title)}»:\n<i>{html.escape(text)}</i>\n\nМогу переписать под твой случай — выбери стиль:", parse_mode="HTML", reply_markup=style_choice_kb())
    try:
        await query.answer()
    except Exception:
        pass


@router.message(Command("decline"))
async def decline_cmd(message: Message, state: FSMContext):
    await state.set_state(GenStates.waiting_scenario_text)
    PENDING[message.from_user.id] = {"scenario": "decline"}
    await message.answer("❌ Что нужно отклонить? Напиши в двух словах. Например: «не хочу идти на вечеринку»\n(/cancel — отмена)")


@router.message(Command("congrats"))
async def congrats_cmd(message: Message, state: FSMContext):
    await state.set_state(GenStates.waiting_scenario_text)
    PENDING[message.from_user.id] = {"scenario": "congrats"}
    await message.answer("🎉 Кого поздравляем? Напиши, например: «поздравить друга с др, с юмором»\n(/cancel — отмена)")


@router.message(Command("apology"))
async def apology_cmd(message: Message, state: FSMContext):
    await state.set_state(GenStates.waiting_scenario_text)
    PENDING[message.from_user.id] = {"scenario": "apology"}
    await message.answer("🙏 Что произошло? Кратко опиши ситуацию — признаю ошибку без манипуляций.\n(/cancel — отмена)")


@router.message(Command("ask"))
async def ask_cmd(message: Message, state: FSMContext):
    await state.set_state(GenStates.waiting_scenario_text)
    PENDING[message.from_user.id] = {"scenario": "request"}
    await message.answer("🙌 О чём попросить? Например: «попросить друга помочь с проектом»\n(/cancel — отмена)")


@router.message(GenStates.waiting_scenario_text)
async def on_scenario_text(message: Message, state: FSMContext):
    scenario = PENDING.get(message.from_user.id, {}).get("scenario", "other")
    prefix = {
        "decline": "Помоги вежливо отказать. Ситуация: ",
        "congrats": "Напиши поздравление. Запрос: ",
        "apology": "Напиши искреннее извинение: признай конкретную ошибку, не перекладывай вину, не требуй прощения. Ситуация: ",
        "request": "Напиши вежливую просьбу. Ситуация: ",
    }.get(scenario, "")
    PENDING[message.from_user.id] = {"text": prefix + message.text}
    await state.clear()
    await message.answer("Понял ситуацию. Какой стиль?", reply_markup=style_choice_kb())


@router.message(Command("mystyle"))
async def mystyle(message: Message):
    from app.core.db import get_session_factory
    from app.database import repositories as repo

    factory = get_session_factory()
    async with factory() as session:
        user = await repo.get_or_create_user(session, message.from_user.id)
        p = user.style_profile or {}
    await message.answer(
        "🧬 <b>Мой стиль</b>\n\n"
        f"Текущий профиль: {p or 'не настроен'}\n\n"
        "Отправь 2–3 своих обычных сообщения одним текстом (каждое с новой строки), "
        "и я буду писать как ты. Команда: /setstyle",
        parse_mode="HTML",
    )


@router.message(Command("setstyle"))
async def setstyle(message: Message):
    await message.answer(
        "Пришли 2–3 своих сообщения одним текстом после команды.\n"
        "Пример:\n<code>/setstyle короче, завтра не приду\nок, давай потом\n😅 сорян, дела</code>",
        parse_mode="HTML",
    )


@router.message(F.text.startswith("/setstyle"))
async def do_setstyle(message: Message):
    from app.core.db import get_session_factory
    from app.database import repositories as repo

    sample = message.text.replace("/setstyle", "", 1).strip()
    if len(sample) < 10:
        await message.answer("Пришли чуть больше примеров (2–3 сообщения).")
        return
    lines = [line for line in sample.splitlines() if line.strip()]
    profile = {
        "avg_len": sum(len(line) for line in lines) // max(len(lines), 1),
        "emoji": any(c in sample for c in "😅😂❤️🎉👍"),
        "samples": lines[:5],
        "note": "Писать в стиле этих примеров: та же длина, пунктуация, эмодзи, формальность.",
    }
    factory = get_session_factory()
    async with factory() as session:
        user = await repo.get_or_create_user(session, message.from_user.id)
        user.style_profile = profile
        await session.commit()
    await message.answer("🧬 Запомнил твой стиль! Теперь «Сделать как я» будет звучать как ты.")
