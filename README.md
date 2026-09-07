# Proxy Platform — Railway Control Plane + Cloudflare/BPB Data Plane + Telegram Seller Bot

Commercial proxy/configuration management platform.

- **Control Plane (Railway):** ONE service — REST API, subscription/status/DNS pages, Persian Telegram bot, background jobs (pg-boss), PostgreSQL. Never touches proxy payload traffic.
- **Data Plane (Cloudflare):** N accounts × 1 forked BPB Worker = N nodes. All VLESS/Trojan/WARP/DoH traffic terminates here.
- **Model:** concierge sales via Telegram bot; stable subscription identity; sticky gaming failover; authoritative per-subscription byte metering; device slots; quota enforcement at the node.

## Deploy (GitHub → Railway — 4 steps)

1. Railway → **New Project** → **Deploy from GitHub repo** → pick `P-panel`.
   Railway reads `railway.json` + `Dockerfile` automatically (single `app` service + `postgres`).
2. Add the variable on the `app` service: `DATABASE_URL` → reference the Postgres service
   (`${{Postgres.DATABASE_URL}}`).
3. Add the remaining variables from `.env.example` (`APP_SECRET`, `PUBLIC_BASE_URL`, `BOT_TOKEN`,
   `BOT_WEBHOOK_SECRET`, `ADMIN_TELEGRAM_IDS`). No `BOT_TOKEN` = bot disabled; everything else still runs.
4. Deploy. Migrations run automatically before start (`preDeployCommand`). Then seed the first admin once:
   open the `app` service **Shell** and run:
   `node packages/database/dist/seed.js` (uses `DATABASE_URL`; set `ADMIN_EMAIL`/`ADMIN_PASSWORD` first, defaults `admin@local` / `changeme-admin-123`).

That's it. One service, one database.

## Layout

```
apps/api        single service: REST + /s/<token> (sub | status | dns) + /v1/node/* + bot + jobs
packages/shared crypto (AES-GCM, HMAC, scrypt), types, Persian strings
packages/database  Drizzle schema + seed
packages/core   naming, tokens, renderers, DNS artifacts, usage ledger, devices, gaming sticky selection
packages/cloudflare  CF API client + idempotent provisioning engine
bpb-fork        fork contract (FORK.md)
```

## Docs

- Architecture, failover, accounting: `docs/ARCHITECTURE.md`
- BPB fork contract: `bpb-fork/FORK.md`
