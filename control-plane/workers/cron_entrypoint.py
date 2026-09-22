"""Verdent Platform — cron service entrypoint (Railway service: `cron`).

Per Dockerfile: start = `python -m workers.cron_entrypoint`

The ≥5-minute jobs (Railway's native cron granularity, Document 6 §N) run
here on a simple internal schedule:
  - expiry + quota sweep (5 min) — customer notifications & edge disables
  - usage reconciliation runs in the worker service, NOT here
"""

import asyncio
import logging

from domain.notifications import expiry_and_quota_sweep

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("verdent.cron")

SWEEP_INTERVAL = 300  # 5 min


async def main() -> None:
    logger.info("verdent cron starting (sweep every %ss)", SWEEP_INTERVAL)
    while True:
        try:
            await expiry_and_quota_sweep()
        except Exception:  # noqa: BLE001
            logger.exception("sweep failed")
        await asyncio.sleep(SWEEP_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())
