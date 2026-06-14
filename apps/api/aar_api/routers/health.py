from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from aar_api import __version__
from aar_api.core.db import get_session

router = APIRouter(tags=["health"])


@router.get("/")
async def root() -> dict[str, object]:
    """Friendly landing for the bare API domain (otherwise a bare 404).

    The browsable docs and health probes live at the paths below.
    """
    return {
        "service": "AAR API",
        "version": __version__,
        "status": "ok",
        "docs": "/docs",
        "health": {"live": "/health/live", "ready": "/health/ready"},
    }


@router.get("/health/live")
async def live() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@router.get("/health/ready")
async def ready(session: AsyncSession = Depends(get_session)) -> dict[str, str]:
    await session.execute(text("SELECT 1"))
    return {"status": "ready"}
