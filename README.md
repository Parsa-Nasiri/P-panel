# Proxy Platform — Railway Control Plane + Cloudflare/BPB Data Plane + Telegram Seller Bot

Commercial proxy/configuration management platform.

- **Control Plane (Railway):** admin panel, REST API, subscription/status/DNS renderer, Persian Telegram seller bot, PostgreSQL + pg-boss jobs. Never touches proxy payload traffic.
- **Data Plane (Cloudflare):** N accounts × 1 forked BPB Worker = N nodes. All VLESS/Trojan/WARP/DoH traffic terminates here.
- **Model:** concierge sales via Telegram bot; stable subscription identity; sticky gaming failover; authoritative per-subscription byte metering; device slots; quota enforcement at the node.

## Deploy (GitHub → Railway, no code edits)

1. Push this repository to GitHub.
2. Railway → New Project → Deploy from GitHub repo (monorepo auto-detects `railway.json`).
3. Add a PostgreSQL database service (or use the `postgres` service defined in `railway.json`).
4. Set environment variables from `.env.example` on each service (api, web, worker, bot).
5. Deploy. Migrations run via `preDeployCommand` (`drizzle-kit push`).
6. Seed the first admin: run once with Railway shell — `npm run seed`.

## Services

| Service | Root | Start |
|---|---|---|
| api | `apps/api` | REST + `/s/<token>` + `/v1/node/*` + `/healthz` |
| web | `apps/web` | admin panel + public status/DNS pages |
| worker | `apps/worker` | pg-boss jobs (health, aggregation, reconcile, expiry, retention, notify) |
| bot | `apps/bot` | Persian Telegram seller bot (webhook/polling) |
| postgres | image | PostgreSQL 16 |

## Docs

- Architecture, failover, accounting: `docs/ARCHITECTURE.md`
- BPB fork contract: `bpb-fork/FORK.md`
