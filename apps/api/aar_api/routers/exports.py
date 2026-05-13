"""Order #440 form exports."""
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from aar_api.core.db import get_session
from aar_api.models.dictionaries import ItemType, LossReason, Operator, RepairReason
from aar_api.models.event import Item, Outcome, UsageEvent
from aar_api.services.mod440 import (
    InventoryRow,
    LossActData,
    MovementRow,
    RepairActData,
    inventory_summary_xlsx,
    loss_act_docx,
    movement_journal_xlsx,
    repair_act_docx,
)

router = APIRouter(prefix="/exports/mod440", tags=["exports"])

DOCX_MEDIA = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _attach(name: str, media: str) -> dict[str, str]:
    return {"Content-Disposition": f'attachment; filename="{name}"'}


async def _build_inventory(session: AsyncSession) -> list[InventoryRow]:
    type_rows = list(await session.scalars(select(ItemType).order_by(ItemType.code)))
    rows: list[InventoryRow] = []
    for t in type_rows:
        item_ids = list(
            await session.scalars(select(Item.id).where(Item.item_type_id == t.id))
        )
        if not item_ids:
            rows.append(
                InventoryRow(
                    item_type_code=t.code,
                    item_type_name=t.name_uk,
                    measure_unit="шт.",
                    on_hand=0,
                    received=len(item_ids),
                    consumed=0,
                    lost=0,
                    in_repair=0,
                )
            )
            continue
        outcome_counts: dict[Outcome, int] = {
            row[0]: row[1]
            for row in (
                await session.execute(
                    select(UsageEvent.outcome, func.count(UsageEvent.id))
                    .where(UsageEvent.item_id.in_(item_ids))
                    .group_by(UsageEvent.outcome)
                )
            ).all()
        }
        consumed = outcome_counts.get(Outcome.SUCCESS, 0)
        lost = outcome_counts.get(Outcome.LOST, 0)
        in_repair = outcome_counts.get(Outcome.REPAIR, 0)
        rows.append(
            InventoryRow(
                item_type_code=t.code,
                item_type_name=t.name_uk,
                measure_unit="шт.",
                on_hand=len(item_ids) - lost,
                received=len(item_ids),
                consumed=consumed,
                lost=lost,
                in_repair=in_repair,
            )
        )
    return rows


@router.get("/inventory.xlsx")
async def export_inventory(
    unit_name: str = Query(default="в/ч"),
    as_of: date | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> Response:
    rows = await _build_inventory(session)
    as_of_date = as_of or date.today()
    data = inventory_summary_xlsx(rows, unit_name=unit_name, as_of=as_of_date)
    return Response(
        content=data,
        media_type=XLSX_MEDIA,
        headers=_attach(f"inventory-{as_of_date.isoformat()}.xlsx", XLSX_MEDIA),
    )


async def _build_movement(
    session: AsyncSession, date_from: date, date_to: date
) -> list[MovementRow]:
    LR = aliased(LossReason)
    RR = aliased(RepairReason)
    stmt = (
        select(
            UsageEvent.event_date,
            Item.serial_no,
            ItemType.code.label("type_code"),
            Operator.code.label("operator_code"),
            UsageEvent.outcome,
            LR.code.label("loss_code"),
            RR.code.label("repair_code"),
            UsageEvent.id,
        )
        .join(Item, Item.id == UsageEvent.item_id)
        .join(ItemType, ItemType.id == Item.item_type_id)
        .join(Operator, Operator.id == UsageEvent.operator_id)
        .join(LR, LR.id == UsageEvent.loss_reason_id, isouter=True)
        .join(RR, RR.id == UsageEvent.repair_reason_id, isouter=True)
        .where(UsageEvent.event_date.between(date_from, date_to))
        .order_by(UsageEvent.event_date, UsageEvent.id)
    )
    rows: list[MovementRow] = []
    for r in await session.execute(stmt):
        rows.append(
            MovementRow(
                event_date=r.event_date,
                serial_no=r.serial_no,
                item_type_code=r.type_code,
                operator_code=r.operator_code,
                outcome=r.outcome.value if hasattr(r.outcome, "value") else str(r.outcome),
                reason_code=r.loss_code or r.repair_code,
                basis=f"подія #{r.id}",
            )
        )
    return rows


@router.get("/movement.xlsx")
async def export_movement(
    date_from: date = Query(),
    date_to: date = Query(),
    unit_name: str = Query(default="в/ч"),
    session: AsyncSession = Depends(get_session),
) -> Response:
    rows = await _build_movement(session, date_from, date_to)
    data = movement_journal_xlsx(
        rows, unit_name=unit_name, date_from=date_from, date_to=date_to
    )
    return Response(
        content=data,
        media_type=XLSX_MEDIA,
        headers=_attach(
            f"movement-{date_from.isoformat()}_{date_to.isoformat()}.xlsx", XLSX_MEDIA
        ),
    )


async def _resolve_event(session: AsyncSession, event_id: int) -> Any:
    LR = aliased(LossReason)
    RR = aliased(RepairReason)
    row = (
        await session.execute(
            select(
                UsageEvent,
                Item.serial_no,
                ItemType.code.label("type_code"),
                ItemType.name_uk.label("type_name"),
                Operator.code.label("operator_code"),
                LR.code.label("loss_code"),
                LR.name_uk.label("loss_name"),
                RR.code.label("repair_code"),
                RR.name_uk.label("repair_name"),
            )
            .join(Item, Item.id == UsageEvent.item_id)
            .join(ItemType, ItemType.id == Item.item_type_id)
            .join(Operator, Operator.id == UsageEvent.operator_id)
            .join(LR, LR.id == UsageEvent.loss_reason_id, isouter=True)
            .join(RR, RR.id == UsageEvent.repair_reason_id, isouter=True)
            .where(UsageEvent.id == event_id)
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(404, "event not found")
    return row


@router.get("/loss-act/{event_id}.docx")
async def export_loss_act(
    event_id: int,
    unit_name: str = Query(default="в/ч"),
    act_no: str = Query(default="auto"),
    responsible_person: str = Query(default="(вкажіть ПІБ)"),
    circumstances: str = Query(default="(вкажіть обставини)"),
    session: AsyncSession = Depends(get_session),
) -> Response:
    row = await _resolve_event(session, event_id)
    event = row[0]
    if event.outcome != Outcome.LOST:
        raise HTTPException(400, "event is not a loss")
    if row.loss_code is None:
        raise HTTPException(400, "loss reason is required")
    today = date.today()
    data = loss_act_docx(
        LossActData(
            act_no=act_no if act_no != "auto" else f"{event_id}/{today.year}",
            act_date=today,
            unit_name=unit_name,
            serial_no=row.serial_no,
            item_type_name=row.type_name,
            measure_unit="шт.",
            operator_code=row.operator_code,
            event_date=event.event_date,
            reason_code=row.loss_code,
            reason_name=row.loss_name or "",
            circumstances=circumstances,
            responsible_person=responsible_person,
        )
    )
    return Response(
        content=data,
        media_type=DOCX_MEDIA,
        headers=_attach(f"loss-act-{event_id}.docx", DOCX_MEDIA),
    )


@router.get("/repair-act/{event_id}.docx")
async def export_repair_act(
    event_id: int,
    unit_name: str = Query(default="в/ч"),
    act_no: str = Query(default="auto"),
    sender: str = Query(default="(здавальник)"),
    receiver: str = Query(default="(приймальник)"),
    defect_description: str = Query(default="(опис дефекту)"),
    session: AsyncSession = Depends(get_session),
) -> Response:
    row = await _resolve_event(session, event_id)
    event = row[0]
    if event.outcome != Outcome.REPAIR:
        raise HTTPException(400, "event is not a repair return")
    if row.repair_code is None:
        raise HTTPException(400, "repair reason is required")
    today = date.today()
    data = repair_act_docx(
        RepairActData(
            act_no=act_no if act_no != "auto" else f"R-{event_id}/{today.year}",
            act_date=today,
            unit_name=unit_name,
            serial_no=row.serial_no,
            item_type_name=row.type_name,
            operator_code=row.operator_code,
            event_date=event.event_date,
            reason_code=row.repair_code,
            reason_name=row.repair_name or "",
            defect_description=defect_description,
            sender=sender,
            receiver=receiver,
        )
    )
    return Response(
        content=data,
        media_type=DOCX_MEDIA,
        headers=_attach(f"repair-act-{event_id}.docx", DOCX_MEDIA),
    )
