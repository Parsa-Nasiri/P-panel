import { createDb, schema } from "@proxy/database";
import { eq } from "drizzle-orm";
import { hashToken } from "@proxy/core";

export const dynamic = "force-dynamic";

export default async function StatusPage({ params }: { params: { token: string } }) {
  const { db } = createDb(process.env.DATABASE_URL!);
  const sub = (await db.select().from(schema.subscriptions)
    .where(eq(schema.subscriptions.tokenHash, hashToken(params.token))).limit(1))[0];
  if (!sub) {
    return <main style={styles.main}><p>لینک نامعتبر است.</p></main>;
  }
  const plan = (await db.select().from(schema.plans).where(eq(schema.plans.id, sub.planId)).limit(1))[0];
  const slots = await db.select().from(schema.deviceSlots).where(eq(schema.deviceSlots.subscriptionId, sub.id));
  const usedGb = (Number(sub.bytesUsed) / 1024 ** 3).toFixed(1);
  const totalGb = (Number(sub.bytesTotal) / 1024 ** 3).toFixed(1);
  const pct = Math.min(100, Math.max(0, Math.round((Number(sub.bytesUsed) / Number(sub.bytesTotal)) * 100)));
  const daysLeft = Math.max(0, Math.ceil((sub.expiresAt.getTime() - Date.now()) / 86_400_000));
  const statusFa = sub.status === "active" ? "🟢 فعال" : sub.status === "exceeded" ? "🟠 اتمام ترافیک" : "🔴 منقضی";

  return (
    <main style={styles.main} dir="rtl">
      <h1 style={styles.title}>{sub.displayName}</h1>
      <p>پلن: {plan?.name ?? "-"} — {statusFa}</p>
      <div style={styles.barOuter}><div style={{ ...styles.barInner, width: `${pct}%` }} /></div>
      <p style={{ fontWeight: 700 }}>{usedGb} از {totalGb} گیگابایت ({pct}٪)</p>
      <p>⏳ {daysLeft} روز باقی‌مانده</p>
      <h2>دستگاه‌ها</h2>
      <ul>
        {slots.map((s) => (
          <li key={s.id}>{s.name ?? `دستگاه ${s.idx + 1}`} — {s.status === "active" ? "فعال" : "لغو شده"}</li>
        ))}
      </ul>
      <h2>دریافت DNS (گیمینگ)</h2>
      <p><a href={`/s/${params.token}/dns`}>🌐 دریافت DNS این کانفیگ</a></p>
      <style>{`body{background:#0b0f17;color:#e6e9ef;font-family:Tahoma,Vazirmatn,sans-serif}`}</style>
    </main>
  );
}

const styles: Record<string, React.CSSProperties> = {
  main: { maxWidth: 480, margin: "40px auto", padding: 24, border: "1px solid #232a38", borderRadius: 16 },
  title: { fontSize: 22, marginBottom: 8 },
  barOuter: { background: "#1a2130", borderRadius: 999, height: 14, overflow: "hidden" },
  barInner: { background: "linear-gradient(90deg,#22c55e,#84cc16)", height: "100%" },
};
