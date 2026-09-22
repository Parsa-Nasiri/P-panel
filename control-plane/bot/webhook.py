"""Verdent Platform — Telegram webhook wiring (aiogram 3 + FastAPI).

The bot lives INSIDE the web service (Document 3 §I): one Railway service,
one process. Updates arrive at POST /webhook/{TELEGRAM_WEBHOOK_SECRET_TOKEN}
— verified both by the path secret and Telegram's X-Telegram-Bot-Api-Secret-
Token header. The webhook is (re-)registered on startup when the bot token
and SUBSCRIPTION_BASE_URL are configured; the app boots fine without them
(bot simply disabled) so the control plane never depends on Telegram to run.

This module owns the Dispatcher (bot.router registers handlers onto it —
imported AFTER this module completes, so keep this file free of bot.router
imports).
"""

import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from domain.config import settings

logger = logging.getLogger("verdent.bot")

dp: Dispatcher = Dispatcher()
bot: Bot | None = None


def bot_enabled() -> bool:
    return bool(settings.telegram_bot_token)


async def send_message(telegram_user_id: str, text: str) -> bool:
    """Outbound helper used by notifications and fulfillment. Never raises."""
    if not bot_enabled():
        logger.warning("bot disabled — cannot message %s", telegram_user_id)
        return False
    try:
        b = Bot(
            token=settings.telegram_bot_token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        async with b.session:
            await b.send_message(chat_id=int(telegram_user_id), text=text)
        return True
    except Exception:  # noqa: BLE001
        logger.exception("send_message failed for %s", telegram_user_id)
        return False


async def register_webhook() -> str | None:
    if not bot_enabled() or not settings.subscription_base_url:
        logger.info("bot webhook not registered (token or SUBSCRIPTION_BASE_URL missing)")
        return None

    base = settings.subscription_base_url.rstrip("/")
    url = f"{base}/webhook/{settings.telegram_webhook_secret_token}"

    b = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    async with b.session:
        me = await b.get_me()
        await b.set_webhook(
            url,
            secret_token=settings.telegram_webhook_secret_token or None,
            allowed_updates=["message", "callback_query", "pre_checkout_query"],
            drop_pending_updates=True,
        )
    logger.info("webhook registered for @%s -> %s", me.username, url)
    return url
