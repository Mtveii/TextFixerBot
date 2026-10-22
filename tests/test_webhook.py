"""Webhook server: health, secret-token auth, update intake."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import httpx
import pytest
from aiogram import Bot, Dispatcher

from app.main import run_webhook

PORT = 18109


@pytest.mark.asyncio
async def test_webhook_endpoints():
    bot = Bot(token="123456:TEST")
    dp = Dispatcher()
    settings = SimpleNamespace(webhook_path="/wh", webhook_secret="s3c-ret", webhook_port=PORT)

    server = asyncio.create_task(run_webhook(bot, dp, settings, handle_signals=False))
    try:
        # wait until the socket is listening
        async with httpx.AsyncClient() as client:
            for _ in range(50):
                try:
                    r = await client.get(f"http://127.0.0.1:{PORT}/health")
                    break
                except httpx.ConnectError:
                    await asyncio.sleep(0.1)
            else:
                pytest.fail("webhook server did not start")

            assert r.status_code == 200

            # wrong/missing secret -> 403
            r = await client.post(f"http://127.0.0.1:{PORT}/wh", json={"update_id": 1})
            assert r.status_code == 403
            r = await client.post(
                f"http://127.0.0.1:{PORT}/wh",
                json={"update_id": 1},
                headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"},
            )
            assert r.status_code == 403

            # invalid body -> 400
            r = await client.post(
                f"http://127.0.0.1:{PORT}/wh",
                content=b"not-json",
                headers={
                    "X-Telegram-Bot-Api-Secret-Token": "s3c-ret",
                    "Content-Type": "application/json",
                },
            )
            assert r.status_code == 400

            # valid update -> 200 (dispatched in background)
            r = await client.post(
                f"http://127.0.0.1:{PORT}/wh",
                json={"update_id": 1},
                headers={"X-Telegram-Bot-Api-Secret-Token": "s3c-ret"},
            )
            assert r.status_code == 200
            await asyncio.sleep(0.2)  # let the background task finish
    finally:
        server.cancel()
        with pytest.raises(asyncio.CancelledError):
            await server
        await bot.session.close()


@pytest.mark.asyncio
async def test_webhook_no_secret_allows_any_header():
    bot = Bot(token="123456:TEST")
    dp = Dispatcher()
    settings = SimpleNamespace(webhook_path="/wh", webhook_secret="", webhook_port=18110)

    server = asyncio.create_task(run_webhook(bot, dp, settings, handle_signals=False))
    try:
        async with httpx.AsyncClient() as client:
            for _ in range(50):
                try:
                    r = await client.post("http://127.0.0.1:18110/wh", json={"update_id": 7})
                    break
                except httpx.ConnectError:
                    await asyncio.sleep(0.1)
            else:
                pytest.fail("webhook server did not start")
            assert r.status_code == 200
    finally:
        server.cancel()
        with pytest.raises(asyncio.CancelledError):
            await server
        await bot.session.close()
