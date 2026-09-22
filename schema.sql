-- BPB Commercial Platform — Database Schema (Railway Postgres)
-- Companion to 03-database-schema-and-api-design.md
-- Design notes, rationale, and what was deliberately left out live in that document —
-- this file is the runnable DDL, not the explanation.

CREATE EXTENSION IF NOT EXISTS pgcrypto; -- for gen_random_uuid()

-- ============================================================================
-- IDENTITY
-- ============================================================================

CREATE TABLE customers (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    telegram_user_id    BIGINT NOT NULL UNIQUE,          -- the stable identity — never username
    telegram_username   TEXT,                            -- cosmetic only, can change or be null
    display_name        TEXT,
    language             TEXT NOT NULL DEFAULT 'fa',
    status               TEXT NOT NULL DEFAULT 'active'
                          CHECK (status IN ('active', 'banned')),
    first_seen_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_interaction_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE admins (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    telegram_user_id    BIGINT NOT NULL UNIQUE,
    role                TEXT NOT NULL
                         CHECK (role IN ('OWNER', 'ADMIN', 'SUPPORT', 'FINANCE', 'INFRASTRUCTURE')),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by          UUID REFERENCES admins(id)       -- NULL only for the bootstrap OWNER
);

-- ============================================================================
-- INFRASTRUCTURE (data plane registry)
-- ============================================================================

CREATE TABLE cloudflare_accounts (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    label               TEXT NOT NULL,
    cf_account_id       TEXT NOT NULL UNIQUE,
    api_token_encrypted BYTEA NOT NULL,                  -- encrypted at rest, see Document 5
    status              TEXT NOT NULL DEFAULT 'active'
                         CHECK (status IN ('active', 'suspended', 'decommissioned')),
    added_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE nodes (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cloudflare_account_id  UUID NOT NULL REFERENCES cloudflare_accounts(id),
    worker_script_name     TEXT NOT NULL,
    custom_domain          TEXT,
    capability_tags        TEXT[] NOT NULL DEFAULT '{}', -- e.g. {general, doh, gaming-tier, warp}
    control_plane_health   BOOLEAN NOT NULL DEFAULT false,
    data_plane_health      BOOLEAN NOT NULL DEFAULT false,
    health_score           NUMERIC(5,2) NOT NULL DEFAULT 0,   -- 0-100, Document 2 scoring model
    current_assignment_count INTEGER NOT NULL DEFAULT 0,
    max_assignment_count   INTEGER NOT NULL DEFAULT 3,        -- BPB's own "2-3 users, free tier" finding
    node_secret_hash       TEXT NOT NULL,                     -- for HMAC-auth'ing this node's own calls
    state                  TEXT NOT NULL DEFAULT 'PROVISIONING'
                            CHECK (state IN ('PROVISIONING','ONLINE','DEGRADED','OFFLINE',
                                              'MAINTENANCE','QUARANTINED','DECOMMISSIONED')),
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_nodes_state ON nodes(state);
CREATE INDEX idx_nodes_capability_tags ON nodes USING GIN(capability_tags);

CREATE TABLE pools (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                   TEXT NOT NULL UNIQUE,
    capability_tags        TEXT[] NOT NULL DEFAULT '{}',
    selection_strategy     TEXT NOT NULL DEFAULT 'round_robin'
                            CHECK (selection_strategy IN ('round_robin','least_loaded','sticky_score')),
    min_health_score       NUMERIC(5,2) NOT NULL DEFAULT 50,
    max_customers_per_node INTEGER NOT NULL DEFAULT 3,
    backup_count           INTEGER NOT NULL DEFAULT 0     -- 0 for cheap tiers, 1-2 for gaming/premium
);

CREATE TABLE pool_nodes (
    pool_id     UUID NOT NULL REFERENCES pools(id) ON DELETE CASCADE,
    node_id     UUID NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    PRIMARY KEY (pool_id, node_id)
);

CREATE TABLE gaming_profiles (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    version       INTEGER NOT NULL,
    name          TEXT NOT NULL,                          -- e.g. "Gaming Profile v3"
    settings_json JSONB NOT NULL,                          -- mtu_hint, doh_endpoint, thresholds, etc.
    is_current    BOOLEAN NOT NULL DEFAULT false,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (name, version)
);

-- ============================================================================
-- COMMERCE
-- ============================================================================

CREATE TABLE plans (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                TEXT NOT NULL,
    description         TEXT,
    price_amount        NUMERIC(12,2) NOT NULL,
    price_currency      TEXT NOT NULL DEFAULT 'IRR',
    duration_days       INTEGER NOT NULL,
    traffic_quota_bytes BIGINT,                            -- NULL = unlimited
    device_limit        INTEGER NOT NULL DEFAULT 1,
    pool_id             UUID NOT NULL REFERENCES pools(id),
    gaming_profile_id   UUID REFERENCES gaming_profiles(id), -- set only for gaming plans
    is_active           BOOLEAN NOT NULL DEFAULT true
);

CREATE TABLE orders (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id              UUID NOT NULL REFERENCES customers(id),
    plan_id                  UUID NOT NULL REFERENCES plans(id),
    requested_display_name   TEXT NOT NULL,
    status                   TEXT NOT NULL DEFAULT 'CREATED'
                             CHECK (status IN ('CREATED','AWAITING_PAYMENT','PAID',
                                                'PROVISIONING','FULFILLED','REJECTED','CANCELLED')),
    idempotency_key          TEXT NOT NULL UNIQUE,          -- derived from the triggering Telegram update
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_orders_customer ON orders(customer_id);

CREATE TABLE payment_attempts (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id            UUID NOT NULL REFERENCES orders(id),
    method              TEXT NOT NULL DEFAULT 'manual_proof'
                         CHECK (method IN ('manual_proof', 'stars', 'gateway')),
    amount              NUMERIC(12,2) NOT NULL,
    currency            TEXT NOT NULL,
    external_reference  TEXT,                              -- Stars/gateway transaction id, once added
    status              TEXT NOT NULL DEFAULT 'SUBMITTED'
                         CHECK (status IN ('SUBMITTED','WAITING_REVIEW','APPROVED','REJECTED','REFUNDED')),
    reviewed_by         UUID REFERENCES admins(id),
    reviewed_at         TIMESTAMPTZ,
    rejection_reason    TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_payment_attempts_order ON payment_attempts(order_id);
CREATE INDEX idx_payment_attempts_status ON payment_attempts(status) WHERE status = 'WAITING_REVIEW';

CREATE TABLE payment_proofs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    payment_attempt_id  UUID NOT NULL REFERENCES payment_attempts(id),
    telegram_file_id    TEXT NOT NULL,
    object_storage_key  TEXT,                              -- populated once async-copied to R2/S3
    mime_type           TEXT,
    size_bytes          BIGINT,
    uploaded_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================================
-- CONFIGURATIONS (the customer-facing core)
-- ============================================================================

CREATE TABLE configurations (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id         UUID NOT NULL REFERENCES customers(id),
    plan_id             UUID REFERENCES plans(id),          -- NULL for test configs
    display_name        TEXT NOT NULL,
    suffix              CHAR(5) NOT NULL,
    subscription_token  TEXT NOT NULL UNIQUE,                -- rotatable independently of proxy creds
    config_type         TEXT NOT NULL DEFAULT 'normal'
                         CHECK (config_type IN ('normal', 'gaming', 'test')),
    gaming_profile_id   UUID REFERENCES gaming_profiles(id),
    status              TEXT NOT NULL DEFAULT 'PENDING'
                         CHECK (status IN ('PENDING','PROVISIONING','ACTIVE','SUSPENDED','EXPIRED','DELETED')),
    is_test             BOOLEAN NOT NULL DEFAULT false,
    test_quota_bytes    BIGINT,                              -- e.g. 100 * 1024 * 1024 for test configs
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at          TIMESTAMPTZ,
    UNIQUE (display_name, suffix)                            -- Document 1 §D: scope is the exact name string
);
CREATE INDEX idx_configurations_customer ON configurations(customer_id);
CREATE INDEX idx_configurations_test_lookup ON configurations(customer_id) WHERE is_test = true;

CREATE TABLE subscription_activations (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id            UUID NOT NULL UNIQUE REFERENCES orders(id), -- UNIQUE = the "approve once" guarantee
    configuration_id    UUID NOT NULL REFERENCES configurations(id),
    activated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE configuration_node_assignments (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    configuration_id    UUID NOT NULL REFERENCES configurations(id),
    node_id             UUID NOT NULL REFERENCES nodes(id),
    role                TEXT NOT NULL DEFAULT 'primary' CHECK (role IN ('primary', 'backup')),
    proxy_uuid          UUID NOT NULL,                        -- the credential minted on that node
    assigned_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at          TIMESTAMPTZ
);
CREATE INDEX idx_assignments_configuration ON configuration_node_assignments(configuration_id)
    WHERE revoked_at IS NULL;
CREATE INDEX idx_assignments_node ON configuration_node_assignments(node_id) WHERE revoked_at IS NULL;

-- ============================================================================
-- USAGE LEDGER (Document 3, §K — append-only by design)
-- ============================================================================

CREATE TABLE usage_events (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    configuration_id    UUID NOT NULL REFERENCES configurations(id),
    node_id             UUID NOT NULL REFERENCES nodes(id),
    connection_id       TEXT NOT NULL,
    sequence_number     INTEGER NOT NULL,
    bytes_up            BIGINT NOT NULL DEFAULT 0,
    bytes_down          BIGINT NOT NULL DEFAULT 0,
    window_started_at   TIMESTAMPTZ NOT NULL,
    reported_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (connection_id, sequence_number)                  -- the idempotency key — never remove this
);
CREATE INDEX idx_usage_events_configuration ON usage_events(configuration_id, reported_at);
CREATE INDEX idx_usage_events_node ON usage_events(node_id, reported_at);

CREATE TABLE usage_daily_aggregates (
    configuration_id    UUID NOT NULL REFERENCES configurations(id),
    usage_date          DATE NOT NULL,
    bytes_up            BIGINT NOT NULL DEFAULT 0,
    bytes_down          BIGINT NOT NULL DEFAULT 0,
    total_bytes         BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (configuration_id, usage_date)
);

CREATE TABLE configuration_active_sessions (
    configuration_id    UUID PRIMARY KEY REFERENCES configurations(id),
    current_count       INTEGER NOT NULL DEFAULT 0,           -- display cache only — the Durable Object
    max_count           INTEGER NOT NULL DEFAULT 1,           -- at the edge is the enforcement source of truth
    last_updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE node_health_samples (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    node_id             UUID NOT NULL REFERENCES nodes(id),
    check_type          TEXT NOT NULL CHECK (check_type IN ('control_plane', 'data_plane', 'dns')),
    success             BOOLEAN NOT NULL,
    latency_ms          NUMERIC(8,2),
    jitter_ms           NUMERIC(8,2),
    packet_loss         NUMERIC(5,4),
    checked_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_health_samples_node_time ON node_health_samples(node_id, checked_at);
-- Operational note: prune/roll this table up after a retention window (e.g. hourly aggregates
-- beyond 7 days) — it's a high-write table by design and isn't meant to be kept at full
-- granularity forever.

-- ============================================================================
-- BOT STATE, AUDIT, NOTIFICATIONS
-- ============================================================================

CREATE TABLE telegram_bot_state (
    telegram_user_id    BIGINT PRIMARY KEY,
    state               TEXT NOT NULL DEFAULT 'IDLE',
    context_json        JSONB NOT NULL DEFAULT '{}',
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE audit_log (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_type          TEXT NOT NULL CHECK (actor_type IN ('admin', 'system')),
    actor_id            UUID,                                  -- references admins(id) when actor_type = 'admin'
    action              TEXT NOT NULL,
    target_type         TEXT NOT NULL,
    target_id           UUID,
    details_json        JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_audit_log_target ON audit_log(target_type, target_id);

CREATE TABLE notifications_log (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id         UUID NOT NULL REFERENCES customers(id),
    notification_type   TEXT NOT NULL,
    sent_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_notifications_customer_type ON notifications_log(customer_id, notification_type);
