# BPB Fork Contract (bpb-fork)

The fork of `bia-pain-bache/BPB-Worker-Panel` is the node runtime. **The proxy core is untouched.** All changes are additive, isolated, and gated behind the `MGT_URL` Worker secret — when it is absent, the bundle behaves exactly like upstream BPB.

## Added modules (`src/mgt/`)

| Module | Responsibility |
|---|---|
| `mgt/agent.ts` | Pulls `GET {MGT_URL}/v1/node/config` every 60 s and on demand (last-good policy cached in KV); pushes usage batches to `POST /v1/node/usage` and health reports to `POST /v1/node/health`. All requests HMAC-SHA256 signed (`x-node-id`, `x-ts`, `x-signature` over `METHOD:path:ts:bodySha256`), timestamp window ±90 s |
| `mgt/meter.ts` | Wraps the proxied duplex stream with a counting `TransformStream`; accumulates `{up, down, conns}` per `(uuid, slot)`; flushes every 30 s / 4 MB / 500 closes via `ctx.waitUntil`; KV snapshot every 5 min merged on cold start |
| `mgt/slots.ts` | Multi-UUID device-slot authentication; per-slot first/last IP (`CF-Connecting-IP`), UA (WS upgrade headers); rolling 5-minute distinct-IP window |
| `mgt/gate.ts` | WS-upgrade gate: unknown UUID / revoked slot / expired subscription / over-quota → reject |

## Upstream touch points (the only edits to BPB code)

1. **Proxy handler** — wrap the client↔remote stream copy with `meter.tap(connId, slotRef)` (~10 lines).
2. **Auth point** — replace the single-UUID check with `gate.check(uuid)` + `slots.observe(...)` (slot map comes from synced policy).
3. **Router** — mount `/mgt/*` internal routes; read node identity from Worker Secrets (`NODE_ID`, `NODE_SECRET`, `MGT_URL`) — never from KV plaintext.

## Deployment

- Built by the fork's existing pipeline into a single ES-module bundle (`worker.js`).
- The control plane deploys the bundle via the Cloudflare Script Upload API with KV binding + secrets; `bundle_version` is stamped and recorded per node for roll-forward/rollback.
- Upstream updates: rebase the three hooks (they are the entire contract), rebuild, roll out via the provisioning "update" job.

## Node policy blob (served by the control plane)

```json
{
  "version": 7,
  "node": { "id": "uuid", "kind": "standard" },
  "slots": [
    { "uuid": "...", "sub_ref": "uuid", "slot": 0, "allowed": true }
  ],
  "issuedAt": "2026-09-07T12:00:00Z"
}
```

Nodes cache last-good policy in KV and keep operating (enforcing the last known quotas/slots) if the control plane is unreachable.
