import { createDb, schema } from "@proxy/database";
import { eq } from "drizzle-orm";
import { buildDisplayName, sanitizeName, ensureSlotsPublic, createSubscription, healthyEndpoints } from "@proxy/core";
import { fa } from "@proxy/shared";

export const { db } = createDb(process.env.DATABASE_URL!);
export { schema, eq, fa };

export function isAdmin(ctx: { from?: { id: number } }): boolean {
  const ids = (process.env.ADMIN_TELEGRAM_IDS ?? "").split(",").map((s) => Number(s.trim())).filter(Boolean);
  return !!ctx.from && ids.includes(ctx.from.id);
}

export async function ensureUser(from: { id: number; username?: string; first_name?: string }) {
  const existing = await db.select().from(schema.users).where(eq(schema.users.telegramId, from.id)).limit(1);
  if (existing[0]) return existing[0];
  return (await db.insert(schema.users).values({
    name: from.first_name ?? `tg-${from.id}`, telegramId: from.id, telegramUsername: from.username,
  }).returning())[0];
}

export async function trialCount(telegramUserId: number): Promise<number> {
  const rows = await db.select({ id: schema.botTrials.id }).from(schema.botTrials).where(eq(schema.botTrials.telegramUserId, telegramUserId));
  return rows.length;
}

export async function createTrial(telegramUserId: number, userId: string, trialPlanId: string) {
  const { subscription, token } = await createSubscription({ db, userId, planId: trialPlanId, displayName: `تست_${Math.floor(10000 + Math.random() * 90000)}` });
  await db.insert(schema.botTrials).values({ telegramUserId, subscriptionId: subscription.id });
  return { subscription, token };
}

export async function activePlans() {
  return db.select().from(schema.plans).where(eq(schema.plans.isActive, true));
}

export async function mySubscriptions(userId: string) {
  return db.select().from(schema.subscriptions).where(eq(schema.subscriptions.userId, userId));
}

export function gb(bytes: number): string {
  return (bytes / 1024 ** 3).toFixed(1);
}

export { buildDisplayName, sanitizeName, ensureSlotsPublic, healthyEndpoints };
