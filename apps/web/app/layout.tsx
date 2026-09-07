import type { Metadata } from "next";
export const metadata: Metadata = { title: "Proxy Control Plane", robots: { index: false, follow: false } };
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="fa"><body style={{ background: "#f6f8fb", margin: 0 }}>{children}</body></html>;
}
