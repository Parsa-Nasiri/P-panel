# BPB Commercial Platform — Complete Setup Guide

**From zero to a running commercial VPN business on this repository.**
Written for the project owner. Every step is exact; every judgment call is
flagged. Read §0 (free-plan reality) first — it shapes several decisions.

---

## §0. FREE-PLAN REALITY (read this first)

You said you intend to use free plans. Here is exactly what "free" buys on
each service, and the two places where paid is structurally required:

| Service | Free tier reality | Impact on this project |
|---|---|---|
| **Cloudflare Workers (Node relay)** | Free plan: 100k req/day, WebSocket relay works, KV works (100k reads / 1k writes per day) | **Works fully for the relay.** This is BPB's home turf — the relay path was built for it. |
| **Cloudflare Durable Objects** | **Not available on free.** Requires Workers Paid ($5/mo) | Device-limit enforcement silently degrades: the Node logs `SESSION_COUNTER binding missing` and **fail-opens** (no concurrent-session caps). This repo already handles it — set `NODES_ENABLE_DURABLE_OBJECTS=false` (default). |
| **Cloudflare KV writes** | 1,000 writes/day free | Fine. The credential map only changes on provisioning/revocation/quota events — dozens per day, not thousands. |
| **Railway** | **No permanent free tier.** "Trial" gives a one-time $5 credit. After it's spent, services stop. | The three services (web/worker/cron) + Postgres + Redis will burn ~$5 in days at idle. **For anything past a 1-week test you need Railway Hobby ($5/mo).** The cheapest honest way to run the control plane free-ish long-term is a single tiny VPS running the same Dockerfile — everything in this repo is plain Docker + Python and runs anywhere. |
| **Telegram Bot API** | Free, unlimited | No impact. |
| **Telegram Stars** | Telegram takes ~30% commission on Stars | Optional payment method; disabled by default. |

**Bottom line:** the data plane (customers' actual VPN traffic) runs 100%
free on Cloudflare. The control plane needs a home: Railway trial for
testing, Railway Hobby or a ~$4/mo VPS for real operation. The only
free-plan *functional* loss is device-limit enforcement.

---

## §1. WHAT YOU'RE DEPLOYING

```
GitHub repo (this)  ──deploy──>  Railway: 3 services (web / worker / cron)
                                  + Postgres + Redis (Railway add-ons)
                                             │
Telegram users  <──webhook──>  web service ──┘  (bot + admin + subscription links)
                                             │
Control plane  ──Cloudflare API──>  Node Worker(s) on Cloudflare (free plan)
                                        └── customers' VLESS/Trojan traffic
```

- **web** — FastAPI: Telegram webhook, subscription links (`/s/{token}`),
  node usage-ingest endpoints, health endpoint. Registers the webhook and
  seeds default plans/pool/profile on first boot.
- **worker** — always-on loops: node health checks (hysteresis + failover),
  usage reconciliation, quota/expiry edge-updates.
- **cron** — customer notifications (expiry/quota warnings).
- **Node Worker** — the forked BPB relay on Cloudflare. Deployed
  **automatically by the control plane** when you add infrastructure
  (§6). No wrangler needed day-to-day.

---

## §2. PREREQUISITES

1. This repository, pushed to <https://github.com/Parsa-Nasiri/P-panel> ✅ (already done)
2. **Railway** account → <https://railway.app>
3. **Cloudflare** account (the one where Nodes will run)
4. **Telegram**: a bot via [@BotFather](https://t.me/BotFather) → keep the token
5. **Your numeric Telegram user ID**: message [@userinfobot](https://t.me/userinfobot)
6. Local: Python 3.12+ (only for the verification script; Railway does the rest)

---

## §3. RAILWAY SETUP (≈10 minutes)

### 3.1 Project + services

1. <https://railway.app> → **New Project** → **Deploy from GitHub repo** →
   select `P-panel`. Railway detects the root `Dockerfile` and builds.
   Rename this service to **`web`**.
2. **+ Create** → **Database** → **Add PostgreSQL**.
3. **+ Create** → **Database** → **Add Redis**.
4. **+ Create** → **GitHub Repo** → same repo → rename to **`worker`** →
   Settings → Deploy → **Start Command**: `python -m workers.main`
5. **+ Create** → **GitHub Repo** → same repo → rename to **`cron`** →
   Settings → Deploy → **Start Command**: `python -m workers.cron_entrypoint`
6. **web** → Settings → Networking → **Generate Domain** → copy the URL
   (e.g. `https://web-production-xxxx.up.railway.app`). This is your
   `SUBSCRIPTION_BASE_URL` and every Node's `verdentUrl`.

> Railway trial note (§0): the trial credit covers this 3-service topology
> for days, not months. For production, either enable the Hobby plan or
> move the three services to one small VPS with Docker Compose
> (same image, same commands — the `railway.toml` start commands are
> ordinary shell commands).

### 3.2 Environment variables (web service → Variables)

| Variable | Value | Notes |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | from BotFather | |
| `TELEGRAM_OWNER_ID` | your numeric ID (step 5 of §2) | **Read exactly once** at first boot to create the bootstrap OWNER. Double-check it — a wrong value here locks you out of admin. |
| `SUBSCRIPTION_BASE_URL` | the URL from 3.1 step 6 | no trailing slash needed |
| `ENVIRONMENT` | `production` | |
| `TELEGRAM_WEBHOOK_SECRET_TOKEN` | `python -c "import secrets; print(secrets.token_hex(32))"` | |
| `JWT_SIGNING_KEY` | same command | |
| `CLOUDFLARE_TOKEN_ENCRYPTION_KEY` | `python -c "import secrets,base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"` | must decode to exactly 32 bytes |
| `NODE_HMAC_SECRET_PEPPER` | `python -c "import secrets; print(secrets.token_hex(32))"` | |
| `PAYMENT_CARD_NUMBER` | your card number | shown to customers on the payment screen |
| `PAYMENT_CARD_HOLDER` | your name | |
| `PAYMENT_INSTRUCTIONS` | e.g. `واریز کنید و اسکرین‌شات رسید را بفرستید` | optional extra line |
| `NODES_ENABLE_DURABLE_OBJECTS` | `false` | **true only if** every Node runs on Workers Paid |
| `STARS_ENABLED` | `false` | set `true` to show the Stars button (XTR plans) |

`DATABASE_URL`, `REDIS_URL`, `PORT` are injected by Railway — never type
them manually.

Copy ALL of the above to `worker` and `cron` (Variables → select the ones
you added → right-click → **Apply to services** → pick both).

### 3.3 First boot + verification

Push to `main` triggers deploys on all three services. When **web** is green:

1. **web → Deployments → View Logs** — expect:
   `bootstrap owner: ok` → `gaming profile: ok` → `default plans: ok`
   → `webhook registered for @YourBot`.
2. Check the DB (web → **Shell** tab):
   ```bash
   python -c "
   import asyncio
   from db.base import SessionLocal
   from db.models import Admin
   from sqlalchemy import select
   async def m():
       async with SessionLocal() as s:
           a = (await s.execute(select(Admin))).scalars().first()
           print('bootstrap OWNER:', a.telegram_user_id if a else 'MISSING')
   asyncio.run(m())
   "
   ```
3. Open `https://<your-web-url>/health` in a browser → `{"status": "ok", ...}`.
4. In Telegram: send `/start` to your bot → the Persian main menu appears.

**Troubleshooting first boot:** if `webhook registration failed` appears,
`SUBSCRIPTION_BASE_URL` is wrong or missing. If plans fail to seed, check
that migrations ran (next section).

### 3.4 Migrations (automatic — but verify)

> **Note:** this repo's `Dockerfile` CMD starts uvicorn directly; migrations
> are NOT auto-run on boot (deliberate — no deploy-time schema surprises).
> Run them once per deploy that changes the schema. For this initial setup:

web → **Shell**:
```bash
alembic upgrade head
python -c "import asyncio; from db.base import SessionLocal; from sqlalchemy import text; print(asyncio.run(SessionLocal().execute(text(\"select count(*) from information_schema.tables where table_schema='public'\"))).scalar())"
```
Expect `22` (21 tables + `alembic_version`).

Then **restart the web service** (Deployments → Redeploy) so the seeds run
against real tables.

---

## §4. CLOUDFLARE SETUP (≈5 minutes)

The control plane deploys Nodes through the Cloudflare API, so it needs ONE
API token with minimal scopes:

1. Cloudflare Dashboard → **My Profile** (top right) → **API Tokens** →
   **Create Token** → **Create Custom Token**:
   - **Permissions:**
     - `Account` · `Workers Scripts` · **Edit**
     - `Account` · `Workers KV Storage` · **Edit**
     - `Account` · `Account Settings` · **Read**
   - **Account Resources:** Include → your account
   - (No zone permissions — Nodes use workers.dev subdomains; the platform
     never touches your DNS.)
2. Create the token, copy it once (it's shown only now).
3. Note your **Account ID**: Dashboard → any domain → right sidebar →
   `Account ID` (or Workers & Pages → overview → right sidebar).

**These two values go into the database encrypted, via the admin panel
(§6) — NOT as env vars.** They're stored AES-256-GCM-encrypted with
`CLOUDFLARE_TOKEN_ENCRYPTION_KEY`.

> Workers **subdomain**: Workers & Pages → your account → right sidebar →
> `workers.dev` — if it shows "Disable", it's already enabled; if it shows
> nothing, click enable and pick a subdomain name (e.g. `parsa-proxy`).
> Node URLs will be `<script-name>.<subdomain>.workers.dev`.

---

## §5. TELEGRAM ADMIN CHECK

In Telegram, send `/admin` to your bot. You should get the admin panel with
your role (`OWNER`). If nothing happens, `TELEGRAM_OWNER_ID` doesn't match
your user ID — fix the variable, restart web, and re-run §3.3 step 2 after
clearing the old row (Shell:
`python -c "import asyncio;from db.base import SessionLocal;from db.models import Admin;asyncio.run(SessionLocal().execute('delete from admins'))"`
— only safe before any other admin exists).

---

## §6. ADD YOUR FIRST NODE (the Phase-2 automation)

1. In Telegram: `/admin` → **🖥 مدیریت نودها**. It says no nodes exist —
   that's expected; node creation is an API operation, added here:

   **web → Shell** (fill the three `<...>` values):
   ```bash
   python -c "
   import asyncio
   from db.base import SessionLocal
   from db.models import CloudflareAccount
   from domain.crypto import encrypt_secret
   from domain.config import settings

   TOKEN = '<cloudflare api token>'
   ACCOUNT_ID = '<cloudflare account id>'

   async def m():
       async with SessionLocal() as s:
           s.add(CloudflareAccount(
               label='main',
               cf_account_id=ACCOUNT_ID,
               api_token_encrypted=encrypt_secret(TOKEN, settings.cloudflare_token_encryption_key).encode(),
           ))
           await s.commit()
           print('cloudflare account added')
   asyncio.run(m())
   "
   ```
2. Provision the Node itself — **from Telegram** (easiest): `/admin` →
   **➕ ساخت نود جدید** → send a script name (e.g. `verdent-node-1`).
   This creates the KV namespace, uploads the forked bundle
   (`control-plane/assets/worker_bundle.js`), enables the workers.dev
   subdomain, seeds the KV (`nodeSecret` + empty `proxyUsers`), and
   registers the node row — all through the encrypted API token from step 1.

   (Equivalent Shell fallback, if Telegram is down:
   ```bash
   python -c "
   import asyncio
   from db.base import SessionLocal
   from sqlalchemy import select
   from db.models import CloudflareAccount
   from domain.provisioning import provision_node, ProvisioningError

   SCRIPT_NAME = 'verdent-node-1'

   async def m():
       async with SessionLocal() as s:
           acct = (await s.execute(select(CloudflareAccount))).scalars().first()
           try:
               node = await provision_node(s, acct.id, SCRIPT_NAME, capability_tags=['general','doh','gaming'])
               print('NODE READY:', node.custom_domain)
           except ProvisioningError as e:
               print('FAILED:', e)
   asyncio.run(m())
   "
   ```
   )
3. Wait ~60s: the worker service's health loop probes the Node and flips it
   to `ONLINE` (score 100). Check in Telegram: `/admin` → 🖥 مدیریت نودها.
4. Re-run step 2 with different `SCRIPT_NAME`s to add capacity (each Node =
   its own KV namespace + workers.dev subdomain). Nodes count against
   Cloudflare's free-plan limits individually.

> **If `FAILED: worker upload failed`** — 99% a token-scope problem
> (re-check §4's three permissions) or the workers.dev subdomain isn't
> enabled on the account.

---

## §7. GO LIVE: SELL SOMETHING

1. **Set real prices**: the seeded plans are placeholders (IRR amounts).
   Edit them directly for now (web → Shell → plain SQL or ask me for an
   admin-panel price editor in the next iteration):
   ```bash
   python -c "
   import asyncio
   from db.base import SessionLocal
   from db.models import Plan
   from sqlalchemy import select
   async def m():
       async with SessionLocal() as s:
           for p in (await s.execute(select(Plan))).scalars():
               print(p.name, p.price_amount, p.price_currency)
   asyncio.run(m())
   "
   ```
   Update with: `UPDATE plans SET price_amount = <rial> WHERE name = '...';`
2. **Buy flow (test it yourself)**: Telegram → 🛒 خرید اشتراک → pick a plan
   → send a display name → the payment screen shows your card → send any
   photo as a "receipt" → as OWNER, `/admin` → 🧾 سفارش‌های در انتظار →
   ✅ تأیید on your test order.
3. The bot receives the **subscription link**. Paste it into Hiddify /
   Streisand / v2rayNG → update → connect. That's a real, working VLESS
   config on your Node.
4. **Usage accounting check** (the Phase-0 acceptance check, now live):
   browse ~50MB on that config, then:
   ```bash
   python scripts/verify_usage.py
   ```
   (web → Shell) — the ledger and aggregate columns must match exactly.

---

## §8. ADMIN OPERATIONS (who can do what)

| Action | SUPPORT | FINANCE | INFRASTRUCTURE | ADMIN | OWNER |
|---|---|---|---|---|---|
| Review payments | ✅ | ✅ | — | ✅ | ✅ |
| Revoke/refund mark | — | ✅ | — | ✅ | ✅ |
| Manage customer configs | ✅ | — | — | ✅ | ✅ |
| Issue test configs | ✅ | — | — | ✅ | ✅ |
| Manage nodes | — | — | ✅ | ✅ | ✅ |
| Edit plans | — | — | — | ✅ | ✅ |
| Ban customers | — | — | — | ✅ | ✅ |
| Add/remove admins | — | — | — | — | ✅ |

Add more admins: `/admin` → 👑 افزودن ادمین → their numeric Telegram ID →
pick a role. Every admin action is audit-logged (`audit_log` table).

**Test configs** (prospective customers): 🧪 from the customer menu
(1 per customer, 100 MB, 24 h, auto-expire) or issued manually via the
admin panel.

---

## §9. WHAT RUNS WHEN (operational cadence)

| Loop | Where | Interval | Does |
|---|---|---|---|
| Node health probe | worker | 60 s | Probe `/{securePath}/health`; DEGRADED at 2 fails, OFFLINE at 5; re-mints configs onto healthy nodes after 10 min offline (failover) |
| Usage reconciliation | worker | 5 min | Repairs aggregate drift from the append-only ledger |
| Quota + expiry push | worker | 5 min | Over-quota credential → `disabled` in Node KV; expiry sweep |
| Notification sweep | cron | 5 min | Expiry warning (T-3 days), quota warnings (80%), all once/day per customer |
| Usage events | Node → web | 30 s / 1 MB per connection | Append-only ledger; duplicates dropped by the `(connection_id, sequence_number)` unique key |

---

## §10. FREE-PLAN OPERATING TIPS

1. **Device limits**: enforced only with Workers Paid. On free, one config
   works on unlimited simultaneous devices. If that matters commercially,
   either upgrade ONE account's Workers plan or price plans assuming
   shared use.
2. **KV 1k writes/day**: each provisioning/quota event = ~2 writes. You'd
   need ~500 quota flips/day to worry. Fine.
3. **Workers 100k req/day per Node**: each customer connection = 1 request
   + a usage POST every ~30s. Roughly: a Node on free handles a few dozen
   concurrent daily users before you should add a second Node (which is
   exactly the multi-Node design).
4. **Railway sleep**: Railway services don't sleep on trial/hobby, but
   restart on crash — the webhook auto-re-registers on boot; usage events
   retry from the Node.
5. **Backups**: `railway db dump` from time to time (or enable Railway's
   backups). The ledger is append-only — it rebuilds everything.

---

## §11. WHAT WAS DELIBERATELY LEFT OUT / KNOWN LIMITS

1. **Web admin panel** — everything is Telegram-first (per Document 4);
   the `admin_panel/` module currently holds the bootstrap logic. A web UI
   is a future iteration; the API surface (`/internal/*`) is ready for it.
2. **Renewal button** — `cfg:renew` is wired in the keyboards, but renewal
   completes via the normal buy flow (choose a plan → pay → approve → the
   platform extends expiry instead of creating a second config). The
   buttons per-config exist; the plan-selection re-entry is one more
   iteration away.
3. **R2 proof backup** — proofs live in Telegram (`telegram_file_id`),
   which is durable enough for review purposes; the R2 copy hook is a
   Phase-5 hardening stub.
4. **Custom domains for Nodes** — workers.dev subdomains only (keeps the
   Cloudflare token scope minimal). Custom domains need Zone:Edit and are
   a one-line addition per node later.
5. **Stars prices** — the seeded XTR plan exists but Stars pays out in
   Telegram's Stars currency; enable `STARS_ENABLED=true` only if you've
   linked a Stars-enabled bot.

---

## §12. QUICK REFERENCE — EVERY SECRET AND WHERE IT LIVES

| Secret | Lives in | Generated |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Railway env (web/worker/cron) | BotFather |
| `TELEGRAM_WEBHOOK_SECRET_TOKEN` | Railway env | you, once |
| `JWT_SIGNING_KEY` | Railway env | you, once |
| `CLOUDFLARE_TOKEN_ENCRYPTION_KEY` | Railway env | you, once (32-byte b64) |
| `NODE_HMAC_SECRET_PEPPER` | Railway env | you, once |
| Cloudflare API token | `cloudflare_accounts.api_token_encrypted` (AES-256-GCM in Postgres) | Cloudflare, §4 |
| Per-Node `nodeSecret` | Node KV (`nodeSecret` key) + `nodes.node_secret_hash` | control plane at provisioning |
| Per-config `proxy_uuid` | `configuration_node_assignments.proxy_uuid` + Node KV | control plane at fulfillment |
| `subscription_token` | `configurations.subscription_token` | control plane at fulfillment |

**Nothing about a customer ever touches a Node except its own UUID** —
compromised Node = forged reports for itself only (Document 5's property),
and revoking a customer is one KV flip.
