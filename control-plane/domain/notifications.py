"""Verdent Platform — notifications + expiry sweep (Phase 5, cron service).

- expiry sweep: EXPIRED at expiry; warning 3 days before (once per day,
  deduplicated through notifications_log)
- quota warnings at 80% (once per day) + exhaustion disable via node KV
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.base import SessionLocal
from db.models import Configuration, ConfigurationNodeAssignment, Customer, Node, NotificationsLog
from bot import texts
from domain.kv_sync import set_entry_status
from domain.subscriptions import usage_current_period

logger = logging.getLogger("verdent.notifications")

EXPIRY_WARN_DAYS = 3
QUOTA_WARN_PERCENT = 80


async def _already_sent(db: AsyncSession, customer_id: str, notification_type: str, day: str) -> bool:
    row = (
        await db.execute(
            select(NotificationsLog.id).where(
                NotificationsLog.customer_id == customer_id,
                NotificationsLog.notification_type == f"{notification_type}:{day}",
            )
        )
    ).scalar_one_or_none()
    return row is not None


async def _record(db: AsyncSession, customer_id: str, notification_type: str) -> None:
    db.add(
        NotificationsLog(
            customer_id=customer_id,
            notification_type=f"{notification_type}:{datetime.now(timezone.utc).date().isoformat()}",
        )
    )
    await db.commit()


async def notify_customer(telegram_user_id: str, message: str) -> bool:
    """Fire a Telegram message. Import-guarded so the cron service also works
    without a bot token configured."""
    try:
        from bot.webhook import send_message

        return await send_message(telegram_user_id, message)
    except Exception:  # noqa: BLE001
        logger.exception("notify failed for %s", telegram_user_id)
        return False


async def expiry_and_quota_sweep() -> dict:
    """Runs from the cron service. Idempotent per (customer, type, day)."""
    now = datetime.now(timezone.utc)
    today = now.date().isoformat()
    stats = {"expired": 0, "expiry_warned": 0, "quota_warned": 0, "quota_exhausted": 0}

    async with SessionLocal() as db:
        active = (
            await db.execute(
                select(Configuration).where(
                    Configuration.status == "ACTIVE",
                    Configuration.is_test.is_(False),
                )
            )
        ).scalars().all()

        for config in active:
            customer = (
                await db.execute(
                    select(Customer).where(Customer.id == config.customer_id)
                )
            ).scalar_one_or_none()
            if customer is None:
                continue

            # ---- expiry -------------------------------------------------
            if config.expires_at is not None:
                remaining = config.expires_at - now

                if remaining <= timedelta(0):
                    config.status = "EXPIRED"
                    stats["expired"] += 1
                    if not await _already_sent(db, customer.id, "expired", today):
                        await notify_customer(
                            customer.telegram_user_id,
                            texts.MSG_EXPIRED.format(display_name=config.display_name),
                        )
                        await _record(db, customer.id, "expired")
                    continue

                if remaining <= timedelta(days=EXPIRY_WARN_DAYS):
                    if not await _already_sent(db, customer.id, "expiry_warn", today):
                        await notify_customer(
                            customer.telegram_user_id,
                            texts.MSG_EXPIRY_WARNING.format(
                                display_name=config.display_name,
                                days=max(1, remaining.days),
                            ),
                        )
                        await _record(db, customer.id, "expiry_warn")
                        stats["expiry_warned"] += 1

            # ---- quota ---------------------------------------------------
            used, quota = await usage_current_period(db, config)
            if quota:
                percent = int(used * 100 / quota)
                if percent >= 100:
                    assignment = (
                        await db.execute(
                            select(ConfigurationNodeAssignment)
                            .where(
                                ConfigurationNodeAssignment.configuration_id == config.id,
                                ConfigurationNodeAssignment.revoked_at.is_(None),
                            )
                            .limit(1)
                        )
                    ).scalar_one_or_none()
                    if assignment is not None:
                        node = (
                            await db.execute(
                                select(Node).where(Node.id == assignment.node_id)
                            )
                        ).scalar_one_or_none()
                        if node is not None:
                            await set_entry_status(
                                db, node, str(assignment.proxy_uuid), "disabled"
                            )
                    stats["quota_exhausted"] += 1
                    if not await _already_sent(db, customer.id, "quota_exhausted", today):
                        await notify_customer(
                            customer.telegram_user_id,
                            texts.MSG_QUOTA_EXHAUSTED.format(display_name=config.display_name),
                        )
                        await _record(db, customer.id, "quota_exhausted")
                elif percent >= QUOTA_WARN_PERCENT:
                    if not await _already_sent(db, customer.id, "quota_warn", today):
                        await notify_customer(
                            customer.telegram_user_id,
                            texts.MSG_QUOTA_WARNING.format(
                                display_name=config.display_name, percent=percent
                            ),
                        )
                        await _record(db, customer.id, "quota_warn")
                        stats["quota_warned"] += 1

        await db.commit()

    logger.info("expiry/quota sweep: %s", stats)
    return stats
