"""Verdent Platform — default plan seeding.

Runs at startup alongside the bootstrap admin, ONLY when the plans table is
empty. Prices are placeholders in IRR (Rial) — the OWNER edits them via the
admin panel (Phase 4) before going live. The XTR (Stars) plan is only
advertised when STARS_ENABLED=true (Phase 5).
"""

import logging

from sqlalchemy import select, func

from db.base import SessionLocal
from db.models import Plan

logger = logging.getLogger("verdent.plans")

GB = 1024 * 1024 * 1024

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
        count = (await db.execute(select(func.count()).select_from(Plan))).scalar_one()
        if count > 0:
            return

        for spec in DEFAULT_PLANS:
            db.add(Plan(**spec))
        await db.commit()
        logger.info("seeded %d default plans", len(DEFAULT_PLANS))
