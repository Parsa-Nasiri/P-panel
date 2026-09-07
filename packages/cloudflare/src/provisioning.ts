import { eq } from "drizzle-orm";
import { encryptSecret, randomToken } from "@proxy/shared";
import { CfClient } from "./client.js";
import { schema } from "@proxy/database";
import type { Db } from "@proxy/database";

export interface ProvisionContext {
  db: Db;
  jobId: string;
  appSecret: string;
  mgtBaseUrl: string; // control plane base URL, e.g. https://cp.example.com
  bundle: string; // fork bundle JS (main module)
  bundleVersion: string;
  poolSlug: string;
  // token is supplied out-of-band (validated first, then encrypted into cf_accounts)
  cfToken?: string;
}

type Step = { name: string; run: (ctx: StepCtx) => Promise<string> };
type StepCtx = ProvisionContext & { state: Record<string, string> };

/**
 * Idempotent provisioning: deterministic names + "already done?" checks per step,
 * checkpointed in provisioning_jobs.current_step. Re-running resumes; failures roll back.
 */
export async function runProvisioningJob(ctx: ProvisionContext): Promise<{ ok: boolean; error?: string }> {
  const { db } = ctx;
  const job = (await db.select().from(schema.provisioningJobs).where(eq(schema.provisioningJobs.id, ctx.jobId)).limit(1))[0];
  if (!job) return { ok: false, error: "job_not_found" };
  const account = (await db.select().from(schema.cloudflareAccounts).where(eq(schema.cloudflareAccounts.id, job.cfAccountId!)).limit(1))[0];
  if (!account) return { ok: false, error: "account_not_found" };

  const cf = new CfClient(ctx.cfToken ?? "");
  const steps: Step[] = [
    { name: "accounts", run: async () => {
      const r = await cf.listAccounts();
      if (!r.success || r.result.length === 0) throw new Error("no_accounts_or_permission");
      return r.result[0].id;
    }},
    { name: "kv", run: async (s) => {
      const name = `bpb-kv-${s.state.name6}`;
      const existing = await cf.listKvNamespaces(s.state.accountId);
      const found = existing.result?.find((n) => n.title === name);
      if (found) return found.id;
      const created = await cf.createKvNamespace(s.state.accountId, name);
      if (!created.success) throw new Error(`kv_create_failed: ${created.errors?.[0]?.message}`);
      return created.result.id;
    }},
    { name: "secret", run: async (s) => {
      s.state.nodeSecret = randomToken(32);
      return "generated";
    }},
    { name: "script", run: async (s) => {
      const exists = await cf.listScripts(s.state.accountId);
      if (exists.result?.some((w) => w.id === s.state.workerName)) return "already_deployed";
      const r = await cf.uploadWorkerScript(s.state.accountId, s.state.workerName, {
        mainModuleContent: ctx.bundle,
        compatibilityDate: "2024-09-23",
        kvNamespaceId: s.state.kvId,
        secrets: { MGT_URL: ctx.mgtBaseUrl, NODE_SECRET: s.state.nodeSecret, NODE_ID: s.state.nodeId },
      });
      if (!r.success) throw new Error(`script_upload_failed: ${r.errors?.[0]?.message}`);
      return r.result.id;
    }},
    { name: "subdomain", run: async (s) => {
      const r = await cf.enableWorkersDev(s.state.accountId, s.state.workerName, true);
      return r.success ? `enabled:${s.state.workerName}.workers.dev` : `warn:${r.errors?.[0]?.message}`;
    }},
    { name: "register", run: async (s) => {
      const existing = await db.select().from(schema.nodes).where(eq(schema.nodes.workerName, s.state.workerName)).limit(1);
      if (existing[0]) { s.state.nodeId = existing[0].id; return "already_registered"; }
      const node = (await db.insert(schema.nodes).values({
        name: `bpb-${s.state.poolSlug}-${s.state.name6}`,
        cfAccountId: job.cfAccountId!, workerName: s.state.workerName,
        workerDomain: `${s.state.workerName}.workers.dev`,
        kind: "standard", status: "PROVISIONING", bundleVersion: ctx.bundleVersion,
      }).returning())[0];
      s.state.nodeId = node.id;
      const box = encryptSecret(s.state.nodeSecret, ctx.appSecret);
      await db.insert(schema.nodeSecrets).values({ nodeId: node.id, secretEnc: box.enc, secretIv: box.iv, secretTag: box.tag });
      await db.update(schema.provisioningJobs).set({ nodeId: node.id }).where(eq(schema.provisioningJobs.id, ctx.jobId));
      return node.id;
    }},
  ];

  const state: Record<string, string> = {};
  state.name6 = Math.random().toString(36).slice(2, 8);
  state.accountId = account.accountCfId;
  state.poolSlug = ctx.poolSlug.replace(/[^a-z0-9]/gi, "").toLowerCase().slice(0, 8) || "pool";
  state.workerName = `bpb-${state.poolSlug}-${state.name6}`;
  state.nodeId = job.nodeId ?? "";

  try {
    await db.update(schema.provisioningJobs).set({ state: "running" }).where(eq(schema.provisioningJobs.id, ctx.jobId));
    for (let i = job.currentStep; i < steps.length; i++) {
      const detail = await steps[i].run({ ...ctx, state });
      const stepsJson = [...(job.stepsJson ?? [])];
      stepsJson[i] = { name: steps[i].name, state: "done", detail };
      await db.update(schema.provisioningJobs).set({ currentStep: i + 1, stepsJson }).where(eq(schema.provisioningJobs.id, ctx.jobId));
      job.currentStep = i + 1; job.stepsJson = stepsJson;
    }
    await db.update(schema.provisioningJobs).set({ state: "done" }).where(eq(schema.provisioningJobs.id, ctx.jobId));
    return { ok: true };
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    await db.update(schema.provisioningJobs).set({ state: "failed", error: msg }).where(eq(schema.provisioningJobs.id, ctx.jobId));
    await rollback({ ...ctx, state });
    return { ok: false, error: msg };
  }
}

/** Compensating deletes in reverse order (best-effort). */
async function rollback(ctx: StepCtx) {
  const cf = new CfClient(ctx.cfToken ?? "");
  try { if (ctx.state.workerName && ctx.state.accountId) await cf.deleteScript(ctx.state.accountId, ctx.state.workerName); } catch { /* best effort */ }
  try { if (ctx.state.kvId && ctx.state.accountId) await cf.deleteKvNamespace(ctx.state.accountId, ctx.state.kvId); } catch { /* best effort */ }
}
