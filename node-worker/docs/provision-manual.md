# Manual Node provisioning (Phase 0 test Worker)

This is the **manual** flow for deploying one forked Node Worker by hand —
used in Phase 0 to validate the fork (two different test UUIDs moving traffic
with independently correct byte counts). The Control Plane's automated
provisioning flow (Phase 2) does all of this via the Cloudflare API with the
scoped token from `CLOUDFLARE_TOKEN_ENCRYPTION_KEY`-secured storage; you do
NOT need this page once Phase 2 exists.

What you create here, step by step:

1. A Cloudflare KV namespace (the Node's only storage)
2. The Node Worker script, deployed with `wrangler`
3. A Durable Object binding (Workers **Paid** plan required — see §4)
4. The provisioned settings + the `proxyUsers` credential map
5. The two test UUIDs and the validation checklist

Everything on this page is per-Node. A second test Node = run these steps
again with different names.

---

## 0. Prerequisites

- A Cloudflare account with **Workers Paid** enabled ($5/mo) — Durable
  Objects require it. On a free-plan account the Node still relays, but the
  concurrent-session check degrades to skip (fail-open) with a one-time
  warning in the Worker logs; device limits are then NOT enforced.
- Node.js 20+ and `npm` on your machine.
- Your Cloudflare **Account ID** (dashboard → any domain → right sidebar,
  or `workers.dev` subdomain page).

```bash
cd node-worker
npm install
npm install -g wrangler   # or use npx wrangler throughout
wrangler login
```

## 1. KV namespace

```bash
wrangler kv namespace create NODE_KV
```

Note the returned `id` — it goes into `wrangler.toml` below.

## 2. Provisioned settings

Pick values now (you'll paste them into `wrangler.toml` and re-use them in
the KV seed in §4):

| Field | What it is | Example |
|---|---|---|
| `nodeId` | Any UUID you generate — the Node's identity on the Control Plane | `wrangler` doesn't generate it; use `python -c "import uuid; print(uuid.uuid4())"` |
| `verdentUrl` | Where the Control Plane is reachable, e.g. your Railway `web` service URL | `https://verdent-platform-web.up.railway.app` |
| `securePath` | A random secret path segment — the ONLY thing protecting the DoH + health routes | `openssl rand -hex 16` |
| `mainDomain` | The public hostname clients will connect through | `my-node.example.workers.dev` |
| `dohUrl` | Optional DoH upstream override | leave empty |

Build the JSON (single line, this exact shape):

```json
{"nodeId":"<uuid>","verdentUrl":"https://...","securePath":"<random-hex>","mainDomain":"<workers.dev-host>","proxyIpMode":"proxyip","proxyIPs":[],"prefixes":[],"fallback":"","dohUrl":""}
```

## 3. wrangler.toml

Edit `node-worker/wrangler.toml`:

- `name = "<short-name>"` → e.g. `verdent-node-test1` (this is also the
  `*.workers.dev` subdomain prefix)
- `id = "<KV_NAMESPACE_ID>"` from §1
- `provisioned = "<PROVISIONED_JSON>"` — the single-line JSON from §2

## 4. Deploy + seed the KV

```bash
wrangler deploy
```

Then seed the credential map — write `proxyUsers` into the KV. Easiest via
the dashboard (Workers & Pages → KV → your namespace → **Add key**):

- Key: `proxyUsers`
- Value (JSON, two test UUIDs — generate your own with the python one-liner
  above; these are placeholders):

```json
{
  "vl:11111111-1111-4111-8111-111111111111": {"configId": "cfg-test-a", "status": "active", "deviceLimit": 2},
  "vl:22222222-2222-4222-8222-222222222222": {"configId": "cfg-test-b", "status": "active", "deviceLimit": 1}
}
```

Also write a `nodeSecret` key — the HMAC key this Node signs its ingest calls
with (§6). Generate one: `openssl rand -hex 32`, and put the value
`sha256(secret + NODE_HMAC_SECRET_PEPPER)` — the same value the Control Plane
stores in `nodes.node_secret_hash` for this Node — into KV key `nodeSecret`.
(For the Phase 0 manual test you can paste the raw hex; the Control Plane's
Phase 2 flow does this hashing for you automatically.)

## 5. Validate the fork — the Phase 0 acceptance check

The whole point of the fork: **two different UUIDs, same Worker, traffic
counted separately.**

1. Pick any VLESS client (v2rayN, Streisand, Hiddify). Add TWO configs that
   differ ONLY in UUID:
   - `vless://11111111-...@my-node.example.workers.dev:443?path=%2Fvl&type=ws&security=tls#testA`
   - `vless://22222222-...@my-node.example.workers.dev:443?path=%2Fvl&type=ws&security=tls#testB`
2. Connect with config A, browse ~50 MB. Disconnect.
3. Connect with config B, browse ~10 MB. Disconnect.
4. Check the Control Plane ledger (Railway Postgres, or `scripts/verify_usage.py`):

```sql
SELECT configuration_id, SUM(bytes_up + bytes_down) AS total
FROM usage_events GROUP BY configuration_id;
-- expect: cfg-test-a ≈ 50MB+, cfg-test-b ≈ 10MB+, independently correct
```

5. Negative checks (equally important):
   - A third, unknown UUID → connection refused immediately (worker logs:
     `invalid user`).
   - Flip config B's entry to `"status": "disabled"` in KV → within the 30s
     cache TTL, config B stops connecting (revocation works).
   - config B has `deviceLimit: 1` → a second simultaneous connection with
     the same UUID on another device/network is refused (device limit works;
     requires the DO binding from §3 — check `wrangler.toml`).

## 6. Where usage goes

The Node POSTs signed events to `{verdentUrl}/internal/nodes/{nodeId}/usage`
every ~30s or ~1MB per connection, whichever first. If the Control Plane is
not yet deployed/reachable, events fail with a log line (`Usage flush
failed`) and the relay keeps working — accounting resumes automatically.

---

**Judgment call, flagged:** the `securePath` secret-in-URL is a deliberate
speed choice from Document 1 (no dependency on a signed-cookie flow for
Phase 0). Document 5 notes its limits — it protects the routes from casual
scanning, not from a determined actor who learns the path. Phase 5 revisits.
