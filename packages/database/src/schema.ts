import { pgTable, uuid, text, integer, bigint, boolean, timestamp, real, jsonb, uniqueIndex, index, primaryKey, serial } from "drizzle-orm/pg-core";
import type { NodeState, SubStatus, OrderStatus, DnsResourceType, DnsRoutingMode, PoolKind, GamingHysteresis } from "@proxy/shared";

// ---------- people ----------
export const users = pgTable("users", {
  id: uuid("id").defaultRandom().primaryKey(),
  email: text("email"),
  name: text("name"),
  note: text("note"),
  status: text("status").$type<"active" | "suspended">().notNull().default("active"),
  telegramId: bigint("telegram_id", { mode: "number" }),
  telegramUsername: text("telegram_username"),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
}, (t) => ({ telegramUq: uniqueIndex("users_telegram_uq").on(t.telegramId) }));

export const admins = pgTable("admins", {
  id: uuid("id").defaultRandom().primaryKey(),
  email: text("email").notNull().unique(),
  passwordHash: text("password_hash").notNull(),
  role: text("role").$type<"owner" | "admin" | "operator" | "viewer">().notNull().default("admin"),
  totpSecret: text("totp_secret"),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
});

export const adminSessions = pgTable("admin_sessions", {
  id: uuid("id").defaultRandom().primaryKey(),
  adminId: uuid("admin_id").notNull().references(() => admins.id, { onDelete: "cascade" }),
  tokenHash: text("token_hash").notNull().unique(),
  expiresAt: timestamp("expires_at", { withTimezone: true }).notNull(),
  ip: text("ip"),
  ua: text("ua"),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
});

// ---------- commerce ----------
export const plans = pgTable("plans", {
  id: uuid("id").defaultRandom().primaryKey(),
  name: text("name").notNull(),
  durationDays: integer("duration_days").notNull(),
  trafficBytes: bigint("traffic_bytes", { mode: "number" }).notNull(),
  maxDevices: integer("max_devices").notNull().default(1),
  profileId: uuid("profile_id").references(() => profiles.id),
  poolId: uuid("pool_id").references(() => nodePools.id),
  gaming: boolean("gaming").notNull().default(false),
  dnsProfileId: uuid("dns_profile_id"),
  failoverMode: text("failover_mode").$type<"re-rank" | "sticky">().notNull().default("re-rank"),
  protocols: jsonb("protocols").$type<string[]>().notNull().default(["vless"]),
  priceCents: integer("price_cents").notNull().default(0),
  isTrial: boolean("is_trial").notNull().default(false),
  isActive: boolean("is_active").notNull().default(true),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
});

export const subscriptions = pgTable("subscriptions", {
  id: uuid("id").defaultRandom().primaryKey(),
  code: text("code").notNull().unique(), // P-ejrnfk-123
  userId: uuid("user_id").notNull().references(() => users.id, { onDelete: "cascade" }),
  planId: uuid("plan_id").notNull().references(() => plans.id),
  tokenHash: text("token_hash").notNull().unique(),
  tokenEnc: text("token_enc"), // AES-GCM copy so the owner can re-display links
  tokenIv: text("token_iv"),
  tokenTag: text("token_tag"),
  displayName: text("display_name").notNull(), // e.g. پارسا_48213
  status: text("status").$type<SubStatus>().notNull().default("active"),
  bytesUsed: bigint("bytes_used", { mode: "number" }).notNull().default(0),
  bytesTotal: bigint("bytes_total", { mode: "number" }).notNull(),
  expiresAt: timestamp("expires_at", { withTimezone: true }).notNull(),
  assignedNodeId: uuid("assigned_node_id"), // gaming sticky
  assignedSince: timestamp("assigned_since", { withTimezone: true }),
  recoveredAt: timestamp("recovered_at", { withTimezone: true }),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
}, (t) => ({ userIdx: index("subs_user_idx").on(t.userId), statusIdx: index("subs_status_idx").on(t.status) }));

export const deviceSlots = pgTable("device_slots", {
  id: uuid("id").defaultRandom().primaryKey(),
  subscriptionId: uuid("subscription_id").notNull().references(() => subscriptions.id, { onDelete: "cascade" }),
  idx: integer("idx").notNull(),
  uuid: text("uuid").notNull().unique(),
  name: text("name"),
  status: text("status").$type<"active" | "revoked">().notNull().default("active"),
  firstIp: text("first_ip"),
  lastIp: text("last_ip"),
  lastUa: text("last_ua"),
  lastSeenAt: timestamp("last_seen_at", { withTimezone: true }),
  revokedAt: timestamp("revoked_at", { withTimezone: true }),
}, (t) => ({ slotIdxUq: uniqueIndex("slot_sub_idx_uq").on(t.subscriptionId, t.idx) }));

export const botTrials = pgTable("bot_trials", {
  id: uuid("id").defaultRandom().primaryKey(),
  telegramUserId: bigint("telegram_user_id", { mode: "number" }).notNull(),
  subscriptionId: uuid("subscription_id").notNull().references(() => subscriptions.id, { onDelete: "cascade" }),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
}, (t) => ({ trialUserIdx: index("bot_trials_user_idx").on(t.telegramUserId) }));

export const orders = pgTable("orders", {
  id: uuid("id").defaultRandom().primaryKey(),
  userId: uuid("user_id").notNull().references(() => users.id, { onDelete: "cascade" }),
  telegramUserId: bigint("telegram_user_id", { mode: "number" }),
  planId: uuid("plan_id").notNull().references(() => plans.id),
  kind: text("kind").$type<"new" | "renew">().notNull().default("new"),
  targetSubscriptionId: uuid("target_subscription_id"),
  status: text("status").$type<OrderStatus>().notNull().default("pending"),
  screenshotFileId: text("screenshot_file_id"),
  customerNote: text("customer_note"),
  displayNameRequested: text("display_name_requested"),
  priceCents: integer("price_cents").notNull().default(0),
  reviewedBy: text("reviewed_by"),
  reviewedAt: timestamp("reviewed_at", { withTimezone: true }),
  rejectReason: text("reject_reason"),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
}, (t) => ({ statusIdx: index("orders_status_idx").on(t.status) }));

// ---------- metering ----------
export const usageEvents = pgTable("usage_events", {
  id: serial("id").primaryKey(),
  nodeId: uuid("node_id").notNull(),
  seq: bigint("seq", { mode: "number" }).notNull(),
  windowStart: timestamp("window_start", { withTimezone: true }).notNull(),
  subscriptionId: uuid("subscription_id").notNull(),
  slotIdx: integer("slot_idx").notNull(),
  up: bigint("up", { mode: "number" }).notNull(),
  down: bigint("down", { mode: "number" }).notNull(),
  conns: integer("conns").notNull().default(0),
  ts: timestamp("ts", { withTimezone: true }).notNull().defaultNow(),
}, (t) => ({
  nodeSeqUq: uniqueIndex("usage_node_seq_uq").on(t.nodeId, t.seq, t.subscriptionId, t.slotIdx),
  subIdx: index("usage_sub_idx").on(t.subscriptionId),
}));

export const usageDaily = pgTable("usage_daily", {
  subscriptionId: uuid("subscription_id").notNull().references(() => subscriptions.id, { onDelete: "cascade" }),
  day: text("day").notNull(), // YYYY-MM-DD UTC
  up: bigint("up", { mode: "number" }).notNull().default(0),
  down: bigint("down", { mode: "number" }).notNull().default(0),
  conns: integer("conns").notNull().default(0),
}, (t) => ({ pk: primaryKey({ columns: [t.subscriptionId, t.day] }) }));

// ---------- infrastructure ----------
export const cloudflareAccounts = pgTable("cloudflare_accounts", {
  id: uuid("id").defaultRandom().primaryKey(),
  label: text("label").notNull(),
  tokenEnc: text("token_enc").notNull(),
  tokenIv: text("token_iv").notNull(),
  tokenTag: text("token_tag").notNull(),
  accountCfId: text("account_cf_id").notNull(),
  accountName: text("account_name").notNull(),
  permissionsJson: jsonb("permissions_json").$type<string[]>().notNull().default([]),
  tokenStatus: text("token_status").$type<"valid" | "expired" | "invalid">().notNull().default("valid"),
  lastValidatedAt: timestamp("last_validated_at", { withTimezone: true }),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
});

export const nodes = pgTable("nodes", {
  id: uuid("id").defaultRandom().primaryKey(),
  name: text("name").notNull().unique(),
  cfAccountId: uuid("cf_account_id").notNull().references(() => cloudflareAccounts.id, { onDelete: "cascade" }),
  workerName: text("worker_name").notNull(),
  workerDomain: text("worker_domain"),
  kind: text("kind").$type<"standard" | "gaming">().notNull().default("standard"),
  poolId: uuid("pool_id").references(() => nodePools.id, { onDelete: "set null" }),
  profileId: uuid("profile_id").references(() => profiles.id),
  bundleVersion: text("bundle_version"),
  configVersion: integer("config_version").notNull().default(0),
  status: text("status").$type<NodeState>().notNull().default("PROVISIONING"),
  healthScore: real("health_score").notNull().default(0),
  lastHeartbeatAt: timestamp("last_heartbeat_at", { withTimezone: true }),
  enabled: boolean("enabled").notNull().default(true),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
}, (t) => ({ accountWorkerUq: uniqueIndex("node_account_worker_uq").on(t.cfAccountId, t.workerName) }));

export const nodeSecrets = pgTable("node_secrets", {
  nodeId: uuid("node_id").primaryKey().references(() => nodes.id, { onDelete: "cascade" }),
  secretEnc: text("secret_enc").notNull(),
  secretIv: text("secret_iv").notNull(),
  secretTag: text("secret_tag").notNull(),
});

export const nodePools = pgTable("node_pools", {
  id: uuid("id").defaultRandom().primaryKey(),
  name: text("name").notNull().unique(),
  kind: text("kind").$type<PoolKind>().notNull().default("standard"),
  region: text("region"),
  profileId: uuid("profile_id").references(() => profiles.id),
  healthPolicy: jsonb("health_policy").$type<GamingHysteresis>(),
  enabled: boolean("enabled").notNull().default(true),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
});

export const poolNodes = pgTable("pool_nodes", {
  poolId: uuid("pool_id").notNull().references(() => nodePools.id, { onDelete: "cascade" }),
  nodeId: uuid("node_id").notNull().references(() => nodes.id, { onDelete: "cascade" }),
  priority: integer("priority").notNull().default(0),
  enabled: boolean("enabled").notNull().default(true),
}, (t) => ({ pk: primaryKey({ columns: [t.poolId, t.nodeId] }) }));

export const profiles = pgTable("profiles", {
  id: uuid("id").defaultRandom().primaryKey(),
  name: text("name").notNull().unique(),
  kind: text("kind").$type<PoolKind>().notNull().default("standard"),
  params: jsonb("params").$type<Record<string, unknown>>().notNull().default({}),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
});

export const dnsResources = pgTable("dns_resources", {
  id: uuid("id").defaultRandom().primaryKey(),
  name: text("name").notNull(),
  type: text("type").$type<DnsResourceType>().notNull(),
  urlOrIp: text("url_or_ip").notNull(),
  nodeId: uuid("node_id").references(() => nodes.id, { onDelete: "set null" }),
  poolId: uuid("pool_id").references(() => nodePools.id, { onDelete: "cascade" }),
  status: text("status").$type<"ONLINE" | "OFFLINE" | "DEGRADED">().notNull().default("OFFLINE"),
  latencyMs: real("latency_ms"),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
});

export const dnsProfiles = pgTable("dns_profiles", {
  id: uuid("id").defaultRandom().primaryKey(),
  name: text("name").notNull().unique(),
  resourceIds: jsonb("resource_ids").$type<string[]>().notNull().default([]),
  routingMode: text("routing_mode").$type<DnsRoutingMode>().notNull().default("direct"),
  upstreams: jsonb("upstreams").$type<string[]>().notNull().default([]),
  params: jsonb("params").$type<Record<string, unknown>>().notNull().default({}),
});

export const gamingAssignments = pgTable("gaming_assignments", {
  id: uuid("id").defaultRandom().primaryKey(),
  subscriptionId: uuid("subscription_id").notNull().references(() => subscriptions.id, { onDelete: "cascade" }),
  poolId: uuid("pool_id").notNull().references(() => nodePools.id, { onDelete: "cascade" }),
  nodeId: uuid("node_id").notNull().references(() => nodes.id),
  since: timestamp("since", { withTimezone: true }).notNull().defaultNow(),
  reason: text("reason"),
});

// ---------- ops ----------
export const healthChecks = pgTable("health_checks", {
  id: serial("id").primaryKey(),
  nodeId: uuid("node_id").notNull().references(() => nodes.id, { onDelete: "cascade" }),
  ts: timestamp("ts", { withTimezone: true }).notNull().defaultNow(),
  httpOk: boolean("http_ok").notNull(),
  latencyMs: real("latency_ms"),
  jitterMs: real("jitter_ms"),
  errRate: real("err_rate"),
  selfReport: jsonb("self_report").$type<Record<string, unknown>>(),
});

export const provisioningJobs = pgTable("provisioning_jobs", {
  id: uuid("id").defaultRandom().primaryKey(),
  cfAccountId: uuid("cf_account_id").references(() => cloudflareAccounts.id, { onDelete: "cascade" }),
  nodeId: uuid("node_id"),
  kind: text("kind").$type<"provision" | "update" | "rollback" | "destroy">().notNull().default("provision"),
  state: text("state").$type<"pending" | "running" | "done" | "failed" | "rolled_back">().notNull().default("pending"),
  currentStep: integer("current_step").notNull().default(0),
  stepsJson: jsonb("steps_json").$type<{ name: string; state: string; detail?: string }[]>().notNull().default([]),
  logText: text("log_text").notNull().default(""),
  error: text("error"),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
});

export const auditLogs = pgTable("audit_logs", {
  id: serial("id").primaryKey(),
  actorType: text("actor_type").$type<"admin" | "system" | "node" | "telegram_customer" | "telegram_admin">().notNull(),
  actorId: text("actor_id"),
  action: text("action").notNull(),
  targetType: text("target_type"),
  targetId: text("target_id"),
  meta: jsonb("meta").$type<Record<string, unknown>>(),
  ts: timestamp("ts", { withTimezone: true }).notNull().defaultNow(),
});

export const settings = pgTable("settings", {
  key: text("key").primaryKey(),
  value: jsonb("value").$type<Record<string, unknown>>().notNull().default({}),
});

export const notifications = pgTable("notifications", {
  id: serial("id").primaryKey(),
  telegramUserId: bigint("telegram_user_id", { mode: "number" }).notNull(),
  text: text("text").notNull(),
  sentAt: timestamp("sent_at", { withTimezone: true }),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
});
