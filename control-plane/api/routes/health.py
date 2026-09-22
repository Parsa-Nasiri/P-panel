"""Verdent Platform — /health liveness endpoint."""

from fastapi import APIRouter

from domain import __version_platform__

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "service": "verdent-platform",
        "version": __version_platform__,
    }
