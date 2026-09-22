"""Verdent Platform — order lifecycle (Phase 1).

The commercial core: create order → attach proof → admin review → approve
(triggers provisioning) or reject. Order state machine per Document 3 §G.
All writes commit; all admin actions audit-logged.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import (
    Customer,
    Order,
    PaymentAttempt,
    PaymentProof,
    Plan,
)
from domain.audit import audit

logger = logging.getLogger("verdent.orders")


class OrderError(Exception):
    pass


async def get_or_create_customer(
    db: AsyncSession, telegram_user_id: int, username: str | None, display_name: str | None
) -> Customer:
    customer = (
        await db.execute(
            select(Customer).where(Customer.telegram_user_id == str(telegram_user_id))
        )
    ).scalar_one_or_none()

    now = datetime.now(timezone.utc)

    if customer is None:
        customer = Customer(
            telegram_user_id=str(telegram_user_id),
            telegram_username=username,
            display_name=display_name,
            first_seen_at=now,
            last_interaction_at=now,
        )
        db.add(customer)
        await db.commit()
        return customer

    customer.telegram_username = username or customer.telegram_username
    customer.display_name = display_name or customer.display_name
    customer.last_interaction_at = now
    await db.commit()
    return customer


async def create_order(
    db: AsyncSession, customer: Customer, plan: Plan, requested_display_name: str, idempotency_suffix: str = ""
) -> Order:
    """Fresh order per purchase attempt. The idempotency key absorbs Telegram
    retries of the same button press within the same minute."""
    idempotency_key = f"tg:{customer.telegram_user_id}:{plan.id}:{idempotency_suffix}"

    existing = (
        await db.execute(select(Order).where(Order.idempotency_key == idempotency_key))
    ).scalar_one_or_none()

    if existing is not None and existing.status in ("CREATED", "AWAITING_PAYMENT"):
        return existing

    order = Order(
        customer_id=customer.id,
        plan_id=plan.id,
        requested_display_name=requested_display_name,
        status="AWAITING_PAYMENT",
        idempotency_key=f"{idempotency_key}:{datetime.now(timezone.utc).timestamp():.0f}"
        if existing is not None
        else idempotency_key,
    )
    db.add(order)
    await db.commit()
    return order


async def attach_payment_proof(
    db: AsyncSession, order: Order, telegram_file_id: str, mime_type: str | None, size_bytes: int | None
) -> PaymentAttempt:
    """Customer submitted their screenshot: order → PAID (paid-pending-review),
    attempt WAITING_REVIEW. Multiple proofs per attempt are allowed (customer
    re-sends a clearer one); review state stays WAITING_REVIEW."""
    attempt = PaymentAttempt(
        order_id=order.id,
        method="manual_proof",
        amount=0,  # exact amount recorded at approve time from the plan
        currency="IRR",
        status="WAITING_REVIEW",
    )
    db.add(attempt)
    await db.flush()

    db.add(
        PaymentProof(
            payment_attempt_id=attempt.id,
            telegram_file_id=telegram_file_id,
            mime_type=mime_type,
            size_bytes=size_bytes,
        )
    )

    order.status = "PAID"
    order.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return attempt


async def reject_payment(
    db: AsyncSession, attempt: PaymentAttempt, admin_id: str, reason: str
) -> None:
    attempt.status = "REJECTED"
    attempt.reviewed_by = admin_id
    attempt.reviewed_at = datetime.now(timezone.utc)
    attempt.rejection_reason = reason

    order = (
        await db.execute(select(Order).where(Order.id == attempt.order_id))
    ).scalar_one()
    order.status = "REJECTED"
    order.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await audit(
        db,
        "payment.reject",
        actor_id=admin_id,
        target_type="payment_attempt",
        target_id=attempt.id,
        details={"reason": reason, "order_id": order.id},
    )


async def mark_order_provisioning(db: AsyncSession, order: Order, attempt: PaymentAttempt, admin_id: str) -> None:
    plan = (await db.execute(select(Plan).where(Plan.id == order.plan_id))).scalar_one_or_none()

    attempt.status = "APPROVED"
    attempt.reviewed_by = admin_id
    attempt.reviewed_at = datetime.now(timezone.utc)
    if plan is not None:
        attempt.amount = float(plan.price_amount)
        attempt.currency = plan.price_currency

    order.status = "PROVISIONING"
    order.updated_at = datetime.now(timezone.utc)
    await db.commit()

    await audit(
        db,
        "payment.approve",
        actor_id=admin_id,
        target_type="payment_attempt",
        target_id=attempt.id,
        details={"order_id": order.id},
    )


async def mark_order_fulfilled(db: AsyncSession, order: Order) -> None:
    order.status = "FULFILLED"
    order.updated_at = datetime.now(timezone.utc)
    await db.commit()


async def get_order_attempts(db: AsyncSession, order_id: str) -> list[PaymentAttempt]:
    rows = (
        await db.execute(
            select(PaymentAttempt)
            .where(PaymentAttempt.order_id == order_id)
            .order_by(PaymentAttempt.created_at.desc())
        )
    ).scalars().all()
    return list(rows)
