"""Verdent Platform — internal node endpoints (HMAC-authenticated).

Document 5, "Node-to-Control-Plane auth" + replay protection:
- POST /internal/nodes/{node_id}/usage  — append usage events (append-only ledger)
- POST /internal/nodes/{node_id}/health — supplementary health samples

Every request is verified in three steps:
  1. node lookup + state check (DECOMMISSIONED rejected)
  2. timestamp window + HMAC over the raw body
  3. Idempotency: (connection_id, sequence_number) UNIQUE — a duplicate is
     acknowledged with 200 and dropped, never double-counted.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from db.base import get_db
from db.models import NodeHealthSample, Node, UsageEvent
from domain.security import (
    compute_expected_signature,
    secure_compare,
    timestamp_within_window,
)

router = APIRouter(prefix="/internal/nodes", tags=["internal"])


class AuthError(Exception):
    pass


async def verify_node_auth(
    node_id: str,
    request: Request,
    x_verdent_timestamp: str,
    x_verdent_nonce: str,
    x_verdent_signature: str,
    db: AsyncSession,
) -> Node:
    if not timestamp_within_window(x_verdent_timestamp):
        raise AuthError("timestamp outside validity window")

    node = (
        await db.execute(select(Node).where(Node.id == node_id))
    ).scalar_one_or_none()

    if node is None:
        raise AuthError("unknown node")

    if node.state == "DECOMMISSIONED":
        raise AuthError("node is decommissioned")

    expected = compute_expected_signature(
        node_secret_hash=node.node_secret_hash or "",
        node_id=node_id,
        timestamp=x_verdent_timestamp,
        nonce=x_verdent_nonce,
        body=await request.body(),
    )

    if not secure_compare(x_verdent_signature, expected):
        raise AuthError("invalid signature")

    return node


class UsageEventPayload(BaseModel):
    configId: str
    connectionId: str
    sequenceNumber: int
    bytesUp: int
    bytesDown: int
    windowStartedAt: str
    reportedAt: str

    @field_validator("configId", "connectionId")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not value:
            raise ValueError("must be a non-empty string")
        return value

    @field_validator("sequenceNumber", "bytesUp", "bytesDown")
    @classmethod
    def _non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("must be non-negative")
        return value


class UsageEventAck(BaseModel):
    status: str = "ok"
    dropped: bool = False


@router.post("/{node_id}/usage")
async def ingest_usage(
    node_id: str,
    payload: UsageEventPayload,
    request: Request,
    x_verdent_timestamp: str = Header(),
    x_verdent_nonce: str = Header(),
    x_verdent_signature: str = Header(),
    db: AsyncSession = Depends(get_db),
) -> UsageEventAck:
    try:
        await verify_node_auth(
            node_id=node_id,
            request=request,
            x_verdent_timestamp=x_verdent_timestamp,
            x_verdent_nonce=x_verdent_nonce,
            x_verdent_signature=x_verdent_signature,
            db=db,
        )
    except AuthError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    try:
        event = UsageEvent(
            configuration_id=payload.configId,
            node_id=node_id,
            connection_id=payload.connectionId,
            sequence_number=payload.sequenceNumber,
            bytes_up=payload.bytesUp,
            bytes_down=payload.bytesDown,
            window_started_at=datetime.fromisoformat(payload.windowStartedAt),
        )

        db.add(event)

        try:
            await db.commit()
        except IntegrityError:
            # (connection_id, sequence_number) already exists — a retried flush.
            # Acknowledge 200 and drop: a duplicate is never an accumulate.
            await db.rollback()
            return UsageEventAck(dropped=True)
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        raise HTTPException(status_code=500, detail="failed to append usage event") from exc

    return UsageEventAck()


class HealthSamplePayload(BaseModel):
    checkType: str
    success: bool
    latencyMs: float | None = None
    jitterMs: float | None = None
    packetLoss: float | None = None
    checkedAt: str | None = None


@router.post("/{node_id}/health")
async def ingest_health(
    node_id: str,
    payload: HealthSamplePayload,
    request: Request,
    x_verdent_timestamp: str = Header(),
    x_verdent_nonce: str = Header(),
    x_verdent_signature: str = Header(),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        await verify_node_auth(
            node_id=node_id,
            request=request,
            x_verdent_timestamp=x_verdent_timestamp,
            x_verdent_nonce=x_verdent_nonce,
            x_verdent_signature=x_verdent_signature,
            db=db,
        )
    except AuthError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    sample = NodeHealthSample(
        node_id=node_id,
        check_type=payload.checkType,
        success=payload.success,
        latency_ms=payload.latencyMs,
        jitter_ms=payload.jitterMs,
        packet_loss=payload.packetLoss,
    )

    db.add(sample)
    await db.commit()
    return {"status": "ok"}
