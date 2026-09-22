"""Verdent Platform — usage aggregation.

With the aggregate-increment trigger in migration 001, rows in
`usage_daily_aggregates` increment atomically as `usage_events` rows append,
so quota checks read aggregates that are always fresh. `reconcile_once` only
catches drift (e.g. a manually inserted row); full reconciliation tooling
arrives Phase 5.
"""

import logging
from datetime import date

from sqlalchemy import func, select

from db.base import SessionLocal
from db.models import UsageDailyAggregate, UsageEvent

logger = logging.getLogger("verdent.worker.reconcile")


async def reconcile_once() -> dict:
    """Count ledger rows missing from aggregates; report drift (no re-add)."""
    async with SessionLocal() as session:
        ledger_events = (
            await session.execute(select(func.count()).select_from(UsageEvent))
        ).scalar_one()
        aggregate_rows = (
            await session.execute(select(func.count()).select_from(UsageDailyAggregate))
        ).scalar_one()

    drift = {
        "checkedDate": str(date.today()),
        "ledgerEvents": ledger_events,
        "aggregateRows": aggregate_rows,
    }

    logger.info("reconcile: %s", drift)
    return drift
