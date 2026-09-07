import type { SubEndpoint, ClientFlavor } from "@proxy/shared";

// ---------- client detection ----------
export function detectClient(ua: string): ClientFlavor {
  const s = ua.toLowerCase();
  if (s.includes("clash") || s.includes("mihomo") || s.includes("flclash") || s.includes("verge")) return "clash";
  if (s.includes("sing-box") || s.includes("singbox") || s.includes("husi") || s.includes("karing")) return "singbox";
  if (s.includes("v2ray") || s.includes("xray") || s.includes("streisand") || s.includes("mahsa") || s.includes("neko")) return "v2ray";
  return "unknown";
}

// ---------- v2ray (Xray family) ----------
export function vlessUri(e: SubEndpoint): string {
  const params = new URLSearchParams({
    type: e.transport, security: e.tls ? "tls" : "none",
    host: e.host, sni: e.sni, path: e.path, fp: "chrome", alpn: "h2,http/1.1",
  });
  return `vless://${e.uuid}@${e.address}:${e.port}?${params.toString()}#${encodeURIComponent(e.name)}`;
}

export function renderV2ray(endpoints: SubEndpoint[]): string {
  return Buffer.from(endpoints.map(vlessUri).join("\n"), "utf8").toString("base64");
}

// ---------- sing-box ----------
export function renderSingBox(endpoints: SubEndpoint[], dns?: Record<string, unknown>): string {
  const outbounds = endpoints.map((e) => ({
    type: "vless", tag: e.name, server: e.address, server_port: e.port, uuid: e.uuid,
    tls: e.tls ? { enabled: true, server_name: e.sni, utls: { enabled: true, fingerprint: "chrome" } } : undefined,
    transport: { type: "ws", path: e.path, headers: { Host: e.host } },
  }));
  const obj: Record<string, unknown> = {
    log: { level: "warn" },
    outbounds: [...outbounds, { type: "direct", tag: "direct" }],
  };
  if (endpoints.length > 1) {
    obj.outbounds = [
      { type: "selector", tag: "proxy", outbounds: [...endpoints.map((e) => e.name), "auto-fallback"], default: endpoints[0].name },
      { type: "urltest", tag: "auto-fallback", outbounds: endpoints.map((e) => e.name),
        url: "https://www.gstatic.com/generate_204", interval: "3m", tolerance: 150 },
      ...outbounds,
      { type: "direct", tag: "direct" },
    ];
  }
  if (dns) obj.dns = dns;
  return JSON.stringify(obj, null, 2);
}

// ---------- clash / mihomo ----------
export function renderClash(endpoints: SubEndpoint[], dns?: string): string {
  const proxies = endpoints.map((e) =>
    `  - name: "${e.name}"\n` +
    `    type: vless\n    server: ${e.address}\n    port: ${e.port}\n    uuid: ${e.uuid}\n` +
    `    tls: ${e.tls}\n    servername: ${e.sni}\n    udp: false\n` +
    `    ws-opts:\n      path: ${e.path}\n      headers:\n        Host: ${e.host}`
  ).join("\n");
  const names = endpoints.map((e) => `"${e.name}"`).join(", ");
  let yml =
    `port: 7890\nallow-lan: false\nmode: rule\nlog-level: warning\n` +
    `proxies:\n${proxies}\n` +
    `proxy-groups:\n  - name: FALLBACK\n    type: fallback\n    proxies: [${names}]\n` +
    `    url: https://www.gstatic.com/generate_204\n    interval: 300\n` +
    `rules:\n  - MATCH,FALLBACK\n`;
  if (dns) yml += dns;
  return yml;
}

// ---------- subscription metadata ----------
export function userInfoHeader(bytesUsed: number, bytesTotal: number, expiresAt: Date): string {
  const used = Math.max(0, bytesUsed);
  const up = Math.floor(used / 2); // convention: up/down split (node reports combined)
  return `upload=${up}; download=${used - up}; total=${bytesTotal}; expire=${Math.floor(expiresAt.getTime() / 1000)}`;
}
