"""Verdent Platform — worker service entrypoint (Railway service: `worker`).

Per Dockerfile: start = `python -m workers.main`

Phase 0 scaffolds the two responsibilities (Document 6 §N):
  1. Job queue consumer  — provisioning comes Phase 2; scaffolds the loop now.
  2. Usage aggregation   — with the aggregate-increment trigger in migration
     001, rows increment as events append; this loop only reconciles.
"""

import asyncio
import logging

from workers.usage_aggregator import reconcile_once

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("verdent.worker")

RECONCILE_INTERVAL_SECONDS = 60


async def job_queue_loop() -> None:
    """Job queue consumer — provisioning arrives Phase 2."""
    logger.info("job queue consumer scaffolding (provisioning Phase 2)")
    while True:
        await asyncio.sleep(3600)


async def usage_reconcile_loop() -> None:
    """Reconcile aggregates vs ledger — normally a no-op behind the trigger."""
    logger.info("usage reconciliation loop started (every %ss)", RECONCILE_INTERVAL_SECONDS)
    while True:
        try:
            await reconcile_once()
        except Exception:  # noqa: BLE001
            logger.exception("usage reconciliation failed")
        await asyncio.sleep(RECONCILE_INTERVAL_SECONDS)


async def main() -> None:
    logger.info("verdent worker starting")
    await asyncio.gather(job_queue_loop(), usage_reconcile_loop())


if __name__ == "__main__":
    asyncio.run(main())
