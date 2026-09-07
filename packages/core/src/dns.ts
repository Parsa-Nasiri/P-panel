import type { DnsRoutingMode, DnsResourceType } from "@proxy/shared";

export interface DnsResourceLite { id: string; type: DnsResourceType; urlOrIp: string; name: string }

/**
 * Builds client-specific DNS artifacts from a pool's DNS profile.
 * doh-worker entries are the pool's own nodes (survive ISP DNS hijack);
 * plain-ip entries bootstrap the DoH hostname resolution;
 * via-tunnel routes DNS queries through the proxy (strongest country-block bypass).
 */
export function singBoxDns(resources: DnsResourceLite[], mode: DnsRoutingMode, proxyTag = "proxy") {
  const doh = resources.filter((r) => r.type === "doh-worker" || r.type === "doh-public");
  const bootstrap = resources.filter((r) => r.type === "plain-ip");
  const servers = [
    ...doh.map((r, i) => ({
      tag: `doh-${i}`, address: r.urlOrIp, detour: mode === "via-tunnel" ? proxyTag : undefined,
    })),
    ...bootstrap.map((r, i) => ({ tag: `boot-${i}`, address: `${r.urlOrIp}`, detour: undefined })),
  ];
  return {
    servers,
    rules: [{ outbound: "any", server: servers[0]?.tag ?? "doh-0" }],
    final: servers[0]?.tag ?? "doh-0",
    strategy: "prefer_ipv4",
  };
}

export function clashDns(resources: DnsResourceLite[], mode: DnsRoutingMode): string {
  const doh = resources.filter((r) => r.type === "doh-worker" || r.type === "doh-public").map((r) => r.urlOrIp);
  const boot = resources.filter((r) => r.type === "plain-ip").map((r) => r.urlOrIp);
  // Note: Clash/Mihomo detour support for DNS is weak; recommended mode is worker DoH or TUN.
  return (
    `dns:\n  enable: true\n  ipv6: false\n` +
    `  nameserver:\n${doh.map((u) => `    - "${u}${mode === "via-tunnel" ? "#proxy" : ""}"`).join("\n")}\n` +
    (boot.length ? `  default-nameserver:\n${boot.map((u) => `    - ${u}`).join("\n")}\n` : "")
  );
}

export function v2rayDns(resources: DnsResourceLite[]): string {
  const doh = resources.filter((r) => r.type === "doh-worker" || r.type === "doh-public").map((r) => r.urlOrIp);
  return doh[0] ?? "1.1.1.1";
}

export function rawDohUrls(resources: DnsResourceLite[]): string[] {
  return resources.filter((r) => r.type === "doh-worker" || r.type === "doh-public").map((r) => r.urlOrIp);
}
