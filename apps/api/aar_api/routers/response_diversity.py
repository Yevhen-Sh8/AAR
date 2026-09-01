"""GET /learning/response-diversity — where the remedial answer never changes."""
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from aar_api.core.db import get_session
from aar_api.services.response_diversity import compute_response_patterns

router = APIRouter(prefix="/learning", tags=["learning"])


class ResponsePatternOut(BaseModel):
    operator_code: str | None
    trigger: str
    cases: int
    recommendations: int
    distinct_responses: int
    dominant_text: str
    dominant_count: int
    dominant_share: float


@router.get("/response-diversity", response_model=list[ResponsePatternOut])
async def response_diversity(
    period_from: datetime | None = Query(default=None),
    period_to: datetime | None = Query(default=None),
    min_cases: int = Query(default=3, ge=2, le=50),
    session: AsyncSession = Depends(get_session),
) -> list[ResponsePatternOut]:
    """Report (operator, trigger) pairs answered with one and the same action.

    Reports the repetition only. Whether that repetition has made the unit
    readable to an adversary is a judgement about the operational picture,
    which the reader has and this service does not.
    """
    patterns = await compute_response_patterns(
        session, period_from, period_to, min_cases=min_cases
    )
    return [ResponsePatternOut(**p.__dict__) for p in patterns]
