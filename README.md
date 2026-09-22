# BPB Commercial Platform ("P-Panel")

Multi-tenant commercial platform built on a forked BPB-Worker-Panel Node,
per the 7-document blueprint (`00`–`06`) and `07-implementation-prompt`.

```
control-plane/   FastAPI control plane (web / worker / cron services)
  api/           FastAPI app: /health, /internal/nodes/{id}/usage|health
  db/            ORM models (exact schema.sql mirror) + Alembic migrations
  domain/        config (env), security (HMAC), crypto (AES-GCM at rest)
  workers/       worker service (queue + reconcile) and cron service scaffolds
  admin_panel/   bootstrap OWNER admin (Phase 0); panel arrives Phase 1
  scripts/       smoke_test.py, verify_usage.py (Phase 0 acceptance check)
node-worker/     forked BPB v5.1.1 Cloudflare Worker ("the Node")
  src/protocols/  VLESS + Trojan relay with per-connection byte counting
  src/usage/      UsageTracker (flush 30s/1MB), SessionCounter DO, health route
  docs/provision-manual.md   manual per-Node provisioning (Phase 0)
docs/            phase-0-setup-guide.md — start here for deployment
schema.sql       canonical DDL (mirrored by db/models.py + migration 001)
Dockerfile       shared image for the three Railway services
railway.toml     Railway web service config (worker/cron commands in comments)
env.example      every environment variable, grouped by "touch now or not"
```

## Status

Phase 0 (per Document 6's roadmap): **code complete** — see
[docs/phase-0-setup-guide.md](docs/phase-0-setup-guide.md) for deployment and
the acceptance check (two test UUIDs, independently correct byte counts).

## Getting started

```bash
# control plane (local dev)
cd control-plane
python -m pip install -r requirements.txt
python scripts/smoke_test.py          # no DB needed
alembic upgrade head                  # needs DATABASE_URL (Railway or local Postgres)

# node worker
cd node-worker
npm install
npm run check && npm run build        # typecheck + bundle
```

Fork provenance: `node-worker` started as a shallow clone of
[bia-pain-bache/BPB-Worker-Panel](https://github.com/bia-pain-bache/BPB-Worker-Panel)
v5.1.1 (GPL-3.0). The fork's changes are documented in
`node-worker/src/settings/settings.ts` (header comment) and follow Document 1's
"BPB Fork Scope": multi-tenant credential map, byte counting, concurrent-session
Durable Object, subtraction of the panel UI.
