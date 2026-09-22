# Phase 0 — Setup & Deployment Guide

Everything needed to take this repository from empty Railway project to a
**validated multi-tenant Node fork**, in order, with no assumed context.
Written for the project owner (non-developer-friendly), assuming Windows.

---

## What Phase 0 delivers

| # | Deliverable | Where | Status |
|---|---|---|---|
| 1 | Control-plane skeleton (`web` / `worker` / `cron`) | `control-plane/` | code complete |
| 2 | Database schema (all 21 tables, exact `schema.sql` mirror) + usage-trigger | `control-plane/db/` | code complete |
| 3 | Bootstrap OWNER admin from `TELEGRAM_OWNER_ID` | `control-plane/admin_panel/` | code complete |
| 4 | The forked BPB Node (multi-tenant credentials, byte counting, session DO) | `node-worker/` | code complete |
| 5 | One manually-deployed test Worker, validated against 2 UUIDs | this guide, §5-7 | **you do this** |

**Definition of done** (from the implementation prompt): migrations run clean
against a real Postgres; the bootstrap OWNER admin exists; the forked Worker
serves two different test UUIDs simultaneously with independently correct
byte counts.

**Risk statement** (unchanged from kickoff): the fork's correctness and the
usage ledger's behavior under real concurrency are the highest-risk items in
the whole project. Steps §7 are the acceptance check — do not skip them.

---

## 1. Prerequisites checklist

- [ ] GitHub account (this repo will be pushed there)
- [ ] Railway account — <https://railway.app> (Hobby plan, $5/mo, covers
      Postgres + the three services at Phase 0 scale)
- [ ] Cloudflare account with **Workers Paid** enabled ($5/mo — Durable
      Objects require it; on free plan the session check degrades to
      fail-open, see `node-worker/wrangler.toml` comment)
- [ ] Python 3.12+ locally (only for the verification script)
- [ ] Node.js 20+ locally (only for `wrangler`)

## 2. Create the Railway project (3 services + 2 add-ons)

Railway pattern (Document 6 §N): ONE project, three services from the same
repo/image, plus managed Postgres and Redis.

1. <https://railway.app> → **New Project** → **Deploy from GitHub repo** →
   select this repository. Railway builds the `Dockerfile` at the repo root.
   Name this service `web`.
2. In the same project: **+ New** → **Database** → **Add PostgreSQL**.
3. **+ New** → **Database** → **Add Redis** (used from Phase 1; added now so
   `REDIS_URL` exists).
4. **+ New** → **GitHub Repo** → same repo again → name this service
   `worker`. In its **Settings → Deploy → Start Command** set:
   `python -m workers.main`
5. **+ New** → **GitHub Repo** → same repo → name `cron`. Start Command:
   `python -m workers.cron_entrypoint`. In its **Settings → Deploy → Cron
   Schedule** leave unset for Phase 0 (scaffold only).
6. `web` service → **Settings → Networking → Generate Domain** — note the
   public URL (e.g. `https://web-production-xxxx.up.railway.app`). This is
   the `verdentUrl` every Node will report to.

### Environment variables

On the **web** service → **Variables** tab, add (names exactly as
`env.example`; `DATABASE_URL`, `REDIS_URL`, `PORT` come from the add-ons
automatically — never overwrite them):

| Variable | Value | How |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | from @BotFather (Phase 1 will use it; harmless to set now) | create bot → copy token |
| `TELEGRAM_OWNER_ID` | **your numeric Telegram user ID** (message `@userinfobot`) — read ONCE at first boot; double-check it | — |
| `SUBSCRIPTION_BASE_URL` | any https URL you control (e.g. `https://sub.yourbrand.tld`) | Phase 3 uses it |
| `ENVIRONMENT` | `production` | by hand here, never in git |
| `TELEGRAM_WEBHOOK_SECRET_TOKEN` | `openssl rand -hex 32` | generate |
| `JWT_SIGNING_KEY` | `openssl rand -hex 32` | generate |
| `CLOUDFLARE_TOKEN_ENCRYPTION_KEY` | `openssl rand -base64 32` (must decode to exactly 32 bytes) | generate |
| `NODE_HMAC_SECRET_PEPPER` | `openssl rand -hex 32` | generate |

Then select all of the above on `web` and use Railway's **copy to other
services** (Variables → right-click a variable → apply to `worker` and
`cron`) so all three services share the same values.

> Windows: `openssl` isn't shipped with cmd — use Git Bash (installed with
> Git), or `python -c "import secrets; print(secrets.token_hex(32))"`.

## 3. Run migrations (Definition-of-done check #1)

Railway `web` deploys automatically on push. Once the first deploy is green:

1. Railway `web` → **Shell** tab (opens a shell inside the running
   container).
2. Run:
   ```bash
   alembic upgrade head
   ```
3. Verify (same shell):
   ```bash
   python -c "
   import asyncio
   from db.base import SessionLocal
   from sqlalchemy import text
   async def main():
       async with SessionLocal() as s:
           n = (await s.execute(text(\"select count(*) from information_schema.tables where table_schema='public'\"))).scalar()
           print('tables in public schema:', n)
   asyncio.run(main())
   "
   ```
   Expect `21` (22 with `alembic_version`).
4. Definition-of-done check #2 — the bootstrap OWNER row (the `web` service
   inserts it at startup when `TELEGRAM_OWNER_ID` is set):
   ```bash
   python -c "
   import asyncio
   from db.base import SessionLocal
   from db.models import Admin
   from sqlalchemy import select
   async def main():
       async with SessionLocal() as s:
           a = (await s.execute(select(Admin))).scalars().first()
           print('bootstrap admin:', a.telegram_user_id, a.role if a else 'MISSING')
   asyncio.run(main())
   "
   ```
   Expect your Telegram ID and `OWNER`. If `MISSING`, check `web` logs for
   the `bootstrap owner` line — most common cause is a wrong
   `TELEGRAM_OWNER_ID`.

## 4. Deploy the test Node (forked BPB Worker)

Follow `node-worker/docs/provision-manual.md` step by step. Short version:

1. `cd node-worker && npm install`
2. `wrangler login`
3. Create KV: `wrangler kv namespace create NODE_KV` → put its `id` in
   `wrangler.toml`
4. Fill `name`, `provisioned` JSON (see that doc §2) in `wrangler.toml`
5. `wrangler deploy`
6. Seed KV keys `proxyUsers` (two test UUIDs) and `nodeSecret` (dashboard →
   KV → add key)

Cloudflare API token scope note (Phase 0 manual flow uses `wrangler login`
browser auth, no token needed). The **automated** Phase 2 provisioning will
need a scoped token: `Workers Scripts:Edit`, `Workers KV:Edit`,
`Account Settings:Read` — same minimal scopes Document 1 requires.

## 5. Point the Node at the Control Plane

In the `provisioned` JSON: set `verdentUrl` to the Railway `web` public URL
from §2 step 6. The Node then POSTs signed usage events to
`{verdentUrl}/internal/nodes/{nodeId}/usage`.

The Node's row in the `nodes` table must exist for auth to pass. For the
Phase 0 manual test, insert it once (Railway `web` → Shell):

```bash
python -c "
import asyncio, uuid
from db.base import SessionLocal
from db.models import CloudflareAccount, Node
from domain.security import derive_node_secret_hash
from sqlalchemy import select

NODE_ID = '<the nodeId UUID from provisioned JSON>'
NODE_SECRET = '<the raw secret you hashed into KV nodeSecret>'

async def main():
    async with SessionLocal() as s:
        acct = (await s.execute(select(CloudflareAccount))).scalars().first()
        if acct is None:
            acct = CloudflareAccount(label='manual-test', cf_account_id='manual', api_token_encrypted=b'placeholder')
            s.add(acct); await s.flush()
        existing = (await s.execute(select(Node).where(Node.id == NODE_ID))).scalars().first()
        if existing:
            print('node already exists'); return
        s.add(Node(
            id=NODE_ID,
            cloudflare_account_id=acct.id,
            worker_script_name='verdent-node-test1',
            node_secret_hash=derive_node_secret_hash(NODE_SECRET),
        ))
        await s.commit()
        print('node row created:', NODE_ID)
asyncio.run(main())
"
```

(Phase 2 automates this entire section.)

## 6. Traffic test (two UUIDs)

Install any VLESS client (v2rayN / Streisand / Hiddify). Add the two test
configs from `provision-manual.md` §5 — identical except the UUID. Connect
with A, move ~50 MB; disconnect; connect with B, move ~10 MB.

While connected, watch live: Railway `web` → **Logs** shows
`POST /internal/nodes/.../usage 200` lines arriving every ~30s per active
connection.

## 7. Acceptance check (Definition-of-done #3)

Railway `web` → Shell:

```bash
python scripts/verify_usage.py
```

Expect two rows (`cfg-test-a`, `cfg-test-b`), each with `ledger` ≈ your
moved traffic and `aggregate` **exactly equal** (the DB trigger keeps them in
sync; any mismatch is a blocker — report it, don't hand-fix the aggregate).

Then the negative checks from `provision-manual.md` §5:
- [ ] Unknown third UUID → refused (`invalid user` in wrangler tail:
      `wrangler tail`)
- [ ] Flip B's KV entry to `"status": "disabled"` → within ~30s B stops
      connecting (revocation)
- [ ] B has `deviceLimit: 1` → second simultaneous connection refused
      (device limit, requires the DO binding)

All three boxes + `verify_usage.py` PASS = **Phase 0 done**.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `web` deploy fails at build | Docker build OOM / typo in requirements | Railway → Deployments → view build log |
| `bootstrap owner FAILED` in logs | `DATABASE_URL` not referenced, or `TELEGRAM_OWNER_ID` wrong | Variables tab; re-check the numeric ID |
| `alembic upgrade head` says "Can't locate revision" | `alembic.ini` not found (wrong cwd) | run from `/app` (the image's WORKDIR) |
| Node logs `Usage flush failed: 403` | Node row missing / wrong `nodeSecret` hash | re-run §5; confirm KV `nodeSecret` matches what you hashed |
| Node logs `SESSION_COUNTER binding missing` | free-plan account | upgrade to Workers Paid, redeploy |
| Two UUIDs both count but totals equal | fork regression — **stop and report** | this is exactly the acceptance check |

## What is deliberately NOT in Phase 0

Telegram bot UX, plans/payments, subscription serving, automated
provisioning, pools/health scoring, gaming profiles. The `worker` and `cron`
services are scaffolds on purpose (Document 6's roadmap) — their loops run
and log, that's all.
