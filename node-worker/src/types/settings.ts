export type LogLevel = 'debug' | 'info' | 'warning' | 'error';
export type Fingerprint = 'chrome' | 'firefox' | 'safari' | 'ios' | 'android' | 'edge' | '360' | 'qq' | 'random';
export type FragmentMode = 'custom' | 'shake' | 'freeze';
export type FragmentPacket = 'tlshello' | 'clienthello' | 'custom';

// ============================================================================
// PROVISIONED PROXY USERS — the multi-tenant credential layer (Verdent fork)
// ============================================================================
// A ProxyUser is one provisioned Configuration's proxy credential on this Node.
// The map is written exclusively by the Control Plane (via the Cloudflare KV
// API) and read by the Node's protocol handlers. Keys:
//   - VLESS:   "vl:<uuid>"
//   - Trojan:  "tr:<sha224(password)-hex>"
// Value shape mirrors Document 1, "BPB Fork Scope" #1:
//   { [uuid]: { configId, status } }
// `deviceLimit` is carried here (not in Postgres) because the enforcement
// authority is the Node's own Durable Object (Document 3, §Device Limits).

export interface ProxyUser {
    configId: string;
    status: 'active' | 'disabled';
    deviceLimit?: number;
}

export type ProxyUserMap = Record<string, ProxyUser>;

// ============================================================================
// EMBEDDED SETTINGS — minimal embed, provisioned at provisioning time.
// Deliberately NO accID / apiToken: a Node never receives the credential that
// provisioned it (Document 5, "Cloudflare API tokens").
// ============================================================================

export interface EmbededSettings {
    nodeId: string;
    verdentUrl: string;
    securePath: string;
    proxyIpMode: string;
    proxyIPs: string[];
    prefixes: string[];
    fallback: string;
    dohUrl: string;
    mainDomain: string;
}

export interface ReqSettings {
    client: string;
    origin: string;
    searchParams: URLSearchParams;
    pathname: string;
    hostname: string;
    httpPorts: number[];
    httpsPorts: number[];
}

export interface DnsHost {
    host: string;
    isDomain: boolean;
    ipv4: string[];
    ipv6: string[];
}

export interface WarpAccount {
    privateKey: string;
    publicKey: string;
    warpIPv6: string;
    reserved: string;
}

export interface UpstreamProxy {
    upstreamServer?: string;
    upstreamPort?: number;
}
