import { eq } from "drizzle-orm";
import { z } from "zod";
import type { FastifyInstance } from "fastify";
import type { Db } from "@proxy/database";
import { schema } from "@proxy/database";
import { verifyNodeAuth } from "../auth.js";
import { ingestUsageBatch } from "@proxy/core";
import { audit } from "@proxy/core";

/** Node uplink: config pull, usage push, health push — all HMAC-signed. */
export async function registerNodeRoutes(app: FastifyInstance, db: Db) {
  app.addContentTypeParser("*", { parseAs: "string" }, (_req, body, done) => done(null, body as string));

  app.post("/v1/node/config", async (req, reply) => {
    const raw = req.body as string ?? "";
    const auth = await verifyNodeAuth(db, req, raw);
    if (!auth) return reply.code(401).send({ error: "NODE_AUTH_FAILED" });
    const node = (await db.select().from(schema.nodes).where(eq(schema.nodes.id, auth.nodeId)).limit(1))[0];
    if (!node) return reply.code(404).send({ error: "NODE_NOT_FOUND" });

    const { quotaStates } = await import("@proxy/core");
    const quotas = await quotaStates(db);
    const slots = await db.select({
      uuid: schema.deviceSlots.uuid, subId: schema.deviceSlots.subscriptionId,
      idx: schema.deviceSlots.idx, status: schema.deviceSlots.status,
    }).from(schema.deviceSlots).where(eq(schema.deviceSlots.status, "active"));
    const subs = await db.select({
      id: schema.subscriptions.id, status: schema.subscriptions.status,
      bytesUsed: schema.subscriptions.bytesUsed, bytesTotal: schema.subscriptions.bytesTotal,
      expiresAt: schema.subscriptions.expiresAt,
    }).from(schema.subscriptions);

    const activeSubs = new Map(subs.map((s) => [s.id, s]));
    const policy = {
      version: node.configVersion,
      node: { id: node.id, kind: node.kind },
      slots: slots
        .filter((s) => activeSubs.has(s.subId))
        .map((s) => {
          const sub = activeSubs.get(s.subId)!;
          const quota = quotas.find((q) => q.subId === s.subId);
          return {
            uuid: s.uuid, sub_ref: s.subId, slot: s.idx,
            allowed: sub.status === "active" && (quota?.allowed ?? false),
          };
        }),
      issuedAt: new Date().toISOString(),
    };
    return { policy };
  });

  app.post("/v1/node/usage", async (req, reply) => {
    const raw = (req.body as string) ?? "{}";
    const auth = await verifyNodeAuth(db, req, raw);
    if (!auth) return reply.code(401).send({ error: "NODE_AUTH_FAILED" });
    const batch = z.object({
      node_id: z.string().uuid(), seq: z.number().int().nonnegative(), window_start: z.string(),
      entries: z.array(z.object({
        sub_ref: z.string().uuid(), slot: z.number().int().min(0),
        up: z.number().nonnegative(), down: z.number().nonnegative(), conns: z.number().int().nonnegative().default(0),
        ips: z.array(z.string()).optional(),
      })).max(2000),
    }).parse(JSON.parse(raw));
    if (batch.node_id !== auth.nodeId) return reply.code(403).send({ error: "NODE_MISMATCH" });

    const result = await ingestUsageBatch(db, batch);
    void audit(db, "node", auth.nodeId, "usage.batch", { seq: batch.seq, ...result });
    return { ok: true, ...result };
  });

  app.post("/v1/node/health", async (req, reply) => {
    const raw = (req.body as string) ?? "{}";
    const auth = await verifyNodeAuth(db, req, raw);
    if (!auth) return reply.code(401).send({ error: "NODE_AUTH_FAILED" });
    const body = z.object({
      version: z.string().optional(), config_version: z.number().optional(),
      latency_ms: z.number().optional(), jitter_ms: z.number().optional(),
      err_rate: z.number().optional(), errors: z.record(z.unknown()).optional(),
    }).parse(JSON.parse(raw));
    await db.insert(schema.healthChecks).values({
      nodeId: auth.nodeId, httpOk: true, latencyMs: body.latency_ms, jitterMs: body.jitter_ms,
      errRate: body.err_rate, selfReport: body.errors ?? {},
    });
    await db.update(schema.nodes)
      .set({ lastHeartbeatAt: new Date(), status: nodeStatusFromErrRate(body.err_rate ?? 0), bundleVersion: body.version })
      .where(eq(schema.nodes.id, auth.nodeId));
    return { ok: true };
  });
}

function nodeStatusFromErrRate(errRate: number): "ONLINE" | "DEGRADED" {
  return errRate > 0.2 ? "DEGRADED" : "ONLINE";
}
