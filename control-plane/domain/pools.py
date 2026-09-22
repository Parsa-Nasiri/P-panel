"""Verdent Platform — pool selection & node admission (Phase 2).

Eligibility gate first (state, capacity, capability, health floor), then the
pool's strategy picks among eligible nodes:
- least_loaded: fewest current_assignment_count (default)
- round_robin: least recently assigned (max assigned_at among actives)
- sticky_score: health-score weighted least-loaded (gaming, Phase 3)
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import ConfigurationNodeAssignment, Node, Pool, PoolNode

logger = logging.getLogger("verdent.pools")

ELIGIBLE_STATES = {"ONLINE", "DEGRADED"}


def node_eligible(node: Node, pool: Pool, capability: str = "general") -> bool:
    if node.state not in ELIGIBLE_STATES:
        return False
    if node.current_assignment_count >= node.max_assignment_count:
        return False
    tags = set(node.capability_tags or [])
    if capability not in tags:
        return False
    if node.health_score is not None and node.health_score < pool.min_health_score:
        return False
    return True


async def select_node_for_pool(
    db: AsyncSession, pool: Pool | None, capability: str = "general"
) -> Node | None:
    """Pick the best eligible node in this pool, or None."""
    if pool is None:
        return None

    candidates = (
        await db.execute(
            select(Node)
            .join(PoolNode, PoolNode.node_id == Node.id)
            .where(PoolNode.pool_id == pool.id)
        )
        .scalars()
        .all()
    )

    eligible = [n for n in candidates if node_eligible(n, pool, capability)]
    if not eligible:
        return None

    if pool.selection_strategy == "round_robin":
        # least recently assigned among actives
        last_assigned: dict[str, datetime] = {}
        epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
        for candidate in eligible:
            row = (
                await db.execute(
                    select(ConfigurationNodeAssignment.assigned_at)
                    .where(
                        ConfigurationNodeAssignment.node_id == candidate.id,
                        ConfigurationNodeAssignment.revoked_at.is_(None),
                    )
                    .order_by(ConfigurationNodeAssignment.assigned_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            last_assigned[candidate.id] = row or epoch

        return min(eligible, key=lambda n: last_assigned[n.id])

    if pool.selection_strategy == "sticky_score":
        # health-weighted: prefer high score, then low load
        return max(
            eligible,
            key=lambda n: (float(n.health_score or 0), -n.current_assignment_count),
        )

    # least_loaded (default)
    return min(eligible, key=lambda n: n.current_assignment_count)
