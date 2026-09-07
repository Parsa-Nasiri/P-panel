import { eq } from "drizzle-orm";
import { z } from "zod";
import type { FastifyInstance } from "fastify";
import type { Db } from "@proxy/database";
import { schema } from "@proxy/database";
import { hashToken, singBoxDns, clashDns, rawDohUrls } from "@proxy/core";
import type { DnsResourceLite } from "@proxy/core";

const PAGE_CSS = `body{background:#0b0f17;color:#e6e9ef;font-family:Tahoma,Vazirmatn,sans-serif;margin:0}
main{max-width:480px;margin:40px auto;padding:24px;border:1px solid #232a38;border-radius:16px}
h1{font-size:20px} h2{font-size:16px}
.bar{background:#1a2130;border-radius:999px;height:14px;overflow:hidden}
.bar>div{background:linear-gradient(90deg,#22c55e,#84cc16);height:100%}
a{color:#7dd3fc} pre{background:#111827;padding:14px;border-radius:12px;overflow:auto;direction:ltr}
.muted{color:#8b93a7;font-size:13px}`;

function html(title: string, body: string): string {
  return `<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>${title}</title>
<style>${PAGE_CSS}</style></head><body>${body}</body></html>`;
}

async function loadByToken(db: Db, token: string) {
  const sub = (await db.select().from(schema.subscriptions)
    .where(eq(schema.subscriptions.tokenHash, hashToken(token))).limit(1))[0];
  if (!sub) return null;
  const plan = (await db.select().from(schema.plans).where(eq(schema.plans.id, sub.planId)).limit(1))[0];
  return { sub, plan };
}

/** Customer-facing read-only pages: /s/<token>/status and /s/<token>/dns */
export async function registerPageRoutes(app: FastifyInstance, db: Db) {
  app.get("/s/:token/status", { config: { rateLimit: { max: 12, timeWindow: "1 minute" } } }, async (req, reply) => {
    const { token } = z.object({ token: z.string().min(20) }).parse(req.params);
    const loaded = await loadByToken(db, token);
    if (!loaded) return reply.code(404).type("text/html; charset=utf-8").send(html("خطا", "<main><p>لینک نامعتبر است.</p></main>"));
    const { sub, plan } = loaded;
    const slots = await db.select().from(schema.deviceSlots).where(eq(schema.deviceSlots.subscriptionId, sub.id));
    const usedGb = (Number(sub.bytesUsed) / 1024 ** 3).toFixed(1);
    const totalGb = (Number(sub.bytesTotal) / 1024 ** 3).toFixed(1);
    const pct = Math.min(100, Math.max(0, Math.round((Number(sub.bytesUsed) / Number(sub.bytesTotal)) * 100)));
    const daysLeft = Math.max(0, Math.ceil((sub.expiresAt.getTime() - Date.now()) / 86_400_000));
    const statusFa = sub.status === "active" ? "🟢 فعال" : sub.status === "exceeded" ? "🟠 اتمام ترافیک" : "🔴 منقضی";

    const devices = slots.map((s) =>
      `<li>${s.name ?? `دستگاه ${s.idx + 1}`} — ${s.status === "active" ? "فعال" : "لغو شده"}</li>`).join("");
    const dnsSection = plan?.dnsProfileId
      ? `<h2>دریافت DNS (گیمینگ)</h2><p><a href="/s/${token}/dns">🌐 دریافت DNS این کانفیگ</a></p>`
      : "";

    reply.type("text/html; charset=utf-8");
    return html(sub.displayName, `
      <main>
        <h1>${sub.displayName}</h1>
        <p>پلن: ${plan?.name ?? "-"} — ${statusFa}</p>
        <div class="bar"><div style="width:${pct}%"></div></div>
        <p style="font-weight:700">${usedGb} از ${totalGb} گیگابایت (${pct}٪)</p>
        <p>⏳ ${daysLeft} روز باقی‌مانده</p>
        <h2>دستگاه‌ها</h2><ul>${devices}</ul>
        ${dnsSection}
        <p class="muted">این صفحه فقط-خواندنی است؛ تغییرات از طریق پشتیبانی انجام می‌شود.</p>
      </main>`);
  });

  app.get("/s/:token/dns", { config: { rateLimit: { max: 12, timeWindow: "1 minute" } } }, async (req, reply) => {
    const { token, client } = z.object({
      token: z.string().min(20),
      client: z.enum(["singbox", "clash", "raw"]).optional(),
    }).parse(req.params);
    const loaded = await loadByToken(db, token);
    if (!loaded) return reply.code(404).type("text/html; charset=utf-8").send(html("خطا", "<main><p>لینک نامعتبر است.</p></main>"));
    if (!loaded.plan?.dnsProfileId) {
      return reply.code(404).type("text/html; charset=utf-8").send(html("DNS", "<main><p>این کانفیگ DNS گیمینگ ندارد.</p></main>"));
    }
    const profile = (await db.select().from(schema.dnsProfiles).where(eq(schema.dnsProfiles.id, loaded.plan.dnsProfileId)).limit(1))[0];
    const resources = (await db.select().from(schema.dnsResources)).filter((r) => profile.resourceIds.includes(r.id));
    const lite: DnsResourceLite[] = resources.map((r) => ({ id: r.id, type: r.type, urlOrIp: r.urlOrIp, name: r.name }));
    const flavor = client ?? "singbox";
    const body =
      flavor === "clash" ? clashDns(lite, profile.routingMode) :
      flavor === "raw" ? rawDohUrls(lite).join("\n") :
      JSON.stringify(singBoxDns(lite, profile.routingMode), null, 2);
    const tabs = ["singbox", "clash", "raw"].map((c) =>
      `<a href="/s/${token}/dns?client=${c}">${c === "singbox" ? "sing-box" : c === "clash" ? "Clash" : "DoH خام"}</a>`).join(" · ");

    reply.type("text/html; charset=utf-8");
    return html("DNS گیمینگ", `
      <main>
        <h1>🌐 DNS گیمینگ — ${loaded.sub.displayName}</h1>
        <p>${tabs}</p>
        <pre>${body.replace(/</g, "&lt;")}</pre>
        <p><a href="/s/${token}/status">🔙 بازگشت</a></p>
      </main>`);
  });
}
