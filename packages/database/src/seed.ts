import { randomUUID } from "node:crypto";
import { hashPassword, randomToken, sha256 } from "@proxy/shared";
import { createDb, schema } from "./client.js";
import { admins, plans, profiles, nodePools, dnsProfiles, dnsResources, settings } from "./schema.js";

export async function seed(databaseUrl: string, adminEmail: string, adminPassword: string) {
  const { db } = createDb(databaseUrl);

  await db.insert(admins).values({ email: adminEmail, passwordHash: hashPassword(adminPassword), role: "owner" }).onConflictDoNothing();

  const stdProfile = await db.insert(profiles).values({
    name: "standard-default", kind: "standard",
    params: { proxyIPs: [], cleanIpDomains: [], fragment: null, ports: [443, 8443] },
  }).onConflictDoNothing().returning();
  const gamingProfile = await db.insert(profiles).values({
    name: "gaming-default", kind: "gaming",
    params: { configType: "warp", mux: false, fragment: null, mtu: 1380, endpoints: [], ports: [443, 8443, 2053], sticky: true },
  }).onConflictDoNothing().returning();

  const pool = await db.insert(nodePools).values({
    name: "EU-Standard-001", kind: "standard", region: "eu",
    profileId: stdProfile[0]?.id ?? randomUUID(),
    healthPolicy: { failureThreshold: 3, recoveryThreshold: 5, soakSec: 300, minResidencySec: 600, cooldownSec: 300 },
  }).onConflictDoNothing().returning();

  const dohProfile = await db.insert(dnsProfiles).values({
    name: "gaming-dns-eu", routingMode: "via-tunnel",
    resourceIds: [], upstreams: ["https://1.1.1.1/dns-query", "https://8.8.8.8/dns-query"],
  }).onConflictDoNothing().returning();

  await db.insert(dnsResources).values([
    { name: "Cloudflare DoH", type: "doh-public", urlOrIp: "https://1.1.1.1/dns-query", poolId: pool[0]?.id },
    { name: "Google DoH", type: "doh-public", urlOrIp: "https://8.8.8.8/dns-query", poolId: pool[0]?.id },
    { name: "CF plain bootstrap", type: "plain-ip", urlOrIp: "1.1.1.1", poolId: pool[0]?.id },
  ]).onConflictDoNothing();

  const trialToken = randomToken();
  await db.insert(plans).values([
    {
      name: "Standard 100GB", durationDays: 30, trafficBytes: 100 * 1024 ** 3, maxDevices: 3,
      profileId: stdProfile[0]?.id, poolId: pool[0]?.id, gaming: false, failoverMode: "re-rank",
      priceCents: 500000, isTrial: false, isActive: true,
    },
    {
      name: "Gaming 200GB", durationDays: 30, trafficBytes: 200 * 1024 ** 3, maxDevices: 2,
      profileId: gamingProfile[0]?.id, poolId: pool[0]?.id, gaming: true, failoverMode: "sticky",
      dnsProfileId: dohProfile[0]?.id, priceCents: 900000, isTrial: false, isActive: true,
    },
    {
      name: "Trial", durationDays: 2, trafficBytes: 100 * 1024 ** 2, maxDevices: 1,
      profileId: stdProfile[0]?.id, poolId: pool[0]?.id, gaming: false, failoverMode: "re-rank",
      priceCents: 0, isTrial: true, isActive: true,
    },
  ]).onConflictDoNothing();

  await db.insert(settings).values([
    { key: "payment_instructions", value: { text: "کارت به کارت: 6037-99xx-xxxx-xxxx — به نام مدیر" } },
    { key: "bot_texts", value: { supportHandle: "@admin" } },
    { key: "_trial_token_unused", value: { t: sha256(trialToken).slice(0, 8) } },
  ]).onConflictDoNothing();

  console.log("Seed complete. Admin:", adminEmail);
  process.exit(0);
}

if (process.argv[2]) {
  const [url, email, pass] = process.argv.slice(2);
  seed(url, email ?? "admin@local", pass ?? randomToken(16));
}
