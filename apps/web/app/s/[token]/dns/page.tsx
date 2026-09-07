import Link from "next/link";
import { createDb, schema } from "@proxy/database";
import { hashToken } from "@proxy/core";
import { clashDns, singBoxDns, rawDohUrls } from "@proxy/core";
import { eq } from "drizzle-orm";

export const dynamic = "force-dynamic";

export default async function DnsPage({ params, searchParams }: { params: { token: string }; searchParams: { client?: string } }) {
  const { db } = createDb(process.env.DATABASE_URL!);
  const sub = (await db.select().from(schema.subscriptions)
    .where(eq(schema.subscriptions.tokenHash, hashToken(params.token))).limit(1))[0];
  if (!sub) return <main dir="rtl" style={{ padding: 40 }}>لینک نامعتبر است.</main>;
  const plan = (await db.select().from(schema.plans).where(eq(schema.plans.id, sub.planId)).limit(1))[0];
  if (!plan?.dnsProfileId) return <main dir="rtl" style={{ padding: 40 }}>این کانفیگ DNS گیمینگ ندارد.</main>;

  const profile = (await db.select().from(schema.dnsProfiles).where(eq(schema.dnsProfiles.id, plan.dnsProfileId)).limit(1))[0];
  const resources = (await db.select().from(schema.dnsResources)).filter((r) => profile.resourceIds.includes(r.id));
  const lite = resources.map((r) => ({ id: r.id, type: r.type, urlOrIp: r.urlOrIp, name: r.name }));
  const client = searchParams.client ?? "singbox";
  const body =
    client === "clash" ? clashDns(lite, profile.routingMode) :
    client === "raw" ? rawDohUrls(lite).join("\n") :
    JSON.stringify(singBoxDns(lite, profile.routingMode), null, 2);

  return (
    <main dir="rtl" style={{ maxWidth: 640, margin: "40px auto", fontFamily: "Tahoma" }}>
      <h1>🌐 DNS گیمینگ — {sub.displayName}</h1>
      <p>
        [<Link href={`?client=singbox`}>sing-box</Link>] ·
        [<Link href={`?client=clash`}>Clash</Link>] ·
        [<Link href={`?client=raw`}>DoH خام</Link>]
      </p>
      <pre style={{ background: "#0b0f17", color: "#e6e9ef", padding: 16, borderRadius: 12, overflow: "auto", direction: "ltr" }}>{body}</pre>
      <Link href={`/s/${params.token}/status`}>🔙 بازگشت</Link>
    </main>
  );
}
