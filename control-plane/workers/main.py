"""Verdent Platform — worker service entrypoint (Railway service: `worker`).

Per Dockerfile: start = `python -m workers.main`

Responsibilities (Document 6 §N — all sub-5-minute loops live here, not in
Railway cron):
  1. Job queue consumer (provisioning retries — Phase 2)
  2. Usage reconciliation loop (Phase 5 — repairs aggregate drift)
  3. Node health-check loop (Phase 2/3 — hysteresis + failover)
  4. Quota/expiry push loop (Phase 5 — disable over-quota credentials at the edge)
"""

import asyncio
import logging

from domain.health import HEALTH_CHECK_INTERVAL, health_check_pass
from domain.notifications import expiry_and_quota_sweep
from domain.reconcile import reconcile_usage

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("verdent.worker")

RECONCILE_INTERVAL = 300          # 5 min
QUOTA_PUSH_INTERVAL = 300         # 5 min


async def job_queue_loop() -> None:
    """Job queue consumer — provisioning retries. Orders stuck in
    PROVISIONING are visible in the admin panel and retried from there."""
    logger.info("job queue consumer: orders retry via admin panel (provisioning Phase 2)")
    while True:
        await asyncio.sleep(3600)


async def usage_reconcile_loop() -> None:
    logger.info("reconciliation loop started (every %ss)", RECONCILE_INTERVAL)
    while True:
        try:
            await reconcile_usage()
        except Exception:  # noqa: BLE001
            logger.exception("reconciliation failed")
        await asyncio.sleep(RECONCILE_INTERVAL)


async def health_loop() -> None:
    logger.info("health loop started (every %ss)", HEALTH_CHECK_INTERVAL)
    while True:
        try:
            await health_check_pass()
        except Exception:  # noqa: BLE001
            logger.exception("health pass failed")
        await asyncio.sleep(HEALTH_CHECK_INTERVAL)


async def quota_push_loop() -> None:
    logger.info("quota/expiry push loop started (every %ss)", QUOTA_PUSH_INTERVAL)
    while True:
        try:
            await expiry_and_quota_sweep()
        except Exception:  # noqa: BLE001
            logger.exception("quota sweep failed")
        await asyncio.sleep(QUOTA_PUSH_INTERVAL)


async def main() -> None:
    logger.info("verdent worker starting")
    await asyncio.gather(
        job_queue_loop(),
        usage_reconcile_loop(),
        health_loop(),
        quota_push_loop(),
    )


if __name__ == "__main__":
    asyncio.run(main())
