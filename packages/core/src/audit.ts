import { eq } from "drizzle-orm";
import type { Db } from "@proxy/database";
import { schema } from "@proxy/database";

export async function audit(
  db: Db,
  actorType: "admin" | "system" | "node" | "telegram_customer" | "telegram_admin",
  actorId: string | null,
  action: string,
  meta?: Record<string, unknown>,
  target?: { type: string; id: string }
) {
  try {
    await db.insert(schema.auditLogs).values({
      actorType, actorId, action, meta,
      targetType: target?.type, targetId: target?.id,
    });
  } catch { /* audit must never break the request path */ }
}
