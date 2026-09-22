"""Verdent Platform — FastAPI application entrypoint.

Railway service: `web`  (start: uvicorn api.main:app --host 0.0.0.0 --port $PORT)
On startup: bootstrap the bootstrap-OWNER admin from TELEGRAM_OWNER_ID if
missing (Document 5, "Bootstrap Owner" — idempotent, safe to re-run).
"""

import contextlib
import logging

from fastapi import FastAPI

from admin_panel.bootstrap_admin import ensure_bootstrap_owner
from api.routes import health as health_routes
from api.routes import nodes as node_routes
from domain.config import settings
from domain import __version_platform__

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("verdent.platform")


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("verdent-platform %s starting (env=%s)", __version_platform__, settings.environment)

    try:
        await ensure_bootstrap_owner()
        logger.info("bootstrap owner ensured")
    except Exception:  # noqa: BLE001
        # Never block boot on bootstrap failure in development; Railway's
        # restart policy retries. Logged loudly either way.
        logger.exception("bootstrap owner FAILED — check DATABASE_URL and TELEGRAM_OWNER_ID")

    yield

    logger.info("verdent-platform shutting down")


app = FastAPI(
    title="Verdent Platform",
    version=__version_platform__,
    lifespan=lifespan,
)

app.include_router(health_routes.router)
app.include_router(node_routes.router)
