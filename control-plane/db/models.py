"""Verdent Platform — SQLAlchemy ORM models.

Mirrors `schema.sql` at the repo root, table for table, constraint for
constraint — column types, CHECK constraints, composite primary keys, JSONB /
BYTEA / TEXT[] columns, and every index (including the partial and GIN ones).
The Alembic migration 001 is generated from this metadata; any change here
must also update `schema.sql` and be done as a NEW migration.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CHAR,
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _gen_uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


def _uuid_pk() -> Mapped[str]:
    return mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        default=_gen_uuid,
    )


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


# ---------------------------------------------------------------------------
# IDENTITY
# ---------------------------------------------------------------------------


class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (CheckConstraint("status IN ('active', 'banned')", name="ck_customers_status"),)

    id: Mapped[str] = _uuid_pk()
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)  # the stable identity — never username
    telegram_username: Mapped[str | None] = mapped_column(Text)
    display_name: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str] = mapped_column(Text, nullable=False, server_default="fa")
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="active")
    first_seen_at: Mapped[datetime] = _created_at()
    last_interaction_at: Mapped[datetime] = _created_at()

    configurations: Mapped[list["Configuration"]] = relationship(back_populates="customer")
    orders: Mapped[list["Order"]] = relationship(back_populates="customer")


class Admin(Base):
    __tablename__ = "admins"
    __table_args__ = (
        CheckConstraint(
            "role IN ('OWNER', 'ADMIN', 'SUPPORT', 'FINANCE', 'INFRASTRUCTURE')",
            name="ck_admins_role",
        ),
    )

    id: Mapped[str] = _uuid_pk()
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _created_at()
    created_by: Mapped[str | None] = mapped_column(ForeignKey("admins.id"))


# ---------------------------------------------------------------------------
# INFRASTRUCTURE (data plane registry)
# ---------------------------------------------------------------------------


class CloudflareAccount(Base):
    __tablename__ = "cloudflare_accounts"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'suspended', 'decommissioned')",
            name="ck_cloudflare_accounts_status",
        ),
    )

    id: Mapped[str] = _uuid_pk()
    label: Mapped[str] = mapped_column(Text, nullable=False)
    cf_account_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    api_token_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="active")
    added_at: Mapped[datetime] = _created_at()

    nodes: Mapped[list["Node"]] = relationship(back_populates="cloudflare_account")


class Node(Base):
    __tablename__ = "nodes"
    __table_args__ = (
        CheckConstraint(
            "state IN ('PROVISIONING','ONLINE','DEGRADED','OFFLINE',"
            "'MAINTENANCE','QUARANTINED','DECOMMISSIONED')",
            name="ck_nodes_state",
        ),
        Index("idx_nodes_state", "state"),
        Index("idx_nodes_capability_tags", "capability_tags", postgresql_using="gin"),
    )

    id: Mapped[str] = _uuid_pk()
    cloudflare_account_id: Mapped[str] = mapped_column(ForeignKey("cloudflare_accounts.id"), nullable=False)
    worker_script_name: Mapped[str] = mapped_column(Text, nullable=False)
    custom_domain: Mapped[str | None] = mapped_column(Text)
    capability_tags: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default=text("'{}'::text[]"))
    control_plane_health: Mapped[bool] = mapped_column(nullable=False, server_default="false")
    data_plane_health: Mapped[bool] = mapped_column(nullable=False, server_default="false")
    health_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, server_default="0")
    current_assignment_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    max_assignment_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="3")
    node_secret_hash: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(Text, nullable=False, server_default="PROVISIONING")
    created_at: Mapped[datetime] = _created_at()

    cloudflare_account: Mapped[CloudflareAccount] = relationship(back_populates="nodes")
    assignments: Mapped[list["ConfigurationNodeAssignment"]] = relationship(back_populates="node")
    health_samples: Mapped[list["NodeHealthSample"]] = relationship(back_populates="node")
    pool_links: Mapped[list["PoolNode"]] = relationship(back_populates="node")


class Pool(Base):
    __tablename__ = "pools"
    __table_args__ = (
        CheckConstraint(
            "selection_strategy IN ('round_robin','least_loaded','sticky_score')",
            name="ck_pools_selection_strategy",
        ),
    )

    id: Mapped[str] = _uuid_pk()
    name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    capability_tags: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default=text("'{}'::text[]"))
    selection_strategy: Mapped[str] = mapped_column(Text, nullable=False, server_default="round_robin")
    min_health_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, server_default="50")
    max_customers_per_node: Mapped[int] = mapped_column(Integer, nullable=False, server_default="3")
    backup_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    node_links: Mapped[list["PoolNode"]] = relationship(back_populates="pool")


class PoolNode(Base):
    __tablename__ = "pool_nodes"

    pool_id: Mapped[str] = mapped_column(ForeignKey("pools.id", ondelete="CASCADE"), primary_key=True)
    node_id: Mapped[str] = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"), primary_key=True)

    pool: Mapped[Pool] = relationship(back_populates="node_links")
    node: Mapped[Node] = relationship(back_populates="pool_links")


class GamingProfile(Base):
    __tablename__ = "gaming_profiles"
    __table_args__ = (
        Index("uq_gaming_profiles_name_version", "name", "version", unique=True),
    )

    id: Mapped[str] = _uuid_pk()
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    settings_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    is_current: Mapped[bool] = mapped_column(nullable=False, server_default="false")
    created_at: Mapped[datetime] = _created_at()


# ---------------------------------------------------------------------------
# COMMERCE
# ---------------------------------------------------------------------------


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[str] = _uuid_pk()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    price_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    price_currency: Mapped[str] = mapped_column(Text, nullable=False, server_default="IRR")
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False)
    traffic_quota_bytes: Mapped[int | None] = mapped_column(BigInteger)  # NULL = unlimited
    device_limit: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    pool_id: Mapped[str] = mapped_column(ForeignKey("pools.id"), nullable=False)
    gaming_profile_id: Mapped[str | None] = mapped_column(ForeignKey("gaming_profiles.id"))
    is_active: Mapped[bool] = mapped_column(nullable=False, server_default="true")


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint(
            "status IN ('CREATED','AWAITING_PAYMENT','PAID','PROVISIONING','FULFILLED','REJECTED','CANCELLED')",
            name="ck_orders_status",
        ),
        Index("idx_orders_customer", "customer_id"),
    )

    id: Mapped[str] = _uuid_pk()
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), nullable=False)
    plan_id: Mapped[str] = mapped_column(ForeignKey("plans.id"), nullable=False)
    requested_display_name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="CREATED")
    idempotency_key: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _created_at()

    customer: Mapped[Customer] = relationship(back_populates="orders")
    payment_attempts: Mapped[list["PaymentAttempt"]] = relationship(back_populates="order")


class PaymentAttempt(Base):
    __tablename__ = "payment_attempts"
    __table_args__ = (
        CheckConstraint("method IN ('manual_proof', 'stars', 'gateway')", name="ck_payment_attempts_method"),
        CheckConstraint(
            "status IN ('SUBMITTED','WAITING_REVIEW','APPROVED','REJECTED','REFUNDED')",
            name="ck_payment_attempts_status",
        ),
        Index("idx_payment_attempts_order", "order_id"),
        Index(
            "idx_payment_attempts_status",
            "status",
            postgresql_where=text("status = 'WAITING_REVIEW'"),
        ),
    )

    id: Mapped[str] = _uuid_pk()
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), nullable=False)
    method: Mapped[str] = mapped_column(Text, nullable=False, server_default="manual_proof")
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(Text, nullable=False)
    external_reference: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="SUBMITTED")
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey("admins.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()

    order: Mapped[Order] = relationship(back_populates="payment_attempts")
    proofs: Mapped[list["PaymentProof"]] = relationship(back_populates="attempt")


class PaymentProof(Base):
    __tablename__ = "payment_proofs"

    id: Mapped[str] = _uuid_pk()
    payment_attempt_id: Mapped[str] = mapped_column(ForeignKey("payment_attempts.id"), nullable=False)
    telegram_file_id: Mapped[str] = mapped_column(Text, nullable=False)
    object_storage_key: Mapped[str | None] = mapped_column(Text)
    mime_type: Mapped[str | None] = mapped_column(Text)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    uploaded_at: Mapped[datetime] = _created_at()

    attempt: Mapped[PaymentAttempt] = relationship(back_populates="proofs")


# ---------------------------------------------------------------------------
# CONFIGURATIONS (the customer-facing core)
# ---------------------------------------------------------------------------


class Configuration(Base):
    __tablename__ = "configurations"
    __table_args__ = (
        CheckConstraint(
            "config_type IN ('normal', 'gaming', 'test')",
            name="ck_configurations_config_type",
        ),
        CheckConstraint(
            "status IN ('PENDING','PROVISIONING','ACTIVE','SUSPENDED','EXPIRED','DELETED')",
            name="ck_configurations_status",
        ),
        # Document 1 §D: what must be unique, forever, is the full displayed string
        Index("uq_configurations_display_name_suffix", "display_name", "suffix", unique=True),
        Index("idx_configurations_customer", "customer_id"),
        Index(
            "idx_configurations_test_lookup",
            "customer_id",
            postgresql_where=text("is_test = true"),
        ),
    )

    id: Mapped[str] = _uuid_pk()
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), nullable=False)
    plan_id: Mapped[str | None] = mapped_column(ForeignKey("plans.id"))  # NULL for test configs
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    suffix: Mapped[str] = mapped_column(CHAR(5), nullable=False)
    subscription_token: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    config_type: Mapped[str] = mapped_column(Text, nullable=False, server_default="normal")
    gaming_profile_id: Mapped[str | None] = mapped_column(ForeignKey("gaming_profiles.id"))
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="PENDING")
    is_test: Mapped[bool] = mapped_column(nullable=False, server_default="false")
    test_quota_bytes: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = _created_at()
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    customer: Mapped[Customer] = relationship(back_populates="configurations")
    assignments: Mapped[list["ConfigurationNodeAssignment"]] = relationship(back_populates="configuration")


class SubscriptionActivation(Base):
    __tablename__ = "subscription_activations"

    id: Mapped[str] = _uuid_pk()
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), unique=True, nullable=False)
    configuration_id: Mapped[str] = mapped_column(ForeignKey("configurations.id"), nullable=False)
    activated_at: Mapped[datetime] = _created_at()


class ConfigurationNodeAssignment(Base):
    __tablename__ = "configuration_node_assignments"
    __table_args__ = (
        CheckConstraint("role IN ('primary', 'backup')", name="ck_assignments_role"),
        Index(
            "idx_assignments_configuration",
            "configuration_id",
            postgresql_where=text("revoked_at IS NULL"),
        ),
        Index("idx_assignments_node", "node_id", postgresql_where=text("revoked_at IS NULL")),
    )

    id: Mapped[str] = _uuid_pk()
    configuration_id: Mapped[str] = mapped_column(ForeignKey("configurations.id"), nullable=False)
    node_id: Mapped[str] = mapped_column(ForeignKey("nodes.id"), nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False, server_default="primary")
    proxy_uuid: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    assigned_at: Mapped[datetime] = _created_at()
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    configuration: Mapped[Configuration] = relationship(back_populates="assignments")
    node: Mapped[Node] = relationship(back_populates="assignments")


# ---------------------------------------------------------------------------
# USAGE LEDGER (Document 3, §K — append-only by design)
# ---------------------------------------------------------------------------


class UsageEvent(Base):
    __tablename__ = "usage_events"
    __table_args__ = (
        # the idempotency key — never remove this
        Index("uq_usage_events_connection_sequence", "connection_id", "sequence_number", unique=True),
        Index("idx_usage_events_configuration", "configuration_id", "reported_at"),
        Index("idx_usage_events_node", "node_id", "reported_at"),
    )

    id: Mapped[str] = _uuid_pk()
    configuration_id: Mapped[str] = mapped_column(ForeignKey("configurations.id"), nullable=False)
    node_id: Mapped[str] = mapped_column(ForeignKey("nodes.id"), nullable=False)
    connection_id: Mapped[str] = mapped_column(Text, nullable=False)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    bytes_up: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    bytes_down: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reported_at: Mapped[datetime] = _created_at()


class UsageDailyAggregate(Base):
    __tablename__ = "usage_daily_aggregates"

    configuration_id: Mapped[str] = mapped_column(ForeignKey("configurations.id"), primary_key=True)
    usage_date: Mapped[date] = mapped_column(Date, primary_key=True)
    bytes_up: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    bytes_down: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    total_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")


class ConfigurationActiveSession(Base):
    __tablename__ = "configuration_active_sessions"

    configuration_id: Mapped[str] = mapped_column(ForeignKey("configurations.id"), primary_key=True)
    current_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    max_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    last_updated_at: Mapped[datetime] = _created_at()


class NodeHealthSample(Base):
    __tablename__ = "node_health_samples"
    __table_args__ = (
        CheckConstraint(
            "check_type IN ('control_plane', 'data_plane', 'dns')",
            name="ck_health_samples_check_type",
        ),
        Index("idx_health_samples_node_time", "node_id", "checked_at"),
    )

    id: Mapped[str] = _uuid_pk()
    node_id: Mapped[str] = mapped_column(ForeignKey("nodes.id"), nullable=False)
    check_type: Mapped[str] = mapped_column(Text, nullable=False)
    success: Mapped[bool] = mapped_column(nullable=False)
    latency_ms: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    jitter_ms: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    packet_loss: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    checked_at: Mapped[datetime] = _created_at()

    node: Mapped[Node] = relationship(back_populates="health_samples")


# ---------------------------------------------------------------------------
# BOT STATE, AUDIT, NOTIFICATIONS
# ---------------------------------------------------------------------------


class TelegramBotState(Base):
    __tablename__ = "telegram_bot_state"

    telegram_user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    state: Mapped[str] = mapped_column(Text, nullable=False, server_default="IDLE")
    context_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    updated_at: Mapped[datetime] = _created_at()


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        CheckConstraint("actor_type IN ('admin', 'system')", name="ck_audit_log_actor_type"),
        Index("idx_audit_log_target", "target_type", "target_id"),
    )

    id: Mapped[str] = _uuid_pk()
    actor_type: Mapped[str] = mapped_column(Text, nullable=False)
    actor_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False))
    action: Mapped[str] = mapped_column(Text, nullable=False)
    target_type: Mapped[str] = mapped_column(Text, nullable=False)
    target_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False))
    details_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = _created_at()


class NotificationsLog(Base):
    __tablename__ = "notifications_log"
    __table_args__ = (
        Index("idx_notifications_customer_type", "customer_id", "notification_type"),
    )

    id: Mapped[str] = _uuid_pk()
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), nullable=False)
    notification_type: Mapped[str] = mapped_column(Text, nullable=False)
    sent_at: Mapped[datetime] = _created_at()
