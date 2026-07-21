"""Universal integration layer: outbound webhooks + inbound REST + GeoJSON.

Compatible target systems (per user policy, Оберіг is EXCLUDED):
  - ODIN (C2)
  - DELTA (situational awareness — GeoJSON FeatureCollection)
  - Kropyva (mapping — single GeoJSON Feature)
  - SAP (flat ERP record)
  - generic (any REST/JSON consumer)
"""
from datetime import date as date_cls
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aar_api.core.db import get_session
from aar_api.models.dictionaries import ItemType, LossReason, Operator, RepairReason
from aar_api.models.event import Item, Outcome, UsageEvent
from aar_api.models.integration import (
    ConnectorKind,
    Delivery,
    Subscription,
    WebhookEventKind,
)
from aar_api.schemas.integrations import (
    DeliveryOut,
    InboundEvent,
    SubscriptionIn,
    SubscriptionOut,
)
from aar_api.services.integrations import (
    canonical_usage_event,
    dispatch,
    render_payload,
)

router = APIRouter(prefix="/integrations", tags=["integrations"])


# -------------------- subscriptions ---------------------------------------

@router.post("/subscriptions", response_model=SubscriptionOut, status_code=201)
async def create_subscription(
    payload: SubscriptionIn, session: AsyncSession = Depends(get_session)
) -> Subscription:
    sub = Subscription(
        name=payload.name,
        kind=payload.kind,
        target_url=str(payload.target_url),
        secret=payload.secret,
        events=[e.value for e in payload.events],
        headers=payload.headers,
        active=payload.active,
    )
    session.add(sub)
    await session.commit()
    await session.refresh(sub)
    return sub


@router.get("/subscriptions", response_model=list[SubscriptionOut])
async def list_subscriptions(
    session: AsyncSession = Depends(get_session),
) -> list[Subscription]:
    rows = await session.scalars(select(Subscription).order_by(Subscription.id))
    return list(rows)


@router.delete("/subscriptions/{sub_id}", status_code=204)
async def delete_subscription(
    sub_id: int, session: AsyncSession = Depends(get_session)
) -> None:
    sub = await session.get(Subscription, sub_id)
    if sub is None:
        raise HTTPException(404, "subscription not found")
    await session.delete(sub)
    await session.commit()


@router.get("/deliveries", response_model=list[DeliveryOut])
async def list_deliveries(
    subscription_id: int | None = None,
    limit: int = Query(default=50, le=500),
    session: AsyncSession = Depends(get_session),
) -> list[Delivery]:
    stmt = select(Delivery).order_by(Delivery.dispatched_at.desc()).limit(limit)
    if subscription_id is not None:
        stmt = stmt.where(Delivery.subscription_id == subscription_id)
    rows = await session.scalars(stmt)
    return list(rows)


# -------------------- preview / connectors --------------------------------

@router.get("/connectors")
async def list_connectors() -> dict[str, Any]:
    return {
        "kinds": [k.value for k in ConnectorKind],
        "events": [e.value for e in WebhookEventKind],
        "excluded": ["oberig"],
        "notes": {
            "delta": "Wraps the usage event into GeoJSON FeatureCollection",
            "kropyva": "Single GeoJSON Feature for direct map import",
            "odin": "C2-style envelope with timestamp/actor/subject/geo",
            "sap": "Flat one-level record with PascalCase field names",
            "generic": "Pass-through {event, data} envelope",
            "telegram": (
                "Повідомлення в Telegram через Bot API. "
                "target_url = chat_id (напр. -1001234567890 або @channel), "
                "secret = токен бота."
            ),
        },
    }


@router.post("/preview")
async def preview_payload(
    kind: ConnectorKind,
    event_id: int,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Render what would be sent to a given connector — useful for partners."""
    event = await session.get(UsageEvent, event_id)
    if event is None:
        raise HTTPException(404, "event not found")
    canonical = canonical_usage_event(event)
    return render_payload(kind, WebhookEventKind.USAGE_EVENT_CREATED, canonical)


# -------------------- dispatch (manual) -----------------------------------

@router.post("/dispatch/{event_id}", response_model=list[DeliveryOut])
async def dispatch_event(
    event_id: int, session: AsyncSession = Depends(get_session)
) -> list[Delivery]:
    event = await session.get(UsageEvent, event_id)
    if event is None:
        raise HTTPException(404, "event not found")
    canonical = canonical_usage_event(event)
    deliveries = await dispatch(
        session, WebhookEventKind.USAGE_EVENT_CREATED, canonical
    )
    await session.commit()
    return deliveries


# -------------------- inbound (universal) ---------------------------------

@router.post("/inbound/events", response_model=dict)
async def inbound_event(
    payload: InboundEvent, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    """Universal entry-point: any external system sends a normalised event here.

    Idempotent on (source, external_id) → stored as `client_event_id`.
    """
    client_event_id = (
        f"{payload.source}:{payload.external_id}" if payload.external_id else None
    )
    if client_event_id:
        existing = await session.scalar(
            select(UsageEvent).where(UsageEvent.client_event_id == client_event_id)
        )
        if existing is not None:
            return {
                "id": existing.id,
                "source": payload.source,
                "duplicate": True,
            }

    item_type = await session.scalar(
        select(ItemType).where(ItemType.code == payload.item_type_code)
    )
    if item_type is None:
        raise HTTPException(404, f"item_type '{payload.item_type_code}' unknown")
    operator = await session.scalar(
        select(Operator).where(Operator.code == payload.operator_code)
    )
    if operator is None:
        raise HTTPException(404, f"operator '{payload.operator_code}' unknown")

    item = await session.scalar(
        select(Item).where(Item.serial_no == payload.item_serial_no)
    )
    if item is None:
        item = Item(serial_no=payload.item_serial_no, item_type_id=item_type.id)
        session.add(item)
        await session.flush()

    loss_id: int | None = None
    repair_id: int | None = None
    if payload.outcome == "lost":
        lr = await session.scalar(
            select(LossReason).where(LossReason.code == payload.loss_reason_code)
        )
        if lr is None:
            raise HTTPException(404, "loss_reason_code required for outcome=lost")
        loss_id = lr.id
    elif payload.outcome == "repair":
        rr = await session.scalar(
            select(RepairReason).where(RepairReason.code == payload.repair_reason_code)
        )
        if rr is None:
            raise HTTPException(404, "repair_reason_code required for outcome=repair")
        repair_id = rr.id

    event_date = datetime.fromisoformat(payload.event_date).date() \
        if "T" in payload.event_date else date_cls.fromisoformat(payload.event_date)

    event = UsageEvent(
        client_event_id=(
            f"{payload.source}:{payload.external_id}" if payload.external_id else None
        ),
        item_id=item.id,
        operator_id=operator.id,
        event_date=event_date,
        outcome=Outcome(payload.outcome),
        loss_reason_id=loss_id,
        repair_reason_id=repair_id,
        notes=payload.notes,
        location=payload.location.model_dump() if payload.location else None,
    )
    session.add(event)
    await session.commit()
    await session.refresh(event)
    return {"id": event.id, "source": payload.source}


# -------------------- GeoJSON export --------------------------------------

@router.get("/events.geojson")
async def events_geojson(
    date_from: date_cls = Query(),
    date_to: date_cls = Query(),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Export events with location as a GeoJSON FeatureCollection."""
    rows = list(
        await session.scalars(
            select(UsageEvent).where(
                UsageEvent.event_date.between(date_from, date_to),
                UsageEvent.location.is_not(None),
            )
        )
    )
    features: list[dict[str, Any]] = []
    for e in rows:
        if not e.location:
            continue
        features.append(
            {
                "type": "Feature",
                "geometry": e.location,
                "properties": {
                    "id": e.id,
                    "operator_id": e.operator_id,
                    "item_id": e.item_id,
                    "event_date": e.event_date.isoformat(),
                    "outcome": e.outcome.value
                    if hasattr(e.outcome, "value")
                    else str(e.outcome),
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}
