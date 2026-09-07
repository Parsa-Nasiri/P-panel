import PgBoss from "pg-boss";
import pino from "pino";
import { eq, isNull } from "drizzle-orm";
import type { Db } from "@proxy/database";
import { schema } from "@proxy/database";
import {
  markExceededIfNeeded, markExpiredIfNeeded, aggregateDaily, pruneUsageEvents, releaseStaleSlots,
} from "@proxy/core";

const log = pino({ level: process.env.LOG_LEVEL ?? "info" });

const QUEUES = {
  usageAggregate: "usage-aggregate",
  reconcile: "reconcile",
  deviceExpiry: "device-expiry",
  subExpiry: "sub-expiry",
  retention: "retention",
  botNotify: "bot-notify",
} as const;

/** Telegram sender used by jobs (interactive bot flows live in bot/index.ts). */
async function sendTelegram(chatId: number, text: string): Promise<boolean> {
  const token = process.env.BOT_TOKEN;
  if (!token) return false;
  try {
    const res = await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chat_id: chatId, text }),
    });
    return res.ok;
  } catch (e) {
    log.warn({ e }, "telegram_send_failed");
    return false;
  }
}

/** Starts pg-boss + all recurring jobs in-process. Called once at boot. */
export async function startJobs(db: Db): Promise<void> {
  const boss = new PgBoss({ connectionString: process.env.DATABASE_URL! });
  boss.on("error", (e) => log.error({ e }, "pg_boss_error"));
  await boss.start();
  for (const name of Object.values(QUEUES)) await boss.createQueue(name);

  await boss.schedule(QUEUES.usageAggregate, "*/1 * * * *");
  await boss.schedule(QUEUES.reconcile, "*/15 * * * *");
  await boss.schedule(QUEUES.deviceExpiry, "*/15 * * * *");
  await boss.schedule(QUEUES.subExpiry, "*/5 * * * *");
  await boss.schedule(QUEUES.retention, "0 4 * * *");
  await boss.schedule(QUEUES.botNotify, "*/5 * * * *");

  await boss.work(QUEUES.usageAggregate, async () => {
    const n = await aggregateDaily(db, new Date(Date.now() - 2 * 86_400_000).toISOString());
    log.info({ rolled: n }, "usage_aggregate");
  });

  await boss.work(QUEUES.reconcile, async () => {
    const { reconcileSubscription } = await import("@proxy/core");
    const subs = await db.select({ id: schema.subscriptions.id }).from(schema.subscriptions).limit(50);
    for (const s of subs) await reconcileSubscription(db, s.id);
    log.info({ checked: subs.length }, "reconcile");
  });

  await boss.work(QUEUES.deviceExpiry, async () => {
    const n = await releaseStaleSlots(db, 30);
    log.info({ released: n }, "device_expiry");
  });

  await boss.work(QUEUES.subExpiry, async () => {
    const expired = await markExpiredIfNeeded(db);
    const exceeded = await markExceededIfNeeded(db);
    log.info({ expired, exceeded }, "sub_expiry");
  });

  await boss.work(QUEUES.retention, async () => {
    const pruned = await pruneUsageEvents(db, 90);
    log.info({ pruned }, "retention");
  });

  await boss.work(QUEUES.botNotify, async () => {
    const rows = await db.select({
      tg: schema.users.telegramId, used: schema.subscriptions.bytesUsed, total: schema.subscriptions.bytesTotal,
      expires: schema.subscriptions.expiresAt, name: schema.subscriptions.displayName,
    }).from(schema.subscriptions)
      .innerJoin(schema.users, eq(schema.users.id, schema.subscriptions.userId))
      .where(eq(schema.subscriptions.status, "active"));
    for (const r of rows) {
      if (!r.tg) continue;
      const pct = r.total > 0 ? Number(r.used) / Number(r.total) : 0;
      if (pct >= 0.8) await sendTelegram(r.tg, `⚠️ ترافیک «${r.name}» به ${Math.floor(pct * 100)}٪ رسید.`);
      const daysLeft = Math.floor((r.expires.getTime() - Date.now()) / 86_400_000);
      if (daysLeft === 3 || daysLeft === 1) {
        await sendTelegram(r.tg, `⏳ اشتراک «${r.name}» تا ${daysLeft} روز دیگر منقضی می‌شود.`);
      }
    }
    const pending = await db.select().from(schema.notifications).where(isNull(schema.notifications.sentAt)).limit(50);
    for (const n of pending) {
      if (await sendTelegram(n.telegramUserId, n.text)) {
        await db.update(schema.notifications).set({ sentAt: new Date() }).where(eq(schema.notifications.id, n.id));
      }
    }
  });

  log.info("jobs started");
}
