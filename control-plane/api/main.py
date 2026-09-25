"""Verdent Platform — FastAPI application entrypoint.

Railway service: `web`  (start: uvicorn api.main:app --host 0.0.0.0 --port $PORT)

On startup:
  1. bootstrap OWNER admin (TELEGRAM_OWNER_ID, read exactly once)
  2. seed default plans (only when the plans table is empty)
  3. seed the default gaming profile (Tier A/B honest settings)
  4. register the Telegram webhook (only when token + base URL are set)

The app boots even when Telegram/Cloudflare are unconfigured — the control
plane never depends on the bot to run.
"""

import contextlib
import logging

from fastapi import FastAPI

from admin_panel.bootstrap_admin import ensure_bootstrap_owner
from api.routes import health as health_routes
from api.routes import nodes as node_routes
from api.routes import subscription as subscription_routes
from api.routes import telegram as telegram_routes
from domain import plans as plans_domain
from domain import gaming as gaming_domain
from domain.config import settings
from domain import __version_platform__

# Importing bot.router is what attaches the Telegram handlers to the webhook
# dispatcher (its last line calls dp.include_router). Without this import the
# webhook route accepts updates but no handler is ever registered, so /start
# and every command silently do nothing. Imported here — after bot.webhook is
# importable — and never from bot.webhook itself (see that module's docstring).
import bot.router  # noqa: E402, F401

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("verdent.platform")


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("verdent-platform %s starting (env=%s)", __version_platform__, settings.environment)

    startup_errors: list[str] = []

    for name, coro_factory in [
        ("bootstrap owner", ensure_bootstrap_owner),
        ("gaming profile", gaming_domain.seed_default_gaming_profile),  # before plans (gaming plan links to it)
        ("default plans", plans_domain.seed_default_plans),
    ]:
        try:
            await coro_factory()
            logger.info("%s: ok", name)
        except Exception:  # noqa: BLE001
            logger.exception("%s FAILED", name)
            startup_errors.append(name)

    try:
        from bot.webhook import register_webhook

        await register_webhook()
    except Exception:  # noqa: BLE001
        logger.exception("webhook registration failed")
        startup_errors.append("webhook")

    if startup_errors:
        logger.warning("startup had failures: %s (continuing — Railway restarts on crash)", startup_errors)

    yield

    logger.info("verdent-platform shutting down")


app = FastAPI(
    title="Verdent Platform",
    version=__version_platform__,
    lifespan=lifespan,
)

app.include_router(health_routes.router)
app.include_router(node_routes.router)
app.include_router(subscription_routes.router)
app.include_router(telegram_routes.router)
