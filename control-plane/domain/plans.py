"""Verdent Platform — default plan seeding.

Runs at startup alongside the bootstrap admin, ONLY when the plans table is
empty. Prices are placeholders in IRR (Rial) — the OWNER edits them via the
admin panel (Phase 4) before going live. The XTR (Stars) plan is only
advertised when STARS_ENABLED=true (Phase 5).

plans.pool_id is NOT NULL (schema), so a default pool is seeded first: the
pool is empty of nodes until the OWNER provisions infrastructure (Phase 2) —
that's correct: nothing is purchasable until a node exists, and the buy
button surfaces an honest "no capacity" message.
"""

import logging

from sqlalchemy import select, func

from db.base import SessionLocal
from db.models import Plan, Pool

logger = logging.getLogger("verdent.plans")

GB = 1024 * 1024 * 1024

DEFAULT_POOL_NAME = "general"

DEFAULT_PLANS = [
    {
        "name": "یک‌ماهه ۵۰ گیگ",
        "description": "اتصال پایدار با DNS امن، مناسب مرور روزمره",
        "price_amount": 900000,       # IRR — placeholder, edit via admin panel
        "price_currency": "IRR",
        "duration_days": 30,
        "traffic_quota_bytes": 50 * GB,
        "device_limit": 1,
        "gaming_profile_id": None,
    },
    {
        "name": "دوماهه نامحدود",
        "description": "حجم نامحدود، ۲ اتصال همزمان",
        "price_amount": 1600000,      # IRR — placeholder
        "price_currency": "IRR",
        "duration_days": 60,
        "traffic_quota_bytes": None,  # unlimited
        "device_limit": 2,
        "gaming_profile_id": None,
    },
    {
        "name": "سه‌ماهه گیمینگ",
        "description": (
            "پروفایل پایداری برای بازی: مسیرهای تمیزتر، DNS سریع‌تر، "
            "جلوگیری از قطعی — بدون وعدهٔ UDP یا کاهش پینگ"
        ),
        "price_amount": 2400000,      # IRR — placeholder
        "price_currency": "IRR",
        "duration_days": 90,
        "traffic_quota_bytes": 150 * GB,
        "device_limit": 2,
        "gaming_profile_id": None,    # bound to the seeded profile at startup
    },
    {
        "name": "بسته ستاره‌ای",
        "description": "پرداخت با تلگرام استارز، یک‌ماهه ۲۰ گیگ",
        "price_amount": 150,          # XTR (Stars)
        "price_currency": "XTR",
        "duration_days": 30,
        "traffic_quota_bytes": 20 * GB,
        "device_limit": 1,
        "gaming_profile_id": None,
    },
]


async def seed_default_plans() -> None:
    async with SessionLocal() as db:
        pool_count = (await db.execute(select(func.count()).select_from(Pool))).scalar_one()
        if pool_count == 0:
            db.add(
                Pool(
                    name=DEFAULT_POOL_NAME,
                    capability_tags=["general", "doh", "gaming"],
                    selection_strategy="least_loaded",
                    min_health_score=0,
                    max_customers_per_node=3,
                    backup_count=0,
                )
            )
            await db.flush()
            logger.info("seeded default pool %r", DEFAULT_POOL_NAME)

        count = (await db.execute(select(func.count()).select_from(Plan))).scalar_one()
        if count > 0:
            await db.commit()
            return

        pool = (
            await db.execute(select(Pool).where(Pool.name == DEFAULT_POOL_NAME))
        ).scalar_one()

        from db.models import GamingProfile

        gaming_profile = (
            await db.execute(
                select(GamingProfile).where(GamingProfile.is_current.is_(True)).limit(1)
            )
        ).scalar_one_or_none()

        for spec in DEFAULT_PLANS:
            # Every spec carries gaming_profile_id=None as its documented default;
            # passing it again as a kwarg raises TypeError. Copy and overwrite.
            fields = dict(spec)
            fields["gaming_profile_id"] = (
                gaming_profile.id
                if gaming_profile is not None and spec["name"].endswith("گیمینگ")
                else None
            )
            db.add(Plan(**fields, pool_id=pool.id))
        await db.commit()
        logger.info("seeded %d default plans", len(DEFAULT_PLANS))
