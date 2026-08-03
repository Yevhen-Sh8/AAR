from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aar_api.core.db import get_session
from aar_api.models.audit import AuditAction
from aar_api.models.dictionaries import ItemType, LossReason, Operator, RepairReason
from aar_api.models.event import Item, Outcome, UsageEvent
from aar_api.schemas.event import UsageEventIn, UsageEventOut
from aar_api.services.audit import append as audit_append
from aar_api.services.imports import parse_bytes

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
        # Accepted by the schema and then silently dropped here, so `aborted`
        # was False for EVERY event ever created through the API or import.
        # That killed the whole MSR-narrow / MSR-full distinction (Wave 2):
        # abort counters read zero everywhere and MSR-full equalled MSR-narrow
        # by construction — a metric that cannot differ from the one beside it
        # is not a second opinion, it is decoration.
        aborted=payload.aborted,
        abort_reason=payload.abort_reason,
    )
    session.add(event)
    await session.flush()
    await audit_append(
        session,
        action=AuditAction.EVENT_CREATED,
        entity_type="usage_event",
        entity_id=event.id,
        payload={
            "outcome": payload.outcome.value,
            "operator_code": payload.operator_code,
            "item_serial_no": payload.item_serial_no,
        },
    )
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


@router.get("/geojson")
async def events_geojson(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    operator_code: str | None = Query(default=None),
    item_type_code: str | None = Query(default=None),
    outcome: Outcome | None = Query(default=None),
    limit: int = Query(default=2000, le=5000),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Geolocated events as a GeoJSON FeatureCollection for the map UI.

    Only events with a non-null Point location are returned; properties carry
    human codes (serial / operator / item type) for tooltips, plus outcome for
    colour-coding.
    """
    stmt = (
        select(
            UsageEvent.id,
            UsageEvent.event_date,
            UsageEvent.outcome,
            UsageEvent.location,
            Item.serial_no,
            ItemType.code.label("item_type_code"),
            Operator.code.label("operator_code"),
        )
        .join(Item, Item.id == UsageEvent.item_id)
        .join(ItemType, ItemType.id == Item.item_type_id)
        .join(Operator, Operator.id == UsageEvent.operator_id)
        .where(UsageEvent.location.is_not(None))
    )
    if date_from:
        stmt = stmt.where(UsageEvent.event_date >= date_from)
    if date_to:
        stmt = stmt.where(UsageEvent.event_date <= date_to)
    if operator_code:
        stmt = stmt.where(Operator.code == operator_code)
    if item_type_code:
        stmt = stmt.where(ItemType.code == item_type_code)
    if outcome:
        stmt = stmt.where(UsageEvent.outcome == outcome)
    stmt = stmt.order_by(UsageEvent.event_date.desc(), UsageEvent.id.desc()).limit(limit)

    features: list[dict[str, Any]] = []
    for row in await session.execute(stmt):
        loc = row.location
        if not loc or loc.get("type") != "Point":
            continue
        oc = row.outcome.value if hasattr(row.outcome, "value") else str(row.outcome)
        features.append({
            "type": "Feature",
            "geometry": loc,
            "properties": {
                "id": row.id,
                "serial_no": row.serial_no,
                "operator_code": row.operator_code,
                "item_type_code": row.item_type_code,
                "outcome": oc,
                "event_date": row.event_date.isoformat(),
            },
        })
    return {"type": "FeatureCollection", "features": features, "count": len(features)}


class ImportRowError(BaseModel):
    row: int
    message: str


class ImportSummary(BaseModel):
    total_rows: int
    parsed: int
    imported: int
    duplicates: int
    failed: int
    parse_errors: list[ImportRowError]
    persist_errors: list[ImportRowError]
    dry_run: bool


async def _persist_event(
    session: AsyncSession, payload: UsageEventIn
) -> tuple[int, bool]:
    """Returns (event_id, is_duplicate). Raises on dictionary mismatch."""
    if payload.client_event_id:
        existing = await session.scalar(
            select(UsageEvent).where(UsageEvent.client_event_id == payload.client_event_id)
        )
        if existing is not None:
            return existing.id, True

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
        # Accepted by the schema and then silently dropped here, so `aborted`
        # was False for EVERY event ever created through the API or import.
        # That killed the whole MSR-narrow / MSR-full distinction (Wave 2):
        # abort counters read zero everywhere and MSR-full equalled MSR-narrow
        # by construction — a metric that cannot differ from the one beside it
        # is not a second opinion, it is decoration.
        aborted=payload.aborted,
        abort_reason=payload.abort_reason,
    )
    session.add(event)
    await session.flush()
    return event.id, False


@router.post("/import", response_model=ImportSummary)
async def import_events(
    file: UploadFile = File(...),
    dry_run: bool = Query(default=False),
    session: AsyncSession = Depends(get_session),
) -> ImportSummary:
    """Bulk-import events from a CSV or XLSX file.

    `dry_run=true` validates and reports without persisting.
    """
    data = await file.read()
    if not file.filename:
        raise HTTPException(400, "filename required")
    preview = parse_bytes(file.filename, data)

    parse_errors = [
        ImportRowError(row=e.row, message=e.message) for e in preview.errors
    ]
    persist_errors: list[ImportRowError] = []
    imported = 0
    duplicates = 0

    if not dry_run:
        for i, ev in enumerate(preview.parsed, start=2):
            try:
                _, is_dup = await _persist_event(session, ev)
                if is_dup:
                    duplicates += 1
                else:
                    imported += 1
            except HTTPException as e:
                persist_errors.append(ImportRowError(row=i, message=str(e.detail)))
        if imported > 0:
            await audit_append(
                session,
                action=AuditAction.EVENT_INBOUND,
                entity_type="usage_event_batch",
                entity_id=0,
                payload={
                    "source": file.filename,
                    "imported": imported,
                    "duplicates": duplicates,
                    "failed": len(parse_errors) + len(persist_errors),
                },
            )
        await session.commit()

    return ImportSummary(
        total_rows=preview.total_rows,
        parsed=len(preview.parsed),
        imported=imported,
        duplicates=duplicates,
        failed=len(parse_errors) + len(persist_errors),
        parse_errors=parse_errors,
        persist_errors=persist_errors,
        dry_run=dry_run,
    )
