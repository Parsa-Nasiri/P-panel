"""Verdent Platform — test configurations (Phase 4; Document 6 §Phase-4).

Abuse mitigations per blueprint:
- exactly ONE active test per customer (is_test + ACTIVE + not expired)
- hard quota: TEST_QUOTA_BYTES (default 100MB), enforced by quota-flag push
- hard expiry: 24h, enforced by the expiry sweep
- config_type='test' keeps them out of normal plan analytics
"""

import logging
import uuid as uuid_lib
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Configuration, ConfigurationNodeAssignment, Node, Plan
from domain.audit import audit
from domain.naming import create_unique_config_name_pair
from domain.kv_sync import sync_assignment

logger = logging.getLogger("verdent.test_configs")

TEST_QUOTA_BYTES = 100 * 1024 * 1024  # 100MB
TEST_DURATION = timedelta(hours=24)


async def has_active_test_config(db: AsyncSession, customer_id: str) -> bool:
    now = datetime.now(timezone.utc)
    row = (
        await db.execute(
            select(Configuration.id)
            .where(
                Configuration.customer_id == customer_id,
                Configuration.is_test.is_(True),
                Configuration.status == "ACTIVE",
                (Configuration.expires_at.is_(None)) | (Configuration.expires_at > now),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    return row is not None


async def create_test_config(
    db: AsyncSession,
    customer_id: str,
    display_name: str,
    node: Node,
    actor_id: str | None = None,
) -> Configuration:
    if await has_active_test_config(db, customer_id):
        raise RuntimeError("customer already has an active test config")

    name, suffix = await create_unique_config_name_pair(db, display_name)
    now = datetime.now(timezone.utc)

    config = Configuration(
        id=str(uuid_lib.uuid4()),
        customer_id=customer_id,
        plan_id=None,
        display_name=name,
        suffix=suffix,
        subscription_token=__import__("secrets").token_urlsafe(24),
        config_type="test",
        gaming_profile_id=None,
        status="ACTIVE",
        is_test=True,
        test_quota_bytes=TEST_QUOTA_BYTES,
        created_at=now,
        expires_at=now + TEST_DURATION,
    )
    db.add(config)
    await db.flush()

    assignment = ConfigurationNodeAssignment(
        configuration_id=config.id,
        node_id=node.id,
        role="primary",
        proxy_uuid=str(uuid_lib.uuid4()),
    )
    db.add(assignment)
    node.current_assignment_count = (node.current_assignment_count or 0) + 1
    await db.commit()

    await sync_assignment(
        db,
        node,
        proxy_uuid=assignment.proxy_uuid,
        config_id=config.id,
        status="active",
        device_limit=1,
    )

    await audit(
        db,
        "config.test_created",
        actor_id=actor_id,
        actor_type="admin" if actor_id else "system",
        target_type="configuration",
        target_id=config.id,
        details={"customer_id": customer_id},
    )
    return config
