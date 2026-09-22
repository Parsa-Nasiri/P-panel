# BPB Commercial Platform — Control Plane image
# Shared by the web, worker, and cron services (Document 6, §N) — each Railway service
# uses this same image with a different start command, set via railway.toml / service settings.

FROM python:3.12-slim

WORKDIR /app

# System deps kept minimal on purpose — this is a network relay's control plane, not the relay itself
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY control-plane/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY control-plane/ .

# Railway injects $PORT and expects the app to bind to it — worker/cron services ignore it.
EXPOSE 8080

# Default: the web service. Override the start command per-service in railway.toml
# for worker (python -m workers.main) and cron (python -m workers.cron_entrypoint) —
# see Document 6 §N for why the health-check loop lives in worker, not Railway's own
# cron feature, which can't go below 5-minute granularity.
#
# Shell form on purpose, not the usual ["uvicorn", ...] array: the array form never
# substitutes $PORT at all (no shell involved to expand it), so it would silently
# always bind to 8080 even when Railway hands it a different port. ${PORT:-8080}
# uses Railway's real port when it's set, and falls back to 8080 for a plain
# `docker run` with no PORT env var — same image, both cases correct.
CMD uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8080}
