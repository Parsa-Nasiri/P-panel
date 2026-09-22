"""One-off: generate Alembic migration 001 from ORM metadata, offline."""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")
os.chdir(os.path.dirname(os.path.abspath(__file__)) + "/..")

from sqlalchemy.schema import CreateTable, CreateIndex  # noqa: E402
from sqlalchemy.dialects import postgresql  # noqa: E402

from db.models import Base  # noqa: E402

HEADER = '''"""Initial schema — all 21 tables + aggregate-increment trigger.

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
'''

FOOTER = '''

def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_usage_events_aggregate ON usage_events")
    op.execute("DROP FUNCTION IF EXISTS fn_usage_event_aggregate()")
'''

TRIGGER_SQL = '''
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
'''


def main() -> None:
    dialect = postgresql.dialect()
    lines = [HEADER]

    for table in Base.metadata.sorted_tables:
        ddl = str(CreateTable(table).compile(dialect=dialect)).strip()
        ddl = re.sub(r"\n\s+", "\n    ", ddl)
        lines.append("    # --- " + table.name + " " + "-" * max(1, 55 - len(table.name)) + "\n")
        lines.append('    op.execute("""\n')
        for line in ddl.splitlines():
            lines.append("        " + line + "\n")
        lines.append('    """)\n\n')

    for table in Base.metadata.sorted_tables:
        for index in table.indexes:
            stmt = str(CreateIndex(index).compile(dialect=dialect)).strip()
            lines.append('    op.execute("""\n')
            for line in stmt.splitlines():
                lines.append("        " + line + "\n")
            lines.append('    """)\n\n')

    lines.append(TRIGGER_SQL)
    lines.append(FOOTER)

    out_path = os.path.join("db", "migrations", "versions", "001_initial.py")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("".join(lines))

    print("migration written:", out_path)
    print("tables:", len(Base.metadata.sorted_tables))


if __name__ == "__main__":
    main()
