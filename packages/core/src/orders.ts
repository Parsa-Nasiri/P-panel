import { eq } from "drizzle-orm";
import type { Db } from "@proxy/database";
import { schema } from "@proxy/database";
import { audit } from "./audit.js";

/**
 * Order state machine shared by the Telegram bot and the admin panel.
 * Idempotent: a second approve/reject on a non-pending order is a no-op.
 */
export async function approveOrder(db: Db, orderId: string, reviewerId: string) {
  const order = (await db.select().from(schema.orders).where(eq(schema.orders.id, orderId)).limit(1))[0];
  if (!order) throw new Error("order_not_found");
  if (order.status !== "pending") return { ok: false, reason: "already_processed" as const };

  await db.update(schema.orders).set({ status: "approved", reviewedBy: reviewerId, reviewedAt: new Date() })
    .where(eq(schema.orders.id, orderId));

  const plan = (await db.select().from(schema.plans).where(eq(schema.plans.id, order.planId)).limit(1))[0];
  let subscription;
  let token: string | undefined;

  if (order.kind === "renew" && order.targetSubscriptionId) {
    const { extendSubscription } = await import("./subscription-service.js");
    await extendSubscription(db, order.targetSubscriptionId, plan.durationDays, plan.trafficBytes);
    subscription = (await db.select().from(schema.subscriptions).where(eq(schema.subscriptions.id, order.targetSubscriptionId)).limit(1))[0];
  } else {
    const { createSubscription } = await import("./subscription-service.js");
    const displayName = order.displayNameRequested ?? `${plan.name}_${Math.floor(10000 + Math.random() * 90000)}`;
    const created = await createSubscription({ db, userId: order.userId, planId: order.planId, displayName });
    subscription = created.subscription;
    token = created.token;
  }

  if (order.telegramUserId) {
    await db.insert(schema.notifications).values({
      telegramUserId: order.telegramUserId,
      text: token
        ? `✅ پرداخت شما تایید شد!\n\n📦 ${subscription.displayName}\n🔗 لینک اشتراک:\n${process.env.PUBLIC_BASE_URL}/s/${token}\n\nاین لینک را در کلاینت (v2rayNG / sing-box / Clash) وارد کنید.`
        : `✅ پرداخت شما تایید شد و اشتراک «${subscription.displayName}» تمدید شد. لینک قبلی معتبر است.`,
    });
  }
  void audit(db, "system", reviewerId, "order.approve", { orderId }, { type: "order", id: orderId });
  return { ok: true as const, subscriptionId: subscription.id, token };
}

export async function rejectOrder(db: Db, orderId: string, reviewerId: string, reason?: string) {
  const order = (await db.select().from(schema.orders).where(eq(schema.orders.id, orderId)).limit(1))[0];
  if (!order) throw new Error("order_not_found");
  if (order.status !== "pending") return { ok: false, reason: "already_processed" as const };

  await db.update(schema.orders).set({ status: "rejected", reviewedBy: reviewerId, reviewedAt: new Date(), rejectReason: reason ?? null })
    .where(eq(schema.orders.id, orderId));

  if (order.telegramUserId) {
    await db.insert(schema.notifications).values({
      telegramUserId: order.telegramUserId,
      text: `❌ سفارش شما تایید نشد.${reason ? `\nدلیل: ${reason}` : ""}\nدر صورت نیاز با پشتیبانی در تماس باشید.`,
    });
  }
  void audit(db, "system", reviewerId, "order.reject", { orderId, reason }, { type: "order", id: orderId });
  return { ok: true as const };
}
