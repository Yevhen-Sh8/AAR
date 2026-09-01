"""Wave 2 — Learning-loop meta-KPI endpoint.

GET /learning/loop-kpi → headline numbers that prove the LL program is alive.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from aar_api.core.db import get_session
from aar_api.services.learning_metrics import compute_loop_kpi

router = APIRouter(prefix="/learning", tags=["learning"])


class LoopKPIOut(BaseModel):
    time_to_validation_days_median: float | None
    time_to_validation_days_p90: float | None
    cases_with_validation: int

    li_to_ll_conversion_pct: float
    cases_analysed_or_later: int
    cases_validated_or_closed: int

    recurrence_rate_pct: float
    regressed_recommendations: int
    validated_recommendations: int

    open_cases_by_opr: dict[str, int]

    decision_quality_counts: dict[str, int]
    endorsed_without_assessment: int
    caught_before_it_cost_anything: int

    msr_narrow: float
    msr_full: float
    launched_count: int
    aborted_count: int
    success_count: int

    cost_per_effect_usd_by_type: dict[str, float]

    period_from: datetime
    period_to: datetime


@router.get("/loop-kpi", response_model=LoopKPIOut)
async def loop_kpi(
    period_from: datetime | None = Query(default=None),
    period_to: datetime | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> LoopKPIOut:
    kpi = await compute_loop_kpi(session, period_from, period_to)
    return LoopKPIOut(**kpi.__dict__)
