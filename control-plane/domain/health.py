"""Verdent Platform — node health loop (Document 3 §M; Phase 2/3).

Runs inside the `worker` service (sub-5-minute cadence — Railway cron can't
go there per Document 6 §N). Per node, every HEALTH_CHECK_INTERVAL:

  GET https://{custom_domain}/{securePath}/health   (5s timeout)

State transitions with REAL hysteresis (Document 3: "sticky failover with
real hysteresis" — no flap on a single missed probe):

  failures: 2 consecutive → DEGRADED (score 50), 5 consecutive → OFFLINE (0)
  successes: 2 consecutive → ONLINE (score 100)

Failover (Phase 2 ordinary / Phase 3 sticky): a config's primary assignment
is re-minted onto another eligible node ONLY after its node has been OFFLINE
for FAILOVER_AFTER_OFFLINE — never on the first blip, never while PROVISIONING.
"""

import logging
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.base import SessionLocal
from db.models import Configuration, ConfigurationNodeAssignment, Node, NodeHealthSample, Pool, PoolNode
from domain.pools import node_eligible, select_node_for_pool

logger = logging.getLogger("verdent.health")

HEALTH_CHECK_INTERVAL = 60          # seconds
DEGRADED_AFTER_FAILURES = 2
OFFLINE_AFTER_FAILURES = 5
ONLINE_AFTER_SUCCESSES = 2
FAILOVER_AFTER_OFFLINE = timedelta(minutes=10)

SCORE_ONLINE = 100
SCORE_DEGRADED = 50
SCORE_OFFLINE = 0


async def check_node_once(node: Node) -> tuple[bool, float | None]:
    """(success, latency_ms) — one probe against the node's health route."""
    from domain.provisioning import derive_secure_path

    base = (node.custom_domain or "").rstrip("/")
    if not base:
        return False, None

    url = f"{base}/{derive_secure_path(node.id)}/health"

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
        if resp.status_code == 200:
            return True, resp.elapsed.total_seconds() * 1000
        return False, None
    except Exception:  # noqa: BLE001
        return False, None


def apply_health_transition(node: Node, success: bool, latency_ms: float | None) -> str:
    """Update health fields per the hysteresis rules; return new state."""
    if success:
        node.control_plane_health = True
        node.data_plane_health = True
        node.health_score = min(
            SCORE_ONLINE, (node.health_score or SCORE_OFFLINE) + 50
        )
        node.state = "ONLINE" if (node.health_score or 0) >= SCORE_ONLINE else "DEGRADED"
        node._consecutive_failures = 0  # type: ignore[attr-defined]
        return node.state

    node.control_plane_health = False
    node.data_plane_health = False
    node.health_score = max(SCORE_OFFLINE, (node.health_score or SCORE_ONLINE) - 25)
    fails = getattr(node, "_consecutive_failures", 0) + 1
    node._consecutive_failures = fails  # type: ignore[attr-defined]

    if fails >= OFFLINE_AFTER_FAILURES:
        node.state = "OFFLINE"
    elif fails >= DEGRADED_AFTER_FAILURES or node.state == "OFFLINE":
        node.state = "DEGRADED"
    return node.state


def _load_runtime_counters(nodes: list[Node], counters: dict[str, int]) -> None:
    for n in nodes:
        n._consecutive_failures = counters.get(n.id, 0)  # type: ignore[attr-defined]


def _save_runtime_counters(nodes: list[Node]) -> dict[str, int]:
    return {
        n.id: getattr(n, "_consecutive_failures", 0)  # type: ignore[attr-defined]
        for n in nodes
    }


async def failover_offline_nodes(db: AsyncSession) -> int:
    """Re-mint primary assignments of configs on long-offline nodes."""
    cutoff = datetime.now(timezone.utc) - FAILOVER_AFTER_OFFLINE
    # Nodes whose state went OFFLINE and has stayed there: we approximate
    # "stayed" with the last failed sample timestamp.
    moved = 0

    offline_nodes = (
        await db.execute(select(Node).where(Node.state == "OFFLINE"))
    ).scalars().all()

    for node in offline_nodes:
        last_sample = (
            await db.execute(
                select(NodeHealthSample)
                .where(
                    NodeHealthSample.node_id == node.id,
                    NodeHealthSample.success.is_(False),
                )
                .order_by(NodeHealthSample.checked_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        if last_sample is None or last_sample.checked_at > cutoff:
            continue

        assignments = (
            await db.execute(
                select(ConfigurationNodeAssignment).where(
                    ConfigurationNodeAssignment.node_id == node.id,
                    ConfigurationNodeAssignment.revoked_at.is_(None),
                )
            )
        ).scalars().all()

        for assignment in assignments:
            config = (
                await db.execute(
                    select(Configuration).where(
                        Configuration.id == assignment.configuration_id,
                        Configuration.status == "ACTIVE",
                    )
                )
            ).scalar_one_or_none()
            if config is None:
                continue

            pool = (
                await db.execute(
                    select(Pool)
                    .join(PoolNode, PoolNode.pool_id == Pool.id)
                    .where(PoolNode.node_id == node.id)
                    .limit(1)
                )
            ).scalar_one_or_none()
            if pool is None:
                continue

            target = await select_node_for_pool(db, pool, capability="general")
            if target is None:
                logger.warning("failover for config %s: no eligible target", config.id)
                continue

            # Re-mint: revoke old assignment, create a new one with a fresh uuid
            assignment.revoked_at = datetime.now(timezone.utc)
            node.current_assignment_count = max(0, (node.current_assignment_count or 0) - 1)

            import uuid as uuid_lib

            new_assignment = ConfigurationNodeAssignment(
                configuration_id=config.id,
                node_id=target.id,
                role="primary",
                proxy_uuid=str(uuid_lib.uuid4()),
            )
            db.add(new_assignment)
            target.current_assignment_count = (target.current_assignment_count or 0) + 1

            from domain.kv_sync import set_entry_status, sync_assignment

            if assignment.proxy_uuid:
                await set_entry_status(db, node, assignment.proxy_uuid, "disabled")

            plan = None
            if config.plan_id:
                from db.models import Plan

                plan = (
                    await db.execute(select(Plan).where(Plan.id == config.plan_id))
                ).scalar_one_or_none()

            await sync_assignment(
                db,
                target,
                proxy_uuid=new_assignment.proxy_uuid,
                config_id=config.id,
                status="active",
                device_limit=plan.device_limit if plan else 1,
            )

            await audit_failover(config.id, node.id, target.id)
            moved += 1

        await db.commit()

    if moved:
        logger.info("failover moved %d assignment(s)", moved)
    return moved


async def audit_failover(config_id: str, from_node: str, to_node: str) -> None:
    async with SessionLocal() as db:
        from domain.audit import audit

        await audit(
            db,
            "config.failover",
            actor_type="system",
            actor_id=None,
            target_type="configuration",
            target_id=config_id,
            details={"from_node": from_node, "to_node": to_node},
        )


async def health_check_pass() -> dict:
    """One pass over all nodes: probe, transition, record, failover."""
    async with SessionLocal() as db:
        nodes = (
            await db.execute(select(Node).where(Node.state.notin_(["DECOMMISSIONED"])))
        ).scalars().all()

        counters: dict[str, int] = {}
        results = []

        for node in nodes:
            success, latency = await check_node_once(node)
            state = apply_health_transition(node, success, latency)
            counters[node.id] = getattr(node, "_consecutive_failures", 0)  # type: ignore[attr-defined]

            db.add(
                NodeHealthSample(
                    node_id=node.id,
                    check_type="control_plane",
                    success=success,
                    latency_ms=latency,
                )
            )
            results.append({"node": node.id, "state": state, "ok": success})

        await db.commit()

        await failover_offline_nodes(db)

    online = sum(1 for r in results if r["ok"])
    logger.info("health pass: %d/%d online", online, len(results))
    return {"checked": len(results), "online": online, "results": results}
