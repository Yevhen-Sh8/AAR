"""Wave 7 — Mission Prep Brief endpoint (AAR як вхід у планування)."""
from dataclasses import asdict

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from aar_api.core.db import get_session
from aar_api.services.mission_brief import compute_mission_brief

router = APIRouter(prefix="/briefing", tags=["briefing"])


class ProfileStatsOut(BaseModel):
    window_days: int
    launched: int
    success: int
    lost: int
    lost_during_abort: int
    repaired: int
    aborted: int
    msr: float
    top_loss_reasons: list[str]


class BriefItemOut(BaseModel):
    id: int
    title: str
    detail: str | None
    meta: str
    relevance: int


class MissionBriefOut(BaseModel):
    query: str
    item_type_code: str | None
    operator_code: str | None
    stats: ProfileStatsOut
    signals: list[BriefItemOut]
    validated_lessons: list[BriefItemOut]
    case_lessons: list[BriefItemOut]
    open_recommendations: list[BriefItemOut]


@router.get("/mission", response_model=MissionBriefOut)
async def mission_brief(
    q: str = Query(default="", max_length=255, description="Профіль завдання"),
    item_type_code: str | None = Query(default=None),
    operator_code: str | None = Query(default=None),
    window_days: int = Query(default=90, ge=7, le=365),
    session: AsyncSession = Depends(get_session),
) -> MissionBriefOut:
    brief = await compute_mission_brief(
        session,
        query=q,
        item_type_code=item_type_code,
        operator_code=operator_code,
        window_days=window_days,
    )
    return MissionBriefOut(**asdict(brief))
