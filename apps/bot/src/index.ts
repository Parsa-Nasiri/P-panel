import { Bot, session, webhookCallback, type Context, type SessionFlavor } from "grammy";
import { createServer } from "node:http";
import { eq } from "drizzle-orm";
import { fa } from "@proxy/shared";
import { sanitizeName, buildDisplayName, approveOrder, rejectOrder } from "@proxy/core";
import { ensureUser, isAdmin, activePlans, mySubscriptions, trialCount, createTrial, db, schema, gb } from "./store.js";
import { mainMenu, planList, planActions, orderCardButtons, subActions } from "./keyboards.js";

interface SessionData {
  flow?:
    | { kind: "receipt"; planId: string }
    | { kind: "name"; subId: string }
    | { kind: "reject"; orderId: string };
}
type Ctx = Context & SessionFlavor<SessionData>;

const bot = new Bot<Ctx>(process.env.BOT_TOKEN!);
bot.use(session({ initial: (): SessionData => ({}) }));

// ---------- global commands ----------
bot.command("start", async (ctx) => {
  await ensureUser(ctx.from!);
  await ctx.reply(fa.welcome, { reply_markup: mainMenu() });
});
bot.command("help", (ctx) => ctx.reply(fa.helpText, { reply_markup: mainMenu() }));
bot.command("settings", (ctx) => ctx.reply(fa.mainMenu, { reply_markup: mainMenu() }));

// ---------- customer menu ----------
bot.hears(fa.buy, async (ctx) => {
  await ensureUser(ctx.from!);
  const plans = (await activePlans()).filter((p) => !p.isTrial);
  if (plans.length === 0) return ctx.reply(fa.error);
  await ctx.reply(fa.choosePlan, { reply_markup: planList(plans) });
});

bot.hears(fa.trial, async (ctx) => {
  const user = await ensureUser(ctx.from!);
  const remaining = 2 - (await trialCount(ctx.from!.id));
  if (remaining <= 0) return ctx.reply(fa.trialNone, { reply_markup: mainMenu() });
  const trialPlan = (await activePlans()).find((p) => p.isTrial);
  if (!trialPlan) return ctx.reply(fa.error);
  const { subscription, token } = await createTrial(ctx.from!.id, user.id, trialPlan.id);
  await ctx.reply(
    `${fa.trialOffer(remaining)}\n\n${fa.trialCreated}\n${fa.nameOk(subscription.displayName)}\n\n` +
    `${fa.linkCopied}\n${process.env.PUBLIC_BASE_URL}/s/${token}`,
    { reply_markup: mainMenu() }
  );
});

bot.hears(fa.myConfigs, async (ctx) => {
  const user = await ensureUser(ctx.from!);
  const subs = await mySubscriptions(user.id);
  if (subs.length === 0) {
    return ctx.reply("شما هنوز کانفیگی ندارید. از 🛒 خرید کانفیگ استفاده کنید.", { reply_markup: mainMenu() });
  }
  for (const s of subs) {
    const daysLeft = Math.max(0, Math.ceil((s.expiresAt.getTime() - Date.now()) / 86_400_000));
    const pct = s.bytesTotal > 0 ? Number(s.bytesUsed) / Number(s.bytesTotal) : 0;
    const status = s.status !== "active" || daysLeft === 0 ? fa.expired : pct >= 0.8 ? fa.lowTraffic : fa.active;
    const plan = (await db.select().from(schema.plans).where(eq(schema.plans.id, s.planId)).limit(1))[0];
    await ctx.reply(fa.subDetail(s.displayName, gb(Number(s.bytesUsed)), gb(Number(s.bytesTotal)), daysLeft) + `\n${status}`, {
      reply_markup: subActions(s.id, !!plan?.dnsProfileId),
    });
  }
});

bot.hears(fa.paymentGuide, (ctx) => ctx.reply(fa.paymentGuideText, { reply_markup: mainMenu() }));
bot.hears(fa.support, (ctx) => ctx.reply(fa.supportText, { reply_markup: mainMenu() }));
bot.hears(fa.help, (ctx) => ctx.reply(fa.helpText, { reply_markup: mainMenu() }));

// ---------- inline callbacks ----------
bot.callbackQuery(/plan:(.+)/, async (ctx) => {
  const plan = (await db.select().from(schema.plans).where(eq(schema.plans.id, ctx.match[1])).limit(1))[0];
  const settingsRow = (await db.select().from(schema.settings).where(eq(schema.settings.key, "payment_instructions")).limit(1))[0];
  const payText = (settingsRow?.value as any)?.text ?? "کارت به کارت — پس از واریز، رسید را ارسال کنید.";
  await ctx.editMessageText(
    fa.planCard(plan.name, String(Math.round(plan.priceCents / 100)), plan.durationDays, Number(plan.trafficBytes / 1024 ** 3), plan.maxDevices, plan.gaming) +
    `\n\n${fa.payInstructions(payText)}`,
    { reply_markup: planActions(plan.id) }
  );
  await ctx.answerCallbackQuery();
});

bot.callbackQuery("cancel", async (ctx) => {
  ctx.session.flow = undefined;
  await ctx.editMessageText(fa.mainMenu);
  await ctx.answerCallbackQuery();
});

bot.callbackQuery("back_main", async (ctx) => {
  await ctx.editMessageText(fa.mainMenu);
  await ctx.answerCallbackQuery();
});

bot.callbackQuery(/receipt:(.+)/, async (ctx) => {
  ctx.session.flow = { kind: "receipt", planId: ctx.match[1] };
  await ctx.editMessageText("📸 لطفا اسکرین‌شات رسید پرداخت را ارسال کنید (و در صورت تمایل یک توضیح کوتاه):");
  await ctx.answerCallbackQuery();
});

bot.callbackQuery(/link:(.+)/, async (ctx) => {
  const { revealToken } = await import("@proxy/core");
  const token = await revealToken(db, ctx.match[1]);
  if (!token) return ctx.answerCallbackQuery({ text: fa.error, show_alert: true });
  await ctx.reply(`${fa.linkCopied}\n${process.env.PUBLIC_BASE_URL}/s/${token}`);
  await ctx.answerCallbackQuery();
});

bot.callbackQuery(/qr:(.+)/, async (ctx) => {
  const { revealToken } = await import("@proxy/core");
  const token = await revealToken(db, ctx.match[1]);
  if (!token) return ctx.answerCallbackQuery({ text: fa.error, show_alert: true });
  const url = `${process.env.PUBLIC_BASE_URL}/s/${token}/status`;
  await ctx.reply(`📷 QR:\n${url}\n\n(صفحه وضعیت شامل QR کد اشتراک است)`);
  await ctx.answerCallbackQuery();
});

bot.callbackQuery(/usage:(.+)/, async (ctx) => {
  const sub = (await db.select().from(schema.subscriptions).where(eq(schema.subscriptions.id, ctx.match[1])).limit(1))[0];
  if (!sub) return ctx.answerCallbackQuery({ text: fa.error, show_alert: true });
  const daysLeft = Math.max(0, Math.ceil((sub.expiresAt.getTime() - Date.now()) / 86_400_000));
  await ctx.answerCallbackQuery({
    text: fa.subDetail(sub.displayName, gb(Number(sub.bytesUsed)), gb(Number(sub.bytesTotal)), daysLeft),
    show_alert: true,
  });
});

bot.callbackQuery(/dns:(.+)/, async (ctx) => {
  const { revealToken } = await import("@proxy/core");
  const token = await revealToken(db, ctx.match[1]);
  if (!token) return ctx.answerCallbackQuery({ text: fa.error, show_alert: true });
  await ctx.reply(`${fa.dnsHeader}\n${process.env.PUBLIC_BASE_URL}/s/${token}/dns`);
  await ctx.answerCallbackQuery();
});

bot.callbackQuery(/rename:(.+)/, async (ctx) => {
  ctx.session.flow = { kind: "name", subId: ctx.match[1] };
  await ctx.reply(fa.askName);
  await ctx.answerCallbackQuery();
});

// ---------- photo = receipt ----------
bot.on("message:photo", async (ctx) => {
  if (!ctx.session.flow || ctx.session.flow.kind !== "receipt") return ctx.reply(fa.error);
  const user = await ensureUser(ctx.from!);
  const planId = ctx.session.flow.planId;
  const plan = (await db.select().from(schema.plans).where(eq(schema.plans.id, planId)).limit(1))[0];
  const order = (await db.insert(schema.orders).values({
    userId: user.id, telegramUserId: ctx.from!.id, planId,
    screenshotFileId: ctx.message.photo.at(-1)!.file_id,
    customerNote: ctx.message.caption ?? null,
    priceCents: plan.priceCents,
  }).returning())[0];
  ctx.session.flow = undefined;

  const adminIds = (process.env.ADMIN_TELEGRAM_IDS ?? "").split(",").map(Number).filter(Boolean);
  const caption = fa.adminNewOrder(
    plan.name, String(Math.round(plan.priceCents / 100)),
    ctx.from!.first_name ?? "", ctx.from!.username ? `@${ctx.from!.username}` : "-",
    ctx.from!.id, ctx.message.caption ?? "", order.id
  );
  for (const adminId of adminIds) {
    await ctx.api.sendPhoto(adminId, order.screenshotFileId!, { caption, reply_markup: orderCardButtons(order.id) });
  }
  await ctx.reply(fa.orderRegistered, { reply_markup: mainMenu() });
});

// ---------- text: name entry / reject reason ----------
bot.on("message:text", async (ctx) => {
  const flow = ctx.session.flow;
  if (!flow) return; // menu handled by .hears(); unknown free text ignored

  if (flow.kind === "name") {
    const res = sanitizeName(ctx.message.text);
    if (!res.ok) return ctx.reply(res.reason === "too_long" ? fa.nameTooLong : fa.nameInvalid);
    const final = await buildDisplayName(res.value, async (c) => {
      const found = await db.select({ id: schema.subscriptions.id }).from(schema.subscriptions)
        .where(eq(schema.subscriptions.displayName, c)).limit(1);
      return found.length > 0;
    });
    await db.update(schema.subscriptions).set({ displayName: final }).where(eq(schema.subscriptions.id, flow.subId));
    ctx.session.flow = undefined;
    return ctx.reply(fa.nameOk(final), { reply_markup: mainMenu() });
  }

  if (flow.kind === "reject") {
    ctx.session.flow = undefined;
    const reason = ctx.message.text === "/skip" ? undefined : ctx.message.text;
    const result = await rejectOrder(db, flow.orderId, String(ctx.from!.id), reason);
    await ctx.reply(result.ok ? fa.orderRejectedCard : fa.alreadyProcessed);
    return;
  }
});

// ---------- admin chat ----------
bot.callbackQuery(/approve:(.+)/, async (ctx) => {
  if (!isAdmin(ctx)) return ctx.answerCallbackQuery({ text: "unauthorized" });
  const result = await approveOrder(db, ctx.match[1], String(ctx.from!.id));
  if (!result.ok) return ctx.answerCallbackQuery({ text: fa.alreadyProcessed, show_alert: true });
  const caption = ctx.update.callback_query.message?.caption ?? "";
  await ctx.editMessageCaption({ caption: `${caption}\n\n${fa.orderApprovedCard}` });
  await ctx.answerCallbackQuery();
});

bot.callbackQuery(/reject:(.+)/, async (ctx) => {
  if (!isAdmin(ctx)) return ctx.answerCallbackQuery({ text: "unauthorized" });
  ctx.session.flow = { kind: "reject", orderId: ctx.match[1] };
  await ctx.reply(fa.rejectReasonPrompt);
  await ctx.answerCallbackQuery();
});

bot.callbackQuery(/profile:(.+)/, async (ctx) => {
  if (!isAdmin(ctx)) return ctx.answerCallbackQuery({ text: "unauthorized" });
  const order = (await db.select().from(schema.orders).where(eq(schema.orders.id, ctx.match[1])).limit(1))[0];
  if (!order) return ctx.answerCallbackQuery();
  const user = (await db.select().from(schema.users).where(eq(schema.users.id, order.userId)).limit(1))[0];
  const subs = await mySubscriptions(user.id);
  await ctx.reply(
    `👤 ${user.name} (${user.telegramUsername ? "@" + user.telegramUsername : user.telegramId})\n📦 اشتراک‌ها: ${subs.length}`
  );
  await ctx.answerCallbackQuery();
});

bot.command("admin", async (ctx) => {
  if (!isAdmin(ctx)) return;
  const nodes = await db.select().from(schema.nodes);
  const online = nodes.filter((n) => n.status === "ONLINE").length;
  const activeSubs = (await db.select().from(schema.subscriptions).where(eq(schema.subscriptions.status, "active"))).length;
  await ctx.reply(fa.adminStats(0, activeSubs, 0, online, nodes.length), { reply_markup: mainMenu() });
});

bot.catch((err) => console.error("bot_error", err));

// ---------- transport ----------
async function start() {
  await bot.api.setMyCommands([
    { command: "start", description: "شروع" },
    { command: "help", description: "راهنما" },
    { command: "settings", description: "منوی اصلی" },
  ]);

  if (process.env.BOT_MODE === "polling") {
    bot.start();
    console.log("bot polling started");
    return;
  }

  // webhook mode with secret-token verification
  const handle = webhookCallback(bot, "http", { secretToken: process.env.BOT_WEBHOOK_SECRET });
  const server = createServer((req, res) => {
    if (req.method === "POST" && req.url === "/telegram/webhook") return handle(req, res);
    res.writeHead(200).end("ok");
  });
  server.listen(Number(process.env.PORT ?? 3001), () => console.log("bot webhook listening"));
}

await bot.init();
start().catch(console.error);
