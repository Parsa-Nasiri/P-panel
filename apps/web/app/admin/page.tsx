import { createDb, schema } from "@proxy/database";
import { sql } from "drizzle-orm";

export const dynamic = "force-dynamic";

export default async function AdminHome() {
  const { db } = createDb(process.env.DATABASE_URL!);
  const [{ count: subCount }] = await db.select({ count: sql<number>`count(*)::int` }).from(schema.subscriptions);
  const [{ count: nodeCount }] = await db.select({ count: sql<number>`count(*)::int` }).from(schema.nodes);
  const pending = await db.select({ id: schema.orders.id }).from(schema.orders).where(sql`status = 'pending'`);

  return (
    <main style={{ fontFamily: "system-ui", maxWidth: 720, margin: "40px auto" }}>
      <h1>Admin Dashboard</h1>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 12 }}>
        <Card title="Active subscriptions" value={subCount} />
        <Card title="Nodes" value={nodeCount} />
        <Card title="Pending orders" value={pending.length} />
      </div>
      <p style={{ color: "#666", marginTop: 24 }}>
        Full admin UI (users, subscriptions, infrastructure, provisioning wizard, pools, gaming, DNS) ships in the UI phase; API endpoints are already live.
      </p>
    </main>
  );
}

function Card({ title, value }: { title: string; value: number }) {
  return (
    <div style={{ border: "1px solid #e2e6ee", borderRadius: 12, padding: 16 }}>
      <div style={{ fontSize: 13, color: "#666" }}>{title}</div>
      <div style={{ fontSize: 28, fontWeight: 700 }}>{value}</div>
    </div>
  );
}
