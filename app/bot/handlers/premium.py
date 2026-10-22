"""Premium через Telegram Stars (XTR): /premium, invoice, pre_checkout, successful_payment.

Зависит от настроек: premium_stars_price (цена в звёздах). is_premium выставляется
после successful_payment; дневной лимит становится premium_daily_limit.
"""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import LabeledPrice, Message, PreCheckoutQuery

from app.core.config import get_settings
from app.core.db import get_session_factory
from app.database import repositories as repo
from app.i18n import fmt as tf
from app.i18n import lang_of, t

log = logging.getLogger(__name__)
router = Router()

PAYLOAD = "premium_month"


@router.message(Command("premium"))
async def premium_cmd(message: Message):
    settings = get_settings()
    factory = get_session_factory()
    async with factory() as session:
        user = await repo.get_or_create_user(session, message.from_user.id)
        is_premium = user.is_premium
    lang = lang_of(message.from_user)
    if is_premium:
        await message.answer(tf("premium_active", lang))
        return
    price = settings.premium_stars_price
    try:
        await message.answer_invoice(
            title=tf("premium_invoice_title", lang),
            description=tf("premium_invoice_description", lang),
            payload=PAYLOAD,
            provider_token="",  # для Stars (XTR) provider_token обязателен пустым
            currency="XTR",
            prices=[LabeledPrice(label="Premium", amount=price)],
        )
    except Exception:
        log.exception("send_invoice failed")
        await message.answer(t("invoice_error", lang))


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    if query.invoice_payload == PAYLOAD:
        await query.answer(ok=True)
    else:
        await query.answer(ok=False, error_message="Неизвестный товар. Попробуй /premium заново.")


@router.message(F.successful_payment)
async def on_paid(message: Message):
    sp = message.successful_payment
    factory = get_session_factory()
    async with factory() as session:
        user = await repo.get_or_create_user(session, message.from_user.id)
        if sp.currency == "XTR" and sp.invoice_payload == PAYLOAD:
            user.is_premium = True
            await repo.add_event(
                session, "purchase", user_id=user.id,
                detail=f"{sp.total_amount} XTR: {sp.invoice_payload}",
            )
            await session.commit()
            await message.answer(tf("premium_activated", lang_of(message.from_user)))
        else:
            await repo.add_event(
                session, "purchase", user_id=user.id,
                detail=f"unexpected: {sp.currency}/{sp.invoice_payload}",
            )
            await session.commit()
            await message.answer(tf("premium_failed", lang_of(message.from_user)))
