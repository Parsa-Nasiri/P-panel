import { and, eq, gt } from "drizzle-orm";
import type { FastifyReply, FastifyRequest } from "fastify";
import { schema } from "@proxy/database";
import type { Db } from "@proxy/database";
import { verifyPassword, verifyNodeSignature, sha256 } from "@proxy/shared";

export type AdminRole = "owner" | "admin" | "operator" | "viewer";
const RANK: Record<AdminRole, number> = { viewer: 0, operator: 1, admin: 2, owner: 3 };

export function requireRole(min: AdminRole) {
  return async (req: FastifyRequest, reply: FastifyReply) => {
    const admin = await sessionAdmin((req.server as any).db as Db, req);
    if (!admin) return reply.code(401).send({ error: "UNAUTHENTICATED" });
    if (RANK[admin.role] < RANK[min]) return reply.code(403).send({ error: "FORBIDDEN" });
    (req as any).admin = admin;
  };
}

export async function sessionAdmin(db: Db, req: FastifyRequest) {
  const token = (req.cookies as Record<string, string | undefined>)["padmin"];
  if (!token) return null;
  const rows = await db.select({ admin: schema.admins })
    .from(schema.adminSessions)
    .innerJoin(schema.admins, eq(schema.admins.id, schema.adminSessions.adminId))
    .where(and(eq(schema.adminSessions.tokenHash, sha256(token)), gt(schema.adminSessions.expiresAt, new Date())))
    .limit(1);
  return rows[0]?.admin ?? null;
}

export interface NodeAuthResult { nodeId: string }

/** HMAC auth for /v1/node/*: headers x-node-id, x-ts, x-signature over "method:path:ts:bodyHash". */
export async function verifyNodeAuth(db: Db, req: FastifyRequest, rawBody: string): Promise<NodeAuthResult | null> {
  const nodeId = req.headers["x-node-id"] as string | undefined;
  const ts = req.headers["x-ts"] as string | undefined;
  const sig = req.headers["x-signature"] as string | undefined;
  if (!nodeId || !ts || !sig) return null;
  const secretRow = (await db.select().from(schema.nodeSecrets).where(eq(schema.nodeSecrets.nodeId, nodeId)).limit(1))[0];
  if (!secretRow) return null;
  const { decryptSecret } = await import("@proxy/shared");
  const secret = decryptSecret(
    { enc: secretRow.secretEnc, iv: secretRow.secretIv, tag: secretRow.secretTag },
    process.env.APP_SECRET!
  );
  const ok = verifyNodeSignature(secret, req.method, req.url.split("?")[0], ts, rawBody, sig);
  return ok ? { nodeId } : null;
}
