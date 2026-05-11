from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aar_api.core.db import get_session
from aar_api.models.aar import (
    AARCase,
    CaseStatus,
    IndividualReport,
    Recommendation,
    RecommendationStatus,
    TriggerType,
)
from aar_api.models.dictionaries import Operator
from aar_api.schemas.aar import (
    AARCaseIn,
    AARCaseOut,
    IndividualReportIn,
    IndividualReportOut,
    RecommendationIn,
    RecommendationOut,
    RecommendationStatusUpdate,
    TriggerResult,
)
from aar_api.services.triggers import TriggerConfig, evaluate_triggers

router = APIRouter(prefix="/aar", tags=["aar"])


async def _get_case(session: AsyncSession, case_id: int) -> AARCase:
    case = await session.get(AARCase, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="case not found")
    return case


@router.post("/cases", response_model=AARCaseOut, status_code=201)
async def create_case(
    payload: AARCaseIn, session: AsyncSession = Depends(get_session)
) -> AARCase:
    op_id: int | None = None
    if payload.operator_code:
        op = await session.scalar(select(Operator).where(Operator.code == payload.operator_code))
        if op is None:
            raise HTTPException(404, f"operator '{payload.operator_code}' not found")
        op_id = op.id
    case = AARCase(
        title=payload.title,
        operator_id=op_id,
        summary=payload.summary,
        trigger=TriggerType.MANUAL,
    )
    session.add(case)
    await session.commit()
    await session.refresh(case)
    return case


@router.get("/cases", response_model=list[AARCaseOut])
async def list_cases(
    status: CaseStatus | None = Query(default=None),
    trigger: TriggerType | None = Query(default=None),
    limit: int = Query(default=100, le=1000),
    session: AsyncSession = Depends(get_session),
) -> list[AARCase]:
    stmt = select(AARCase).order_by(AARCase.opened_at.desc()).limit(limit)
    if status:
        stmt = stmt.where(AARCase.status == status)
    if trigger:
        stmt = stmt.where(AARCase.trigger == trigger)
    return list(await session.scalars(stmt))


@router.get("/cases/{case_id}", response_model=AARCaseOut)
async def get_case(case_id: int, session: AsyncSession = Depends(get_session)) -> AARCase:
    return await _get_case(session, case_id)


@router.post("/cases/{case_id}/close", response_model=AARCaseOut)
async def close_case(case_id: int, session: AsyncSession = Depends(get_session)) -> AARCase:
    case = await _get_case(session, case_id)
    case.status = CaseStatus.CLOSED
    case.closed_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(case)
    return case


@router.post(
    "/cases/{case_id}/reports", response_model=IndividualReportOut, status_code=201
)
async def add_report(
    case_id: int,
    payload: IndividualReportIn,
    session: AsyncSession = Depends(get_session),
) -> IndividualReport:
    await _get_case(session, case_id)
    report = IndividualReport(case_id=case_id, **payload.model_dump())
    session.add(report)
    await session.commit()
    await session.refresh(report)
    return report


@router.get("/cases/{case_id}/reports", response_model=list[IndividualReportOut])
async def list_reports(
    case_id: int, session: AsyncSession = Depends(get_session)
) -> list[IndividualReport]:
    await _get_case(session, case_id)
    rows = await session.scalars(
        select(IndividualReport).where(IndividualReport.case_id == case_id)
    )
    return list(rows)


@router.post(
    "/cases/{case_id}/recommendations",
    response_model=RecommendationOut,
    status_code=201,
)
async def add_recommendation(
    case_id: int,
    payload: RecommendationIn,
    session: AsyncSession = Depends(get_session),
) -> Recommendation:
    await _get_case(session, case_id)
    rec = Recommendation(case_id=case_id, text=payload.text)
    session.add(rec)
    await session.commit()
    await session.refresh(rec)
    return rec


@router.patch(
    "/recommendations/{rec_id}",
    response_model=RecommendationOut,
)
async def update_recommendation_status(
    rec_id: int,
    payload: RecommendationStatusUpdate,
    session: AsyncSession = Depends(get_session),
) -> Recommendation:
    rec = await session.get(Recommendation, rec_id)
    if rec is None:
        raise HTTPException(404, "recommendation not found")
    rec.status = payload.status
    if payload.status == RecommendationStatus.VALIDATED:
        rec.validated_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(rec)
    return rec


@router.post("/run-triggers", response_model=TriggerResult)
async def run_triggers(
    today: date = Query(default_factory=lambda: datetime.now(UTC).date()),
    session: AsyncSession = Depends(get_session),
) -> TriggerResult:
    created, skipped = await evaluate_triggers(session, today, TriggerConfig())
    await session.commit()
    return TriggerResult(
        created_case_ids=[c.id for c in created], skipped_existing=skipped
    )
