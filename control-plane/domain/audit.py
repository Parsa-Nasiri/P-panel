"""Verdent Platform — audit logging (Phase 5, used everywhere).

Every admin/state-changing action appends an audit_log row. Never raises:
auditing must not break the action it records.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from db.models import AuditLog

logger = logging.getLogger("verdent.audit")


async def audit(
    db: AsyncSession,
    action: str,
    *,
    actor_type: str = "admin",
    actor_id: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    details: dict | None = None,
) -> None:
    import json

    try:
        db.add(
            AuditLog(
                actor_type=actor_type,
                actor_id=actor_id,
                action=action,
                target_type=target_type,
                target_id=target_id,
                details_json=json.dumps(details or {}, ensure_ascii=False),
            )
        )
        await db.commit()
    except Exception:  # noqa: BLE001
        logger.exception("audit log failed for action %s", action)
        await db.rollback()
