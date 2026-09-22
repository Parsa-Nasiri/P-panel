"""Verdent Platform — bootstrap-OWNER admin (Document 5, "Bootstrap Owner").

Idempotent: if TELEGRAM_OWNER_ID is set and the admins table is empty, insert
the first OWNER with created_by NULL. On any subsequent run, no-op. Exactly
one bootstrap OWNER exists per environment; additional admins are created
from inside the app (Phase 1) and always have created_by set.
"""

import logging

from sqlalchemy import select, func

from db.base import SessionLocal
from db.models import Admin
from domain.config import settings

logger = logging.getLogger("verdent.platform.bootstrap")


async def ensure_bootstrap_owner() -> None:
    owner_id = settings.telegram_owner_id

    if not owner_id:
        logger.warning("TELEGRAM_OWNER_ID not set — skipping bootstrap owner (development only)")
        return

    telegram_owner_str = str(owner_id)

    async with SessionLocal() as session:
        existing_owner = (
            await session.execute(
                select(Admin).where(Admin.telegram_user_id == telegram_owner_str)
            )
        ).scalar_one_or_none()

        if existing_owner is not None:
            logger.info("bootstrap owner already exists (id=%s)", existing_owner.id)
            return

        count = (
            await session.execute(select(func.count()).select_from(Admin))
        ).scalar_one()

        if count > 0:
            # The table is not empty and no OWNER row for TELEGRAM_OWNER_ID —
            # the bootstrap OWNER is the FIRST admin; never silently add a
            # second bootstrap row for a different environment.
            logger.warning("admins table is not empty and no row matches TELEGRAM_OWNER_ID — skipping bootstrap")
            return

        session.add(
            Admin(
                telegram_user_id=telegram_owner_str,
                role="OWNER",
                created_by=None,
            )
        )
        await session.commit()
        logger.info("bootstrap OWNER inserted for telegram user %s", telegram_owner_str)
