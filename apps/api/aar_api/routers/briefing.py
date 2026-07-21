"""Wave 7 — Mission Prep Brief endpoint (AAR як вхід у планування)."""
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from aar_api.core.db import get_session
from aar_api.services import llm as llm_service
from aar_api.services.context_assets import persist_drafts
from aar_api.services.mission_brief import MissionBrief, compute_mission_brief

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


# -------------------- LLM synthesis over the brief -------------------------

class SynthRiskOut(BaseModel):
    risk: str
    evidence: str
    mitigation: str


class MissionSynthesisOut(BaseModel):
    headline: str
    key_risks: list[SynthRiskOut]
    precautions: list[str]
    confidence_note: str


def _synth_payload(brief: MissionBrief) -> dict[str, Any]:
    """Compact package for the LLM — titles + meta only, capped per section."""
    def items(xs: list, n: int = 6) -> list[dict[str, Any]]:
        return [{"title": i.title, "detail": i.detail, "meta": i.meta} for i in xs[:n]]

    return {
        "profile": {
            "query": brief.query,
            "item_type_code": brief.item_type_code,
            "operator_code": brief.operator_code,
        },
        "stats": asdict(brief.stats),
        "active_signals": items(brief.signals),
        "validated_lessons": items(brief.validated_lessons),
        "case_lessons": items(brief.case_lessons),
        "open_recommendations": items(brief.open_recommendations),
    }


@router.get("/mission/synthesis", response_model=MissionSynthesisOut)
async def mission_synthesis(
    q: str = Query(default="", max_length=255),
    item_type_code: str | None = Query(default=None),
    operator_code: str | None = Query(default=None),
    window_days: int = Query(default=90, ge=7, le=365),
    session: AsyncSession = Depends(get_session),
) -> MissionSynthesisOut:
    """LLM synthesis of the brief into a planner-facing pre-mission briefing.

    User-initiated (a button in the UI), so persisting any draft assets the
    model surfaces is on-pattern (ADR-008 — human validates later), matching
    the GET-triggers-LLM convention of /llm/cases/{id}/analogies. Returns 503
    when the LLM is disabled.
    """
    brief = await compute_mission_brief(
        session,
        query=q,
        item_type_code=item_type_code,
        operator_code=operator_code,
        window_days=window_days,
    )
    try:
        result = llm_service.synthesize_mission_brief(
            brief_payload=_synth_payload(brief)
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    if result.context_assets:
        await persist_drafts(
            session,
            result.context_assets,
            source=f"briefing:{q or 'profile'}",
            source_agent="mission_synthesis",
        )
        await session.commit()

    return MissionSynthesisOut(**result.task_output.model_dump())
