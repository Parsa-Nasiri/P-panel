import { and, eq, sql } from "drizzle-orm";
import type { Db } from "@proxy/database";
import { usageEvents, usageDaily, subscriptions, deviceSlots, nodes } from "@proxy/database";
import type { UsageBatch } from "@proxy/shared";

/**
 * Idempotent usage ingestion: UNIQUE(node_id, seq, subscription_id, slot_idx).
 * Duplicate deliveries are no-ops -> at-least-once delivery is safe.
 */
export async function ingestUsageBatch(db: Db, batch: UsageBatch): Promise<{ accepted: number; duplicates: number }> {
  let accepted = 0, duplicates = 0;
  for (const e of batch.entries) {
    const rows = await db.insert(usageEvents).values({
      nodeId: batch.node_id, seq: batch.seq, windowStart: new Date(batch.window_start),
      subscriptionId: e.sub_ref, slotIdx: e.slot, up: e.up, down: e.down, conns: e.conns,
    }).onConflictDoNothing().returning({ id: usageEvents.id });
    if (rows.length === 0) { duplicates++; continue; }
    accepted++;
    await db.update(subscriptions)
      .set({ bytesUsed: sql`${subscriptions.bytesUsed} + ${e.up + e.down}` })
      .where(eq(subscriptions.id, e.sub_ref));
    if (e.ips?.length && e.slot !== undefined) {
      await db.update(deviceSlots)
        .set({ lastSeenAt: new Date() })
        .where(and(eq(deviceSlots.subscriptionId, e.sub_ref), eq(deviceSlots.idx, e.slot)));
    }
  }
  return { accepted, duplicates };
}

/** Rolls recent events into usage_daily (idempotent upsert). */
export async function aggregateDaily(db: Db, sinceIso: string): Promise<number> {
  const since = new Date(sinceIso);
  const rows = await db
    .select({
      subId: usageEvents.subscriptionId,
      day: sql<string>`to_char(${usageEvents.ts}, 'YYYY-MM-DD')`,
      up: sql<number>`sum(${usageEvents.up})`,
      down: sql<number>`sum(${usageEvents.down})`,
      conns: sql<number>`sum(${usageEvents.conns})`,
    })
    .from(usageEvents)
    .where(sql`${usageEvents.ts} >= ${since}`)
    .groupBy(usageEvents.subscriptionId, sql`to_char(${usageEvents.ts}, 'YYYY-MM-DD')`);
  for (const r of rows) {
    await db.insert(usageDaily)
      .values({ subscriptionId: r.subId, day: r.day, up: Number(r.up), down: Number(r.down), conns: Number(r.conns) })
      .onConflictDoUpdate({
        target: [usageDaily.subscriptionId, usageDaily.day],
        set: { up: sql`${usageDaily.up} + ${Number(r.up)}`, down: sql`${usageDaily.down} + ${Number(r.down)}` },
      });
  }
  return rows.length;
}

/** Exact recompute of a subscription's bytes from the event ledger. */
export async function reconcileSubscription(db: Db, subscriptionId: string): Promise<number> {
  const rows = await db.select({ total: sql<number>`coalesce(sum(${usageEvents.up} + ${usageEvents.down}), 0)` })
    .from(usageEvents).where(eq(usageEvents.subscriptionId, subscriptionId));
  const total = Number(rows[0]?.total ?? 0);
  await db.update(subscriptions).set({ bytesUsed: total }).where(eq(subscriptions.id, subscriptionId));
  return total;
}

/** Quota state used by /v1/node/config policy sync. */
export async function quotaStates(db: Db): Promise<{ subId: string; allowed: boolean }[]> {
  const rows = await db.select({
    id: subscriptions.id, used: subscriptions.bytesUsed, total: subscriptions.bytesTotal,
    status: subscriptions.status, expiresAt: subscriptions.expiresAt,
  }).from(subscriptions);
  const now = Date.now();
  return rows.map((r) => ({
    subId: r.id,
    allowed: r.status === "active" && r.used < r.total && r.expiresAt.getTime() > now,
  }));
}

export async function markExceededIfNeeded(db: Db): Promise<number> {
  const res = await db.update(subscriptions)
    .set({ status: "exceeded" })
    .where(and(eq(subscriptions.status, "active"), sql`${subscriptions.bytesUsed} >= ${subscriptions.bytesTotal}`))
    .returning({ id: subscriptions.id });
  return res.length;
}

export async function markExpiredIfNeeded(db: Db): Promise<number> {
  const res = await db.update(subscriptions)
    .set({ status: "expired" })
    .where(and(eq(subscriptions.status, "active"), sql`${subscriptions.expiresAt} <= now()`))
    .returning({ id: subscriptions.id });
  return res.length;
}

export async function pruneUsageEvents(db: Db, olderThanDays: number): Promise<number> {
  const res = await db.delete(usageEvents)
    .where(sql`${usageEvents.ts} < now() - interval '${sql.raw(String(olderThanDays))} days'`)
    .returning({ id: usageEvents.id });
  return res.length;
}

export async function nodeByWorker(db: Db, nodeId: string) {
  const r = await db.select().from(nodes).where(eq(nodes.id, nodeId)).limit(1);
  return r[0];
}
