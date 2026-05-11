from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from aar_api.core.db import get_session
from aar_api.schemas.reports import DailyReport
from aar_api.services.exports import daily_report_to_pdf, daily_report_to_xlsx
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
