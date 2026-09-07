import Fastify, { type FastifyInstance } from "fastify";
import { sql } from "drizzle-orm";
import cookie from "@fastify/cookie";
import rateLimit from "@fastify/rate-limit";
import { createDb, schema } from "@proxy/database";
import { registerAdminRoutes } from "./routes/admin.js";
import { registerPublicRoutes } from "./routes/public.js";
import { registerNodeRoutes } from "./routes/node.js";
import { audit } from "@proxy/core";

export async function buildServer() {
  const app = Fastify({ logger: { level: process.env.NODE_ENV === "production" ? "info" : "debug" } });
  const { db } = createDb(process.env.DATABASE_URL!);
  (app as any).db = db;

  await app.register(cookie);
  await app.register(rateLimit, { global: false });

  app.get("/healthz", async () => {
    await db.execute(sql`select 1`);
    return { ok: true, ts: Date.now() };
  });

  await registerAdminRoutes(app, db);
  await registerPublicRoutes(app, db);
  await registerNodeRoutes(app, db);

  app.setErrorHandler((err, req, reply) => {
    req.log.error(err);
    void audit(db, "system", null, "error", { message: err.message, path: req.url });
    reply.code(err.statusCode ?? 500).send({ error: err.name ?? "INTERNAL", message: err.message });
  });

  return { app, db, schema };
}

if (process.env.JOB_MODE !== "1") {
  buildServer().then(({ app }) => app.listen({ port: Number(process.env.PORT ?? 3000), host: "0.0.0.0" }));
}

export type { FastifyInstance };
