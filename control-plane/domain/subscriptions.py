"""Verdent Platform — subscription serving (Document 3 §L; Phase 1).

- create_configuration_for_order: builds the Configuration + mints the
  proxy credential on the selected node (assignment), the ONE place where
  the "one order → one activation" idempotency guarantee is enforced.
- render_vless_uris / build_subscription_body: the /s/{token} renderer.
- usage_totals: quota math — the current period starts at
  (expires_at - plan.duration_days), which makes renewal reset consumption
  WITHOUT any schema change.
"""

import base64
import secrets
import uuid as uuid_lib
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import (
    Configuration,
    ConfigurationNodeAssignment,
    Node,
    Order,
    Plan,
    SubscriptionActivation,
    UsageDailyAggregate,
)
from domain.config import settings
from domain.naming import create_unique_config_name_pair


class SubscriptionError(Exception):
    pass


async def create_configuration_for_order(
    db: AsyncSession,
    order: Order,
    node: Node,
    *,
    device_limit: int | None = None,
    gaming_profile_id: str | None = None,
) -> Configuration:
    """Create the Configuration + assignment for a PAID order. Idempotent via
    subscription_activations.order_id UNIQUE — a re-run returns the existing
    config instead of double-provisioning."""
    existing = (
        await db.execute(
            select(Configuration)
            .join(SubscriptionActivation, SubscriptionActivation.configuration_id == Configuration.id)
            .where(SubscriptionActivation.order_id == order.id)
        )
    ).scalar_one_or_none()

    if existing is not None:
        return existing

    plan = (
        await db.execute(select(Plan).where(Plan.id == order.plan_id))
    ).scalar_one_or_none()

    display_name, suffix = await create_unique_config_name_pair(
        db, order.requested_display_name
    )

    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=plan.duration_days if plan else 30)

    config = Configuration(
        id=str(uuid_lib.uuid4()),
        customer_id=order.customer_id,
        plan_id=order.plan_id,
        display_name=display_name,
        suffix=suffix,
        subscription_token=secrets.token_urlsafe(24),
        config_type="gaming" if (gaming_profile_id or (plan and plan.gaming_profile_id)) else "normal",
        gaming_profile_id=gaming_profile_id or (plan.gaming_profile_id if plan else None),
        status="ACTIVE",
        is_test=False,
        created_at=now,
        expires_at=expires,
    )
    db.add(config)
    await db.flush()

    proxy_uuid = str(uuid_lib.uuid4())
    assignment = ConfigurationNodeAssignment(
        configuration_id=config.id,
        node_id=node.id,
        role="primary",
        proxy_uuid=proxy_uuid,
    )
    db.add(assignment)

    db.add(SubscriptionActivation(order_id=order.id, configuration_id=config.id))

    node.current_assignment_count = (node.current_assignment_count or 0) + 1
    await db.commit()

    return config


async def extend_configuration(
    db: AsyncSession, config: Configuration, plan: Plan
) -> Configuration:
    """Renewal: extend from max(now, current expiry) — renewing early never
    loses remaining days."""
    now = datetime.now(timezone.utc)
    base = max(config.expires_at or now, now)
    config.expires_at = base + timedelta(days=plan.duration_days)
    if config.status == "EXPIRED":
        config.status = "ACTIVE"
    await db.commit()
    return config


# ---------------------------------------------------------------------------
# Usage + quota (Document 3 §K)
# ---------------------------------------------------------------------------


async def usage_current_period(db: AsyncSession, config: Configuration) -> tuple[int, int | None]:
    """(used_bytes, quota_bytes|None). Period start = expiry minus plan
    duration, so renewals reset consumption without a schema change."""
    quota: int | None = None
    period_start = config.created_at

    if config.is_test:
        quota = config.test_quota_bytes
    elif config.plan_id:
        plan = (await db.execute(select(Plan).where(Plan.id == config.plan_id))).scalar_one_or_none()
        if plan is not None:
            quota = plan.traffic_quota_bytes
            if config.expires_at:
                period_start = config.expires_at - timedelta(days=plan.duration_days)

    row = (
        await db.execute(
            select(UsageDailyAggregate)
            .where(
                UsageDailyAggregate.configuration_id == config.id,
                UsageDailyAggregate.usage_date >= period_start.date(),
            )
        )
    ).scalars().all()

    used = sum(a.total_bytes for a in row)
    return used, quota


async def active_assignments(db: AsyncSession, config: Configuration) -> list[tuple[ConfigurationNodeAssignment, Node]]:
    rows = (
        await db.execute(
            select(ConfigurationNodeAssignment, Node)
            .join(Node, Node.id == ConfigurationNodeAssignment.node_id)
            .where(
                ConfigurationNodeAssignment.configuration_id == config.id,
                ConfigurationNodeAssignment.revoked_at.is_(None),
                Node.state.notin_(["DECOMMISSIONED", "OFFLINE", "QUARANTINED"]),
            )
        )
    ).all()
    return [(a, n) for a, n in rows]


# ---------------------------------------------------------------------------
# Subscription rendering
# ---------------------------------------------------------------------------


def render_vless_uri(
    node_domain: str,
    proxy_uuid: str,
    display_name: str,
    port: int = 443,
) -> str:
    host = node_domain.removeprefix("https://").removeprefix("http://").rstrip("/")
    label = quote(f"{display_name}", safe="")
    return (
        f"vless://{proxy_uuid}@{host}:{port}"
        f"?type=ws&path=%2Fvl&security=tls&sni={host}&fp=chrome#{label}"
    )


def build_subscription_body(uris: list[str]) -> str:
    return base64.b64encode("\n".join(uris).encode()).decode()


def subscription_url(config: Configuration) -> str:
    base = settings.subscription_base_url.rstrip("/")
    return f"{base}/s/{config.subscription_token}"
