"""Verdent Platform — gaming profiles (Phase 3).

A GamingProfile is a versioned tuning bundle (mtu_hint, DoH endpoint,
stability thresholds) pushed to gaming nodes' provisioning data and honored
by subscription rendering (DNS delivery per Document 2). Versioned immutably:
"publish" means insert a new row with version+1 and flip is_current.

Honesty guard (Document 2 Tier A/B): profile keys describe STABILITY and DNS
behavior. Keys like udp_enabled/ping_reduction are rejected — the platform
must not ship settings that imply capabilities Workers don't have.
"""

import json
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.base import SessionLocal
from db.models import GamingProfile

logger = logging.getLogger("verdent.gaming")

FORBIDDEN_KEYS = {
    "udp", "udp_enabled", "udp_relay", "ping_reduction", "jitter_reduction",
    "packet_loss_fix", "real_udp",
}

DEFAULT_SETTINGS = {
    "mtu_hint": 1280,
    "doh_endpoint": "https://cloudflare-dns.com/dns-query",
    "stability_thresholds": {
        "degraded_after_failures": 2,
        "offline_after_failures": 5,
        "failover_after_offline_minutes": 10,
    },
    "dns_mode": "antisanction",  # Tier A: DNS-level anti-sanction delivery
}


def validate_settings(settings_json: dict) -> list[str]:
    """Return a list of honesty violations (empty = valid)."""
    violations = []
    for key in settings_json:
        normalized = key.lower().replace("_", "").replace("-", "")
        for banned in FORBIDDEN_KEYS:
            if banned.replace("_", "") in normalized:
                violations.append(key)
    return violations


async def publish_profile(
    db: AsyncSession, name: str, settings_json: dict
) -> GamingProfile:
    violations = validate_settings(settings_json)
    if violations:
        raise ValueError(
            f"honesty violation: {violations} — gaming copy may not imply UDP/ping gains"
        )

    current = (
        await db.execute(
            select(GamingProfile).where(
                GamingProfile.name == name, GamingProfile.is_current.is_(True)
            )
        )
    ).scalar_one_or_none()

    new = GamingProfile(
        version=(current.version + 1) if current else 1,
        name=name,
        settings_json=json.dumps(settings_json, ensure_ascii=False),
        is_current=True,
    )

    if current is not None:
        current.is_current = False

    db.add(new)
    await db.commit()
    logger.info("published gaming profile %s v%d", name, new.version)
    return new


async def get_current_profile(db: AsyncSession, name: str) -> GamingProfile | None:
    return (
        await db.execute(
            select(GamingProfile).where(
                GamingProfile.name == name, GamingProfile.is_current.is_(True)
            )
        )
    ).scalar_one_or_none()


async def seed_default_gaming_profile() -> None:
    async with SessionLocal() as db:
        existing = await get_current_profile(db, "Gaming Profile")
        if existing is not None:
            return
        try:
            await publish_profile(db, "Gaming Profile", DEFAULT_SETTINGS)
        except Exception:  # noqa: BLE001
            logger.exception("gaming profile seed failed")
