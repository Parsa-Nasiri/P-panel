"""Verdent Platform — Telegram webhook route.

POST /webhook/{secret} — the path secret IS the first auth layer; Telegram's
X-Telegram-Bot-Api-Secret-Token header (set at registration) is the second.
No secret, no service.
"""

import logging

from fastapi import APIRouter, Header, HTTPException, Request

from domain.config import settings

logger = logging.getLogger("verdent.bot.webhook")

router = APIRouter(tags=["telegram"])


@router.post("/webhook/{secret_token}")
async def telegram_webhook(
    secret_token: str,
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
):
    if secret_token != settings.telegram_webhook_secret_token:
        raise HTTPException(status_code=403, detail="forbidden")

    if settings.telegram_webhook_secret_token and (
        x_telegram_bot_api_secret_token != settings.telegram_webhook_secret_token
    ):
        raise HTTPException(status_code=403, detail="forbidden")

    if not settings.telegram_bot_token:
        raise HTTPException(status_code=503, detail="bot disabled")

    update_json = await request.json()

    from aiogram.types import Update

    try:
        update = Update.model_validate(update_json, context={"bot": None})
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="bad update")

    from bot import webhook as bot_webhook

    if bot_webhook.bot is None:
        from aiogram import Bot
        from aiogram.client.default import DefaultBotProperties
        from aiogram.enums import ParseMode

        bot_webhook.bot = Bot(
            token=settings.telegram_bot_token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )

    await bot_webhook.dp.feed_update(bot_webhook.bot, update)
    return {"ok": True}
