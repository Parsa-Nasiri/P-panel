import { and, desc, eq } from "drizzle-orm";
import { z } from "zod";
import type { FastifyInstance } from "fastify";
import type { Db } from "@proxy/database";
import { schema } from "@proxy/database";
import { hashPassword, verifyPassword, randomToken, sha256 } from "@proxy/shared";
import { requireRole, type AdminRole } from "../auth.js";
import { audit } from "@proxy/core";

export async function registerAdminRoutes(app: FastifyInstance, db: Db) {
  // ---------- auth ----------
  app.post("/api/auth/login", { config: { rateLimit: { max: 10, timeWindow: "1 minute" } } }, async (req, reply) => {
    const body = z.object({ email: z.string().email(), password: z.string().min(8) }).parse(req.body);
    const admin = (await db.select().from(schema.admins).where(eq(schema.admins.email, body.email)).limit(1))[0];
    if (!admin || !verifyPassword(body.password, admin.passwordHash)) {
      return reply.code(401).send({ error: "INVALID_CREDENTIALS" });
    }
    const token = randomToken(32);
    await db.insert(schema.adminSessions).values({
      adminId: admin.id, tokenHash: sha256(token),
      expiresAt: new Date(Date.now() + 7 * 86_400_000),
      ip: req.ip, ua: req.headers["user-agent"] ?? "",
    });
    reply.setCookie("padmin", token, { httpOnly: true, sameSite: "strict", path: "/" });
    void audit(db, "admin", admin.id, "login");
    return { ok: true, role: admin.role };
  });

  app.post("/api/auth/logout", { preHandler: requireRole("viewer") }, async (req, reply) => {
    const token = (req.cookies as any)["padmin"] as string | undefined;
    if (token) await db.delete(schema.adminSessions).where(eq(schema.adminSessions.tokenHash, sha256(token)));
    reply.clearCookie("padmin");
    return { ok: true };
  });

  // ---------- users ----------
  app.get("/api/users", { preHandler: requireRole("viewer") }, async () =>
    db.select().from(schema.users).orderBy(desc(schema.users.createdAt)).limit(500));

  app.post("/api/users", { preHandler: requireRole("admin") }, async (req) => {
    const body = z.object({ name: z.string().min(1), email: z.string().email().optional(), note: z.string().optional() }).parse(req.body);
    const row = (await db.insert(schema.users).values(body).returning())[0];
    void audit(db, "admin", (req as any).admin.id, "user.create", body, { type: "user", id: row.id });
    return row;
  });

  app.post("/api/users/:id/suspend", { preHandler: requireRole("admin") }, async (req) => {
    const { id } = z.object({ id: z.string().uuid() }).parse(req.params);
    const row = (await db.update(schema.users).set({ status: "suspended" }).where(eq(schema.users.id, id)).returning())[0];
    void audit(db, "admin", (req as any).admin.id, "user.suspend", undefined, { type: "user", id });
    return row;
  });

  // ---------- plans ----------
  app.get("/api/plans", { preHandler: requireRole("viewer") }, async () => db.select().from(schema.plans));

  app.post("/api/plans", { preHandler: requireRole("admin") }, async (req) => {
    const body = z.object({
      name: z.string(), durationDays: z.number().int().positive(), trafficBytes: z.number().positive(),
      maxDevices: z.number().int().min(1).default(1), gaming: z.boolean().default(false),
      poolId: z.string().uuid().nullable(), profileId: z.string().uuid().nullable(),
      dnsProfileId: z.string().uuid().nullable(), failoverMode: z.enum(["re-rank", "sticky"]).default("re-rank"),
      priceCents: z.number().int().default(0), isTrial: z.boolean().default(false),
    }).parse(req.body);
    const row = (await db.insert(schema.plans).values(body).returning())[0];
    void audit(db, "admin", (req as any).admin.id, "plan.create", body, { type: "plan", id: row.id });
    return row;
  });

  // ---------- subscriptions ----------
  app.get("/api/subscriptions", { preHandler: requireRole("viewer") }, async (req) => {
    const { userId } = z.object({ userId: z.string().uuid().optional() }).parse(req.query);
    const q = db.select().from(schema.subscriptions).orderBy(desc(schema.subscriptions.createdAt)).limit(500);
    return userId ? q.where(eq(schema.subscriptions.userId, userId)) : q;
  });

  app.post("/api/subscriptions", { preHandler: requireRole("admin") }, async (req, reply) => {
    const body = z.object({
      userId: z.string().uuid(), planId: z.string().uuid(), displayName: z.string().min(1).max(40),
    }).parse(req.body);
    const { createSubscription } = await import("@proxy/core");
    const { subscription, token, slots } = await createSubscription({ db, ...body });
    void audit(db, "admin", (req as any).admin.id, "sub.create", { displayName: body.displayName }, { type: "subscription", id: subscription.id });
    return reply.code(201).send({ subscription, token, slots }); // token shown once
  });

  app.post("/api/subscriptions/:id/regenerate-secret", { preHandler: requireRole("admin") }, async (req) => {
    const { id } = z.object({ id: z.string().uuid() }).parse(req.params);
    const { regenerateSubscription } = await import("@proxy/core");
    const { token } = await regenerateSubscription(db, id);
    void audit(db, "admin", (req as any).admin.id, "sub.regenerate", undefined, { type: "subscription", id });
    return { token };
  });

  app.post("/api/subscriptions/:id/revoke", { preHandler: requireRole("admin") }, async (req) => {
    const { id } = z.object({ id: z.string().uuid() }).parse(req.params);
    const { revokeSubscription } = await import("@proxy/core");
    await revokeSubscription(db, id);
    void audit(db, "admin", (req as any).admin.id, "sub.revoke", undefined, { type: "subscription", id });
    return { ok: true };
  });

  app.post("/api/subscriptions/:id/extend", { preHandler: requireRole("admin") }, async (req) => {
    const { id } = z.object({ id: z.string().uuid() }).parse(req.params);
    const body = z.object({ extraDays: z.number().int().positive(), extraBytes: z.number().optional() }).parse(req.body);
    const { extendSubscription } = await import("@proxy/core");
    await extendSubscription(db, id, body.extraDays, body.extraBytes);
    void audit(db, "admin", (req as any).admin.id, "sub.extend", body, { type: "subscription", id });
    return { ok: true };
  });

  app.get("/api/subscriptions/:id/usage", { preHandler: requireRole("viewer") }, async (req) => {
    const { id } = z.object({ id: z.string().uuid() }).parse(req.params);
    return db.select().from(schema.usageEvents).where(eq(schema.usageEvents.subscriptionId, id))
      .orderBy(desc(schema.usageEvents.id)).limit(200);
  });

  app.post("/api/usage/:id/reconcile", { preHandler: requireRole("admin") }, async (req) => {
    const { id } = z.object({ id: z.string().uuid() }).parse(req.params);
    const { reconcileSubscription } = await import("@proxy/core");
    const total = await reconcileSubscription(db, id);
    void audit(db, "admin", (req as any).admin.id, "usage.reconcile", { total }, { type: "subscription", id });
    return { bytesUsed: total };
  });

  // ---------- device slots ----------
  app.get("/api/subscriptions/:id/slots", { preHandler: requireRole("viewer") }, async (req) => {
    const { id } = z.object({ id: z.string().uuid() }).parse(req.params);
    return db.select().from(schema.deviceSlots).where(eq(schema.deviceSlots.subscriptionId, id));
  });

  app.delete("/api/subscriptions/:id/slots/:slotId", { preHandler: requireRole("admin") }, async (req) => {
    const { slotId } = z.object({ slotId: z.string().uuid() }).parse(req.params);
    const { revokeSlot } = await import("@proxy/core");
    await revokeSlot(db, slotId);
    void audit(db, "admin", (req as any).admin.id, "slot.revoke", undefined, { type: "device_slot", id: slotId });
    return { ok: true };
  });

  // ---------- pools / dns / profiles ----------
  app.get("/api/pools", { preHandler: requireRole("viewer") }, async () => db.select().from(schema.nodePools));
  app.post("/api/pools", { preHandler: requireRole("admin") }, async (req) => {
    const body = z.object({
      name: z.string(), kind: z.enum(["standard", "gaming"]).default("standard"),
      region: z.string().optional(), profileId: z.string().uuid().nullable(),
    }).parse(req.body);
    return (await db.insert(schema.nodePools).values(body).returning())[0];
  });
  app.patch("/api/pools/:id/nodes", { preHandler: requireRole("admin") }, async (req) => {
    const { id } = z.object({ id: z.string().uuid() }).parse(req.params);
    const body = z.object({ ordered: z.array(z.object({ nodeId: z.string().uuid(), enabled: z.boolean() })) }).parse(req.body);
    for (const [i, n] of body.ordered.entries()) {
      await db.update(schema.poolNodes).set({ priority: i, enabled: n.enabled })
        .where(and(eq(schema.poolNodes.poolId, id), eq(schema.poolNodes.nodeId, n.nodeId)));
    }
    return { ok: true };
  });

  app.get("/api/dns/resources", { preHandler: requireRole("viewer") }, async () => db.select().from(schema.dnsResources));
  app.post("/api/dns/resources", { preHandler: requireRole("admin") }, async (req) => {
    const body = z.object({
      name: z.string(), type: z.enum(["doh-worker", "doh-public", "dot-public", "plain-ip"]),
      urlOrIp: z.string(), poolId: z.string().uuid().nullable(), nodeId: z.string().uuid().nullable(),
    }).parse(req.body);
    return (await db.insert(schema.dnsResources).values(body).returning())[0];
  });

  app.get("/api/profiles", { preHandler: requireRole("viewer") }, async () => db.select().from(schema.profiles));

  // ---------- cloudflare accounts + provisioning ----------
  app.post("/api/cloudflare/accounts", { preHandler: requireRole("admin") }, async (req, reply) => {
    const body = z.object({ label: z.string().min(1), token: z.string().min(20) }).parse(req.body);
    const { CfClient } = await import("@proxy/cloudflare");
    const cf = new CfClient(body.token);
    const verify = await cf.verifyToken();
    if (!verify.success) return reply.code(400).send({ error: "TOKEN_INVALID", detail: verify.errors });
    const accounts = await cf.listAccounts();
    if (!accounts.success || accounts.result.length === 0) return reply.code(400).send({ error: "NO_ACCOUNT_ACCESS" });
    const { encryptSecret } = await import("@proxy/shared");
    const box = encryptSecret(body.token, process.env.APP_SECRET!);
    const row = (await db.insert(schema.cloudflareAccounts).values({
      label: body.label, tokenEnc: box.enc, tokenIv: box.iv, tokenTag: box.tag,
      accountCfId: accounts.result[0].id, accountName: accounts.result[0].name,
      permissionsJson: ["WorkersScripts:Edit", "WorkersKVStorage:Edit", "AccountSettings:Read"],
      tokenStatus: "valid", lastValidatedAt: new Date(),
    }).returning())[0];
    void audit(db, "admin", (req as any).admin.id, "cf.account.add", { label: body.label }, { type: "cf_account", id: row.id });
    return reply.code(201).send({ account: { id: row.id, label: row.label, accountName: row.accountName }, accounts: accounts.result });
  });

  app.post("/api/provisioning/jobs", { preHandler: requireRole("admin") }, async (req, reply) => {
    const body = z.object({
      cfAccountId: z.string().uuid(), poolSlug: z.string().min(1),
      cfToken: z.string().optional(), // only needed if token not yet stored
    }).parse(req.body);
    const { runProvisioningJob } = await import("@proxy/cloudflare");
    const job = (await db.insert(schema.provisioningJobs).values({
      cfAccountId: body.cfAccountId, kind: "provision", stepsJson: [],
    }).returning())[0];
    const bundle = process.env.BPB_BUNDLE ?? "// placeholder fork bundle";
    const result = await runProvisioningJob({
      db, jobId: job.id, appSecret: process.env.APP_SECRET!,
      mgtBaseUrl: process.env.PUBLIC_BASE_URL!, bundle, bundleVersion: "v0.1.0",
      poolSlug: body.poolSlug, cfToken: body.cfToken,
    });
    return reply.code(result.ok ? 201 : 500).send({ jobId: job.id, ...result });
  });

  app.get("/api/provisioning/jobs/:id", { preHandler: requireRole("viewer") }, async (req) => {
    const { id } = z.object({ id: z.string().uuid() }).parse(req.params);
    return (await db.select().from(schema.provisioningJobs).where(eq(schema.provisioningJobs.id, id)).limit(1))[0];
  });

  // ---------- orders (synced with bot) ----------
  app.get("/api/orders", { preHandler: requireRole("viewer") }, async (req) => {
    const { status } = z.object({ status: z.enum(["pending", "approved", "rejected", "cancelled"]).optional() }).parse(req.query);
    const q = db.select().from(schema.orders).orderBy(desc(schema.orders.createdAt)).limit(200);
    return status ? q.where(eq(schema.orders.status, status)) : q;
  });

  app.post("/api/orders/:id/approve", { preHandler: requireRole("admin") }, async (req) => {
    const { id } = z.object({ id: z.string().uuid() }).parse(req.params);
    const { approveOrder } = await import("@proxy/core");
    const result = await approveOrder(db, id, (req as any).admin.id);
    void audit(db, "admin", (req as any).admin.id, "order.approve.panel", { id });
    return result;
  });

  app.post("/api/orders/:id/reject", { preHandler: requireRole("admin") }, async (req) => {
    const { id } = z.object({ id: z.string().uuid() }).parse(req.params);
    const body = z.object({ reason: z.string().optional() }).parse(req.body ?? {});
    const { rejectOrder } = await import("@proxy/core");
    const result = await rejectOrder(db, id, (req as any).admin.id, body.reason);
    void audit(db, "admin", (req as any).admin.id, "order.reject.panel", { id });
    return result;
  });

  // ---------- audit ----------
  app.get("/api/audit", { preHandler: requireRole("admin") }, async () =>
    db.select().from(schema.auditLogs).orderBy(desc(schema.auditLogs.id)).limit(200));
}

export type { AdminRole };
