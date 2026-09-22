"""Initial schema — all 21 tables + aggregate-increment trigger.

Revision ID: 001
Revises:
Create Date: auto

Mirrors `schema.sql` at the repo root, table for table. Every change to
`db/models.py` must update `schema.sql` and be done as a NEW migration.

Includes the usage-ledger aggregate mechanism (schema.sql §K #4): an
AFTER INSERT trigger on `usage_events` upserts `usage_daily_aggregates`,
so quota checks read aggregates that are always fresh without a scan.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")  # gen_random_uuid()
    # --- admins -------------------------------------------------
    op.execute("""
        CREATE TABLE admins (
            id UUID DEFAULT gen_random_uuid() NOT NULL, 
            telegram_user_id BIGINT NOT NULL, 
            role TEXT NOT NULL, 
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
            created_by UUID, 
            PRIMARY KEY (id), 
            CONSTRAINT ck_admins_role CHECK (role IN ('OWNER', 'ADMIN', 'SUPPORT', 'FINANCE', 'INFRASTRUCTURE')), 
            UNIQUE (telegram_user_id), 
            FOREIGN KEY(created_by) REFERENCES admins (id)
        )
    """)

    # --- audit_log ----------------------------------------------
    op.execute("""
        CREATE TABLE audit_log (
            id UUID DEFAULT gen_random_uuid() NOT NULL, 
            actor_type TEXT NOT NULL, 
            actor_id UUID, 
            action TEXT NOT NULL, 
            target_type TEXT NOT NULL, 
            target_id UUID, 
            details_json JSONB DEFAULT '{}'::jsonb NOT NULL, 
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
            PRIMARY KEY (id), 
            CONSTRAINT ck_audit_log_actor_type CHECK (actor_type IN ('admin', 'system'))
        )
    """)

    # --- cloudflare_accounts ------------------------------------
    op.execute("""
        CREATE TABLE cloudflare_accounts (
            id UUID DEFAULT gen_random_uuid() NOT NULL, 
            label TEXT NOT NULL, 
            cf_account_id TEXT NOT NULL, 
            api_token_encrypted BYTEA NOT NULL, 
            status TEXT DEFAULT 'active' NOT NULL, 
            added_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
            PRIMARY KEY (id), 
            CONSTRAINT ck_cloudflare_accounts_status CHECK (status IN ('active', 'suspended', 'decommissioned')), 
            UNIQUE (cf_account_id)
        )
    """)

    # --- customers ----------------------------------------------
    op.execute("""
        CREATE TABLE customers (
            id UUID DEFAULT gen_random_uuid() NOT NULL, 
            telegram_user_id BIGINT NOT NULL, 
            telegram_username TEXT, 
            display_name TEXT, 
            language TEXT DEFAULT 'fa' NOT NULL, 
            status TEXT DEFAULT 'active' NOT NULL, 
            first_seen_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
            last_interaction_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
            PRIMARY KEY (id), 
            CONSTRAINT ck_customers_status CHECK (status IN ('active', 'banned')), 
            UNIQUE (telegram_user_id)
        )
    """)

    # --- gaming_profiles ----------------------------------------
    op.execute("""
        CREATE TABLE gaming_profiles (
            id UUID DEFAULT gen_random_uuid() NOT NULL, 
            version INTEGER NOT NULL, 
            name TEXT NOT NULL, 
            settings_json JSONB NOT NULL, 
            is_current BOOLEAN DEFAULT 'false' NOT NULL, 
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
            PRIMARY KEY (id)
        )
    """)

    # --- pools --------------------------------------------------
    op.execute("""
        CREATE TABLE pools (
            id UUID DEFAULT gen_random_uuid() NOT NULL, 
            name TEXT NOT NULL, 
            capability_tags TEXT[] DEFAULT '{}'::text[] NOT NULL, 
            selection_strategy TEXT DEFAULT 'round_robin' NOT NULL, 
            min_health_score NUMERIC(5, 2) DEFAULT '50' NOT NULL, 
            max_customers_per_node INTEGER DEFAULT '3' NOT NULL, 
            backup_count INTEGER DEFAULT '0' NOT NULL, 
            PRIMARY KEY (id), 
            CONSTRAINT ck_pools_selection_strategy CHECK (selection_strategy IN ('round_robin','least_loaded','sticky_score')), 
            UNIQUE (name)
        )
    """)

    # --- telegram_bot_state -------------------------------------
    op.execute("""
        CREATE TABLE telegram_bot_state (
            telegram_user_id BIGSERIAL NOT NULL, 
            state TEXT DEFAULT 'IDLE' NOT NULL, 
            context_json JSONB DEFAULT '{}'::jsonb NOT NULL, 
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
            PRIMARY KEY (telegram_user_id)
        )
    """)

    # --- nodes --------------------------------------------------
    op.execute("""
        CREATE TABLE nodes (
            id UUID DEFAULT gen_random_uuid() NOT NULL, 
            cloudflare_account_id UUID NOT NULL, 
            worker_script_name TEXT NOT NULL, 
            custom_domain TEXT, 
            capability_tags TEXT[] DEFAULT '{}'::text[] NOT NULL, 
            control_plane_health BOOLEAN DEFAULT 'false' NOT NULL, 
            data_plane_health BOOLEAN DEFAULT 'false' NOT NULL, 
            health_score NUMERIC(5, 2) DEFAULT '0' NOT NULL, 
            current_assignment_count INTEGER DEFAULT '0' NOT NULL, 
            max_assignment_count INTEGER DEFAULT '3' NOT NULL, 
            node_secret_hash TEXT NOT NULL, 
            state TEXT DEFAULT 'PROVISIONING' NOT NULL, 
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
            PRIMARY KEY (id), 
            CONSTRAINT ck_nodes_state CHECK (state IN ('PROVISIONING','ONLINE','DEGRADED','OFFLINE','MAINTENANCE','QUARANTINED','DECOMMISSIONED')), 
            FOREIGN KEY(cloudflare_account_id) REFERENCES cloudflare_accounts (id)
        )
    """)

    # --- notifications_log --------------------------------------
    op.execute("""
        CREATE TABLE notifications_log (
            id UUID DEFAULT gen_random_uuid() NOT NULL, 
            customer_id UUID NOT NULL, 
            notification_type TEXT NOT NULL, 
            sent_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
            PRIMARY KEY (id), 
            FOREIGN KEY(customer_id) REFERENCES customers (id)
        )
    """)

    # --- plans --------------------------------------------------
    op.execute("""
        CREATE TABLE plans (
            id UUID DEFAULT gen_random_uuid() NOT NULL, 
            name TEXT NOT NULL, 
            description TEXT, 
            price_amount NUMERIC(12, 2) NOT NULL, 
            price_currency TEXT DEFAULT 'IRR' NOT NULL, 
            duration_days INTEGER NOT NULL, 
            traffic_quota_bytes BIGINT, 
            device_limit INTEGER DEFAULT '1' NOT NULL, 
            pool_id UUID NOT NULL, 
            gaming_profile_id UUID, 
            is_active BOOLEAN DEFAULT 'true' NOT NULL, 
            PRIMARY KEY (id), 
            FOREIGN KEY(pool_id) REFERENCES pools (id), 
            FOREIGN KEY(gaming_profile_id) REFERENCES gaming_profiles (id)
        )
    """)

    # --- configurations -----------------------------------------
    op.execute("""
        CREATE TABLE configurations (
            id UUID DEFAULT gen_random_uuid() NOT NULL, 
            customer_id UUID NOT NULL, 
            plan_id UUID, 
            display_name TEXT NOT NULL, 
            suffix CHAR(5) NOT NULL, 
            subscription_token TEXT NOT NULL, 
            config_type TEXT DEFAULT 'normal' NOT NULL, 
            gaming_profile_id UUID, 
            status TEXT DEFAULT 'PENDING' NOT NULL, 
            is_test BOOLEAN DEFAULT 'false' NOT NULL, 
            test_quota_bytes BIGINT, 
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
            expires_at TIMESTAMP WITH TIME ZONE, 
            PRIMARY KEY (id), 
            CONSTRAINT ck_configurations_config_type CHECK (config_type IN ('normal', 'gaming', 'test')), 
            CONSTRAINT ck_configurations_status CHECK (status IN ('PENDING','PROVISIONING','ACTIVE','SUSPENDED','EXPIRED','DELETED')), 
            FOREIGN KEY(customer_id) REFERENCES customers (id), 
            FOREIGN KEY(plan_id) REFERENCES plans (id), 
            UNIQUE (subscription_token), 
            FOREIGN KEY(gaming_profile_id) REFERENCES gaming_profiles (id)
        )
    """)

    # --- node_health_samples ------------------------------------
    op.execute("""
        CREATE TABLE node_health_samples (
            id UUID DEFAULT gen_random_uuid() NOT NULL, 
            node_id UUID NOT NULL, 
            check_type TEXT NOT NULL, 
            success BOOLEAN NOT NULL, 
            latency_ms NUMERIC(8, 2), 
            jitter_ms NUMERIC(8, 2), 
            packet_loss NUMERIC(5, 4), 
            checked_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
            PRIMARY KEY (id), 
            CONSTRAINT ck_health_samples_check_type CHECK (check_type IN ('control_plane', 'data_plane', 'dns')), 
            FOREIGN KEY(node_id) REFERENCES nodes (id)
        )
    """)

    # --- orders -------------------------------------------------
    op.execute("""
        CREATE TABLE orders (
            id UUID DEFAULT gen_random_uuid() NOT NULL, 
            customer_id UUID NOT NULL, 
            plan_id UUID NOT NULL, 
            requested_display_name TEXT NOT NULL, 
            status TEXT DEFAULT 'CREATED' NOT NULL, 
            idempotency_key TEXT NOT NULL, 
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
            PRIMARY KEY (id), 
            CONSTRAINT ck_orders_status CHECK (status IN ('CREATED','AWAITING_PAYMENT','PAID','PROVISIONING','FULFILLED','REJECTED','CANCELLED')), 
            FOREIGN KEY(customer_id) REFERENCES customers (id), 
            FOREIGN KEY(plan_id) REFERENCES plans (id), 
            UNIQUE (idempotency_key)
        )
    """)

    # --- pool_nodes ---------------------------------------------
    op.execute("""
        CREATE TABLE pool_nodes (
            pool_id UUID NOT NULL, 
            node_id UUID NOT NULL, 
            PRIMARY KEY (pool_id, node_id), 
            FOREIGN KEY(pool_id) REFERENCES pools (id) ON DELETE CASCADE, 
            FOREIGN KEY(node_id) REFERENCES nodes (id) ON DELETE CASCADE
        )
    """)

    # --- configuration_active_sessions --------------------------
    op.execute("""
        CREATE TABLE configuration_active_sessions (
            configuration_id UUID NOT NULL, 
            current_count INTEGER DEFAULT '0' NOT NULL, 
            max_count INTEGER DEFAULT '1' NOT NULL, 
            last_updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
            PRIMARY KEY (configuration_id), 
            FOREIGN KEY(configuration_id) REFERENCES configurations (id)
        )
    """)

    # --- configuration_node_assignments -------------------------
    op.execute("""
        CREATE TABLE configuration_node_assignments (
            id UUID DEFAULT gen_random_uuid() NOT NULL, 
            configuration_id UUID NOT NULL, 
            node_id UUID NOT NULL, 
            role TEXT DEFAULT 'primary' NOT NULL, 
            proxy_uuid UUID NOT NULL, 
            assigned_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
            revoked_at TIMESTAMP WITH TIME ZONE, 
            PRIMARY KEY (id), 
            CONSTRAINT ck_assignments_role CHECK (role IN ('primary', 'backup')), 
            FOREIGN KEY(configuration_id) REFERENCES configurations (id), 
            FOREIGN KEY(node_id) REFERENCES nodes (id)
        )
    """)

    # --- payment_attempts ---------------------------------------
    op.execute("""
        CREATE TABLE payment_attempts (
            id UUID DEFAULT gen_random_uuid() NOT NULL, 
            order_id UUID NOT NULL, 
            method TEXT DEFAULT 'manual_proof' NOT NULL, 
            amount NUMERIC(12, 2) NOT NULL, 
            currency TEXT NOT NULL, 
            external_reference TEXT, 
            status TEXT DEFAULT 'SUBMITTED' NOT NULL, 
            reviewed_by UUID, 
            reviewed_at TIMESTAMP WITH TIME ZONE, 
            rejection_reason TEXT, 
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
            PRIMARY KEY (id), 
            CONSTRAINT ck_payment_attempts_method CHECK (method IN ('manual_proof', 'stars', 'gateway')), 
            CONSTRAINT ck_payment_attempts_status CHECK (status IN ('SUBMITTED','WAITING_REVIEW','APPROVED','REJECTED','REFUNDED')), 
            FOREIGN KEY(order_id) REFERENCES orders (id), 
            FOREIGN KEY(reviewed_by) REFERENCES admins (id)
        )
    """)

    # --- subscription_activations -------------------------------
    op.execute("""
        CREATE TABLE subscription_activations (
            id UUID DEFAULT gen_random_uuid() NOT NULL, 
            order_id UUID NOT NULL, 
            configuration_id UUID NOT NULL, 
            activated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
            PRIMARY KEY (id), 
            UNIQUE (order_id), 
            FOREIGN KEY(order_id) REFERENCES orders (id), 
            FOREIGN KEY(configuration_id) REFERENCES configurations (id)
        )
    """)

    # --- usage_daily_aggregates ---------------------------------
    op.execute("""
        CREATE TABLE usage_daily_aggregates (
            configuration_id UUID NOT NULL, 
            usage_date DATE NOT NULL, 
            bytes_up BIGINT DEFAULT '0' NOT NULL, 
            bytes_down BIGINT DEFAULT '0' NOT NULL, 
            total_bytes BIGINT DEFAULT '0' NOT NULL, 
            PRIMARY KEY (configuration_id, usage_date), 
            FOREIGN KEY(configuration_id) REFERENCES configurations (id)
        )
    """)

    # --- usage_events -------------------------------------------
    op.execute("""
        CREATE TABLE usage_events (
            id UUID DEFAULT gen_random_uuid() NOT NULL, 
            configuration_id UUID NOT NULL, 
            node_id UUID NOT NULL, 
            connection_id TEXT NOT NULL, 
            sequence_number INTEGER NOT NULL, 
            bytes_up BIGINT DEFAULT '0' NOT NULL, 
            bytes_down BIGINT DEFAULT '0' NOT NULL, 
            window_started_at TIMESTAMP WITH TIME ZONE NOT NULL, 
            reported_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
            PRIMARY KEY (id), 
            FOREIGN KEY(configuration_id) REFERENCES configurations (id), 
            FOREIGN KEY(node_id) REFERENCES nodes (id)
        )
    """)

    # --- payment_proofs -----------------------------------------
    op.execute("""
        CREATE TABLE payment_proofs (
            id UUID DEFAULT gen_random_uuid() NOT NULL, 
            payment_attempt_id UUID NOT NULL, 
            telegram_file_id TEXT NOT NULL, 
            object_storage_key TEXT, 
            mime_type TEXT, 
            size_bytes BIGINT, 
            uploaded_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
            PRIMARY KEY (id), 
            FOREIGN KEY(payment_attempt_id) REFERENCES payment_attempts (id)
        )
    """)

    op.execute("""
        CREATE INDEX idx_audit_log_target ON audit_log (target_type, target_id)
    """)

    op.execute("""
        CREATE UNIQUE INDEX uq_gaming_profiles_name_version ON gaming_profiles (name, version)
    """)

    op.execute("""
        CREATE INDEX idx_nodes_capability_tags ON nodes USING gin (capability_tags)
    """)

    op.execute("""
        CREATE INDEX idx_nodes_state ON nodes (state)
    """)

    op.execute("""
        CREATE INDEX idx_notifications_customer_type ON notifications_log (customer_id, notification_type)
    """)

    op.execute("""
        CREATE UNIQUE INDEX uq_configurations_display_name_suffix ON configurations (display_name, suffix)
    """)

    op.execute("""
        CREATE INDEX idx_configurations_customer ON configurations (customer_id)
    """)

    op.execute("""
        CREATE INDEX idx_configurations_test_lookup ON configurations (customer_id) WHERE is_test = true
    """)

    op.execute("""
        CREATE INDEX idx_health_samples_node_time ON node_health_samples (node_id, checked_at)
    """)

    op.execute("""
        CREATE INDEX idx_orders_customer ON orders (customer_id)
    """)

    op.execute("""
        CREATE INDEX idx_assignments_node ON configuration_node_assignments (node_id) WHERE revoked_at IS NULL
    """)

    op.execute("""
        CREATE INDEX idx_assignments_configuration ON configuration_node_assignments (configuration_id) WHERE revoked_at IS NULL
    """)

    op.execute("""
        CREATE INDEX idx_payment_attempts_status ON payment_attempts (status) WHERE status = 'WAITING_REVIEW'
    """)

    op.execute("""
        CREATE INDEX idx_payment_attempts_order ON payment_attempts (order_id)
    """)

    op.execute("""
        CREATE INDEX idx_usage_events_configuration ON usage_events (configuration_id, reported_at)
    """)

    op.execute("""
        CREATE UNIQUE INDEX uq_usage_events_connection_sequence ON usage_events (connection_id, sequence_number)
    """)

    op.execute("""
        CREATE INDEX idx_usage_events_node ON usage_events (node_id, reported_at)
    """)


    # --- usage-ledger aggregate mechanism (schema.sql §K #4) ---------------
    # An AFTER INSERT trigger on `usage_events` upserts `usage_daily_aggregates`
    # atomically per event, so quota checks read aggregates that are always
    # fresh without scanning the ledger. `workers.usage_aggregator` only
    # reconciles drift (Phase 5 adds the full reconciliation cron).
    op.execute("""
        CREATE OR REPLACE FUNCTION fn_usage_event_aggregate()
        RETURNS trigger AS $$
        BEGIN
            INSERT INTO usage_daily_aggregates (
                configuration_id, usage_date, bytes_up, bytes_down, total_bytes
            ) VALUES (
                NEW.configuration_id, (NEW.reported_at AT TIME ZONE 'UTC')::date,
                NEW.bytes_up, NEW.bytes_down, NEW.bytes_up + NEW.bytes_down
            )
            ON CONFLICT (configuration_id, usage_date) DO UPDATE SET
                bytes_up = usage_daily_aggregates.bytes_up + EXCLUDED.bytes_up,
                bytes_down = usage_daily_aggregates.bytes_down + EXCLUDED.bytes_down,
                total_bytes = usage_daily_aggregates.total_bytes + EXCLUDED.total_bytes;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)

    op.execute("""
        CREATE TRIGGER trg_usage_events_aggregate
        AFTER INSERT ON usage_events
        FOR EACH ROW
        EXECUTE FUNCTION fn_usage_event_aggregate()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_usage_events_aggregate ON usage_events")
    op.execute("DROP FUNCTION IF EXISTS fn_usage_event_aggregate()")
