import { and, eq } from "drizzle-orm";
import { z } from "zod";
import type { FastifyInstance } from "fastify";
import type { Db } from "@proxy/database";
import { schema } from "@proxy/database";
import { hashToken } from "@proxy/core";
import { userInfoHeader, renderV2ray, renderSingBox, renderClash, detectClient } from "@proxy/core";
import { singBoxDns, clashDns, v2rayDns, rawDohUrls, type DnsResourceLite } from "@proxy/core";
import { healthyEndpoints } from "@proxy/core";

async function loadByToken(db: Db, token: string) {
  const sub = (await db.select().from(schema.subscriptions).where(eq(schema.subscriptions.tokenHash, hashToken(token))).limit(1))[0];
  if (!sub) return null;
  const plan = (await db.select().from(schema.plans).where(eq(schema.plans.id, sub.planId)).limit(1))[0];
  return { sub, plan };
}

function endpointsWithSlot(endpoints: Awaited<ReturnType<typeof healthyEndpoints>>["endpoints"], slotUuid: string, displayName: string): typeof endpoints {
  return endpoints.map((e, i) => ({ ...e, uuid: slotUuid, name: `${displayName} #${i + 1}` }));
}

export async function registerPublicRoutes(app: FastifyInstance, db: Db) {
  // ---------- subscription config ----------
  app.get("/s/:token", { config: { rateLimit: { max: 12, timeWindow: "1 minute" } } }, async (req, reply) => {
    const { token } = z.object({ token: z.string().min(20) }).parse(req.params);
    const loaded = await loadByToken(db, token);
    if (!loaded) return reply.code(404).send({ error: "TOKEN_INVALID" });
    const { sub, plan } = loaded;
    const flavor = detectClient(req.headers["user-agent"] ?? "");
    const { endpoints } = await healthyEndpoints(db, sub.id);
    const slot = (await db.select().from(schema.deviceSlots)
      .where(and(eq(schema.deviceSlots.subscriptionId, sub.id), eq(schema.deviceSlots.status, "active"))).limit(1))[0];
    const filled = endpointsWithSlot(endpoints, slot?.uuid ?? "", sub.displayName);

    reply.header("subscription-userinfo", userInfoHeader(sub.bytesUsed, sub.bytesTotal, sub.expiresAt));
    reply.header("profile-update-interval", "12");
    reply.header("content-disposition", `attachment; filename="${sub.displayName}"`);
    reply.type("text/plain; charset=utf-8");

    if (flavor === "clash") return renderClash(filled);
    if (flavor === "singbox") return renderSingBox(filled);
    return renderV2ray(filled); // default: Xray family
  });

  // ---------- per-device slot link ----------
  app.get("/s/:token/d/:slot", async (req, reply) => {
    const { token, slot } = z.object({ token: z.string().min(20), slot: z.coerce.number().int().min(0) }).parse(req.params);
    const loaded = await loadByToken(db, token);
    if (!loaded) return reply.code(404).send({ error: "TOKEN_INVALID" });
    const { sub } = loaded;
    const slotRow = (await db.select().from(schema.deviceSlots)
      .where(and(eq(schema.deviceSlots.subscriptionId, sub.id), eq(schema.deviceSlots.idx, slot), eq(schema.deviceSlots.status, "active"))).limit(1))[0];
    if (!slotRow) return reply.code(404).send({ error: "SLOT_NOT_FOUND" });
    const { endpoints } = await healthyEndpoints(db, sub.id);
    reply.header("subscription-userinfo", userInfoHeader(sub.bytesUsed, sub.bytesTotal, sub.expiresAt));
    reply.type("text/plain; charset=utf-8");
    return renderV2ray(endpointsWithSlot(endpoints, slotRow.uuid, sub.displayName));
  });

  // ---------- machine-readable DNS artifact (HTML page lives in pages.ts) ----------
  app.get("/s/:token/dns/raw", async (req, reply) => {
    const { token, client } = z.object({ token: z.string().min(20), client: z.enum(["singbox", "clash", "v2ray"]).optional() }).parse(req.params);
    const loaded = await loadByToken(db, token);
    if (!loaded?.plan?.dnsProfileId) return reply.code(404).send({ error: "NO_DNS_PROFILE" });
    const profile = (await db.select().from(schema.dnsProfiles).where(eq(schema.dnsProfiles.id, loaded.plan.dnsProfileId)).limit(1))[0];
    const resources = (await db.select().from(schema.dnsResources)).filter((r) => profile.resourceIds.includes(r.id));
    const lite: DnsResourceLite[] = resources.map((r) => ({ id: r.id, type: r.type, urlOrIp: r.urlOrIp, name: r.name }));
    const flavor = client ?? detectClient(req.headers["user-agent"] ?? "");
    reply.type("text/plain; charset=utf-8");
    if (flavor === "clash") return clashDns(lite, profile.routingMode);
    if (flavor === "singbox") return JSON.stringify(singBoxDns(lite, profile.routingMode), null, 2);
    return v2rayDns(lite);
  });

  // ---------- raw doh list (status page helper) ----------
  app.get("/s/:token/doh", async (req) => {
    const { token } = z.object({ token: z.string().min(20) }).parse(req.params);
    const loaded = await loadByToken(db, token);
    if (!loaded?.plan?.dnsProfileId) return { urls: [] };
    const profile = (await db.select().from(schema.dnsProfiles).where(eq(schema.dnsProfiles.id, loaded.plan.dnsProfileId)).limit(1))[0];
    const resources = (await db.select().from(schema.dnsResources)).filter((r) => profile.resourceIds.includes(r.id));
    return { urls: rawDohUrls(resources.map((r) => ({ id: r.id, type: r.type, urlOrIp: r.urlOrIp, name: r.name }))) };
  });
}
