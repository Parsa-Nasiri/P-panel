"""Verdent Platform — Phase 0 usage-ledger validation.

Run AFTER the manual Node test (see node-worker/docs/provision-manual.md §5)
with DATABASE_URL pointed at the same Postgres the Worker reported to:

    cd control-plane
    python scripts/verify_usage.py

Prints, per Configuration, the summed ledger bytes vs the maintained daily
aggregate — the two numbers must match exactly (the trigger guarantees it;
any mismatch here is a Phase 0 blocker, not a data quirk).
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, func  # noqa: E402

from db.base import SessionLocal  # noqa: E402
from db.models import UsageDailyAggregate, UsageEvent  # noqa: E402


async def main() -> None:
    async with SessionLocal() as session:
        ledger = (
            await session.execute(
                select(
                    UsageEvent.configuration_id,
                    func.count().label("events"),
                    func.sum(UsageEvent.bytes_up).label("up"),
                    func.sum(UsageEvent.bytes_down).label("down"),
                ).group_by(UsageEvent.configuration_id)
            )
        ).all()

        aggregates = (
            await session.execute(
                select(
                    UsageDailyAggregate.configuration_id,
                    func.sum(UsageDailyAggregate.total_bytes).label("total"),
                ).group_by(UsageDailyAggregate.configuration_id)
            )
        ).all()

    agg_by_cfg = {row.configuration_id: int(row.total or 0) for row in aggregates}

    print(f"{'configuration_id':<40} {'events':>7} {'up':>12} {'down':>12} {'ledger':>13} {'aggregate':>13} {'match':>6}")
    print("-" * 105)

    ok = True
    for row in ledger:
        cfg, events, up, down = row[0], row[1], int(row[2] or 0), int(row[3] or 0)
        total = up + down
        agg = agg_by_cfg.pop(cfg, 0)
        match = total == agg
        ok = ok and match
        print(f"{cfg:<40} {events:>7} {up:>12} {down:>12} {total:>13} {agg:>13} {'OK' if match else 'MISMATCH':>6}")

    for cfg, agg in agg_by_cfg.items():
        ok = ok and agg == 0
        print(f"{cfg:<40} {'-':>7} {'-':>12} {'-':>12} {'0':>13} {agg:>13} {'OK' if agg == 0 else 'MISMATCH':>6}")

    print("-" * 105)
    print("RESULT:", "PASS — ledger and aggregates agree" if ok else "FAIL — investigate mismatches above")


if __name__ == "__main__":
    asyncio.run(main())
