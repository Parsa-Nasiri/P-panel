import Link from "next/link";

export default function Home() {
  return (
    <main style={{ maxWidth: 560, margin: "80px auto", fontFamily: "system-ui" }}>
      <h1>Proxy Control Plane</h1>
      <p>Admin panel and customer status pages.</p>
      <ul>
        <li><Link href="/admin">Admin panel (login required)</Link></li>
        <li>Customer status: <code>/s/&lt;token&gt;/status</code></li>
        <li>Subscription: <code>/s/&lt;token&gt;</code></li>
      </ul>
    </main>
  );
}
