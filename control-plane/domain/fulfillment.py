"""Verdent Platform — fulfillment orchestration (Phase 1/2 bridge).

Called when an admin approves a payment (or a Stars payment succeeds):
select pool → select node → create config + assignment → sync the Node's
KV credential map → mark order fulfilled → hand back what the customer
needs (subscription link).

Phase 1 behavior when no Cloudflare account/pool exists yet: raises
FulfillmentError with a clear message — the admin keeps the order in
PROVISIONING and can retry after adding infrastructure. Never silently
half-provision: config creation and KV sync both happen, or the order stays
put for retry.
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Configuration, Node, Order, PaymentAttempt, Plan, Pool, PoolNode
from domain.audit import audit
from domain.kv_sync import sync_assignment
from domain.orders import mark_order_fulfilled
from domain.pools import select_node_for_pool
from domain.subscriptions import (
    create_configuration_for_order,
    subscription_url,
)


class FulfillmentError(Exception):
    pass


async def fulfill_order(
    db: AsyncSession,
    order: Order,
    attempt: PaymentAttempt,
    admin_id: str,
) -> Configuration:
    plan = (await db.execute(select(Plan).where(Plan.id == order.plan_id))).scalar_one_or_none()
    if plan is None:
        raise FulfillmentError("plan missing for order")

    capability = "gaming" if plan.gaming_profile_id else "general"

    pool = (
        await db.execute(select(Pool).where(Pool.id == plan.pool_id))
    ).scalar_one_or_none()

    if pool is None:
        pool = (
            await db.execute(
                select(Pool)
                .join(PoolNode, PoolNode.pool_id == Pool.id)
                .limit(1)
            )
        ).scalar_one_or_none()

    if pool is None:
        raise FulfillmentError(
            "no pool with nodes exists yet — add infrastructure before approving"
        )

    node = await select_node_for_pool(db, pool, capability=capability)
    if node is None:
        raise FulfillmentError(
            f"no eligible node in pool {pool.name!r} (state/capacity/health)"
        )

    config = await create_configuration_for_order(
        db,
        order,
        node,
        device_limit=plan.device_limit,
        gaming_profile_id=plan.gaming_profile_id,
    )

    assignment_proxy_uuid = await _primary_proxy_uuid(db, config.id)
    if assignment_proxy_uuid is None:
        raise FulfillmentError("assignment missing after creation")

    ok = await sync_assignment(
        db,
        node,
        proxy_uuid=assignment_proxy_uuid,
        config_id=config.id,
        status="active",
        device_limit=plan.device_limit,
    )
    if not ok:
        # Config exists but the edge doesn't know the credential yet — keep
        # the order in PROVISIONING so a retry only re-syncs the KV map.
        raise FulfillmentError("node KV sync failed — retry approval to re-sync")

    await mark_order_fulfilled(db, order)

    await audit(
        db,
        "config.fulfilled",
        actor_id=admin_id,
        target_type="configuration",
        target_id=config.id,
        details={"order_id": order.id, "node_id": node.id},
    )

    return config


async def _primary_proxy_uuid(db: AsyncSession, config_id: str) -> str | None:
    from db.models import ConfigurationNodeAssignment

    row = (
        await db.execute(
            select(ConfigurationNodeAssignment.proxy_uuid)
            .where(
                ConfigurationNodeAssignment.configuration_id == config_id,
                ConfigurationNodeAssignment.revoked_at.is_(None),
                ConfigurationNodeAssignment.role == "primary",
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    return row


def customer_link_block(config: Configuration) -> str:
    url = subscription_url(config)
    return f"🔗 لینک اشتراک:\n<code>{url}</code>"
