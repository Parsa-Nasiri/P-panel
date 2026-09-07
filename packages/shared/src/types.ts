export type NodeState = "ONLINE" | "DEGRADED" | "OFFLINE" | "PROVISIONING" | "MAINTENANCE" | "QUARANTINED";
export type SubStatus = "active" | "expired" | "suspended" | "exceeded";
export type OrderStatus = "pending" | "approved" | "rejected" | "cancelled";
export type PoolKind = "standard" | "gaming";
export type DnsResourceType = "doh-worker" | "doh-public" | "dot-public" | "plain-ip";
export type DnsRoutingMode = "direct" | "via-tunnel";
export type ClientFlavor = "v2ray" | "singbox" | "clash" | "unknown";

export interface SubEndpoint {
  uuid: string;
  address: string;
  port: number;
  sni: string;
  host: string;
  path: string;
  tls: boolean;
  name: string;
  transport: "ws";
}

export interface UsageEntry {
  sub_ref: string; // subscription id (uuid)
  slot: number; // device slot idx
  up: number;
  down: number;
  conns: number;
  ips?: string[]; // distinct client IPs seen in window (slot sharing signal)
}

export interface UsageBatch {
  node_id: string;
  seq: number;
  window_start: string; // ISO
  entries: UsageEntry[];
}

export interface GamingHysteresis {
  failureThreshold: number;
  recoveryThreshold: number;
  soakSec: number;
  minResidencySec: number;
  cooldownSec: number;
}

export const DEFAULT_HYSTERESIS: GamingHysteresis = {
  failureThreshold: 3,
  recoveryThreshold: 5,
  soakSec: 300,
  minResidencySec: 600,
  cooldownSec: 300,
};
