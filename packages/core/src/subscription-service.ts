import { and, eq, inArray } from "drizzle-orm";
import { encryptSecret, decryptSecret } from "@proxy/shared";
import type { Db } from "@proxy/database";
import {
  subscriptions, plans, deviceSlots, nodes, poolNodes, nodePools, profiles, users,
} from "@proxy/database";
import { newSubCode, newSubToken } from "./tokens.js";
import type { SubEndpoint } from "@proxy/shared";

export interface CreateSubInput {
  userId: string;
  planId: string;
  displayName: string;
  db: Db;
}

export async function createSubscription(input: CreateSubInput) {
  const plan = (await input.db.select().from(plans).where(eq(plans.id, input.planId)).limit(1))[0];
  if (!plan || !plan.isActive) throw new Error("plan_not_found");
  const { token, tokenHash } = newSubToken();
  const expiresAt = new Date(Date.now() + plan.durationDays * 86_400_000);
  const box = encryptSecret(token, process.env.APP_SECRET ?? "dev-secret");
  const row = (await input.db.insert(subscriptions).values({
    code: newSubCode(), userId: input.userId, planId: input.planId,
    tokenHash, tokenEnc: box.enc, tokenIv: box.iv, tokenTag: box.tag,
    displayName: input.displayName,
    bytesTotal: plan.trafficBytes, expiresAt,
  }).returning())[0];
  const slots = await ensureSlotsPublic(input.db, row.id, plan.maxDevices);
  return { subscription: row, token, slots };
}

/** Re-derives the raw token from its encrypted copy (owner re-display only). */
export async function revealToken(db: Db, subscriptionId: string): Promise<string | null> {
  const sub = (await db.select().from(subscriptions).where(eq(subscriptions.id, subscriptionId)).limit(1))[0];
  if (!sub?.tokenEnc || !sub.tokenIv || !sub.tokenTag) return null;
  return decryptSecret({ enc: sub.tokenEnc, iv: sub.tokenIv, tag: sub.tokenTag }, process.env.APP_SECRET ?? "dev-secret");
}

export async function ensureSlotsPublic(db: Db, subscriptionId: string, maxDevices: number) {
  const existing = await db.select().from(deviceSlots).where(eq(deviceSlots.subscriptionId, subscriptionId));
  if (existing.length >= maxDevices) return existing;
  const startIdx = existing.reduce((m, s) => Math.max(m, s.idx), -1) + 1;
  return db.insert(deviceSlots).values(
    Array.from({ length: maxDevices - existing.length }, (_, i) => ({
      subscriptionId, idx: startIdx + i, uuid: crypto.randomUUID(),
    }))
  ).returning();
}

export async function revokeSubscription(db: Db, subscriptionId: string) {
  await db.update(subscriptions).set({ status: "suspended" }).where(eq(subscriptions.id, subscriptionId));
  await db.update(deviceSlots).set({ status: "revoked", revokedAt: new Date() })
    .where(eq(deviceSlots.subscriptionId, subscriptionId));
}

/** Rotates the sub token AND all slot UUIDs (nukes leaked copies). */
export async function regenerateSubscription(db: Db, subscriptionId: string) {
  const { token, tokenHash } = newSubToken();
  const box = encryptSecret(token, process.env.APP_SECRET ?? "dev-secret");
  await db.update(subscriptions).set({ tokenHash, tokenEnc: box.enc, tokenIv: box.iv, tokenTag: box.tag })
    .where(eq(subscriptions.id, subscriptionId));
  const slots = await db.select().from(deviceSlots).where(eq(deviceSlots.subscriptionId, subscriptionId));
  for (const s of slots) {
    await db.update(deviceSlots).set({ uuid: crypto.randomUUID() }).where(eq(deviceSlots.id, s.id));
  }
  return { token };
}

export async function extendSubscription(db: Db, subscriptionId: string, extraDays: number, extraBytes?: number) {
  const sub = (await db.select().from(subscriptions).where(eq(subscriptions.id, subscriptionId)).limit(1))[0];
  if (!sub) throw new Error("subscription_not_found");
  const base = Math.max(sub.expiresAt.getTime(), Date.now());
  await db.update(subscriptions).set({
    expiresAt: new Date(base + extraDays * 86_400_000),
    bytesTotal: sub.bytesTotal + (extraBytes ?? 0),
    status: "active",
  }).where(eq(subscriptions.id, subscriptionId));
}

/** Healthy nodes of the subscription's pool, ranked by pool priority. */
export async function healthyEndpoints(db: Db, subscriptionId: string): Promise<{ endpoints: SubEndpoint[]; dnsPoolId: string | null; profileParams: Record<string, unknown> }> {
  const sub = (await db.select().from(subscriptions).where(eq(subscriptions.id, subscriptionId)).limit(1))[0];
  if (!sub) throw new Error("subscription_not_found");
  const plan = (await db.select().from(plans).where(eq(plans.id, sub.planId)).limit(1))[0];
  if (!plan?.poolId) return { endpoints: [], dnsPoolId: null, profileParams: {} };

  const pool = (await db.select().from(nodePools).where(eq(nodePools.id, plan.poolId)).limit(1))[0];
  const profile = pool?.profileId
    ? (await db.select().from(profiles).where(eq(profiles.id, pool.profileId)).limit(1))[0]
    : undefined;

  const rows = await db.select({ node: nodes, priority: poolNodes.priority })
    .from(poolNodes)
    .innerJoin(nodes, eq(nodes.id, poolNodes.nodeId))
    .where(and(eq(poolNodes.poolId, plan.poolId), eq(poolNodes.enabled, true), eq(nodes.enabled, true), inArray(nodes.status, ["ONLINE"])))
    .orderBy(poolNodes.priority);

  const params = (profile?.params ?? {}) as Record<string, unknown>;
  const ports = (params.ports as number[] | undefined) ?? [443];
  const pathPrefix = (params.pathPrefix as string | undefined) ?? `/mgt-${sub.code.replace(/-/g, "").slice(2)}`;

  const endpoints: SubEndpoint[] = rows.map((r, i) => ({
    uuid: "", // per-slot UUID injected by caller
    address: r.node.workerDomain ?? `${r.node.workerName}.workers.dev`,
    port: ports[0] ?? 443,
    sni: r.node.workerDomain ?? `${r.node.workerName}.workers.dev`,
    host: r.node.workerDomain ?? `${r.node.workerName}.workers.dev`,
    path: `${pathPrefix}-${i}`,
    tls: true,
    transport: "ws",
    name: `${sub.displayName}-${i + 1}`,
  }));
  return { endpoints, dnsPoolId: plan.dnsProfileId ?? null, profileParams: params };
}

export async function userByTelegram(db: Db, telegramId: number) {
  return (await db.select().from(users).where(eq(users.telegramId, telegramId)).limit(1))[0];
}
