import { randomUUID } from "node:crypto";
import { and, eq, asc, sql } from "drizzle-orm";
import type { Db } from "@proxy/database";
import { deviceSlots, subscriptions, plans } from "@proxy/database";
import type { GamingHysteresis, NodeState } from "@proxy/shared";
import { DEFAULT_HYSTERESIS } from "@proxy/shared";

// ---------- device slots ----------
export async function ensureSlots(db: Db, subscriptionId: string, maxDevices: number) {
  const existing = await db.select().from(deviceSlots).where(eq(deviceSlots.subscriptionId, subscriptionId));
  if (existing.length >= maxDevices) return existing;
  const toCreate = maxDevices - existing.length;
  const startIdx = existing.reduce((m, s) => Math.max(m, s.idx), -1) + 1;
  const values = Array.from({ length: toCreate }, (_, i) => ({
    subscriptionId, idx: startIdx + i, uuid: randomUUID(),
  }));
  return [...existing, ...await db.insert(deviceSlots).values(values).returning()];
}

/** Auto-assign on first import of a device link / main link. */
export async function autoAssignSlot(db: Db, subscriptionId: string, name?: string) {
  const subs = await db.select().from(subscriptions).where(eq(subscriptions.id, subscriptionId)).limit(1);
  const plan = subs[0] ? (await db.select().from(plans).where(eq(plans.id, subs[0].planId)).limit(1))[0] : null;
  if (!subs[0] || !plan) throw new Error("subscription_not_found");
  const slots = await db.select().from(deviceSlots)
    .where(and(eq(deviceSlots.subscriptionId, subscriptionId), eq(deviceSlots.status, "active")))
    .orderBy(asc(deviceSlots.idx));
  const free = slots.find((s) => !s.lastSeenAt);
  if (free) return free;
  if (slots.length < plan.maxDevices) {
    const maxIdx = slots.reduce((m, s) => Math.max(m, s.idx), -1);
    const created = await db.insert(deviceSlots)
      .values({ subscriptionId, idx: maxIdx + 1, uuid: randomUUID(), name })
      .returning();
    return created[0];
  }
  return null; // device limit reached
}

export async function revokeSlot(db: Db, slotId: string) {
  await db.update(deviceSlots)
    .set({ status: "revoked", revokedAt: new Date() })
    .where(eq(deviceSlots.id, slotId));
}

export async function releaseStaleSlots(db: Db, inactiveDays: number): Promise<number> {
  const res = await db.update(deviceSlots)
    .set({ status: "revoked", revokedAt: new Date() })
    .where(and(
      eq(deviceSlots.status, "active"),
      sql`(${deviceSlots.lastSeenAt} IS NULL OR ${deviceSlots.lastSeenAt} < now() - interval '${sql.raw(String(inactiveDays))} days')`
    ))
    .returning({ id: deviceSlots.id });
  return res.length;
}

// ---------- gaming sticky selection ----------
export interface GamingNodeSnapshot {
  id: string;
  state: NodeState;
  enabled: boolean;
  priority: number;
  recoveredAt?: Date | null;
}

export interface GamingSelectionInput {
  current?: { nodeId: string; since: Date; recoveredAt?: Date | null } | null;
  poolNodes: GamingNodeSnapshot[];
  hysteresis?: Partial<GamingHysteresis>;
}

/**
 * Sticky gaming node selection: stay on the healthy primary; switch ONLY on real
 * failure (node OFFLINE). Degraded primaries are kept. Deterministic rank order.
 */
export function selectGamingNode(input: GamingSelectionInput): { nodeId: string; switched: boolean; reason: string } {
  const h = { ...DEFAULT_HYSTERESIS, ...input.hysteresis };
  const ordered = input.poolNodes.filter((n) => n.enabled).sort((a, b) => a.priority - b.priority);
  const cur = input.current ? ordered.find((n) => n.id === input.current!.nodeId) : undefined;

  if (cur) {
    const healthy = cur.state === "ONLINE";
    const residencyMs = input.current ? Date.now() - input.current.since.getTime() : 0;
    if (healthy && residencyMs >= h.minResidencySec * 1000) {
      return { nodeId: cur.id, switched: false, reason: "sticky_healthy" };
    }
    if (cur.state === "DEGRADED") {
      return { nodeId: cur.id, switched: false, reason: "degraded_kept" };
    }
    if (cur.state === "OFFLINE" || !healthy) {
      const next = ordered.find((n) => n.id !== cur.id && n.state === "ONLINE");
      if (next) return { nodeId: next.id, switched: true, reason: `failover_${cur.state.toLowerCase()}` };
      return { nodeId: cur.id, switched: false, reason: "no_healthy_backup" };
    }
    // healthy but residency not reached -> stay
    return { nodeId: cur.id, switched: false, reason: "min_residency" };
  }
  const first = ordered.find((n) => n.state === "ONLINE") ?? ordered[0];
  if (!first) throw new Error("pool_empty");
  return { nodeId: first.id, switched: false, reason: "initial" };
}
