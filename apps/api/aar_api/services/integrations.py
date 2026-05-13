"""Universal outbound integration layer.

Architecture:
- One generic webhook contract (REST/JSON + optional HMAC-SHA256 signature).
- `ConnectorKind` selects a per-target *shape adapter* that transforms the
  canonical event payload to whatever DELTA/Кропива/ODIN/SAP expects. This
  keeps the core engine independent of any specific target.
- Geospatial data is carried as GeoJSON Point (RFC 7946), so the same
  payload is consumable by mapping clients without translation.

Excluded by policy: «Оберіг» (classified system — no integration).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aar_api.models.aar import AARCase
from aar_api.models.event import UsageEvent
from aar_api.models.integration import (
    ConnectorKind,
    Delivery,
    DeliveryStatus,
    Subscription,
    WebhookEventKind,
)

logger = logging.getLogger(__name__)


def canonical_usage_event(event: UsageEvent) -> dict[str, Any]:
    """Stable normalised shape used by all adapters."""
    return {
        "id": event.id,
        "client_event_id": event.client_event_id,
        "item_id": event.item_id,
        "operator_id": event.operator_id,
        "event_date": event.event_date.isoformat(),
        "outcome": event.outcome.value
        if hasattr(event.outcome, "value")
        else str(event.outcome),
        "loss_reason_id": event.loss_reason_id,
        "repair_reason_id": event.repair_reason_id,
        "notes": event.notes,
        "location": event.location,
        "recorded_at": event.recorded_at.isoformat() if event.recorded_at else None,
    }


def canonical_aar_case(case: AARCase) -> dict[str, Any]:
    return {
        "id": case.id,
        "title": case.title,
        "trigger": case.trigger.value if hasattr(case.trigger, "value") else str(case.trigger),
        "status": case.status.value if hasattr(case.status, "value") else str(case.status),
        "operator_id": case.operator_id,
        "summary": case.summary,
        "opened_at": case.opened_at.isoformat() if case.opened_at else None,
        "closed_at": case.closed_at.isoformat() if case.closed_at else None,
    }


# -------------------------- adapters --------------------------------------

def _adapt_generic(payload: dict[str, Any], event_kind: WebhookEventKind) -> dict[str, Any]:
    return {"event": event_kind.value, "data": payload}


def _to_geojson_feature(event_payload: dict[str, Any]) -> dict[str, Any] | None:
    """Wrap a usage event with location into a GeoJSON Feature for DELTA/Кропива."""
    loc = event_payload.get("location")
    if not loc or loc.get("type") != "Point":
        return None
    props = {k: v for k, v in event_payload.items() if k != "location"}
    return {"type": "Feature", "geometry": loc, "properties": props}


def _adapt_delta(payload: dict[str, Any], event_kind: WebhookEventKind) -> dict[str, Any]:
    """DELTA situational-awareness: prefers GeoJSON FeatureCollection."""
    feature = _to_geojson_feature(payload)
    if feature is None:
        return {"event": event_kind.value, "data": payload}
    return {
        "event": event_kind.value,
        "geojson": {"type": "FeatureCollection", "features": [feature]},
        "data": payload,
    }


def _adapt_kropyva(payload: dict[str, Any], event_kind: WebhookEventKind) -> dict[str, Any]:
    """Kropyva map import: single GeoJSON Feature is sufficient."""
    feature = _to_geojson_feature(payload)
    return {
        "event": event_kind.value,
        "feature": feature,
        "data": payload,
    }


def _adapt_odin(payload: dict[str, Any], event_kind: WebhookEventKind) -> dict[str, Any]:
    """ODIN: military C2-style envelope with timestamp + actor."""
    return {
        "event_type": event_kind.value,
        "timestamp": payload.get("recorded_at"),
        "actor": {"operator_id": payload.get("operator_id")},
        "subject": {
            "item_id": payload.get("item_id"),
            "serial_no": payload.get("client_event_id"),
        },
        "outcome": payload.get("outcome"),
        "geo": payload.get("location"),
        "raw": payload,
    }


def _adapt_sap(payload: dict[str, Any], event_kind: WebhookEventKind) -> dict[str, Any]:
    """SAP-friendly flat record (one level deep)."""
    flat = {
        "EventType": event_kind.value,
        "ItemID": payload.get("item_id"),
        "OperatorID": payload.get("operator_id"),
        "EventDate": payload.get("event_date"),
        "Outcome": payload.get("outcome"),
        "LossReasonID": payload.get("loss_reason_id"),
        "RepairReasonID": payload.get("repair_reason_id"),
        "Notes": payload.get("notes"),
        "RecordedAt": payload.get("recorded_at"),
    }
    return flat


_ADAPTERS = {
    ConnectorKind.GENERIC: _adapt_generic,
    ConnectorKind.ODIN: _adapt_odin,
    ConnectorKind.DELTA: _adapt_delta,
    ConnectorKind.KROPYVA: _adapt_kropyva,
    ConnectorKind.SAP: _adapt_sap,
}


def render_payload(
    kind: ConnectorKind, event_kind: WebhookEventKind, canonical: dict[str, Any]
) -> dict[str, Any]:
    adapter = _ADAPTERS[kind]
    return adapter(canonical, event_kind)


def sign(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


# -------------------------- dispatcher -------------------------------------

async def _post(
    sub: Subscription, body: bytes, *, client: httpx.AsyncClient
) -> tuple[int | None, str | None]:
    headers = {"Content-Type": "application/json"}
    if sub.headers:
        headers.update(sub.headers)
    if sub.secret:
        headers["X-AAR-Signature"] = sign(sub.secret, body)
    try:
        resp = await client.post(sub.target_url, content=body, headers=headers, timeout=10.0)
        return resp.status_code, None if resp.is_success else resp.text[:500]
    except httpx.HTTPError as e:
        return None, str(e)


async def dispatch(
    session: AsyncSession,
    event_kind: WebhookEventKind,
    canonical: dict[str, Any],
    *,
    http_client: httpx.AsyncClient | None = None,
) -> list[Delivery]:
    """Fan-out to every active subscription registered for this event kind."""
    subs = list(
        await session.scalars(
            select(Subscription).where(Subscription.active.is_(True))
        )
    )
    deliveries: list[Delivery] = []
    owns_client = http_client is None
    client = http_client or httpx.AsyncClient()
    try:
        for sub in subs:
            if event_kind.value not in (sub.events or []):
                continue
            payload = render_payload(sub.kind, event_kind, canonical)
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            status, error = await _post(sub, body, client=client)
            delivery = Delivery(
                subscription_id=sub.id,
                event_kind=event_kind,
                payload=payload,
                response_code=status,
                attempts=1,
                error=error,
                status=DeliveryStatus.DELIVERED
                if status is not None and 200 <= status < 300
                else DeliveryStatus.FAILED,
            )
            session.add(delivery)
            deliveries.append(delivery)
            logger.info(
                "integration.dispatch sub=%s kind=%s status=%s",
                sub.id, event_kind.value, status,
            )
    finally:
        if owns_client:
            await client.aclose()
    await session.flush()
    return deliveries
