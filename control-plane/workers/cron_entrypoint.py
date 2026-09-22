"""Verdent Platform — cron service entrypoint (Railway service: `cron`).

Per Dockerfile: start = `python -m workers.cron_entrypoint`

Phase 0 scaffolds the daily jobs (Document 3, #5; Document 6):
  - Expiry sweep: configurations whose expires_at has passed -> EXPIRED (Phase 3).
  - Quota-flag push: near/over-limit flags onto node KV (Phase 5, cron).
"""

import asyncio
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("verdent.cron")

INTERVAL_SECONDS = 60


async def expiry_sweep() -> None:
    logger.info("expiry sweep scaffolding (Phase 3)")


async def quota_flag_push() -> None:
    logger.info("quota-flag push scaffolding (Phase 5)")


async def main() -> None:
    logger.info("verdent cron starting")
    while True:
        await expiry_sweep()
        await quota_flag_push()
        await asyncio.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
