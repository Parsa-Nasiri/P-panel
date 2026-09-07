# Architecture (condensed)

Two planes; the control plane never carries proxy payload traffic.

```
Admin ──► web (Next.js) ──► api (Fastify) ──► PostgreSQL (+ pg-boss)
Customer Telegram ──► bot (grammY) ──────────┘        ▲
Client apps ──► /s/<token> (sub|status|dns) ──────────┤
Client apps ──► Cloudflare Workers (forked BPB) ──► Internet
Workers ──► /v1/node/{config,usage,health} ──► api   (HMAC-signed pull/push)
api ──► Cloudflare API (provisioning: KV + script upload + workers.dev)
```

## Key mechanisms

- **Subscription identity:** immutable `P-xxxxx-yyy` code; 256-bit token (SHA-256 at rest, AES-GCM copy for owner re-display); display name `{name}_{5digits}`; token rotation revokes all slot UUIDs.
- **Multi-node failover:** standard pools re-rank healthy nodes on every render; gaming pools use sticky assignment with hysteresis (3 failures → DOWN; recovery 5 checks + 5 min soak; 10 min min-residency; 5 min cooldown; degraded primaries kept).
- **Usage accounting:** bytes metered in the node (`mgt/meter.ts`), batched (30 s / 4 MB / 500 closes), pushed with per-node monotonic `seq`; `UNIQUE(node_id, seq, sub, slot)` makes delivery at-least-once-idempotent; hourly reconciliation recomputes from the ledger.
- **Devices:** plan max_devices = N device slots (per-slot UUIDs); nodes accept only synced slot UUIDs; >2 concurrent distinct IPs per slot flags/blocks per plan policy; 30-day inactivity auto-release.
- **Quota:** nodes gate WS upgrades on synced policy; ≤60 s propagation; status `exceeded` set centrally.
- **Gaming DNS:** typed DNS pool (`doh-worker` hosted on nodes, `doh-public`, `dot-public`, `plain-ip` bootstrap) with `direct`/`via-tunnel` routing; per-config Get DNS artifacts for sing-box/Clash/Xray/raw DoH.
- **Provisioning:** CF token → verify → capabilities → KV + Worker script upload (idempotent, checkpointed, rollback-able) → register node → health → pool.
