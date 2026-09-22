"""Verdent Platform — public subscription endpoint (Document 3 §L).

GET /s/{subscription_token}
  - auth by capability token only (rotatable independently of proxy creds)
  - returns base64 vless:// URI list + standard subscription headers
  - subscription-userinfo carries upload/download/total/expire from the
    usage ledger (Document 3 §L)
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.base import get_db
from db.models import Configuration
from domain.subscriptions import (
    active_assignments,
    build_subscription_body,
    render_vless_uri,
    usage_current_period,
)

router = APIRouter(tags=["subscriptions"])


@router.get("/s/{subscription_token}")
async def get_subscription(
    subscription_token: str,
    user_agent: str | None = Header(default=None, alias="User-Agent"),
    db: AsyncSession = Depends(get_db),
) -> Response:
    config = (
        await db.execute(
            select(Configuration).where(
                Configuration.subscription_token == subscription_token
            )
        )
    ).scalar_one_or_none()

    if config is None or config.status == "DELETED":
        raise HTTPException(status_code=404, detail="not found")

    now = datetime.now(timezone.utc)
    if config.expires_at is not None and config.expires_at <= now and config.status == "ACTIVE":
        config.status = "EXPIRED"
        await db.commit()

    assignments = await active_assignments(db, config)
    uris = [
        render_vless_uri(
            node.custom_domain or "",
            str(assignment.proxy_uuid),
            config.display_name,
        )
        for assignment, node in assignments
        if node.custom_domain
    ]

    used, quota = await usage_current_period(db, config)

    userinfo_parts = [f"upload={used}", f"download={used}", f"total={quota or 0}"]
    if config.expires_at:
        userinfo_parts.append(f"expire={int(config.expires_at.timestamp())}")

    headers = {
        "content-type": "text/plain; charset=utf-8",
        "profile-title": config.display_name,
        "profile-update-interval": "6",
        "subscription-userinfo": "; ".join(userinfo_parts),
    }

    body = build_subscription_body(uris) if uris else ""
    return Response(content=body, headers=headers)
