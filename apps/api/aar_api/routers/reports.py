from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from aar_api.core.db import get_session
from aar_api.schemas.monthly import MonthlyReport
from aar_api.schemas.reports import DailyReport
from aar_api.services.exports import (
    daily_report_to_pdf,
    daily_report_to_xlsx,
    monthly_report_to_pdf,
    monthly_report_to_xlsx,
)
from aar_api.services.monthly import build_monthly_report
from aar_api.services.reports import build_daily_report

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/daily", response_model=DailyReport)
async def daily(
    report_date: date = Query(alias="date"),
    session: AsyncSession = Depends(get_session),
) -> DailyReport:
    return await build_daily_report(session, report_date)


@router.get("/daily.xlsx")
async def daily_xlsx(
    report_date: date = Query(alias="date"),
    session: AsyncSession = Depends(get_session),
) -> Response:
    report = await build_daily_report(session, report_date)
    data = daily_report_to_xlsx(report)
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="daily-{report_date.isoformat()}.xlsx"'
        },
    )


@router.get("/daily.pdf")
async def daily_pdf(
    report_date: date = Query(alias="date"),
    session: AsyncSession = Depends(get_session),
) -> Response:
    report = await build_daily_report(session, report_date)
    data = daily_report_to_pdf(report)
    return Response(
        content=data,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="daily-{report_date.isoformat()}.pdf"'
        },
    )


@router.get("/monthly", response_model=MonthlyReport)
async def monthly(
    year: int = Query(ge=2000, le=2100),
    month: int = Query(ge=1, le=12),
    session: AsyncSession = Depends(get_session),
) -> MonthlyReport:
    return await build_monthly_report(session, year, month)


@router.get("/monthly.xlsx")
async def monthly_xlsx(
    year: int = Query(ge=2000, le=2100),
    month: int = Query(ge=1, le=12),
    session: AsyncSession = Depends(get_session),
) -> Response:
    report = await build_monthly_report(session, year, month)
    data = monthly_report_to_xlsx(report)
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="monthly-{year}-{month:02d}.xlsx"'},
    )


@router.get("/monthly.pdf")
async def monthly_pdf(
    year: int = Query(ge=2000, le=2100),
    month: int = Query(ge=1, le=12),
    session: AsyncSession = Depends(get_session),
) -> Response:
    report = await build_monthly_report(session, year, month)
    data = monthly_report_to_pdf(report)
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="monthly-{year}-{month:02d}.pdf"'},
    )
