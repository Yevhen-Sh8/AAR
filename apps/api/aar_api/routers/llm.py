from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aar_api.core.config import get_settings
from aar_api.core.db import get_session
from aar_api.models.aar import AARCase, IndividualReport
from aar_api.models.audit import AuditAction
from aar_api.models.dictionaries import LossReason, Operator, RepairReason
from aar_api.models.event import UsageEvent
from aar_api.schemas.llm import (
    AnalogyMatchOut,
    AnalogyResponse,
    ClassifyRequest,
    ClassifyResponse,
    DraftAnalysisResponse,
)
from aar_api.services import llm as llm_service
from aar_api.services.audit import append as audit_append
from aar_api.services.context_assets import (
    persist_drafts,
    record_usage,
    validated_assets,
)

router = APIRouter(prefix="/llm", tags=["llm"])


async def _persist_assets_if_any(
    session: AsyncSession,
    result: llm_service.LLMResult,
    *,
    source: str,
    source_agent: str,
) -> None:
    if not result.context_assets:
        return
    await persist_drafts(
        session, result.context_assets, source=source, source_agent=source_agent
    )
    await session.commit()


@router.post("/classify-reason", response_model=ClassifyResponse)
async def classify_reason(
    payload: ClassifyRequest,
    session: AsyncSession = Depends(get_session),
) -> ClassifyResponse:
    model: Any = LossReason if payload.kind == "loss" else RepairReason
    rows = list(await session.scalars(select(model).order_by(model.code)))
    catalog = [
        llm_service.ReasonCatalogEntry(code=r.code, name_uk=r.name_uk, zone=r.zone.value)
        for r in rows
    ]
    try:
        result = llm_service.classify_reason(
            payload.text, catalog, kind=payload.kind, use_fast_model=payload.use_fast_model
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    await _persist_assets_if_any(
        session, result, source=f"classify:{payload.kind}", source_agent="classify_reason"
    )
    return ClassifyResponse(**result.task_output.model_dump())


@router.post("/cases/{case_id}/draft-analysis", response_model=DraftAnalysisResponse)
async def draft_case_analysis(
    case_id: int, session: AsyncSession = Depends(get_session)
) -> DraftAnalysisResponse:
    case = await session.get(AARCase, case_id)
    if case is None:
        raise HTTPException(404, "case not found")

    op_code: str | None = None
    if case.operator_id is not None:
        op = await session.get(Operator, case.operator_id)
        op_code = op.code if op else None

    if op_code:
        ev_rows = await session.scalars(
            select(UsageEvent).where(UsageEvent.operator_id == case.operator_id).limit(50)
        )
        events = list(ev_rows)
        ev_summary = (
            f"Усього подій (до 50): {len(events)}. "
            f"Успіх: {sum(1 for e in events if e.outcome == 'success')}, "
            f"Втрати: {sum(1 for e in events if e.outcome == 'lost')}, "
            f"Ремонт: {sum(1 for e in events if e.outcome == 'repair')}."
        )
    else:
        ev_summary = "Контекстні події не привʼязані до кейсу."

    rep_rows = await session.scalars(
        select(IndividualReport).where(IndividualReport.case_id == case_id)
    )
    reports = [
        {
            "what_happened": r.what_happened,
            "what_worked": r.what_worked,
            "what_failed": r.what_failed,
            "why": r.why,
            "external_factors": r.external_factors,
            "what_to_change": r.what_to_change,
        }
        for r in rep_rows
    ]

    try:
        result = llm_service.draft_case_analysis(
            case_title=case.title,
            trigger=case.trigger.value,
            operator_code=op_code,
            events_summary=ev_summary,
            individual_reports=reports,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    # Persist the draft into the case so it survives close (Wave 1 gap #2).
    # Don't overwrite a human-edited analysis — only fill if empty.
    if not case.analysis:
        case.analysis = result.task_output
        case.analysis_source = f"llm:{get_settings().llm_default_model}"
        case.analysis_drafted_at = datetime.now(UTC)
        await audit_append(
            session,
            action=AuditAction.CASE_ANALYSIS_DRAFTED,
            entity_type="aar_case",
            entity_id=case.id,
            payload={"source": case.analysis_source, "via": "llm"},
        )

    await _persist_assets_if_any(
        session, result, source=f"case:{case_id}", source_agent="draft_case_analysis"
    )
    await session.commit()
    await session.refresh(case)
    return DraftAnalysisResponse(markdown=result.task_output)


@router.get("/cases/{case_id}/analogies", response_model=AnalogyResponse)
async def find_case_analogies(
    case_id: int,
    top_k: int = 3,
    session: AsyncSession = Depends(get_session),
) -> AnalogyResponse:
    """Search analogies only among VALIDATED context assets (ADR-009)."""
    case = await session.get(AARCase, case_id)
    if case is None:
        raise HTTPException(404, "case not found")

    assets = await validated_assets(session, limit=50)
    if not assets:
        return AnalogyResponse(matches=[])

    knowledge: list[dict[str, str | int]] = [
        {"id": a.id, "title": a.title, "content": a.description[:500]} for a in assets
    ]
    query = f"{case.title}\n{case.summary or ''}"
    try:
        result = llm_service.find_analogies(
            query=query, knowledge_entries=knowledge, top_k=top_k
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    by_id = {a.id: a for a in assets}
    for m in result.task_output.matches:
        asset = by_id.get(m.knowledge_id)
        if asset is not None:
            await record_usage(
                session, asset, used_in=f"case:{case_id}", used_by_agent="find_analogies"
            )

    await _persist_assets_if_any(
        session, result, source=f"case:{case_id}", source_agent="find_analogies"
    )
    if not result.context_assets:
        await session.commit()

    return AnalogyResponse(
        matches=[AnalogyMatchOut(**m.model_dump()) for m in result.task_output.matches]
    )
