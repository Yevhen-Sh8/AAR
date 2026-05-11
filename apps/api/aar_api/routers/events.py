from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aar_api.core.db import get_session
from aar_api.models.dictionaries import ItemType, LossReason, Operator, RepairReason
from aar_api.models.event import Item, Outcome, UsageEvent
from aar_api.schemas.event import UsageEventIn, UsageEventOut

router = APIRouter(prefix="/events", tags=["events"])


async def _resolve_code(session: AsyncSession, model: Any, code: str) -> int:
    row = await session.scalar(select(model).where(model.code == code))
    if row is None:
        raise HTTPException(status_code=404, detail=f"{model.__name__} code='{code}' not found")
    return int(row.id)


async def _get_or_create_item(
    session: AsyncSession, serial_no: str, item_type_id: int
) -> Item:
    item = await session.scalar(select(Item).where(Item.serial_no == serial_no))
    if item is None:
        item = Item(serial_no=serial_no, item_type_id=item_type_id)
        session.add(item)
        await session.flush()
    return item


@router.post("", response_model=UsageEventOut, status_code=201)
async def create_event(
    payload: UsageEventIn, session: AsyncSession = Depends(get_session)
) -> UsageEvent:
    if payload.client_event_id:
        existing = await session.scalar(
            select(UsageEvent).where(
                UsageEvent.client_event_id == payload.client_event_id
            )
        )
        if existing is not None:
            return existing

    item_type_id = await _resolve_code(session, ItemType, payload.item_type_code)
    operator_id = await _resolve_code(session, Operator, payload.operator_code)
    item = await _get_or_create_item(session, payload.item_serial_no, item_type_id)

    loss_id = (
        await _resolve_code(session, LossReason, payload.loss_reason_code)
        if payload.loss_reason_code
        else None
    )
    repair_id = (
        await _resolve_code(session, RepairReason, payload.repair_reason_code)
        if payload.repair_reason_code
        else None
    )

    event = UsageEvent(
        client_event_id=payload.client_event_id,
        item_id=item.id,
        operator_id=operator_id,
        event_date=payload.event_date,
        outcome=payload.outcome,
        loss_reason_id=loss_id,
        repair_reason_id=repair_id,
        notes=payload.notes,
    )
    session.add(event)
    await session.commit()
    await session.refresh(event)
    return event


@router.get("", response_model=list[UsageEventOut])
async def list_events(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    operator_code: str | None = Query(default=None),
    outcome: Outcome | None = Query(default=None),
    limit: int = Query(default=100, le=1000),
    session: AsyncSession = Depends(get_session),
) -> list[UsageEvent]:
    stmt = select(UsageEvent)
    if date_from:
        stmt = stmt.where(UsageEvent.event_date >= date_from)
    if date_to:
        stmt = stmt.where(UsageEvent.event_date <= date_to)
    if operator_code:
        op_id = await _resolve_code(session, Operator, operator_code)
        stmt = stmt.where(UsageEvent.operator_id == op_id)
    if outcome:
        stmt = stmt.where(UsageEvent.outcome == outcome)
    stmt = stmt.order_by(UsageEvent.event_date.desc(), UsageEvent.id.desc()).limit(limit)
    rows = await session.scalars(stmt)
    return list(rows)
